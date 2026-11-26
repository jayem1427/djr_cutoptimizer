# Changelog

## v0.6.0 — 2026-11-26

**Tool presets.** A new *Tool preset* section under Results saves the optimized cut as a preset on the operation's tool: spindle speed, cutting feed, ramp spindle speed and ramp feed, stepover and stepdown. New operations with that tool can start from it. The name fills in from material and pass (for example "djr · Aluminium (wrought) · Rough") until you type your own, and saving under an existing name updates that preset. *Use it on this operation* (on by default) assigns it. *Also add it to my tool library* adds the same preset to that tool in your local and cloud tool libraries. The operation card now shows which preset an operation uses.

**Parameter names verified against real Fusion data.** The `djr_dump_cam_params` output from a real document (Fusion 2706) is now in `docs/cam_params`, and a test runs on it. Several guesses were wrong:
- **Finish passes couldn't set stock to leave.** The parameters are `stockToLeave` (radial), `verticalStockToLeave` (axial) and `useStockToLeave`, not `radialStockToLeave`/`axialStockToLeave`. Wall and floor finish Apply now writes them.
- **Feeds written as expressions read 10× too high.** Fusion stores feeds in mm/min, not cm/min. This hit ramp and plunge feeds like `tool_feedPlunge`.
- **Feeds written as `900mmpm` read 10× too high.** That unit wasn't recognised. `inpm` is now recognised too, and so are numbers with a trailing point (`16000.`, `62.in/min`).
- **The ramp diameter wasn't found.** It's `helicalRampDiameter`. The ramp angle is stored in degrees, not radians. The helix ramp now uses the operation's real angle and diameter instead of assuming 2° and Ø<sub>tool</sub>.
- **Single-pass 2D contours** reported their switched-off "multiple stepovers" value as the stepover, and 0 as the stepdown. Fields Fusion has switched off are now ignored, so the panel asks for the engagement or takes it from the roughing.

## v0.5.2 — 2026-11-25

**Fixed: "Optimal Load … should not exceed 99% of the tool diameter."** With *Keep stepover* off, the optimizer could pick a stepover up to the full tool diameter. On an adaptive, Fusion refuses to generate when the optimal load plus the load deviation is over 99% of the diameter. The panel now reads the operation's load deviation and never suggests more than that allows: 0.99·D − deviation, or 0.99·D ÷ (1 + ratio) when the deviation is written as a fraction of the optimal load. If the deviation can't be read, it assumes 20% of the diameter. Apply also refuses to write an optimal load over the cap, so a stale panel can't cause it either.

If an operation already shows the error, use **Revert** (in the same Fusion session), or reselect it and Apply again.

**Max stepover.** New limit under More limits, 40% of the tool diameter by default. The optimizer used to search all the way to a full-width cut, and with generous force and slope limits it picked one, which isn't how anyone runs an adaptive. It doesn't apply to a stepover you keep, or to slots.

**Helix ramp feed.** Adaptives and pockets enter with a helical ramp at their own ramp feed and ramp spindle speed, which usually come from the tool library and are often far too slow. The panel now works out a ramp feed inside the same limits and Apply writes it, with the ramp spindle speed set to the cutting rpm. Each turn of the helix descends π·Ø<sub>helix</sub>·tan(angle), and the tool cuts full width, so the ramp is modelled as a slot that deep. The feed is the tool centre's, so it's scaled by Ø<sub>helix</sub> ÷ (Ø<sub>helix</sub> + Ø<sub>tool</sub>) because the outer wall moves faster, and it's never above the cutting feed. Results shows it as *Helix ramp feed*. If the operation doesn't give the ramp angle or diameter, 2° and a helix as wide as the tool are assumed, and the panel says so. Profile and zig-zag ramps are left alone.

**Apply greys out once it's done.** After a successful Apply the panel reads the operations back, and Apply stays disabled (grey, not faded blue) while Fusion already holds exactly what it would write. Change a limit, the pass or the selection and it lights up again. Revert stays available.

**Spindle defaults** now match a 1.5 kW, 24,000 rpm constant-torque spindle (Jianken JGD-80/1.5R24): 1.5 kW, 0.6 N·m, efficiency 0.8. The old 0.89 N·m was the torque of a 2.2 kW spindle. Saved working limits and profiles keep their own values, so check yours under More limits.

