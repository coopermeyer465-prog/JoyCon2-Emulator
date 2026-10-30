(function(root) {
    "use strict";
    class MouseInput {
        constructor() { this.mode = "off"; this.gain = 1; this.stop(); }
        stop() { this.active = false; this.x = this.y = this.dx = this.dy = 0; this.last = -Infinity; this.clickUntil = 0; }
        start(mode) {
            if (!["native", "left", "right"].includes(mode)) throw new Error("Invalid mouse target");
            this.stop(); this.mode = mode; this.active = true;
        }
        move(dx, dy, now) {
            if (!this.active || ![dx, dy, now, this.gain].every(Number.isFinite)) return;
            const clamp = (v, max) => Math.max(-max, Math.min(max, v));
            dx = clamp(dx, 1000); dy = clamp(dy, 1000);
            const gain = Math.max(0.25, Math.min(4, this.gain));
            this.x = clamp(dx * gain * 4, 100);
            this.y = clamp(-dy * gain * 4, 100);
            this.dx = clamp(this.dx + dx * gain * 8, 2047);
            this.dy = clamp(this.dy + dy * gain * 8, 2047);
            this.last = now;
        }
        stick(now) {
            if (!this.active || !["left", "right"].includes(this.mode)) return null;
            return {target: this.mode, x: now - this.last < 90 ? this.x : 0,
                y: now - this.last < 90 ? this.y : 0};
        }
        mouse() {
            if (!this.active || this.mode !== "native") return null;
            const dx = Math.trunc(this.dx), dy = Math.trunc(this.dy);
            this.dx -= dx; this.dy -= dy;
            return dx || dy ? {dx, dy} : null;
        }
        click(now) {
            if (!this.active || !Number.isFinite(now) || now < this.clickUntil) return false;
            this.clickUntil = now + 80;
            return true;
        }
        pressingClick(now) { return this.active && now < this.clickUntil; }
    }
    root.NxbtMouse = {MouseInput};
    if (typeof module !== "undefined") module.exports = root.NxbtMouse;
})(typeof window === "undefined" ? globalThis : window);
