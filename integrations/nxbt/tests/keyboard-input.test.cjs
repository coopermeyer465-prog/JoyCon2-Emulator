const test = require('node:test');
const assert = require('node:assert/strict');
const {KEYMAP, setControl} = require('../web/static/js/keyboard-input.js');

test('every keyboard action presses and releases the correct packet field', () => {
    for (const control of Object.values(KEYMAP)) {
        const packet = {L_STICK: {PRESSED: false}, R_STICK: {PRESSED: false}};
        const stick = control.startsWith('LS_') ? packet.L_STICK : packet.R_STICK;
        const nested = /^(LS|RS)_/.test(control);
        const key = control.endsWith('_PRESS') ? 'PRESSED' : control;
        const target = nested ? stick : packet;
        setControl(packet, control, true);
        assert.equal(target[key], true, control);
        setControl(packet, control, false);
        assert.equal(target[key], false, control);
        if (nested) assert.equal(Object.hasOwn(packet, control), false, control);
    }
});

test('R/ZR match their displayed keys and extra right-half buttons are reachable', () => {
    assert.equal(KEYMAP[56], 'R');
    assert.equal(KEYMAP[57], 'ZR');
    assert.equal(KEYMAP[48], 'C');
    assert.equal(KEYMAP[189], 'JCR_SL');
    assert.equal(KEYMAP[187], 'JCR_SR');
    assert.equal(KEYMAP[84], 'LS_PRESS');
    assert.equal(KEYMAP[89], 'RS_PRESS');
});
