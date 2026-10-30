(function(root) {
    "use strict";
    const KEYMAP = {
        87: "LS_UP", 65: "LS_LEFT", 68: "LS_RIGHT", 83: "LS_DOWN", 84: "LS_PRESS",
        38: "RS_UP", 37: "RS_LEFT", 39: "RS_RIGHT", 40: "RS_DOWN", 89: "RS_PRESS",
        71: "DPAD_UP", 86: "DPAD_LEFT", 78: "DPAD_RIGHT", 66: "DPAD_DOWN",
        219: "HOME", 221: "CAPTURE", 54: "PLUS", 55: "MINUS",
        76: "A", 75: "B", 73: "X", 74: "Y",
        49: "L", 50: "ZL", 56: "R", 57: "ZR",
        48: "C", 189: "JCR_SL", 187: "JCR_SR"
    };
    function setControl(packet, control, pressed) {
        if (control === "LS_PRESS") packet.L_STICK.PRESSED = pressed;
        else if (control === "RS_PRESS") packet.R_STICK.PRESSED = pressed;
        else if (["LS_UP", "LS_DOWN", "LS_LEFT", "LS_RIGHT"].includes(control)) packet.L_STICK[control] = pressed;
        else if (["RS_UP", "RS_DOWN", "RS_LEFT", "RS_RIGHT"].includes(control)) packet.R_STICK[control] = pressed;
        else packet[control] = pressed;
    }
    const api = {KEYMAP, setControl};
    if (typeof module === "object" && module.exports) module.exports = api;
    else root.NxbtKeyboard = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
