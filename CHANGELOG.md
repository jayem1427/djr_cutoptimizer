# Changelog

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
