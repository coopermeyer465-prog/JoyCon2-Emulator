const assert = require('node:assert/strict');
const {MouseInput} = require('../web/static/js/mouse-input.js');
const mouse = new MouseInput();
assert.equal(mouse.mode, 'off');
assert.equal(mouse.stick(0), null);
for (const target of ['left', 'right']) {
    mouse.start(target); mouse.move(10, -5, 0);
    assert.deepEqual(mouse.stick(30), {target, x: 40, y: 20});
    assert.deepEqual(mouse.stick(90), {target, x: 0, y: 0});
    mouse.move(1000, -1000, 100);
    assert.deepEqual(mouse.stick(101), {target, x: 100, y: 100});
    assert.equal(mouse.mouse(), null);
    mouse.stop(); assert.equal(mouse.stick(101), null);
}
mouse.start('native'); mouse.move(10, -3, 0);
assert.deepEqual(mouse.mouse(), {dx: 80, dy: -24});
assert.equal(mouse.mouse(), null);
mouse.move(1e9, -1e9, 1);
assert.deepEqual(mouse.mouse(), {dx: 2047, dy: -2047});
mouse.move(NaN, 1, 2); assert.equal(mouse.mouse(), null);
mouse.gain = 0.25; mouse.move(0.1, 0, 3); assert.equal(mouse.mouse(), null);
mouse.move(0.4, 0, 4); assert.deepEqual(mouse.mouse(), {dx: 1, dy: 0});
mouse.move(8, 8, 5); mouse.stop(); assert.equal(mouse.mouse(), null);
assert.throws(() => mouse.start('both'));
assert.equal(mouse.click(0), false);
for (const target of ['left', 'right', 'native']) {
    mouse.start(target);
    assert.equal(mouse.pressingA(0), false);
    assert.equal(mouse.click(0), true);
    assert.equal(mouse.pressingA(79), true);
    assert.equal(mouse.click(40), false);
    assert.equal(mouse.pressingA(80), false);
    assert.equal(mouse.click(100), true);
    mouse.stop(); assert.equal(mouse.pressingA(101), false);
    assert.equal(mouse.click(Infinity), false);
}
console.log('Mouse mapping tests passed');
