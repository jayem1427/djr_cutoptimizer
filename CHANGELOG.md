# Changelog

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
