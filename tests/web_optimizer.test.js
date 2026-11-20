// Tests the bundled copy of the calculator's optimizer. Run with: node --test tests/
// Reference numbers come from HANDOFF §3 (Sandvik CoroPlus check cut and the 3/8" HSM cut).
const test = require("node:test");
const assert = require("node:assert/strict");
const C = require("../web/optimizer.js");

const near = (got, want, tol, label) => {
  const err = Math.abs(got - want) / Math.abs(want);
  assert.ok(err <= tol, `${label}: got ${got}, want ${want} (${(err * 100).toFixed(2)}% off, limit ${tol * 100}%)`);
};

const MAT = { kc1: 295, mc: 0.25, rake: 0, kappa: 90 };
const CASES = {
  sandvik: {
    p: { ...MAT, D: 6, z: 4, helix: 35, ae: 1.67, ap: 15, fz: 0.0654, vc: 452.39 },
    want: { n: 24000, vf: 6278, Q: 157.3, hm: 0.0328, hex: 0.0586, kc: 693, Pc: 1.82, peak: 271.9, slope: 3.04, pitch: 6.73 }
  },
  hsm: {
    p: { ...MAT, D: 9.525, z: 3, helix: 45, ae: 0.5, ap: 10, fz: 0.06, vc: 612 },
    want: { n: 20452, vf: 3681, Q: 18.4, hm: 0.0136, hex: 0.0268, kc: 863, Pc: 0.265, peak: 26.5, slope: 1.92, pitch: 9.97 }
  }
};

for (const [name, { p, want }] of Object.entries(CASES)) {
  test(`reference case: ${name}`, () => {
    const m = C.cutModel(p);
    near(m.n, want.n, 0.005, "n");
    near(m.vf, want.vf, 0.005, "vf");
    near(m.Q, want.Q, 0.005, "Q");
    near(m.hm, want.hm, 0.005, "hm");
    near(m.hex, want.hex, 0.005, "hex");
    near(m.kc, want.kc, 0.005, "kc");
    near(m.Pc, want.Pc, 0.005, "Pc");
    near(C.flutePitch(p.D, p.z, p.helix), want.pitch, 0.005, "flute pitch");
    const s = C.forceStats(C.forceCurve(p.D, p.z, p.helix, p.ae, p.ap, p.fz, m.kc, 0.05), 0.05);
    near(s.peak, want.peak, 0.005, "peak force");
    near(s.maxSlope, want.slope, 0.01, "max slope");
    near(C.slopeClosedForm(p.D, p.helix, m.kc, m.hex), want.slope, 0.01, "closed-form slope");
  });
}

test("Sandvik torque matches CoroPlus (0.722 N·m)", () => {
  near(C.cutModel(CASES.sandvik.p).Mc, 0.722, 0.005, "Mc");
});

test("force curve mean equals the model's mean tangential force", () => {
  for (const { p } of Object.values(CASES)) {
    const m = C.cutModel(p);
    const s = C.forceStats(C.forceCurve(p.D, p.z, p.helix, p.ae, p.ap, p.fz, m.kc, 0.1), 0.1);
    near(s.mean, m.Fc, 0.01, "mean force");
  }
});

test("deep cuts (ap·tanβ/R > 2π) still integrate the whole flute", () => {
  const p = CASES.hsm.p, m = C.cutModel(p);
  // 60 mm deep with a 45° helix wraps the flute ~2 turns
  const ap = 60;
  const s = C.forceStats(C.forceCurve(p.D, p.z, p.helix, p.ae, ap, p.fz, m.kc, 0.1), 0.1);
  const mean = C.cutModel({ ...p, ap }).Fc;
  near(s.mean, mean, 0.01, "mean force at 60 mm");
});

test("slope reported in N/ms", () => {
  assert.equal(C.slopePerMs(2, 24000), 2 * 6 * 24000 / 1000);
});

const TOOL38 = { ...MAT, D: 9.525, z: 3, helix: 45, fluteLen: 25.4 };

