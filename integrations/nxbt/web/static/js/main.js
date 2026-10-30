/**********************************************/
/* Globals, Constants, and Enums */
/**********************************************/

let NXBT_CONTROLLER_INDEX = false;
let CONTROLLER_INDEX = false;
let CONTROLLER_CONNECTED = false;
let STATE = false;
let ACTIVE_BACKEND = "pro";
let lastInputSent = 0;
let sequenceRunning = false;
let eventLoopStarted = false;

// HTML SECTIONS
let HTML_CONTROLLER_SELECTION = document.getElementById("controller-selection");
let HTML_LOADER = document.getElementById("loader");
let HTML_LOADER_TEXT = document.getElementById("loader-text");
let HTML_CONTROLLER_CONFIG = document.getElementById("controller-config");
let HTML_MACRO_TEXT = document.getElementById("macro-text");
let HTML_STATUS_INDICATOR = document.getElementById("status-indicator");
let HTML_STATUS_INDICATOR_LIGHT = document.getElementById("status-indicator-light");
let HTML_STATUS_INDICATOR_TEXT = document.getElementById("status-indicator-text");
let HTML_KEYBOARD_MAP = document.getElementById("keyboard-map");
let HTML_CONTROLLER_MAP = document.getElementById("controller-map");
let HTML_ERROR_DISPLAY = document.getElementById("error-display");
let HTML_CONTROLLER_SESSIONS = document.getElementById("controller-sessions");
let HTML_CONTROLLER_SESSIONS_CONTAINER = document.getElementById("controller-session-container");

const ControllerState = {
    INITIALIZING: "initializing",
    CONNECTING: "connecting",
    RECONNECTING: "reconnecting",
    CONNECTED: "connected",
    CRASHED: "crashed",
}

const InputDevice = {
    KEYBOARD: "keyboard",
    GAMEPAD: "gamepad",
    WEBHID: "webhid"
}
let INPUT_DEVICE = InputDevice.KEYBOARD;

const ControllerType = {
    PRO_CONTROLLER: "pro_controller",
    JOYCON_L: "joycon_l",
    JOYCON_R: "joycon_r"
}

const KEYMAP = NxbtKeyboard.KEYMAP;

const LEFT_STICK = [
    "LS_UP",
    "LS_LEFT",
    "LS_RIGHT",
    "LS_DOWN"
]
const RIGHT_STICK = [
    "RS_UP",
    "RS_LEFT",
    "RS_RIGHT",
    "RS_DOWN"
]

let INPUT_PACKET = {
    // Sticks
    "L_STICK": {
        "PRESSED": false,
        "X_VALUE": 0,
        "Y_VALUE": 0,
        // Keyboard position calculation values
        "LS_UP": false,
        "LS_LEFT": false,
        "LS_RIGHT": false,
        "LS_DOWN": false
    },
    "R_STICK": {
        "PRESSED": false,
        "X_VALUE": 0,
        "Y_VALUE": 0,
        // Keyboard position calculation values
        "RS_UP": false,
        "RS_LEFT": false,
        "RS_RIGHT": false,
        "RS_DOWN": false
    },
    // Dpad
    "DPAD_UP": false,
    "DPAD_LEFT": false,
    "DPAD_RIGHT": false,
    "DPAD_DOWN": false,
    // Triggers
    "L": false,
    "ZL": false,
    "R": false,
    "ZR": false,
    // Joy-Con Specific Buttons
    "JCL_SR": false,
    "JCL_SL": false,
    "JCR_SR": false,
    "JCR_SL": false,
    // Meta buttons
    "PLUS": false,
    "MINUS": false,
    "HOME": false,
    "CAPTURE": false,
    "C": false,
    // Buttons
    "Y": false,
    "X": false,
    "B": false,
    "A": false
}
let INPUT_PACKET_OLD = JSON.parse(JSON.stringify(INPUT_PACKET));
const NEUTRAL_INPUT_PACKET = JSON.parse(JSON.stringify(INPUT_PACKET));
const mouseInput = new NxbtMouse.MouseInput();
const mouseTarget = document.getElementById("mouse-target");
const mouseSurface = document.getElementById("mouse-surface");
const mouseStatus = document.getElementById("mouse-status");
const mouseCapture = document.getElementById("mouse-capture");
let nativeMouseRequested = false;
let nativeMouseSeen = false;
let mouseBusy = false;
let mouseCapturePending = false;
const virtualPresses = new Map();
let hidDevice = null;
let hidLayouts = null;
let hidState = null;
let hidReports = 0;
let hidBusy = false;
const hidButton = document.getElementById("connect-hid");
const hidStatus = document.getElementById("hid-status");
hidButton.hidden = !navigator.hid;

function resetInput() {
    stopMouseCapture();
    INPUT_PACKET = JSON.parse(JSON.stringify(NEUTRAL_INPUT_PACKET));
    sendInputIfChanged();
}

