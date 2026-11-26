# CAM parameter dumps

Output of `scripts/djr_dump_cam_params` from Fusion 2706.1.17, on the owner's Grid Vacuum Plate document (Nov 2026). There's one `.txt` per operation: every operation, tool and tool-preset parameter, with name, expression, internal value, editability and title. A trimmed copy of the parameters the add-in uses is in `tests/fixtures/fusion_dump_ops.json` and covered by `RealFusionDump` in the tests.

| File | Strategy |
|---|---|
| `adaptive_R2_Rough_-_3D_Adaptive_12.txt` | 3D Adaptive with a helical ramp |
| `adaptive2d_Rough_Profile_-_2D_Adaptive_12.txt` | 2D Adaptive |
| `contour2d_Finish_Profile_-_2D_Contour_12.txt` | 2D Contour, single pass |
| `pocket2d_Rough_Channels_-_2D_Pocket_1.txt` | 2D Pocket with a profile ramp |
| `face_Face_Rough_-_BAP10_14.txt` | Face |
| `bore_Stud_Seats_16H6_-_Bore_12.txt` | Bore (refused by the add-in) |

## What the dump settled

| What | Verified |
|---|---|
| Spindle speed, cutting feed | `tool_spindleSpeed`, `tool_feedCutting` |
| Stepover | `optimalLoad` (adaptive), `maximumStepover` (pocket; switched off on single-pass contours), `stepover` (face) |
| Stepdown | `maximumStepdown` (switched off and 0 when multiple depths is off) |
| Load deviation | `loadDeviation`, default `(optimalLoad<(tool_diameter-optimalLoad*0.20))?(optimalLoad*0.10):(…)`, so 10 % of the optimal load. `maximumLoad = optimalLoad + loadDeviation` |
| Stock to leave | checkbox `useStockToLeave`, radial `stockToLeave`, axial `verticalStockToLeave` |
| Ramp | `rampType` ('helix', 'profile', …), `rampAngle` (degrees), `helicalRampDiameter` (an expression), `tool_feedRamp`, `tool_rampSpindleSpeed` |
| Tool | `tool_diameter`, `tool_numberOfFlutes`, `tool_fluteLength`, `tool_bodyLength`, `tool_cornerRadius`. There is **no** helix angle parameter. |
| Tool preset | `tool_spindleSpeed`, `tool_feedCutting`, `tool_rampSpindleSpeed`, `tool_feedRamp`, `tool_stepover`, `tool_stepdown`, … (17 parameters) |
| Internal units | length **cm**, feed **mm/min**, angle **degrees**, speed rpm |
| Expression formats | `"16000."`, `"62.in/min"`, `"900mmpm"`, `"1.2deg"`, `"0.375in"` |

Run the script again after a Fusion update, or for a strategy that isn't here yet (slot, 3D contour), and add the files.
