import json
import os
from threading import RLock
import time
from socket import gethostname

from .cert import generate_cert
from .joycon2_bridge import JoyCon2Bridge, input_step, RIGHT_BUTTON_NAMES, map_button
from ..nxbt import Nxbt, PRO_CONTROLLER
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import eventlet


app = Flask(__name__,
            static_url_path='',
            static_folder='static',)
nxbt = None
joycon2 = JoyCon2Bridge()
JOYCON2_INDEX = -1
joycon2_owner = None


def pro_backend():
    global nxbt
    if nxbt is None:
        nxbt = Nxbt()
    return nxbt


def owns(index):
    return USER_INFO.get(request.sid, {}).get("controller_index") == index

# Configuring/retrieving secret key
secrets_path = os.path.join(
    os.path.dirname(__file__), "secrets.txt"
)
if not os.path.isfile(secrets_path):
    secret_key = os.urandom(24).hex()
    with open(secrets_path, "w") as f:
        f.write(secret_key)
else:
    secret_key = None
    with open(secrets_path, "r") as f:
        secret_key = f.read()
app.config['SECRET_KEY'] = secret_key

# Starting socket server with Flask app
sio = SocketIO(app, cookie=False)

user_info_lock = RLock()
USER_INFO = {}


@app.route('/')
def index():
    return render_template('index.html')


@sio.on('connect')
def on_connect():
    with user_info_lock:
        USER_INFO[request.sid] = {}


@sio.on('state')
def on_state():
    state_proxy = nxbt.state.copy() if nxbt else {}
    state = {}
    for controller in state_proxy.keys():
        state[controller] = state_proxy[controller].copy()
    if joycon2_owner is not None:
        try:
            state[JOYCON2_INDEX] = joycon2.status()
        except (OSError, ValueError):
            state[JOYCON2_INDEX] = {"state": "crashed", "errors": ["Joy-Con 2 backend unavailable"]}
    emit('state', state)


@sio.on('disconnect')
def on_disconnect():
    with user_info_lock:
        index = USER_INFO.get(request.sid, {}).get("controller_index")
        if index is not None:
            on_shutdown(index)
        USER_INFO.pop(request.sid, None)


@sio.on('shutdown')
def on_shutdown(index):
    global joycon2_owner
    with user_info_lock:
        if not owns(index):
            return {"ok": False, "error": "This tab does not own the controller"}
        if index == JOYCON2_INDEX:
            joycon2.stop()
            joycon2_owner = None
        elif nxbt:
            nxbt.remove_controller(index)
        USER_INFO[request.sid].pop("controller_index", None)
        return {"ok": True}


@sio.on('web_create_pro_controller')
def on_create_controller(options=None):
    global joycon2_owner
    print("Create Controller")

    try:
        with user_info_lock:
            options = options or {}
            backend = options.get("backend", "pro")
            if backend not in ("pro", "joycon2_right"):
                raise ValueError("Unknown controller backend")
            if USER_INFO[request.sid].get("controller_index") is not None:
                raise ValueError("Disconnect the current controller first")
            if backend == "joycon2_right":
                if joycon2_owner is not None or (nxbt and len(nxbt.state)):
                    raise ValueError("The adapter is already in use; disconnect existing sessions")
                joycon2.start()
                index = JOYCON2_INDEX
                joycon2_owner = request.sid
            else:
                if joycon2_owner is not None:
                    raise ValueError("Disconnect Joy-Con 2 before using the Pro backend")
                joycon2.stop()
                pro = pro_backend()
                reconnect_addresses = pro.get_switch_addresses()
                index = pro.create_controller(PRO_CONTROLLER, reconnect_address=reconnect_addresses)
            USER_INFO[request.sid]["controller_index"] = index

        emit('create_pro_controller', index)
    except Exception as e:
        emit('error', str(e))


@sio.on('input')
def handle_input(message):
    try:
        if not isinstance(message, str) or len(message) > 16384:
            raise ValueError("Invalid input message")
        message = json.loads(message)
        index, packet = message[:2]
        if not owns(index):
            raise ValueError("This session does not own the controller")
        if index == JOYCON2_INDEX:
            with user_info_lock:
                if not owns(index) or joycon2.mouse_test_active is True:
                    return
                options = message[2] if len(message) > 2 else {}
                value = input_step(packet, options.get("stick", "left"), options.get("orientation", "sideways-right"),
                                   options.get("button_layout", "printed"))
                joycon2.request({"op": "set", "state": value})
        else:
            nxbt.set_controller_input(index, packet)
    except (OSError, ValueError, TypeError, IndexError, AttributeError) as error:
        emit('error', str(error))


def restore_after_mouse(owner, generation):
    try:
        while joycon2_owner == owner and joycon2.generation == generation and joycon2.active():
            sio.sleep(0.5)
        with user_info_lock:
            if joycon2_owner == owner and joycon2.generation == generation:
                joycon2.start()
    except Exception:
        sio.emit("error", "Native cursor ended; reconnect the controller", to=owner)


@sio.on('joycon2_mouse_test')
def handle_mouse_test():
    with user_info_lock:
        if not owns(JOYCON2_INDEX):
            return {"ok": False, "error": "This tab does not own a right Joy-Con"}
        if joycon2.mouse_test_active is True:
            return {"ok": False, "error": "Native cursor test already running"}
        try:
            joycon2.start(native_mouse=True)
            sio.start_background_task(restore_after_mouse, request.sid, joycon2.generation)
            return {"ok": True}
        except Exception:
            try:
                joycon2.start()
            except Exception:
                pass
            return {"ok": False, "error": "Native cursor unavailable; check the private motion capture"}