function sendInputIfChanged() {
    if (nativeMouseRequested || STATE?.[NXBT_CONTROLLER_INDEX]?.native_test) return;
    const outgoing = JSON.parse(JSON.stringify(INPUT_PACKET));
    const now = performance.now();
    for (const [button, until] of virtualPresses) {
        if (until > now) outgoing[button] = true;
        else virtualPresses.delete(button);
    }
    if (mouseInput.pressingA(performance.now())) outgoing.A = true;
    const mouseStick = mouseInput.stick(performance.now());
    if (mouseStick) {
        const stick = outgoing[mouseStick.target === "left" ? "L_STICK" : "R_STICK"];
        stick.X_VALUE = mouseStick.x; stick.Y_VALUE = mouseStick.y;
    }
    const changed = JSON.stringify(outgoing) !== JSON.stringify(INPUT_PACKET_OLD);
    const joycon = ACTIVE_BACKEND === "joycon2_right";
    if (joycon && STATE?.[NXBT_CONTROLLER_INDEX]?.state !== ControllerState.CONNECTED) return;
    if (document.hidden && joycon) return;
    if (joycon && now - lastInputSent < 33) return;
    if (NXBT_CONTROLLER_INDEX !== false && (changed || (joycon && !sequenceRunning && now - lastInputSent > 100))) {
        if (changed) sequenceRunning = false;
        const options = {stick: mouseStick ? mouseStick.target : document.getElementById("joycon-stick").value,
            orientation: document.getElementById("joycon-orientation").value,
            button_layout: document.getElementById("joycon-face-layout").value};
        socket.emit('input', JSON.stringify([NXBT_CONTROLLER_INDEX, outgoing, options]));
        INPUT_PACKET_OLD = outgoing;
        lastInputSent = now;
    }
}

document.addEventListener("visibilitychange", () => {
    if (document.hidden) resetInput();
});
window.addEventListener("blur", resetInput);

function stopMouseCapture() {
    const wasNative = mouseInput.active && mouseInput.mode === "native";
    mouseInput.stop(); mouseCapturePending = false;
    mouseSurface.classList.remove("capturing");
    mouseCapture.textContent = "Capture Mouse";
    mouseCapture.disabled = mouseTarget.value === "off" || NXBT_CONTROLLER_INDEX === false;
    mouseStatus.textContent = mouseTarget.value === "off" ? "Off" : "Stopped";
    if (document.pointerLockElement === mouseSurface) document.exitPointerLock();
    if (wasNative && nativeMouseRequested) socket.emit("joycon2_mouse_release");
}

function updateMouseAvailability() {
    const joycon = ACTIVE_BACKEND === "joycon2_right";
    mouseCapture.disabled = mouseTarget.value === "off" || NXBT_CONTROLLER_INDEX === false
        || mouseCapturePending || mouseInput.active;
    mouseTarget.querySelector('[value="left"]').disabled = joycon;
    mouseTarget.querySelector('[value="native"]').disabled = !joycon || !STATE?.[NXBT_CONTROLLER_INDEX]?.native_available;
    if ((joycon && mouseTarget.value === "left") || (!joycon && mouseTarget.value === "native")) {
        mouseTarget.value = "off"; stopMouseCapture();
    }
    for (const button of document.querySelectorAll("#joycon-button-pad button, #joycon-stick-pad button")) {
        button.disabled = nativeMouseRequested;
    }
    document.querySelector('#joycon-options button[onclick="registerJoyCon()"]').disabled = nativeMouseRequested;
    document.querySelector('#controller-commands button[onclick="sendMacro()"]').disabled = nativeMouseRequested;
    HTML_MACRO_TEXT.disabled = nativeMouseRequested;
}

function beginMouseCapture() {
    const mode = mouseTarget.value;
    if (mode === "off" || NXBT_CONTROLLER_INDEX === false || mouseInput.active || mouseCapturePending) return;
    if (typeof mouseSurface.requestPointerLock !== "function") {
        mouseStatus.textContent = "Pointer lock unsupported in this browser";
        return;
    }
    mouseCapturePending = true;
    mouseCapture.disabled = true;
    mouseStatus.textContent = "Requesting capture...";
    try {
        const locking = mouseSurface.requestPointerLock();
        locking?.catch(mouseCaptureFailed);
    } catch (_) {
        mouseCaptureFailed();
    }
}

function mouseCaptureFailed(error) {
    if (document.pointerLockElement === mouseSurface) return;
    mouseCapturePending = false;
    stopMouseCapture();
    mouseStatus.textContent = "Pointer lock denied";
    console.warn("Mouse capture failed", error?.name || error?.type || "unknown", error?.message || "");
}

function activateLockedMouse() {
    const mode = mouseTarget.value;
    if (!mouseCapturePending || mode === "off") { document.exitPointerLock(); return; }
    mouseCapturePending = false;
    mouseInput.start(mode);
    mouseSurface.classList.add("capturing");
    mouseCapture.textContent = "Captured";
    mouseCapture.disabled = true;
    mouseStatus.textContent = "Captured";
    if (mode === "native" && !nativeMouseRequested) {
        nativeMouseRequested = true; nativeMouseSeen = false;
        mouseStatus.textContent = "Connecting native cursor...";
        updateMouseAvailability();
        socket.emit("joycon2_mouse_test", result => {
            if (!result?.ok) {
                nativeMouseRequested = false; stopMouseCapture();
                mouseStatus.textContent = result?.error || "Native cursor unavailable";
                updateMouseAvailability();
            }
        });
    }
}