## v0.5.1 — 2026-11-25

**Fixed: panel half light, half dark (#6).** On some systems, after Apply the lower part of the panel (Results, the force graph, Revert) lost its dark background, leaving light text on Fusion's light gray. Every part of the panel now paints its own background, and the panel repaints itself after Apply, Revert, a selection change, and when it's shown, focused or resized.

**Fixed: version label.** The panel footer said v0.4.1. It now shows the add-in's version, and the release check fails if they disagree.

**Spindle power and torque in Results.** The panel already calculated cutting power and torque but never showed them. Results now has *Spindle power* (at the motor: net ÷ efficiency, kW) and *Spindle torque* (N·m) for both the current and optimized cut. With *Limit power* on, a current cut over your spindle power gets ⚠.

**Spindle torque limit.** New *Max spindle torque* field under More limits, defaulting to 0.89 N·m, the LemonTart spindle's rating. The optimizer never suggests a cut that needs more motor torque (cutting torque ÷ efficiency) than that, and a current cut over it gets ⚠. VFD spindles have constant torque up to their rated speed, so this is the real ceiling whenever a cut runs below max rpm. Shared model: optimizer.js 1.1.0.

## v0.5.0 — 2026-11-24

**Native Fusion look.** The panel now looks like a Fusion command dialog, in the dark blue theme: collapsible Operation, Limits, Results and Force sections, label-on-the-left rows, square fields with units inside, a plain current-vs-optimized table, and a primary Apply button. The cards, pills, badges and meters are gone (#3).

**Flute count (#1).** The flute count is read from the tool library's own record (`Tool.toJson()`), then from the tool's parameters, and shown as an editable field on the operation. The library is trusted: if it's wrong, fix the tool in Fusion's Tool Library (issue #1 turned out to be a tool entered as 1 flute). A missing flute count no longer silently becomes 2; Apply skips that op until you enter one.

**Force graph.** It has axes in newtons and degrees, a grid every 90°, current and optimized lines, and the force limit as a dashed line. The fill is gone. Current values over a limit are marked with ⚠ in the table.

**New icon.** Three force humps under a limit line, with a simplified 16 px version (#2).

## v0.4.1 — 2026-11-24

**Fixed.** After an update, Stop/Run in Fusion loaded the new panel but kept running the old Python code, so Apply answered "unknown action apply" and nothing changed. The add-in now clears its cached modules when it starts and stops, so Stop/Run picks up an update. If you're coming from v0.4.0 or earlier, restart Fusion once.

The panel now explains a mismatch like that instead of showing "unknown action".

## v0.4.0 — 2026-11-23

**Apply.** Select operations, mark each one Rough, Wall finish or Floor finish, and write the suggested feeds and speeds back to them in one go.

### New
- **Apply / Apply to N ops** writes spindle speed and cutting feed to the operation, then regenerates the toolpaths. Click once to arm it, then again within 4 s to confirm. It covers the current operation in *This operation* and every optimized row in *All selected*.
- **Pass type per operation:** Rough, Wall finish or Floor finish. It's on the card and in a new *Pass* column in the bulk table. The default comes from the operation: a contour is a wall finish; a name containing "floor", "wall", "rough" or "finish" decides it; everything else is rough.
- **Finishing rule.** Apply sets stock to leave on finish passes. A wall finish gets 0 radial and **0.05 mm axial**, so it stays off the floor. A floor finish gets **0.05 mm radial** and 0 axial, so it stays off the walls. The 0.05 mm is *Finish clearance* under More limits.
- **Finish passes keep their engagement** and only optimize rpm and feed, under a tighter **Finish deflection** limit (0.01 mm by default). A wall finish's stepover defaults to the radial stock that the selected roughing ops in the same setup leave. A floor finish's stepdown defaults to their axial stock. Type over either under *Current*.
- **Revert** puts back every value the last Apply changed, then regenerates.

### Safety
- Each write is read back. If Fusion refuses a value or it reads back differently, that operation is put back exactly as it was, and the panel says why. The other operations still apply.
- An operation is never half-applied. If the stock-to-leave parameters or a stepover/stepdown being written can't be found, nothing on that operation changes.
- Rough passes write stepover/stepdown only when the optimizer was allowed to change them (Keep unticked) or you typed a value under *Current*. Ramp, plunge and lead feeds aren't touched.
- rpm and feed are rounded **down**, so a written value is never over a limit.

### Changed
- Apply and Revert results show in the footer, so the panel doesn't start scrolling. Problems still show in the message box.

## v0.3.0 — 2026-11-23

Chip limits by material, tool deflection, and the force graph back in its familiar style. The full calculator is gone from the add-in.

### New
- **Chip thickness limits by material.** Max chip and Min chip fill in from a table per material (max chip as a fraction of tool diameter, e.g. 0.008 × D for aluminium; min chip as the rubbing threshold). The values show greyed as *auto*; type a value to override. See the README for the table and its sources.
- **Tool deflection** for the current and optimized cut, from the peak force and the tool's stickout, plus an optional **Max deflection** limit (More limits).
- **Stickout on the card,** read from the tool or assumed (1.25 × flute length) until you enter it.
- A hint when the optimizer runs the stepover down to its 2% floor with no max feed set.

### Changed
- **The force graph matches the calculator's style again:** the optimized cut as a filled curve, the current cut as a grey line, 0 N at the bottom, a grid line every 90°, the force limit dashed, and a taller plot. Nothing is filtered; it's the exact force curve sampled every 0.1°.
- **Removed the full calculator** from the add-in. The panel is the only page now, and only `optimizer.js` is copied from djr_cutcalculator.
- Bulk view: the *Limited by* column uses short names (force, slope, max chip, …).

## v0.2.0 — 2026-11-23

A compact panel made for Fusion, which follows what you select. The full calculator is one click away.

### New
- **Compact panel, no scrolling.** The operation card at the top names what you're optimizing: tool number, operation, strategy, tool Ø and flutes, helix, and setup. Below it are the key limits, a current-vs-optimized table with the removal-rate gain, and a small force curve.
- **Follows the CAM browser selection.** Click an operation and the panel updates and re-optimizes on its own. Clicking into the panel keeps what's shown.
- **Bulk: select several operations or a whole setup.** The *All selected* tab lists every operation with its removal rate now, the best inside your limits, the gain and what limits it. Operations the model doesn't cover say why. Bulk keeps each operation's stepover and stepdown by default. Click a row to open that operation.
- **Sensible defaults per operation type.** An adaptive keeps its stepdown, a contour or slot keeps its stepover, and a slot's stepover is always the tool diameter. Untick *Keep stepover* or *Keep stepdown* to free them.
- **Current stepover and stepdown are editable,** for when Fusion's values can't be read.
- **Helix per tool:** enter it once on the card. Tools without one use *Helix if unknown* (default 35°) and are marked "assumed".
- **Material per setup:** pick it and press *Confirm*. It's saved on every setup in the selection.
- Working limits are saved automatically, and named limit profiles live under *More limits*.
- A gain below ×1 shows in amber: the current cut is over your limits, so the safe cut is slower.
- The full calculator (with the stepover × depth map) has a link back to the compact panel.

## v0.1.1 — 2026-11-23

### Fixed
- On Windows the panel showed “This site can’t be reached” (`ERR_INVALID_URL`, `file:///C:/%5CUsers%5C…`). The page path is now passed to Fusion with forward slashes.

## v0.1.0 — 2026-11-20

First release: read-only. Select an operation, open the optimizer, and get the stepover, depth, feed and speed that give the highest removal rate inside your limits.

> Not yet tested in a real Fusion session, and the Fusion parameter names it reads are unverified. Treat it as a preview and check the numbers it reads against the operation.

### New
- **Optimize feeds & speeds** button in the Manufacture **Actions** panel. It opens the djr_cutcalculator in a docked panel and fills it from the selected operation's tool and cutting data.
- **Optimizer:** maximizes removal rate under limits on peak cutting force, force slope (N/°), feed rate, depth, chip thickness, cutting speed and spindle power. Stepover or depth can be locked.
- **Stepover × depth map** of removal rate, showing which limit fails where and the smooth depths just under each flute pitch. Click a cell to use it.
- **Limit profiles** are saved to your app-data folder, so they survive add-in upgrades.
- **Material per setup:** asked once and stored on the setup.
- Drilling, boring, threading, chamfering, engraving and 3D finishing operations are refused with a reason.
- **`djr_dump_cam_params`** script (separate zip): lists every operation and tool parameter, for verifying the names the add-in reads.
