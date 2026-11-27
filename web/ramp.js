/* djr_cutoptimizer: helical ramp planning and machine-feed helpers for the panel.
 *
 * Owned by this repo (not synced from cutcalculator). A classic script like optimizer.js:
 * in the palette it defines window.RampPlan; in Node, require() it.
 *
 * Geometry: the tool centre follows a helix of diameter dia. The hole it cuts is dia + D, so
 * the cutting edge on the wall travels (dia + D) / dia times faster than the programmed
 * (centre) feed. On a small helix that multiplier is large, so a slow-looking ramp feed can
 * still overload the edge, and a fast-looking one can still rub.
 *
 * Units: mm, mm/min, degrees, rpm.
 */
(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.RampPlan = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const RAD = Math.PI / 180;
  const ANGLE_STEP = 0.25;            // degrees between the ramp angles tried
  const ANGLE_MAX = 15;               // never suggest a steeper helix than this

  const pos = v => typeof v === "number" && isFinite(v) && v > 0;

  /* Centre feed ÷ edge feed on a helix of centre diameter dia with a tool of diameter D. */
  function helixK(dia, D) { return pos(dia) && pos(D) ? dia / (dia + D) : NaN; }

  /* Depth one turn of the helix descends: the slot the tool cuts on each lap. */
  function pitch(dia, angle) { return Math.PI * dia * Math.tan(angle * RAD); }

  /* How fast the ramp goes down (mm/min) at a centre feed vf and ramp angle. */
  function descent(vf, angle) { return pos(vf) && pos(angle) ? vf * Math.tan(angle * RAD) : NaN; }

  /* The helix diameters to check. Fusion uses helicalRampDiameter when there's room and
     shrinks the helix down to minimumRampDiameter when there isn't, so both are checked and
     the slower answer wins: the small helix has the biggest wall multiplier. */
  function diameters(dia, minDia) {
    const out = [];
    if (pos(dia)) out.push(dia);
    if (pos(minDia) && (!out.length || minDia < out[0] - 1e-9)) out.push(minDia);
    return out;
  }

  /* Ramp angles to try: from the operation's angle up to maxAngle (inclusive), in
     ANGLE_STEP steps. Only ever steeper than now: a shallower helix is never faster to descend
     at the same chip, and the operation's angle may be what the tool maker allows. */
  function anglesToTry(current, maxAngle) {
    if (!pos(current)) return [];
    const top = pos(maxAngle) ? Math.min(maxAngle, ANGLE_MAX) : current;
    const out = [current];
    if (top <= current + 1e-9) return out;
    let a = Math.ceil((current + 1e-9) / ANGLE_STEP) * ANGLE_STEP;
    for (; a < top - 1e-9; a += ANGLE_STEP) out.push(Math.round(a * 1000) / 1000);
    out.push(Math.round(top * 1000) / 1000);
    return out;
  }

  /* Pick the ramp angle that descends fastest.
     evalAngle(angle) -> { vf } (centre feed, mm/min) or null when that angle isn't feasible.
     Ties within 1 % keep the shallower angle (easier on the tool for the same time).
     Returns { angle, vf, descent, result } or null when no angle works. */
  function chooseAngle(current, maxAngle, evalAngle) {
    let best = null;
    for (const a of anglesToTry(current, maxAngle)) {
      const r = evalAngle(a);
      if (!r || !pos(r.vf)) continue;
      const d = descent(r.vf, a);
      if (!best || d > best.descent * 1.01) best = { angle: a, vf: r.vf, descent: d, result: r };
    }
    return best;
  }

  /* Machines rarely reach the programmed feed on adaptive paths: acceleration and jerk limits
     slow every arc and direction change. If the machine only reaches pct % of the feed, the
     chip there is pct % as thick, so the min chip must hold at that feed. Returns the min chip
     to require at the programmed feed. pct blank, 0 or ≥ 100 means the full feed is reached. */
  function minChipAtFullFeed(hmMin, pct) {
    if (!pos(hmMin)) return hmMin;
    return pos(pct) && pct < 100 ? hmMin * 100 / pct : hmMin;
  }

  /* Edge feed per tooth of the current ramp: centre feed vf at rpm n, z flutes, helix k. */
  function edgeFz(vf, n, z, k) { return pos(vf) && pos(n) && pos(z) && pos(k) ? vf / k / (n * z) : NaN; }

  /* Minutes to ramp down depth mm at a given descent rate. */
  function rampMinutes(depth, descentRate) { return pos(depth) && pos(descentRate) ? depth / descentRate : NaN; }

  return { ANGLE_STEP, ANGLE_MAX, helixK, pitch, descent, diameters, anglesToTry, chooseAngle,
    minChipAtFullFeed, edgeFz, rampMinutes };
});