function onHidInput(event) {
    const state = Lic2HID.decode(hidLayouts?.get(event.reportId), event.data);
    if (!state || event.device !== hidDevice) return;
    hidState = state;
    hidReports++;
    hidStatus.textContent = `${hidDevice.productName}: ${hidReports} reports`;
    if (INPUT_DEVICE === InputDevice.WEBHID) {
        INPUT_PACKET = Lic2HID.toNxbt(hidState);
        sendInputIfChanged();
    }
}

async function disconnectHid() {
    const device = hidDevice;
    hidDevice = null;
    hidState = null;
    hidLayouts = null;
    document.querySelector('#input-device option[value="webhid"]').disabled = true;
    if (INPUT_DEVICE === InputDevice.WEBHID) {
        const inputs = document.getElementById("input-device");
        inputs.value = InputDevice.KEYBOARD;
        changeInput({target: inputs});
    }
    hidButton.textContent = "Connect WebHID";
    hidStatus.textContent = "WebHID disconnected";
    if (device) {
        device.removeEventListener("inputreport", onHidInput);
        if (device.opened) await device.close();
    }
    for (const gamepad of navigator.getGamepads()) if (gamepad) addGamepadOption(gamepad);
}

async function connectHid() {
    if (hidBusy || !navigator.hid) return;
    hidBusy = true;
    hidButton.disabled = true;
    try {
        if (hidDevice) {
            await disconnectHid();
            return;
        }
        const devices = await navigator.hid.requestDevice({filters: [{usagePage: 1, usage: 5}, {usagePage: 1, usage: 4}]});
        const device = devices[0];
        if (!device) return;
        if (!/^Lic2 Pro Controller\b/i.test(device.productName)) throw new Error("Select Lic2 Pro Controller");
        const reports = Lic2HID.layouts(device.collections);
        if (!reports.size) throw new Error("No supported Lic2 stick report found");
        if (!device.opened) await device.open();
        hidDevice = device;
        hidLayouts = reports;
        hidState = null;
        hidReports = 0;
        device.addEventListener("inputreport", onHidInput);
        const inputs = document.getElementById("input-device");
        for (const duplicate of inputs.querySelectorAll('option[value="gamepad"]')) {
            if (duplicate.textContent.toLowerCase().startsWith(device.productName.toLowerCase())) duplicate.remove();
        }
        const option = inputs.querySelector('option[value="webhid"]');
        option.textContent = `${device.productName} (WebHID)`;
        option.disabled = false;
        inputs.value = InputDevice.WEBHID;
        changeInput({target: inputs});
        hidStatus.textContent = `${device.productName}: waiting for input`;
        hidButton.textContent = "Disconnect WebHID";
    } catch (error) {
        hidStatus.textContent = error.message;
    } finally {
        hidBusy = false;
        hidButton.disabled = false;
    }
}

if (navigator.hid) navigator.hid.addEventListener("disconnect", event => {
    if (event.device === hidDevice) disconnectHid().catch(error => {hidStatus.textContent = error.message;});
});

let PRO_CONTROLLER_DISPLAY = {
    // Sticks
    "L_STICK": {
        "STICK": true,
        "ELEMENT": document.getElementById("pc_ls"),
        "MAX_X": 23,
        "MIN_X": 15.5,
        "DIFF_X": 7.5,
        "MAX_Y": 29,
        "MIN_Y": 18,
        "DIFF_Y": 11
    },
    "R_STICK": {
        "STICK": true,
        "ELEMENT": document.getElementById("pc_rs"),
        "MAX_X": 63.5,
        "MIN_X": 56,
        "DIFF_X": 7.5,
        "MAX_Y": 50,
        "MIN_Y": 38.125,
        "DIFF_Y": 11.875,
    },
    // Dpad
    "DPAD_UP": document.getElementById("pc_du"),
    "DPAD_LEFT": document.getElementById("pc_dl"),
    "DPAD_RIGHT": document.getElementById("pc_dr"),
    "DPAD_DOWN": document.getElementById("pc_dd"),
    // Triggers
    "L": document.getElementById("pc_l"),
    "ZL": document.getElementById("pc_zl"),
    "R": document.getElementById("pc_r"),
    "ZR": document.getElementById("pc_zr"),
    // Meta buttons
    "PLUS": document.getElementById("pc_p"),
    "MINUS": document.getElementById("pc_m"),
    "HOME": document.getElementById("pc_h"),
    "CAPTURE": document.getElementById("pc_c"),
    // Buttons
    "Y": document.getElementById("pc_y"),
    "X": document.getElementById("pc_x"),
    "B": document.getElementById("pc_b"),
    "A": document.getElementById("pc_a")
}

