## Install / upgrade

1. Download **`djr_cutoptimizer-v{version}.zip`** below (not the "Source code" zips) and unzip it. You get a folder named `djr_cutoptimizer`. Don't rename it: Fusion needs the folder name to match the files inside.
2. Copy that folder into Fusion's add-ins folder, replacing the old one if you're upgrading:
   - **Windows:** `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\`
   - **Mac:** `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/`
3. Restart Fusion, or open **Utilities → Add-Ins → Scripts and Add-Ins** (Shift+S), select **djr_cutoptimizer**, click **Run**, and tick **Run on startup**. When upgrading, **Stop** then **Run** is enough.

Your limits are kept outside the add-in folder (`%APPDATA%\djr_cutoptimizer\` on Windows, `~/Library/Application Support/djr_cutoptimizer/` on Mac), so upgrading keeps them.

## Quick start

1. In **Manufacture**, click **Optimize feeds & speeds** in the **Actions** panel. The panel opens on the right.
2. Click an operation in the CAM browser. The panel shows the tool (Ø, flutes, helix, stickout), then the **current** cut next to the **optimized** one, and the force on the tool through one revolution.
3. The first time for each setup, pick the stock **Material** and click **Save to setup**.
4. Set your **Max force** and **Max force slope** under **Limits**. Under **More limits**, set **Max feed** to what your machine can really do, and **Max deflection** if you want one.
5. Check the tool's **helix** and **stickout**. Values marked *assumed* are guesses, because Fusion tools often lack them. Enter them once per tool. The flute count comes from your tool library, so make sure it's right there.
6. Pick the **Pass**: **Rough**, **Wall finish** or **Floor finish**. Finish passes keep their engagement, use a tight deflection limit (0.01 mm) and set stock to leave so they stay off the other surface.
7. Click **Apply**, then click again within 4 s to confirm. Spindle speed and cutting feed are written and the toolpath regenerates. **Revert** undoes the last Apply.

**Several at once:** Shift- or Ctrl-click operations, or click a whole setup, and open **All selected**. Each row shows the pass, the removal rate now and the best, the gain, and what limits it. **Apply to N ops** writes them all.

**Good to know**
- An adaptive keeps its stepdown, and a contour or slot keeps its stepover. Untick **Keep stepover** / **Keep stepdown** to let the optimizer change them too.
- Every value is read back after it's written. If Fusion refuses one, that operation is put back exactly as it was, and the rest still apply.
- Drilling, boring, threading, chamfering, engraving and 3D finishing are skipped, with a reason.
- Results are planning values. Check every new cut conservatively before running it at full speed.

**Parameter dump script (optional):** `djr_dump_cam_params-v{version}.zip` is a Fusion *script* that lists every parameter of the selected operations. Unzip it, then in Scripts and Add-Ins open the **Scripts** tab, click **+** and pick the unzipped folder.

Full guide: [README](https://github.com/jayem1427/djr_cutoptimizer#readme) · History: [CHANGELOG](https://github.com/jayem1427/djr_cutoptimizer/blob/main/CHANGELOG.md)
