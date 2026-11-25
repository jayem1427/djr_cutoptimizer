# CLAUDE.md: working on djr_cutoptimizer

A Fusion add-in (Python) that opens the djr_cutcalculator page in a palette, fills it from the selected CAM operation, and optimizes feeds and speeds. The owner runs a LemonTart CNC mill on LinuxCNC (2.2 kW, 24,000 rpm, ER16), mostly cutting 6061. Read `README.md` for user-facing behaviour.

## Where things live

| What | Where |
|---|---|
| This repo | `jayem1427/djr_cutoptimizer`, branch `main`. The repo root **is** the add-in folder. |
| Model source | `jayem1427/cutcalculator` (`optimizer.js` and its Node tests). `web/optimizer.js` here is a copy made by `tools/sync_web.py`; never edit it directly. `web/panel.html` is owned here. |
| Installed add-in | `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\djr_cutoptimizer\` |
| Limit profiles | `%APPDATA%\djr_cutoptimizer\limit_profiles.json` (Mac: `~/Library/Application Support/djr_cutoptimizer/`) |
| Material per setup | setup attribute group `djr_cutcalc`, name `material` |
| Sibling add-in | `jayem1427/djr_batchpost`. This repo copies its layout, `lib/fusionAddInUtils` and release tooling. |

**The folder must be named `djr_cutoptimizer`.** Fusion loads `<folder>/<folder>.py` and `<folder>.manifest`, and command IDs come from the folder name. The tests import the add-in as the package `djr_cutoptimizer` from the parent folder, so CI checks out into a folder of that name.

## Code map

```
djr_cutoptimizer.py / .manifest / .svg   entry point (run/stop), metadata, icon
config.py                                PLUGIN_VERSION, DEBUG
commands/commands.py                     registers OptimizerCommand
commands/optimizer/
  config.py          command and palette IDs, CAM workspace/panel IDs, attribute names
  palette_command.py toolbar button, palette, HTML bridge, read_selection, set_material (adsk)
  cam_mapping.py     PURE: parameter names, unit parsing, supported strategies, payload
  profiles.py        PURE: limit profiles JSON (atomic write)
web/panel.html       the compact panel the palette opens (owned here). Holds the material table
                     (kc1, mc, chip limits), deflection, per-op-type defaults and the bulk view.