/**********************************************/
/* Socket.IO Functionality */
/**********************************************/

let socket = io();

mouseTarget.addEventListener("change", () => {
    stopMouseCapture();
    if (nativeMouseRequested) socket.emit("joycon2_mouse_stop");
    nativeMouseRequested = false; nativeMouseSeen = false;
    resetInput(); updateMouseAvailability();
});
document.getElementById("mouse-gain").addEventListener("input", event => {
    mouseInput.gain = Number(event.target.value);
    document.getElementById("mouse-gain-value").textContent = `${mouseInput.gain}x`;
});
mouseSurface.addEventListener("click", beginMouseCapture);
document.addEventListener("mousemove", event => {
    if (document.pointerLockElement === mouseSurface) mouseInput.move(event.movementX, event.movementY, performance.now());
});
document.addEventListener("pointerlockchange", () => {
    if (document.pointerLockElement === mouseSurface) activateLockedMouse();
    else if (mouseInput.active || mouseCapturePending) { stopMouseCapture(); sendInputIfChanged(); }
});
document.addEventListener("pointerlockerror", mouseCaptureFailed);
document.addEventListener("mousedown", event => {
    if (document.pointerLockElement !== mouseSurface || !mouseInput.active) return;
    event.preventDefault(); event.stopImmediatePropagation();
    if (event.button !== 0) return;
    if (mouseInput.mode === "native" && !STATE?.[NXBT_CONTROLLER_INDEX]?.mouse_ready) return;
    if (!mouseInput.click(performance.now())) return;
    if (mouseInput.mode === "native") {
        socket.emit("joycon2_mouse_click", result => {
            if (!result?.ok && mouseInput.active) mouseStatus.textContent = "Click dropped";
        });
    } else sendInputIfChanged();
}, true);
document.addEventListener("click", event => {
    if (document.pointerLockElement === mouseSurface) {
        event.preventDefault(); event.stopImmediatePropagation();
    }
}, true);
document.addEventListener("keydown", event => {
    if (event.key === "Escape" && (mouseInput.active || mouseCapturePending)) {
        stopMouseCapture(); sendInputIfChanged();
    }
}, true);
mouseSurface.addEventListener("contextmenu", event => event.preventDefault());
setInterval(() => {
    if (!nativeMouseRequested || !mouseInput.active || mouseBusy || document.hidden
            || !STATE?.[NXBT_CONTROLLER_INDEX]?.mouse_ready) return;
    if (performance.now() - mouseInput.last > 250) { mouseInput.dx = mouseInput.dy = 0; return; }
    const delta = mouseInput.mouse();
    if (!delta) return;
    mouseBusy = true;
    socket.emit("joycon2_mouse", delta, result => {
        mouseBusy = false;
        if (!result?.ok && mouseInput.active) mouseStatus.textContent = "Movement dropped";
    });
}, 16);

// Request to the state at 1Hz
socket.emit('state');
let stateInterval = setInterval(function() {
    socket.emit('state');
}, 1000);

socket.on('state', function(state) {
    STATE = state;
    const session = state[NXBT_CONTROLLER_INDEX];
    if (session?.native_test) {
        nativeMouseSeen = true;
        if (mouseInput.active) mouseStatus.textContent = session.mouse_ready ?
            `Native cursor - ${session.native_remaining}s` : "Connecting native cursor...";
    } else if (nativeMouseRequested && nativeMouseSeen) {
        nativeMouseRequested = false; nativeMouseSeen = false; stopMouseCapture();
        mouseStatus.textContent = "Native test ended";
    }
    updateMouseAvailability();
});

socket.on('connect', function() {
    console.log("Connected");
});

checkForLoadInterval = false;
socket.on('create_pro_controller', function(index) {
    NXBT_CONTROLLER_INDEX = index;
    checkForLoadInterval = setInterval(checkForLoad, 1000);
});

socket.on('disconnect', function() {
    stopMouseCapture(); nativeMouseRequested = false; mouseBusy = false;
    NXBT_CONTROLLER_INDEX = false;
    CONTROLLER_CONNECTED = false;
    HTML_CONTROLLER_CONFIG.classList.add('hidden');
    HTML_LOADER.classList.add('hidden');
    HTML_CONTROLLER_SELECTION.classList.remove('hidden');
});

socket.on('error', function(errorMessage) {
    displayError(errorMessage);
    if (NXBT_CONTROLLER_INDEX === false) {
        HTML_LOADER.classList.add('hidden');
        HTML_CONTROLLER_SELECTION.classList.remove('hidden');
    }
});

/**********************************************/
/* Listeners and Startup Functionality */
/**********************************************/

// Startup Functions
window.onload = function() {
    // Run the Loader animation
    setInterval(updateLoader, 85);
    // // Print out the latency of setTimeout
    // measureTimeoutLatency.start(120, 60);
}

// Keydown listener
function setKeyboardControl(control, pressed) {
    NxbtKeyboard.setControl(INPUT_PACKET, control, pressed);
}

