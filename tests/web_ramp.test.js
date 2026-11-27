// Tests web/ramp.js (helical ramp planning). Run with: node --test tests/web_ramp.test.js
// Numbers come from the R2 Rough - 3D Adaptive #12 case: 9.525 mm 3-flute, 6061,
// ramp 275 mm/min at 16,000 rpm, 1.2°, helicalRampDiameter 9.05 mm, the G-code helix ~6 mm.
const test = require("node:test");
const assert = require("node:assert/strict");
const R = require("../web/ramp.js");
const C = require("../web/optimizer.js");

const near = (got, want, tol, label) =>
  assert.ok(Math.abs(got - want) <= tol, `${label}: got ${got}, want ${want} ± ${tol}`);

test("helix wall multiplier", () => {
  near(1 / R.helixK(6, 9.525), 2.5875, 1e-3, "6 mm helix");
  near(1 / R.helixK(9.525, 9.525), 2, 1e-9, "helix as wide as the tool");
  assert.ok(Number.isNaN(R.helixK(0, 9.525)));
});

test("pitch and descent", () => {
  near(R.pitch(6, 1.5), 0.4935, 1e-3, "pitch");
  near(R.descent(275, 1.5), 7.2, 0.01, "R2 ramp descends ~7 mm/min");
  near(R.descent(900, 3), 47.17, 0.01, "proposed ramp");
  near(R.rampMinutes(19.5, R.descent(275, 1.5)), 2.71, 0.01, "minutes");
  assert.ok(Number.isNaN(R.descent(0, 3)));
});

test("R2's current ramp rubs at the wall", () => {
  const k = R.helixK(6, 9.525), fz = R.edgeFz(275, 16000, 3, k);
  near(fz, 0.0148, 2e-4, "edge feed per tooth");
  // as a full-width slot the average chip is 2/π of fz
  const c = C.describe(C.normTool({ D: 9.525, z: 3, helix: 45, kc1: 295, mc: 0.25, rake: 0, kappa: 90 }),
    16000, 9.525, R.pitch(6, 1.5), fz, 0.1);
  near(c.hm, fz * 2 / Math.PI, 1e-3, "slot average chip");
});

test("diameters: the small helix Fusion may shrink to is checked too", () => {
  assert.deepEqual(R.diameters(9.05, 4.76), [9.05, 4.76]);
  assert.deepEqual(R.diameters(9.05, null), [9.05]);
  assert.deepEqual(R.diameters(9.05, 9.05), [9.05]);
  assert.deepEqual(R.diameters(9.05, 12), [9.05]);
});

test("angles to try only go steeper, up to the max", () => {
  assert.deepEqual(R.anglesToTry(1.2, null), [1.2]);
  assert.deepEqual(R.anglesToTry(1.2, 1), [1.2]);
  assert.deepEqual(R.anglesToTry(1.2, 2), [1.2, 1.25, 1.5, 1.75, 2]);
  assert.deepEqual(R.anglesToTry(2, 3), [2, 2.25, 2.5, 2.75, 3]);
  assert.equal(R.anglesToTry(2, 90).at(-1), R.ANGLE_MAX);
  assert.deepEqual(R.anglesToTry(0, 3), []);
});

test("chooseAngle picks the fastest descent, keeps the shallower on a tie", () => {
  // feed falls slower than tan rises: steepest wins
  let best = R.chooseAngle(1.2, 3, a => ({ vf: 900 / Math.sqrt(a) }));
  assert.equal(best.angle, 3);
  // feed falls exactly as tan rises: descent flat, so the current angle stays
  best = R.chooseAngle(2, 3, a => ({ vf: 1000 / Math.tan(a * Math.PI / 180) }));
  assert.equal(best.angle, 2);
  // infeasible above 2.5°
  best = R.chooseAngle(2, 3, a => a > 2.5 ? null : { vf: 900 });
  assert.equal(best.angle, 2.5);
  assert.equal(R.chooseAngle(2, 3, () => null), null);
});

test("feed reached raises the min chip at the programmed feed", () => {
  near(R.minChipAtFullFeed(0.005, 50), 0.01, 1e-12, "50 %");
  assert.equal(R.minChipAtFullFeed(0.005, ""), 0.005);
  assert.equal(R.minChipAtFullFeed(0.005, 100), 0.005);
  assert.equal(R.minChipAtFullFeed(0.005, 150), 0.005);
  assert.equal(R.minChipAtFullFeed(undefined, 50), undefined);
});
