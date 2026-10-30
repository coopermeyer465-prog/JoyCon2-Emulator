(function(root) {
    "use strict";
    // Reused from the working SwitchRemotePlay Lic2 input decoder.
    const buttonBits = [2, 4, 1, 8, 64, 128, 16, 32, 256, 512, 1024, 2048, 4096, 8192];

    function layouts(collections) {
        const result = new Map();
        function visit(collection) {
            for (const report of collection.inputReports || []) {
                if (result.has(report.reportId)) continue;
                let offset = 0;
                const fields = [];
                for (const item of report.items) {
                    for (let i = 0; i < item.reportCount; i++) {
                        const usage = item.isRange ? Math.min(item.usageMinimum + i, item.usageMaximum) : item.usages?.[i];
                        if (!item.isConstant && !item.isArray && usage !== undefined) {
                            fields.push({offset, size: item.reportSize, usage, min: item.logicalMinimum, max: item.logicalMaximum});
                        }
                        offset += item.reportSize;
                    }
                }
                if ([0x10030, 0x10031, 0x10033, 0x10034].every(usage => fields.some(field => field.usage === usage))) {
                    result.set(report.reportId, {fields, bytes: Math.ceil(offset / 8)});
                }
            }
            for (const child of collection.children || []) visit(child);
        }
        collections.forEach(visit);
        return result;
    }

    function decode(layout, data) {
        if (!layout || data.byteLength < layout.bytes) return null;
        const state = {buttons: 0, hat: 8, lx: 128, ly: 128, rx: 128, ry: 128};
        const axes = {65584: "lx", 65585: "ly", 65587: "rx", 65588: "ry"};
        for (const field of layout.fields) {
            if (field.size < 1 || field.size > 32) continue;
            let value = 0;
            for (let bit = 0; bit < field.size; bit++) {
                value += ((data.getUint8((field.offset + bit) >> 3) >> ((field.offset + bit) % 8)) & 1) * 2 ** bit;
            }
            if (field.min < 0 && value >= 2 ** (field.size - 1)) value -= 2 ** field.size;
            if ((field.usage >>> 16) === 9) {
                if (value) state.buttons |= buttonBits[(field.usage & 65535) - 1] || 0;
            } else if (field.usage === 0x10039) {
                if (value >= field.min && value <= field.max && field.max - field.min === 7) state.hat = value - field.min;
            } else if (axes[field.usage] && field.max > field.min) {
                const normalized = Math.max(0, Math.min(1, (value - field.min) / (field.max - field.min)));
                state[axes[field.usage]] = Math.abs(normalized - 0.5) < 0.025 ? 128 : Math.round(1 + normalized * 254);
            }
        }
        return state;
    }

    function toNxbt(state) {
        const buttons = {
            Y: 1, B: 2, A: 4, X: 8, L: 16, R: 32, ZL: 64, ZR: 128,
            MINUS: 256, PLUS: 512, HOME: 4096, CAPTURE: 8192
        };
        const packet = {
            L_STICK: {PRESSED: !!(state.buttons & 1024), X_VALUE: (state.lx - 128) / 127 * 100, Y_VALUE: (128 - state.ly) / 127 * 100},
            R_STICK: {PRESSED: !!(state.buttons & 2048), X_VALUE: (state.rx - 128) / 127 * 100, Y_VALUE: (128 - state.ry) / 127 * 100},
            DPAD_UP: [7, 0, 1].includes(state.hat), DPAD_RIGHT: [1, 2, 3].includes(state.hat),
            DPAD_DOWN: [3, 4, 5].includes(state.hat), DPAD_LEFT: [5, 6, 7].includes(state.hat),
            JCL_SR: false, JCL_SL: false, JCR_SR: false, JCR_SL: false
        };
        for (const [name, bit] of Object.entries(buttons)) packet[name] = !!(state.buttons & bit);
        return packet;
    }

    const api = {layouts, decode, toNxbt};
    if (typeof module !== "undefined" && module.exports) module.exports = api;
    else root.Lic2HID = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