function globalKeydownHandler(evt) {
    if (evt.target?.closest("input, select, textarea")) return;
    if (INPUT_DEVICE !== InputDevice.KEYBOARD) {
        return
    }

    evt = evt || window.event;
    // Prevent scrolling on keypress
    if([32, 37, 38, 39, 40].indexOf(evt.keyCode) > -1) {
        evt.preventDefault();
    }

    if (Object.keys(KEYMAP).indexOf(JSON.stringify(evt.keyCode)) > -1) {
        control = KEYMAP[evt.keyCode];
        setKeyboardControl(control, true);
    }
}
document.onkeydown = globalKeydownHandler;

// Keyup listener
function globalKeyupHandler(evt) {
    if (INPUT_DEVICE !== InputDevice.KEYBOARD) {
        return
    }

    evt = evt || window.event;

    if (Object.keys(KEYMAP).indexOf(JSON.stringify(evt.keyCode)) > -1) {
        control = KEYMAP[evt.keyCode];
        setKeyboardControl(control, false);
    }
}
document.onkeyup = globalKeyupHandler;

function disableKeyHandlers() {
    document.onkeydown = false;
    document.onkeyup = false;
}

function enableKeyHandlers() {
    document.onkeydown = globalKeydownHandler;
    document.onkeyup = globalKeyupHandler;
}

function addGamepadOption(gamepad) {
    if (hidDevice && gamepad.id.toLowerCase().startsWith(hidDevice.productName.toLowerCase())) return;
    const inputs = document.getElementById("input-device");
    if (inputs.querySelector(`option[value="gamepad"][index="${gamepad.index}"]`)) return;
    const input = document.createElement("option");
    input.textContent = `${gamepad.id} (Gamepad)`;
    input.setAttribute("value", "gamepad");
    input.setAttribute("index", gamepad.index);
    inputs.appendChild(input);
}

window.addEventListener("gamepadconnected", function(evt) {
    addGamepadOption(evt.gamepad);
});

window.addEventListener("gamepaddisconnected", function(evt) {
    if (INPUT_DEVICE === InputDevice.GAMEPAD && Number(CONTROLLER_INDEX) === evt.gamepad.index) {
        const inputs = document.getElementById("input-device");
        inputs.value = InputDevice.KEYBOARD;
        changeInput({target: inputs});
    }
    document.querySelector(`#input-device option[value="gamepad"][index="${evt.gamepad.index}"]`)?.remove();
});

/**********************************************/
/* UI, Input Monitoring, Gamepad Functionality */
/**********************************************/

function displayOtherSessions() {
    controllerIndices = Object.keys(STATE);
    // If there aren't any controller sessions
    if (controllerIndices.length < 1) {
        HTML_CONTROLLER_SESSIONS.classList.add("hidden");
        return;
    // If the only controller session is the current one
    } else if (controllerIndices.length === 1 &&
            Number(controllerIndices[0]) === NXBT_CONTROLLER_INDEX) {
        HTML_CONTROLLER_SESSIONS.classList.add("hidden");
        return;
    }

    HTML_CONTROLLER_SESSIONS.classList.remove('hidden');
    HTML_CONTROLLER_SESSIONS_CONTAINER.innerHTML = ""
    for (let i = 0; i < controllerIndices.length; i++) {
        sessionIndex = controllerIndices[i];
        if (sessionIndex === NXBT_CONTROLLER_INDEX) {
            continue
        }

        let session = document.createElement("div")
        session.classList.add("controller-session");
        let sessionTitle = document.createElement("h1");
        sessionTitle.innerHTML = "Session #" + sessionIndex;
        let sessionEnd = document.createElement("button");
        sessionEnd.innerHTML = "END";
        sessionEnd.onclick = function() {
            socket.emit('shutdown', Number(sessionIndex));
        }

        session.appendChild(sessionTitle);
        session.appendChild(sessionEnd);

        HTML_CONTROLLER_SESSIONS_CONTAINER.appendChild(session);
    }
}
// Set a first quick call to make sure results appear
// on page load, if available. The timeout is necessary
// due to the time it takes for the initial State to load.
setTimeout(displayOtherSessions, 250);
setInterval(displayOtherSessions, 2000);

function displayError(errorText) {
    let errorContainer = document.createElement('div');
    errorContainer.classList.add('error');

    let errorHeader = document.createElement('h1');
    errorHeader.innerHTML = "ERROR";

    let errorMessage = document.createElement('p');
    errorMessage.textContent = errorText;

    errorContainer.appendChild(errorHeader);
    errorContainer.appendChild(errorMessage);
    HTML_ERROR_DISPLAY.appendChild(errorContainer);

    setTimeout(function() {
        errorContainer.remove();
    }, 10000);
}