web/optimizer.js     the model (copied from cutcalculator; see above)
docs/images/         README renderings of panel.html (headless Chrome, fake bridge, sample ops)
scripts/djr_dump_cam_params/  Fusion script that dumps every op/tool parameter
tools/               build_release.py, release_intro.md + release_install.md (release notes), sync_web.py
tests/               test_addin.py (stdlib unittest with a fake adsk), web_optimizer.test.js (Node)
```

## Bridge

- JS → Python: `adsk.fusionSendData(action, json)` → `palette.incomingFromHTML`; the handler sets `args.returnData`, which the JS receives as a Promise result.
- Python → JS: `palette.sendInfoToHTML(action, json)` → `window.fusionJavaScriptHandler.handle(action, data)`.
- Actions from the page: `ready`/`readOps` (every selected op; setups, folders and patterns expand), `getLimits`, `saveLimits`, `setMaterial` (`{material, setups}`), `apply` (`{items:[{id, n, vf, pass, ae?, ap?}], clearance}`), `revert`. To the page: `selectionChanged` (pushed from `ui.activeSelectionChanged` while the palette is visible; an empty selection is ignored), `fusionStatus`.
- Each op payload carries `src` (the parameter each of n/vf/ae/ap was read from; `ae` is null for slots), `stock` ({radial, axial} mm) and `stockSrc` ({radial, axial, flag}). Apply writes back to exactly those names.
- **Apply** (`OptimizerCommand.apply`): re-reads each op, calls the pure `cam_mapping.plan_writes`, writes each parameter by expression (a boolean flag by `value.value`), and reads it back with `write_matches`. Any failure restores that op from its snapshot. Changed ops regenerate in one `cam.generateToolpath(ObjectCollection)`. The snapshots of the last apply are kept in memory for `revert`; they're lost when the add-in stops.
- **Passes:** `rough` / `wall` / `floor`. Finish passes lock ae and ap, use `min(deflMax, deflFinish)`, and write stock to leave: wall = 0 radial / clearance axial; floor = clearance radial / 0 axial. The panel stores the pass in overrides as `pass:<op id>` (only when it differs from `defaultPass`). A finish op's engagement defaults to the max stock the selected rough ops in the same setup leave.
- Limit profiles: names starting `__` are internal. `__working` holds the panel's working limits and per-tool overrides (helix by tool key, `so:` stickout, `geom:` current stepover/stepdown, `pass:` pass type).
- The full calculator page was removed from the add-in in v0.3.0 at the owner's request; don't bring it back.
- Python sends metric (mm, rpm, mm/min); the page switches to metric on load.
- Fusion keeps one Python process per session. `djr_cutoptimizer.py` drops the add-in's cached modules (matched by file path) on import and on `stop`, so Stop/Run loads updated code. Keep that, or updates need a full Fusion restart.
- The page detects Fusion lazily (`hasFusion()` at init and again after 800 ms), because `window.adsk` may be injected late.

## Testing

```bash
python -m pytest                        # or: python -m unittest discover -s tests -v
node --test tests/web_optimizer.test.js
python tools/build_release.py --check
python tools/sync_web.py --check        # only with ../cutcalculator checked out
```

None of this replaces a real Fusion run. Be explicit about what was verified in Fusion versus only in tests.

## Releasing

1. Bump `"version"` in `djr_cutoptimizer.manifest` **and** `PLUGIN_VERSION` in `config.py`.
2. Add `## vX.Y.Z — date` to `CHANGELOG.md`. The release notes are `tools/release_intro.md` (summary and screenshots pinned to the tag), then that body as "What's new", then `tools/release_install.md` (install and quick start).
3. Push to `main`, then `git tag vX.Y.Z && git push origin vX.Y.Z`. `.github/workflows/release.yml` tests, builds `djr_cutoptimizer-vX.Y.Z.zip` and `djr_dump_cam_params-vX.Y.Z.zip`, and publishes the release. A tag that doesn't match the version fails on purpose.

## Next work (from the original handoff)

1. **Verify parameter names.** The owner runs `djr_dump_cam_params` on an adaptive, a 2D contour (stock to leave ticked), a 2D pocket and a slot, and the output goes in `docs/cam_params/`. Then fix `OP_NAMES`, `TOOL_NAMES`, `STOCK_NAMES`, `STOCK_FLAG` and `INTERNAL_TO_CALC` in `cam_mapping.py`. The feed and speed internal units are unverified. Expression parsing is used first, so internal units only matter for expressions that reference other parameters.
2. **Finish Apply in Fusion.** Rough Apply works in Fusion (v0.4.1, 3D Adaptive: rpm, feed and `optimalLoad` written and read back, toolpath regenerated). Still untried for real: wall/floor finish stock to leave, Revert, pocket/contour/slot, bulk. Also check that the feed per tooth follows the cutting feed.
3. **Later:** scale ramp and plunge feeds with the cutting feed; auto-assign tools and geometry (the owner assigns them by hand for now); "Save as preset" into the tool library; djr_batchpost integration.

## Model notes (don't relearn these)

- Force slope near a whole flute pitch is one-sided: smooth just *below* m·pitch, full entry slope immediately above. `robustSlope` takes the worst within ±0.05 mm, and the optimizer snaps to `m·pitch − tol`.
- With no max chip thickness, kc's chip-thinning reward pushes toward thick chips; v0.3 fills max chip from the material table. With no max feed, thin stepovers allow very high feeds; the panel hints to set Max feed.
- Deflection uses the PEAK force (the calculator used the mean). A deflection limit is converted to an equivalent force cap per op (`effLimits`).
- Don't copy FSWizard's data or methods (EULA).