@sio.on('joycon2_mouse_stop')
def handle_mouse_stop():
    with user_info_lock:
        if not owns(JOYCON2_INDEX):
            return {"ok": False}
        try:
            if joycon2.mouse_test_active is True:
                joycon2.start()
            return {"ok": True}
        except Exception:
            return {"ok": False, "error": "Controller reconnection failed"}


@sio.on('joycon2_mouse')
def handle_mouse_input(value):
    if not owns(JOYCON2_INDEX) or joycon2.mouse_test_active is not True:
        return {"ok": False}
    try:
        if not isinstance(value, dict) or set(value) - {"dx", "dy", "lifted"}:
            raise ValueError("Invalid mouse request")
        dx, dy, lifted = value.get("dx", 0), value.get("dy", 0), value.get("lifted", False)
        if (any(type(axis) is not int or not -2047 <= axis <= 2047 for axis in (dx, dy))
                or type(lifted) is not bool or (lifted and (dx or dy))):
            raise ValueError("Invalid mouse delta")
        command = {"op": "mouse", "dx": dx, "dy": dy}
        command.update({"lifted": True} if lifted else {"surface": 50})
        joycon2.request(command)
        return {"ok": True}
    except (OSError, ValueError):
        return {"ok": False}


@sio.on('joycon2_mouse_click')
def handle_mouse_click(value=None):
    if value is not None or not owns(JOYCON2_INDEX) or joycon2.mouse_test_active is not True:
        return {"ok": False}
    try:
        joycon2.request({"op": "mouse_click"})
        return {"ok": True}
    except (OSError, ValueError):
        return {"ok": False}


@sio.on('joycon2_mouse_release')
def handle_mouse_release():
    if not owns(JOYCON2_INDEX) or joycon2.mouse_test_active is not True:
        return {"ok": False}
    try:
        joycon2.request({"op": "release"})
        return {"ok": True}
    except (OSError, ValueError):
        return {"ok": False}


@sio.on('joycon2_join')
def handle_joycon2_join():
    if owns(JOYCON2_INDEX):
        try:
            joycon2.request({"op": "set", "state": {"buttons": ["SL", "SR"], "duration": 0.25}})
        except (OSError, ValueError) as error:
            emit('error', str(error))


@sio.on('joycon2_reconnect')
def handle_joycon2_reconnect():
    if not owns(JOYCON2_INDEX):
        return {"ok": False, "error": "This tab does not own a right Joy-Con"}
    if joycon2.mouse_test_active is True:
        return {"ok": False, "error": "Stop native cursor mode before reconnecting"}
    try:
        joycon2.reconnect()
        return {"ok": True}
    except (OSError, ValueError, RuntimeError):
        return {"ok": False, "error": "Controller reconnection failed"}


@sio.on('joycon2_button')
def handle_joycon2_button(button):
    layout = "printed"
    if isinstance(button, dict):
        layout, button = button.get("layout", "printed"), button.get("button")
    if owns(JOYCON2_INDEX) and button in RIGHT_BUTTON_NAMES:
        try:
            joycon2.request({"op": "set", "state": {"buttons": [map_button(button, layout)],
                "duration": 0.05 if button == "HOME" else 0.1}})
        except (OSError, ValueError) as error:
            emit('error', str(error))


@sio.on('macro')
def handle_macro(message):
    try:
        if not isinstance(message, str) or len(message) > 65536:
            raise ValueError("Macro too large")
        index, macro = json.loads(message)
        if not owns(index):
            raise ValueError("This session does not own the controller")
        if index == JOYCON2_INDEX:
            joycon2.request({"op": "sequence", "steps": json.loads(macro)})
        else:
            nxbt.macro(index, macro)
    except (OSError, ValueError, TypeError) as error:
        emit('error', str(error))


def start_web_app(ip='0.0.0.0', port=8000, usessl=False, cert_path=None):
    if usessl:
        if cert_path is None:
            # Store certs in the package directory
            cert_path = os.path.join(
                os.path.dirname(__file__), "cert.pem"
            )
            key_path = os.path.join(
                os.path.dirname(__file__), "key.pem"
            )
        else:
            # If specified, store certs at the user's preferred location
            cert_path = os.path.join(
                cert_path, "cert.pem"
            )
            key_path = os.path.join(
                cert_path, "key.pem"
            )
        if not os.path.isfile(cert_path) or not os.path.isfile(key_path):
            print(
                "\n"
                "-----------------------------------------\n"
                "---------------->WARNING<----------------\n"
                "The NXBT webapp is being run with self-\n"
                "signed SSL certificates for use on your\n"
                "local network.\n"
                "\n"
                "These certificates ARE NOT safe for\n"
                "production use. Please generate valid\n"
                "SSL certificates if you plan on using the\n"
                "NXBT webapp anywhere other than your own\n"
                "network.\n"
                "-----------------------------------------\n"
                "\n"
                "The above warning will only be shown once\n"
                "on certificate generation."
                "\n"
            )
            print("Generating certificates...")
            cert, key = generate_cert(gethostname())
            with open(cert_path, "wb") as f:
                f.write(cert)
            with open(key_path, "wb") as f:
                f.write(key)

        eventlet.wsgi.server(eventlet.wrap_ssl(eventlet.listen((ip, port)),
            certfile=cert_path, keyfile=key_path), app)
    else:
        eventlet.wsgi.server(eventlet.listen((ip, port)), app)


if __name__ == "__main__":
    start_web_app()