function createProController(backend = "pro") {
    stopMouseCapture(); nativeMouseRequested = false;
    STATE = {};
    clearInterval(checkForLoadInterval);
    HTML_LOADER_TEXT.textContent = "connecting";
    ACTIVE_BACKEND = backend;
    updateMouseAvailability();
    const joycon = backend === "joycon2_right";
    document.body.classList.toggle("joycon-right-mode", joycon);
    document.getElementById("joycon-options").classList.toggle("hidden", !joycon);
    document.getElementById("pro-options").classList.toggle("hidden", joycon);
    document.getElementById("backend-name").textContent = joycon ? "Joy-Con 2 (R)" : "Pro Controller";
    document.getElementById("procon-underlay").parentElement.classList.toggle("hidden", joycon);
    document.getElementById("joyconr-underlay").parentElement.classList.toggle("hidden", !joycon);
    document.getElementById("joyconr-underlay").classList.toggle("hidden", !joycon);
    document.getElementById("macro-label").textContent = joycon ? "JSON Sequence" : "Controller Macro";
    HTML_MACRO_TEXT.placeholder = joycon ? '[{"buttons":["HOME"],"duration":0.05}]' : "Type Your Macro Here";
    HTML_CONTROLLER_SELECTION.classList.add('hidden');
    HTML_LOADER.classList.remove('hidden');

    socket.emit('web_create_pro_controller', {backend});
}

function changeBackend() {
    socket.emit('shutdown', NXBT_CONTROLLER_INDEX, result => {
        if (!result?.ok) { displayError(result?.error || "Controller did not stop"); return; }
        NXBT_CONTROLLER_INDEX = false;
        clearInterval(checkForLoadInterval);
        resetInput();
        HTML_CONTROLLER_CONFIG.classList.add('hidden');
        HTML_LOADER.classList.add('hidden');
        HTML_STATUS_INDICATOR.classList.add('hidden');
        HTML_CONTROLLER_SELECTION.classList.remove('hidden');
    });
}

function tapJoyCon(button) {
    sequenceRunning = true;
    socket.emit('joycon2_button', {button, layout: document.getElementById("joycon-face-layout").value});
}

function tapStick(x, y) {
    sequenceRunning = true;
    const steps = [{x, y, duration: 0.15,
        orientation: document.getElementById("joycon-orientation").value}];
    socket.emit('macro', JSON.stringify([NXBT_CONTROLLER_INDEX, JSON.stringify(steps)]));
}

function registerJoyCon() {
    sequenceRunning = true;
    socket.emit('joycon2_join');
}

function reconnectJoyCon() {
    mouseStatus.textContent = "Reconnecting Joy-Con...";
    socket.emit('joycon2_reconnect', result => {
        if (!result?.ok) mouseStatus.textContent = result?.error || "Controller reconnection failed";
    });
}

function tapPro(button) {
    if (ACTIVE_BACKEND !== "pro" || NXBT_CONTROLLER_INDEX === false) return;
    virtualPresses.set(button, performance.now() + 90);
    sendInputIfChanged();
    setTimeout(sendInputIfChanged, 100);
}

function shutdownController() {
    if (STATE[NXBT_CONTROLLER_INDEX]) {
        socket.emit('shutdown', NXBT_CONTROLLER_INDEX);
    }
}

function recreateProController() {
    NXBT_CONTROLLER_INDEX = false;
    createProController(ACTIVE_BACKEND);
}

function restartController() {
    shutdownController();
    setTimeout(recreateProController, 2000);
}

function checkForLoad() {
    if (STATE[NXBT_CONTROLLER_INDEX]) {
        controller_state = STATE[NXBT_CONTROLLER_INDEX].state
        HTML_LOADER_TEXT.innerHTML = controller_state;

        if (controller_state === ControllerState.CONNECTED) {
            // Show the connected message for 1 second
            setTimeout(function() {
                clearInterval(checkForLoadInterval);
                HTML_LOADER.classList.add('hidden');
                HTML_CONTROLLER_CONFIG.classList.remove('hidden');
                HTML_STATUS_INDICATOR.classList.remove('hidden');
                setInterval(updateStatusIndicator, 1000);
                if (!eventLoopStarted) {
                    eventLoopStarted = true;
                    eventLoop();
                }
            }, 1000);
        }
    }
}

function updateStatusIndicator() {
    if (STATE[NXBT_CONTROLLER_INDEX]) {
        controller_state = STATE[NXBT_CONTROLLER_INDEX].state;
        if (controller_state === ControllerState.CONNECTED) {
            changeStatusIndicatorState("indicator-green", "CONNECTED");
        } else if (controller_state === ControllerState.CONNECTING) {
            changeStatusIndicatorState("indicator-yellow", "CONNECTING");
        } else if (controller_state === ControllerState.RECONNECTING) {
            changeStatusIndicatorState("indicator-yellow", "RECONNECTING");
        } else if (controller_state === ControllerState.CRASHED) {
            changeStatusIndicatorState("indicator-red", "CRASHED");
        }
    } else {
        changeStatusIndicatorState("indicator-red", "NO INPUT");
    }
}

