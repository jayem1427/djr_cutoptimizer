/* djr_cutcalculator: cutting model, exact force curve and feeds-and-speeds optimizer.
 *
 * One source shared by index.html, the Node tests and the Fusion add-in palette.
 * It is a classic script, not an ES module: browsers refuse <script type="module">
 * from file:// (and Fusion's palette loads from a file URL), so the page would break
 * when opened locally. In a browser it defines window.CutOpt; in Node, require() it.
 *
 * Units: mm, mm/tooth, m/min, rpm, N, N/mm², kW, degrees. Q is cm³/min.
 */
(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.CutOpt = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const RAD = Math.PI / 180;
  const DEG = 180 / Math.PI;
  /** Below this helix angle the force slope has no useful bound. */
  const STRAIGHT_FLUTE_DEG = 1;
  /** Reference feed per tooth used to evaluate geometry before scaling. */
  const FZ_REF = 0.05;

  const clamp = (x, lo, hi) => Math.min(hi, Math.max(lo, x));
  const isNum = x => typeof x === "number" && isFinite(x);
  const pos = x => isNum(x) && x > 0;

  /* ---------- chip geometry ---------- */

  /** Radial engagement ratio and engagement angle φ (rad), ae clamped to D. */
  function engagement(D, ae) {
    const aeR = clamp(ae / D, 1e-9, 1);
    return { aeR, phi: Math.acos(1 - 2 * aeR) };
  }
  /** hm / fz: exact side-milling average chip thickness per unit feed. */
  function hmPerFz(D, ae, kappaDeg = 90) {
    const { aeR, phi } = engagement(D, ae);
    return Math.sin(kappaDeg * RAD) * (2 * aeR) / phi;
  }
  /** hex / fz: maximum chip thickness per unit feed. */
  function hexPerFz(D, ae, kappaDeg = 90) {
    const { aeR, phi } = engagement(D, ae);
    return Math.sin(kappaDeg * RAD) * (aeR < 0.5 ? Math.sin(phi) : 1);
  }
  /** Specific cutting force kc (N/mm²) at average chip thickness hm (mm). */
  function kcAt(kc1, mc, rakeDeg, hm) {
    return kc1 * Math.pow(hm, -mc) * (1 - rakeDeg / 100);
  }
  /** Axial distance between flutes: smooth stepdowns are whole multiples of this. */
  function flutePitch(D, z, helixDeg) {
    if (!(helixDeg >= STRAIGHT_FLUTE_DEG)) return Infinity;
    return Math.PI * D / (z * Math.tan(helixDeg * RAD));
  }

  /* ---------- the cut ---------- */

  /**
   * Full model for one cut. p: { D, z, helix, ae, ap, fz, vc | n, kc1, mc, rake, kappa }.
   * Gives n, vc, vf, Q, phi, aeR, hm, hex, kc, Pc (kW), Mc (N·m), Fc (mean tangential, N).
   */
  function cutModel(p) {
    const rake = p.rake || 0, kappa = isNum(p.kappa) ? p.kappa : 90;
    const n = pos(p.n) ? p.n : 1000 * p.vc / (Math.PI * p.D);
    const vc = Math.PI * p.D * n / 1000;
    const vf = p.fz * n * p.z;
    const Q = p.ae * p.ap * vf / 1000;
    const { aeR, phi } = engagement(p.D, p.ae);
    const hm = Math.max(1e-4, p.fz * hmPerFz(p.D, p.ae, kappa));
    const hex = p.fz * hexPerFz(p.D, p.ae, kappa);
    const kc = kcAt(p.kc1, p.mc, rake, hm);
    const Pc = p.ae * p.ap * vf * kc / 60e6;
    const Mc = Pc * 30e3 / (Math.PI * n);
    const Fc = Pc * 60000 / vc;
    return { n, vc, vf, Q, aeR, phi, hm, hex, kc, Pc, Mc, Fc };
  }

  /* ---------- exact force curve ---------- */

  /**
   * Tangential force vs rotation for climb milling, integrated exactly along the axis.
   * D, ap, ae, fz in mm; helix in degrees; kc in N/mm². Returns N per sample,
   * sample i at i·stepDeg, one full revolution.
   */
  function forceCurve(D, z, helixDeg, ae, ap, fz, kc, stepDeg = 0.25) {
    const R = D / 2;
    const tb = Math.tan(Math.max(helixDeg, 0.5) * RAD);
    const Rt = R / tb;                                   // axial height per radian of lag
    const lag = ap / Rt;                                 // angular lag across the full depth
    const th0 = Math.PI - Math.acos(Math.max(-1, 1 - Math.min(ae, D) / R));
    const th1 = Math.PI;
    const TWO_PI = 2 * Math.PI;
    // base lies in [0, 4π); a flute point is engaged when th0 ≤ b − h/Rt ≤ th1, 0 ≤ h ≤ ap,
    // so b must lie in [th0, th1 + lag]. That fixes the unwrap range for any depth.
    const kMin = Math.floor((th0 - 2 * TWO_PI) / TWO_PI);
    const kMax = Math.ceil((th1 + lag) / TWO_PI);
    const N = Math.max(1, Math.round(360 / stepDeg));
    const step = 360 / N;
    const F = new Array(N);
    const scale = kc * fz * Rt;
    for (let i = 0; i < N; i++) {
      const a = i * step;
      let A = 0;
      for (let t = 0; t < z; t++) {
        const base = (a + 360 * t / z) * RAD;
        for (let k = kMin; k <= kMax; k++) {
          const b = base + TWO_PI * k;
          if (b < th0 || b - lag > th1) continue;
          const h0 = Math.max(0, (b - th1) * Rt), h1 = Math.min(ap, (b - th0) * Rt);
          if (h1 > h0) A += Math.cos(b - h1 / Rt) - Math.cos(b - h0 / Rt);
        }
      }
      F[i] = scale * A;
    }
    return F;
  }

  /** Peak, min, mean, ripple and steepest rise (N per degree, wrapping) of a force curve. */
  function forceStats(F, stepDeg) {
    const N = F.length, step = 360 / N;
    let peak = -Infinity, min = Infinity, sum = 0, slope = -Infinity, slopeAt = 0;
    for (let i = 0; i < N; i++) {
      const f = F[i];
      if (f > peak) peak = f;
      if (f < min) min = f;
      sum += f;
      const d = (F[(i + 1) % N] - f) / step;
      if (d > slope) { slope = d; slopeAt = i * step; }
    }
    const mean = sum / N;
    return { peak, min, mean, ripple: mean > 0 ? (peak - min) / mean : 0, maxSlope: Math.max(0, slope), slopeAt, step: stepDeg ?? step };
  }

  /** Force slope per degree converted to N/ms at n rpm: dF/dt = dF/dθ · 6n per second. */
  function slopePerMs(slopePerDeg, n) { return slopePerDeg * 6 * n / 1000; }

  /** Closed-form check of the steepest rise: kc·hex·R / tanβ, per degree. */
  function slopeClosedForm(D, helixDeg, kc, hex) {
    return kc * hex * (D / 2) / Math.tan(helixDeg * RAD) / DEG;
  }

  /* ---------- optimizer ---------- */

  const LIMIT_LABEL = {
    force: "cutting force", slope: "force slope", feed: "feed rate", power: "spindle power", torque: "spindle torque",
    hexMax: "max chip thickness", hmMin: "min chip thickness", vc: "cutting speed", rpm: "spindle speed"
  };

  function normTool(t) {
    return {
      D: +t.D, z: Math.max(1, Math.round(+t.z)), helix: +t.helix,
      kc1: +t.kc1, mc: isNum(+t.mc) ? +t.mc : 0.25, rake: +t.rake || 0,
      kappa: isNum(+t.kappa) && +t.kappa > 0 ? +t.kappa : 90,
      fluteLen: pos(+t.fluteLen) ? +t.fluteLen : null
    };
  }

  /** The spindle speed the optimizer uses: as fast as rpm and vc limits allow. */
  function chooseRpm(tool, L) {
    const cands = [];
    if (pos(L.nmax)) cands.push(L.nmax);
    if (pos(L.vcMax)) cands.push(L.vcMax * 1000 / (Math.PI * tool.D));
    if (!cands.length) return { error: "Set a max spindle speed (or a max cutting speed)." };
    const n = Math.min(...cands);
    const vc = Math.PI * tool.D * n / 1000;
    if (pos(L.vcMin) && vc < L.vcMin * (1 - 1e-9)) {
      return { error: `The fastest allowed spindle speed (${Math.round(n)} rpm) only reaches ${vc.toFixed(0)} m/min, below the ${L.vcMin} m/min minimum cutting speed. Use a larger tool or relax the limit.` };
    }
    return { n, vc };
  }

  /** Default depth tolerance (mm) when checking slope near a whole flute pitch. */
  const AP_TOL = 0.05;

  /**
   * Force slope that doesn't rely on exact flute-pitch cancellation.
   * At ap = m·pitch one flute's entry and another's exit coincide, so the computed
   * slope collapses to ~0, but 0.03 mm off it is back at full value. Runout and depth
   * error make that cancellation unreliable, so near a multiple of the pitch we also
   * take the slope at ap ± tol and use the worst.
   */
  function robustSlope(tool, ae, ap, fz, kc, stepDeg, slopeHere, tol) {
    const pitch = flutePitch(tool.D, tool.z, tool.helix);
    const t = isNum(tol) && tol >= 0 ? tol : AP_TOL;
    if (!isFinite(pitch) || t === 0) return slopeHere;
    const m = Math.round(ap / pitch);
    if (m < 1 || Math.abs(ap - m * pitch) > t) return slopeHere;
    let worst = slopeHere;
    for (const a of [ap - t, ap + t]) {
      if (a <= 0) continue;
      const s = forceStats(forceCurve(tool.D, tool.z, tool.helix, ae, a, fz, kc, stepDeg), stepDeg).maxSlope;
      if (s > worst) worst = s;
    }
    return worst;
  }

  /**
   * Best feed per tooth at one (ae, ap): the largest fz every limit allows.
   * Force, slope, power and torque scale exactly with fz^(1−mc), so one force curve at a
   * reference feed is enough.
   */
  function evaluate(tool, L, n, ae, ap, stepDeg) {
    const { D, z, helix, kc1, mc, rake, kappa } = tool;
    const e = 1 / (1 - mc);
    const hmK = hmPerFz(D, ae, kappa), hexK = hexPerFz(D, ae, kappa);
    const kc0 = kcAt(kc1, mc, rake, FZ_REF * hmK);
    const caps = [];
    let stats0 = null;
    if (pos(L.Fmax) || pos(L.slopeMax)) {
      stats0 = forceStats(forceCurve(D, z, helix, ae, ap, FZ_REF, kc0, stepDeg), stepDeg);
      if (pos(L.Fmax) && stats0.peak > 0) caps.push(["force", FZ_REF * Math.pow(L.Fmax / stats0.peak, e)]);
      if (pos(L.slopeMax)) {
        const slope0 = robustSlope(tool, ae, ap, FZ_REF, kc0, stepDeg, stats0.maxSlope, L.apTol);
        if (slope0 > 0) caps.push(["slope", FZ_REF * Math.pow(L.slopeMax / slope0, e)]);
      }
    }
    if (pos(L.vfmax)) caps.push(["feed", L.vfmax / (z * n)]);
    const Pc0 = ae * ap * FZ_REF * z * n * kc0 / 60e6, eta = pos(L.eta) ? L.eta : 1;
    if (pos(L.Pmax)) caps.push(["power", FZ_REF * Math.pow(L.Pmax * eta / Pc0, e)]);
    if (pos(L.Tmax)) {
      // Motor torque = cutting torque / eta. Cutting torque Mc = Pc·30e3/(π·n); it doesn't depend on n.
      const Mc0 = Pc0 * 30e3 / (Math.PI * n);
      caps.push(["torque", FZ_REF * Math.pow(L.Tmax * eta / Mc0, e)]);
    }
    if (pos(L.hexMax)) caps.push(["hexMax", L.hexMax / hexK]);
    if (!caps.length) return { ae, ap, feasible: false, bind: "none", fz: NaN, Q: 0 };
    let bind = caps[0][0], fz = caps[0][1];
    for (const [k, v] of caps) if (v < fz) { fz = v; bind = k; }
    const fzLow = pos(L.hmMin) ? L.hmMin / hmK : 0;
    if (!(fz >= fzLow)) return { ae, ap, feasible: false, bind, fz, fzLow, Q: 0 };
    return { ae, ap, feasible: true, bind, fz, fzLow, Q: ae * ap * fz * z * n / 1000 };
  }

  function linspace(a, b, k) {
    if (k <= 1 || a === b) return [a];
    return Array.from({ length: k }, (_, i) => a + (b - a) * i / (k - 1));
  }
  function logspace(a, b, k) {
    if (k <= 1 || a === b) return [a];
    const la = Math.log(a), lb = Math.log(b);
    return Array.from({ length: k }, (_, i) => Math.exp(la + (lb - la) * i / (k - 1)));
  }

  /** Full results for one chosen point, re-checked on a fine force curve. */
  function describe(tool, n, ae, ap, fz, stepDeg, apTol) {
    const m = cutModel({ ...tool, ae, ap, fz, n });
    const F = forceCurve(tool.D, tool.z, tool.helix, ae, ap, fz, m.kc, stepDeg);
    const s = forceStats(F, stepDeg);
    const robust = robustSlope(tool, ae, ap, fz, m.kc, stepDeg, s.maxSlope, apTol);
    return { ...m, ae, ap, fz, forces: F, peak: s.peak, minForce: s.min, meanForce: s.mean, ripple: s.ripple,
      maxSlope: s.maxSlope, robustSlope: robust, slopeMs: slopePerMs(robust, n) };
  }

  /**
   * Maximize removal rate Q over (n, fz, ae, ap).
   *
   * tool:   { D, z, helix, kc1, mc, rake, kappa, fluteLen }
   * limits: { nmax, vfmax, Fmax, slopeMax, Pmax (motor kW), Tmax (motor N·m), eta, hexMax, hmMin, vcMin, vcMax }
   * opts:   { aeLock, apLock, aeMin, aeMax, apMin, apMax, nAe, nAp, gridStep, refineStep, verifyStep }
   *
   * Returns { ok, reason?, n, vc, best, grid: { ae[], ap[], cells[i][j] }, pitch, smoothDepths, snapped }.
   */
  function optimize(toolIn, limits, opts = {}) {
    const tool = normTool(toolIn);
    const L = Object.assign({ hmMin: 0.005, eta: 1 }, limits);
    const fail = reason => ({ ok: false, reason });

    if (![tool.D, tool.kc1].every(pos) || !(tool.mc >= 0 && tool.mc < 1)) return fail("Tool diameter, kc1 and mc must be set.");
    const straight = !(tool.helix >= STRAIGHT_FLUTE_DEG);
    if (straight && pos(L.slopeMax)) {
      return fail("Force slope is unbounded for a straight-flute tool (helix near 0°), so it can't be limited. Clear the slope limit or set the tool's helix angle.");
    }
    if (![L.Fmax, L.slopeMax, L.vfmax, L.Pmax, L.Tmax, L.hexMax].some(pos)) {
      return fail("Set at least one limit on force, force slope, feed rate, power, torque or chip thickness; otherwise the feed is unbounded.");
    }
    const rpm = chooseRpm(tool, L);
    if (rpm.error) return fail(rpm.error);
    const { n, vc } = rpm;

    const D = tool.D;
    const gridStep = opts.gridStep || 0.25, refineStep = opts.refineStep || 0.1, verifyStep = opts.verifyStep || 0.05;
    const aeMin = pos(opts.aeMin) ? opts.aeMin : 0.02 * D, aeMax = Math.min(pos(opts.aeMax) ? opts.aeMax : D, D);
    const apMax = pos(opts.apMax) ? opts.apMax : (tool.fluteLen || 3 * D);
    const apMin = Math.min(pos(opts.apMin) ? opts.apMin : 0.1 * D, apMax);
    const aeLock = pos(opts.aeLock) ? Math.min(opts.aeLock, D) : null;
    const apLock = pos(opts.apLock) ? opts.apLock : null;

    const aes = aeLock ? [aeLock] : logspace(aeMin, aeMax, opts.nAe || 30);
    const aps = apLock ? [apLock] : linspace(apMin, apMax, opts.nAp || 30);

    // 1. coarse grid
    const cells = aes.map(ae => aps.map(ap => evaluate(tool, L, n, ae, ap, gridStep)));
    let bi = -1, bj = -1, bestQ = 0;
    cells.forEach((row, i) => row.forEach((c, j) => { if (c.feasible && c.Q > bestQ) { bestQ = c.Q; bi = i; bj = j; } }));

    if (bi < 0) {
      const tally = {};
      cells.forEach(row => row.forEach(c => { tally[c.bind] = (tally[c.bind] || 0) + 1; }));
      const worst = Object.keys(tally).sort((a, b) => tally[b] - tally[a])[0];
      const lim = LIMIT_LABEL[worst] || worst;
      return Object.assign(fail(
        `No feasible cut: the ${lim} limit forces chips thinner than the ${L.hmMin} mm minimum chip thickness at every stepover and depth tried. ` +
        `Raise the ${lim} limit, lower the minimum chip thickness, or use a different tool.`),
        { n, vc, grid: { ae: aes, ap: aps, cells } });
    }

    // 2. refine around the best grid point
    const around = (arr, i, lock) => lock ? [lock] : [arr[Math.max(0, i - 1)], arr[Math.min(arr.length - 1, i + 1)]];
    let best = cells[bi][bj];
    let [aeLo, aeHi] = aeLock ? [aeLock, aeLock] : around(aes, bi);
    let [apLo, apHi] = apLock ? [apLock, apLock] : around(aps, bj);
    for (let pass = 0; pass < 2; pass++) {
      const ra = aeLock ? [aeLock] : logspace(aeLo, aeHi, 9);
      const rp = apLock ? [apLock] : linspace(apLo, apHi, 9);
      let ci = 0, cj = 0;
      ra.forEach((ae, i) => rp.forEach((ap, j) => {
        const c = evaluate(tool, L, n, ae, ap, refineStep);
        if (c.feasible && c.Q > best.Q * (1 + 1e-12)) { best = c; ci = i; cj = j; }
      }));
      if (!aeLock) [aeLo, aeHi] = around(ra, ci);
      if (!apLock) [apLo, apHi] = around(rp, cj);
    }

    // 3. smooth stepdowns: whole multiples of the axial flute pitch
    const pitch = flutePitch(D, tool.z, tool.helix);
    const smoothDepths = [];
    if (isFinite(pitch)) for (let m = 1; m * pitch <= apMax * (1 + 1e-9) && m < 50; m++) smoothDepths.push(m * pitch);
    let snapped = null;
    if (!apLock && smoothDepths.length) {
      const verified = evaluate(tool, L, n, best.ae, best.ap, verifyStep);
      const target = verified.feasible ? verified.Q : best.Q;
      // Force is smooth just *below* m·pitch and jumps to the full entry slope the moment
      // the depth passes it, so aim a depth tolerance under each multiple.
      const tol = isNum(L.apTol) && L.apTol >= 0 ? L.apTol : AP_TOL;
      for (const exact of smoothDepths) {
        const d = exact - tol * 1.01;
        if (d <= 0 || d < apMin * (1 - 1e-9)) continue;
        // best stepover at this depth: scan, then refine
        let cand = null;
        const scan = aeLock ? [aeLock] : logspace(aeMin, aeMax, 30);
        let si = 0;
        scan.forEach((ae, i) => { const c = evaluate(tool, L, n, ae, d, refineStep); if (c.feasible && (!cand || c.Q > cand.Q)) { cand = c; si = i; } });
        if (!cand) continue;
        if (!aeLock) {
          const fine = logspace(scan[Math.max(0, si - 1)], scan[Math.min(scan.length - 1, si + 1)], 15);
          fine.forEach(ae => { const c = evaluate(tool, L, n, ae, d, refineStep); if (c.feasible && c.Q > cand.Q) cand = c; });
        }
        const v = evaluate(tool, L, n, cand.ae, d, verifyStep);
        if (v.feasible && v.Q >= 0.99 * target && (!snapped || v.Q > snapped.Q)) snapped = v;
      }
      if (snapped) best = snapped;
    }

    // 4. final fz from a fine force curve, so every limit holds at 0.05°
    const fin = evaluate(tool, L, n, best.ae, best.ap, verifyStep);
    if (!fin.feasible) return fail("The best point failed its fine re-check. Try a looser limit or a finer grid.");
    const fz = fin.fz * (1 - 1e-9);
    const out = describe(tool, n, fin.ae, fin.ap, fz, verifyStep, L.apTol);
    out.bind = fin.bind;
    out.bindLabel = LIMIT_LABEL[fin.bind] || fin.bind;

    return {
      ok: true, n, vc, best: out,
      grid: { ae: aes, ap: aps, cells },
      pitch, smoothDepths, snapped: !!snapped
    };
  }

  /** Check a cut against limits. Returns a list of { limit, value, max } that fail. */
  function checkLimits(r, L, n) {
    const bad = [];
    const over = (limit, value, max) => { if (pos(max) && value > max * (1 + 1e-6)) bad.push({ limit, value, max }); };
    over("force", r.peak, L.Fmax);
    over("slope", isNum(r.robustSlope) ? r.robustSlope : r.maxSlope, L.slopeMax);
    over("feed", r.vf, L.vfmax);
    over("power", r.Pc / (pos(L.eta) ? L.eta : 1), L.Pmax);
    over("torque", r.Mc / (pos(L.eta) ? L.eta : 1), L.Tmax);
    over("hexMax", r.hex, L.hexMax);
    over("rpm", n, L.nmax);
    over("vc", r.vc, L.vcMax);
    if (pos(L.hmMin) && r.hm < L.hmMin * (1 - 1e-6)) bad.push({ limit: "hmMin", value: r.hm, max: L.hmMin });
    if (pos(L.vcMin) && r.vc < L.vcMin * (1 - 1e-6)) bad.push({ limit: "vcMin", value: r.vc, max: L.vcMin });
    return bad;
  }

  return {
    VERSION: "1.1.0",
    STRAIGHT_FLUTE_DEG, LIMIT_LABEL,
    engagement, hmPerFz, hexPerFz, kcAt, flutePitch,
    AP_TOL, cutModel, forceCurve, forceStats, robustSlope, slopePerMs, slopeClosedForm,
    describe, evaluate, optimize, checkLimits, normTool
  };
});
