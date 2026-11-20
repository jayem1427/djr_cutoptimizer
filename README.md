# DJR Cut Optimizer

A Fusion add-in that picks **feeds, speeds, stepover and stepdown** for a CAM operation. It gives the **highest removal rate** that stays inside limits you set, such as peak cutting force and how sharply the force rises as each flute enters the cut.

It opens the [djr_cutcalculator](https://github.com/jayem1427/cutcalculator) in a panel beside the Manufacture workspace and fills it from the operation you selected.

> **Status: v0.1.0, read-only, not yet tested in a real Fusion session.** The add-in reads the selected operation and optimizes it in the panel. It doesn't write anything back to the operation yet; that's the next version (Apply). The Fusion parameter names it reads aren't verified yet either. See [Status](#status).

## Install

1. Download **`djr_cutoptimizer-vX.Y.Z.zip`** from the [latest release](https://github.com/jayem1427/djr_cutoptimizer/releases/latest) (not the "Source code" zips) and unzip it. You get a folder named `djr_cutoptimizer`. Don't rename it.
2. Copy the folder into Fusion's add-ins folder:
   - **Windows:** `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\`
   - **Mac:** `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/`
3. Restart Fusion, or open **Utilities → Add-Ins → Scripts and Add-Ins** (Shift+S), select **djr_cutoptimizer**, click **Run**, and tick **Run on startup**.

To upgrade, replace the folder. Your limit profiles live outside it and carry over.

## Use

1. In **Manufacture**, select an operation (adaptive, 2D contour, pocket, slot or face) in the browser.
2. Click **Optimize feeds & speeds** in the **Actions** panel. The calculator opens on the right with the operation's tool, stepover, stepdown, spindle speed and feed filled in. Press **Read selected operation** to load a different one.
3. The first time for each setup, pick the stock **material**. It's saved on the setup.
4. Check the tool's **helix angle**. Fusion tools often don't have one, and the force-slope limit needs it.
5. Set your limits (see below) and press **Optimize**. The best stepover, depth, feed per tooth and cutting speed are filled in, and the stepover × depth map shows the alternatives. Click any cell on the map to use it instead.
6. Copy the numbers into the operation by hand. (Apply comes in the next version.)

### Limits

The quick path is just the first two: **max cutting force** and **max force slope**.

| Limit | What it means |
|---|---|
| Max cutting force | Peak tangential force over one revolution (not the average). |
| Max force slope | Steepest rise in force per degree of rotation (N/°). It doesn't depend on rpm. Also shown as N/ms at the chosen rpm. Lower means gentler flute entry and less chatter. |
| Max feed rate | Your machine's practical feed limit. |
| Max depth | Usually the flute length (filled in from the tool). |
| Max chip thickness | The tool's chip-load limit. **Set this.** Without it the model favors very thick chips (see Known limitations). |
| Min chip thickness | Stops the edge rubbing. Default 0.005 mm. |
| Min / max cutting speed | Optional surface-speed window. |
| Spindle power | Tick to also limit by the spindle power in “Your machine”. |

Save sets of limits as named **profiles**, for example per machine, material or tool. Max spindle speed comes from “Your machine”. Tick **Lock** next to stepover or depth to keep it fixed while optimizing, for example to hold depth at the floor depth.

## How it works

The model is the djr_cutcalculator's: Sandvik Coromant's specific-cutting-force formulas, with wrought aluminium k<sub>c1</sub> calibrated to Sandvik CoroPlus (6061: 1.82 kW for the reference cut, matching Sandvik). The force through one revolution is the exact integral of k<sub>c</sub>·f<sub>z</sub>·sin θ along each helical flute.

Force and force slope both scale exactly with f<sub>z</sub><sup>1−m<sub>c</sub></sup>, and per degree neither depends on rpm. So the optimizer:

1. runs the spindle as fast as the rpm and cutting-speed limits allow;
2. for each stepover × depth on a 30 × 30 grid, computes one force curve and solves for the largest feed per tooth every limit allows;
3. refines around the best point and re-checks the final cut on a 0.05° force curve, so every limit holds;
4. snaps the depth to just under a whole multiple of the flute pitch πD/(z·tan β) when that gives at least 99% of the best removal rate. Force is nearly constant there.

**Smooth depths are one-sided.** At depths just under a multiple of the flute pitch, force barely changes through the revolution. But go even 0.02 mm deeper and the full force slope comes back. So near a multiple, the slope is taken as the worst within ±0.05 mm of depth.

## Known limitations

- **Planning values only.** Check every new cut conservatively.
- Adaptive toolpaths go above the nominal engagement in corners. The optimizer uses the nominal optimal load, so leave margin on the force limit.
- Forces are tangential only. The resultant force is typically 1.1–1.3× higher.
- Only wrought aluminium (and cast, by scaling) is calibrated to Sandvik. Other materials are uncalibrated reference values.
- Thicker chips lower k<sub>c</sub>, so with no max chip thickness the optimizer tends toward thick chips and very high feeds. Set a max chip thickness for your tool.
- Drilling, boring, threading, chamfering, engraving and 3D finishing are refused, because the side-milling model doesn't cover them.

## Status

| | |
|---|---|
| Verified by tests | The force model and optimizer against the Sandvik and HSM reference cuts (15 tests on the bundled `optimizer.js`). Unit-reading, operation filtering, limit profiles, and no crash with no document, no CAM data, nothing selected or an unsupported operation (19 tests against a fake Fusion API). The panel page's Fusion mode, driven by a fake bridge in headless Chrome. |
| Not verified yet | Anything inside real Fusion: the toolbar button, the panel, reading a real operation. |
| Unverified names | The CAM parameter names in `commands/optimizer/cam_mapping.py` (`tool_spindleSpeed`, `optimalLoad`, `maximumStepdown`, …). |

**Help verify the parameter names:** run the `djr_dump_cam_params` script from the release (Scripts tab → **+** → the unzipped folder → **Run**) with an adaptive, a 2D contour and a slot selected. Then commit its output to `docs/cam_params/`.

## Roadmap

- **v0.2: Apply.** Write spindle speed and feed (and stepover/stepdown, if ticked) back to the operation and regenerate it, with undo or revert. Don't overwrite ramp, plunge or lead feeds that you set as expressions.
- **Later.** "Save as preset" into the tool library, and "Optimize all in setup", possibly hooking into [djr_batchpost](https://github.com/jayem1427/djr_batchpost).

## Development

The calculator page (`web/index.html`, `web/optimizer.js`) is a copy. Its source is [jayem1427/cutcalculator](https://github.com/jayem1427/cutcalculator). Change it there, then copy it in:

```bash
python tools/sync_web.py            # from ../cutcalculator
python -m pytest                    # add-in tests (stdlib unittest; pytest optional)
node --test tests/web_optimizer.test.js
python tools/build_release.py       # dist/djr_cutoptimizer-vX.Y.Z.zip
```

To release, bump `"version"` in `djr_cutoptimizer.manifest` and `PLUGIN_VERSION` in `config.py`, then add a `## vX.Y.Z — date` section to `CHANGELOG.md`. Push to `main` and push a tag `vX.Y.Z`. The Release workflow runs the tests, builds both zips and publishes the release.

## Credits and license

MIT. See [LICENSE](LICENSE). The calculator page derives from [joevenzon/cutcalculator](https://github.com/joevenzon/cutcalculator) (MIT). The add-in's structure follows [djr_batchpost](https://github.com/jayem1427/djr_batchpost).