function changeStatusIndicatorState(className, text) {
    HTML_STATUS_INDICATOR_LIGHT.className = "";
    HTML_STATUS_INDICATOR_LIGHT.classList.add(className);
    HTML_STATUS_INDICATOR_TEXT.innerHTML = text;
}

function changeInput(evt) {
    inputType = evt.target.value
    if (inputType === InputDevice.GAMEPAD && hidDevice && evt.target.selectedOptions[0].textContent.toLowerCase().startsWith(hidDevice.productName.toLowerCase())) {
        inputType = InputDevice.WEBHID;
        evt.target.value = inputType;
    }
    resetInput();

    if (inputType === InputDevice.KEYBOARD) {
        INPUT_DEVICE = inputType;

        document.onkeydown = globalKeydownHandler;
        document.onkeyup = globalKeyupHandler;

        HTML_CONTROLLER_MAP.classList.add('hidden');
        HTML_KEYBOARD_MAP.classList.remove('hidden');

        CONTROLLER_INDEX = false;
    } else if (inputType == InputDevice.GAMEPAD || inputType == InputDevice.WEBHID) {
        INPUT_DEVICE = inputType;

        document.onkeydown = false;
        document.onkeyup = false;

        HTML_KEYBOARD_MAP.classList.add('hidden');
        HTML_CONTROLLER_MAP.classList.remove('hidden');

        selectedGamepad = evt.target.children[evt.target.selectedIndex]
        CONTROLLER_INDEX = selectedGamepad.getAttribute("index");
    }
}

function changeFrequency(evt) {
    let newFrequency = evt.target.value;

    if (newFrequency === "RAF") {
        useRAF = true;
    } else {
        newFrequency = Number(newFrequency);
        if (!isNaN(newFrequency)) {
            useRAF = false;
            frequency = (1/newFrequency) * 1000;
        } else {
            console.log("New frequency is not a number");
        }
    }
}

const LOADER_ANIMATION_FRAMES = [0,1,2,3,3,2,1,0];
let loaderFrame = 1;
let highlightedBlock = false;
function updateLoader() {
    loaderBlocks = document.getElementById("loader-blocks").children;

    if (highlightedBlock === false) {
        highlightedBlock = loaderBlocks[0];
    }
    highlightedBlock.classList.remove("loader-block-highlight");
    highlightedBlock = loaderBlocks[LOADER_ANIMATION_FRAMES[loaderFrame]];
    highlightedBlock.classList.add("loader-block-highlight");

    loaderFrame += 1;
    if (loaderFrame >= LOADER_ANIMATION_FRAMES.length) {
        loaderFrame = 0;
    }
}

function updateGamepadInput() {
    let gp = navigator.getGamepads()[CONTROLLER_INDEX];
    INPUT_PACKET["L_STICK"]["X_VALUE"] = gp.axes[0] * 100;
    INPUT_PACKET["L_STICK"]["Y_VALUE"] = gp.axes[1] * -100;
    INPUT_PACKET["L_STICK"]["PRESSED"] = gp["buttons"][10]["pressed"];

    INPUT_PACKET["R_STICK"]["X_VALUE"] = gp.axes[2] * 100;
    INPUT_PACKET["R_STICK"]["Y_VALUE"] = gp.axes[3] * -100;
    INPUT_PACKET["R_STICK"]["PRESSED"] = gp["buttons"][11]["pressed"];

    INPUT_PACKET["DPAD_UP"] = gp["buttons"][12]["pressed"];
    INPUT_PACKET["DPAD_DOWN"] = gp["buttons"][13]["pressed"];
    INPUT_PACKET["DPAD_LEFT"] = gp["buttons"][14]["pressed"];
    INPUT_PACKET["DPAD_RIGHT"] = gp["buttons"][15]["pressed"];

    if (gp["buttons"][16]) {
        INPUT_PACKET["HOME"] = gp["buttons"][16]["pressed"];
    }

    if (gp["buttons"][17]) {
        INPUT_PACKET["CAPTURE"] = gp["buttons"][17]["pressed"];
    }

    INPUT_PACKET["B"] = gp["buttons"][0]["pressed"];
    INPUT_PACKET["A"] = gp["buttons"][1]["pressed"];
    INPUT_PACKET["Y"] = gp["buttons"][2]["pressed"];
    INPUT_PACKET["X"] = gp["buttons"][3]["pressed"];

    INPUT_PACKET["L"] = gp["buttons"][4]["pressed"];
    INPUT_PACKET["R"] = gp["buttons"][5]["pressed"];
    INPUT_PACKET["ZL"] = gp["buttons"][6]["pressed"];
    INPUT_PACKET["ZR"] = gp["buttons"][7]["pressed"];

    INPUT_PACKET["PLUS"] = gp["buttons"][8]["pressed"];
    INPUT_PACKET["MINUS"] = gp["buttons"][9]["pressed"];
}