test("optimizer: Fmax 30 N, slope 2.5 N/° on the 3/8\" tool at 24,000 rpm", () => {
  const L = { nmax: 24000, Fmax: 30, slopeMax: 2.5 };
  const r = C.optimize(TOOL38, L);
  assert.ok(r.ok, r.reason);
  assert.equal(Math.round(r.n), 24000);
  const b = r.best;
  // every limit holds on an independent 0.05° re-check
  const m = C.cutModel({ ...TOOL38, ae: b.ae, ap: b.ap, fz: b.fz, n: r.n });
  const s = C.forceStats(C.forceCurve(TOOL38.D, TOOL38.z, TOOL38.helix, b.ae, b.ap, b.fz, m.kc, 0.05), 0.05);
  assert.ok(s.peak <= 30 * (1 + 1e-6), `peak ${s.peak}`);
  assert.ok(s.maxSlope <= 2.5 * (1 + 1e-6), `slope ${s.maxSlope}`);
  assert.ok(m.hm >= 0.005, `hm ${m.hm}`);
  assert.deepEqual(C.checkLimits({ ...m, peak: s.peak, maxSlope: s.maxSlope }, L, r.n), []);
  // at least as good as the HSM reference cut run at the same rpm
  const ref = C.cutModel({ ...CASES.hsm.p, n: 24000 });
  assert.ok(b.Q >= ref.Q, `optimizer Q ${b.Q} < reference ${ref.Q}`);
});

test("optimizer respects locks and the feed-rate cap", () => {
  const r = C.optimize(TOOL38, { nmax: 24000, Fmax: 30, slopeMax: 2.5, vfmax: 3000 }, { apLock: 12 });
  assert.ok(r.ok, r.reason);
  assert.equal(r.best.ap, 12);
  assert.ok(r.best.vf <= 3000 * (1 + 1e-6), `vf ${r.best.vf}`);
  const r2 = C.optimize(TOOL38, { nmax: 24000, Fmax: 30 }, { aeLock: 1 });
  assert.ok(r2.ok, r2.reason);
  assert.equal(r2.best.ae, 1);
});

test("optimizer respects power and chip limits", () => {
  const L = { nmax: 24000, Pmax: 0.5, eta: 0.85, hexMax: 0.05 };
  const r = C.optimize(TOOL38, L);
  assert.ok(r.ok, r.reason);
  assert.ok(r.best.Pc / 0.85 <= 0.5 * (1 + 1e-6), `power ${r.best.Pc / 0.85}`);
  assert.ok(r.best.hex <= 0.05 * (1 + 1e-6));
});

test("an unreachable slope limit gives a clear message, not NaN", () => {
  const r = C.optimize(TOOL38, { nmax: 24000, Fmax: 30, slopeMax: 0.001 });
  assert.equal(r.ok, false);
  assert.match(r.reason, /No feasible cut/);
  assert.match(r.reason, /force slope/);
  assert.doesNotMatch(r.reason, /NaN/);
});

test("straight flute refuses a slope limit", () => {
  const r = C.optimize({ ...TOOL38, helix: 0 }, { nmax: 24000, slopeMax: 2 });
  assert.equal(r.ok, false);
  assert.match(r.reason, /unbounded/);
});

test("no limits at all is refused", () => {
  const r = C.optimize(TOOL38, { nmax: 24000 });
  assert.equal(r.ok, false);
});

test("minimum cutting speed is checked", () => {
  const r = C.optimize(TOOL38, { nmax: 2000, vcMin: 200, Fmax: 30 });
  assert.equal(r.ok, false);
  assert.match(r.reason, /minimum cutting speed/);
});

test("smooth stepdowns are multiples of the flute pitch", () => {
  const r = C.optimize(TOOL38, { nmax: 24000, Fmax: 30, slopeMax: 2.5 });
  assert.ok(r.smoothDepths.length >= 2);
  near(r.smoothDepths[1], 2 * r.pitch, 1e-9, "2× pitch");
});

test("slope limit isn't beaten by sitting exactly on a flute pitch", () => {
  const L = { nmax: 24000, Fmax: 30, slopeMax: 2.5 };
  const r = C.optimize(TOOL38, L);
  assert.ok(r.ok, r.reason);
  const b = r.best;
  // the cut must still hold the slope limit 0.03 mm deeper or shallower
  for (const ap of [b.ap - 0.03, b.ap + 0.03]) {
    const m = C.cutModel({ ...TOOL38, ae: b.ae, ap, fz: b.fz, n: r.n });
    const s = C.forceStats(C.forceCurve(TOOL38.D, TOOL38.z, TOOL38.helix, b.ae, ap, b.fz, m.kc, 0.05), 0.05);
    assert.ok(s.maxSlope <= 2.5 * 1.02, `slope ${s.maxSlope} at ap ${ap}`);
  }
});