function updateGamepadDisplay() {
    controls = Object.keys(INPUT_PACKET);
    for (let i = 0; i < controls.length; i++) {
        controlState = INPUT_PACKET[controls[i]];
        control = PRO_CONTROLLER_DISPLAY[controls[i]];

        if (!control) {
            continue;
        }

        if (control.STICK) {
            xRatio = (controlState["X_VALUE"] + 100)/200;
            yRatio = (controlState["Y_VALUE"] + 100)/200;
            xPos = control["MIN_X"] + (xRatio * control["DIFF_X"]);
            yPos = control["MAX_Y"] - (yRatio * control["DIFF_Y"]);
            control["ELEMENT"].style.left = xPos + "%";
            control["ELEMENT"].style.top = yPos + "%";
        } else {
            if (controlState) {
                control.classList.remove('hidden');
            } else {
                control.classList.add('hidden');
            }
        }
    }
}

let timeOld = false;
let frequency = (1/120) * 1000;
let useRAF = true;
function eventLoop() {
    // Update x/y ratio for the sticks based on
    // pressed buttons if we're using a keyboard
    if (INPUT_DEVICE == InputDevice.KEYBOARD) {
        // Calculating left x/y stick values
        lXValue = 0
        lYValue = 0
        if (INPUT_PACKET["L_STICK"]["LS_LEFT"]) {
            lXValue -= 100
        }
        if (INPUT_PACKET["L_STICK"]["LS_RIGHT"]) {
            lXValue += 100
        }
        if (INPUT_PACKET["L_STICK"]["LS_UP"]) {
            lYValue += 100
        }
        if (INPUT_PACKET["L_STICK"]["LS_DOWN"]) {
            lYValue -= 100
        }
        INPUT_PACKET["L_STICK"]["X_VALUE"] = lXValue
        INPUT_PACKET["L_STICK"]["Y_VALUE"] = lYValue

        // Calculating left x/y stick values
        rXValue = 0
        rYValue = 0
        if (INPUT_PACKET["R_STICK"]["RS_LEFT"]) {
            rXValue -= 100
        }
        if (INPUT_PACKET["R_STICK"]["RS_RIGHT"]) {
            rXValue += 100
        }
        if (INPUT_PACKET["R_STICK"]["RS_UP"]) {
            rYValue += 100
        }
        if (INPUT_PACKET["R_STICK"]["RS_DOWN"]) {
            rYValue -= 100
        }
        INPUT_PACKET["R_STICK"]["X_VALUE"] = rXValue
        INPUT_PACKET["R_STICK"]["Y_VALUE"] = rYValue
    } else if (INPUT_DEVICE == InputDevice.GAMEPAD) {
        updateGamepadInput();
    } else if (INPUT_DEVICE == InputDevice.WEBHID && hidState) {
        INPUT_PACKET = Lic2HID.toNxbt(hidState);
    }

    // Only send packet if it's not a duplicate of previous.
    // We can do this since NXBT will hold the previously sent value
    // until we send it a new one.
    sendInputIfChanged();

    updateGamepadDisplay()

    if (useRAF) {
        requestAnimationFrame(eventLoop);
    } else {
        if (!timeOld) {
            timeOld = performance.now();
        }
        timeNew = performance.now();
        delta = timeNew - timeOld;
        diff = delta - frequency;

        if (diff > 0) {
            setTimeout(eventLoop, frequency - diff);
        } else {
            setTimeout(eventLoop, frequency);
        }
        timeOld = timeNew;
    }
}

function sendMacro() {
    let macro = ACTIVE_BACKEND === "joycon2_right" ? HTML_MACRO_TEXT.value : HTML_MACRO_TEXT.value.toUpperCase();
    sequenceRunning = ACTIVE_BACKEND === "joycon2_right";
    socket.emit('macro', JSON.stringify([NXBT_CONTROLLER_INDEX, macro]));
}

/**********************************************/
/* Debug Functionality */
/**********************************************/

const measureTimeoutLatency = {
    debug: false,
    count: 0,
    maxCount: 0,
    deltaSum: 0,
    diffSum: 0,
    timeOld: false,
    rawFrequency: false,
    frequency: false,

    start: function(frequency, iterations) {
        this.rawFrequency = frequency;
        this.frequency = (1/frequency)*1000;
        this.maxCount = iterations;
        this.timeOld = performance.now();
        this.loop(this);
    },

    loop: function(context) {
        timeNew = performance.now();
        delta = timeNew - context.timeOld;
        diff = delta - context.frequency;

        if (context.debug) {
            console.log(diff);
        }

        context.deltaSum += Math.abs(delta);
        context.diffSum += Math.abs(diff);
        context.count += 1

        if (context.count >= context.maxCount) {
            avgDelta = context.deltaSum/context.count;
            avgDiff = context.diffSum/context.count;

            console.log("Average Time setTimeout Delta (ms):", avgDelta);
            console.log("Average Difference between Delta and Frequency (ms):", avgDiff);
        } else {
            if (diff > 0) {
                setTimeout(function(){context.loop(context);}, context.frequency - diff);
            } else {
                setTimeout(function(){context.loop(context);}, context.frequency);
            }
            context.timeOld = timeNew;
        }
    }
}
