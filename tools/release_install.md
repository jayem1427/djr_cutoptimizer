---

## Install / upgrade

1. Download **`djr_cutoptimizer-v{version}.zip`** below (not the "Source code" zips) and unzip it. You get a folder named `djr_cutoptimizer`. Don't rename it: Fusion needs the folder name to match the files inside.
2. Copy that folder into Fusion's add-ins folder, replacing the old one if you're upgrading:
   - **Windows:** `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\`
   - **Mac:** `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/`
3. Restart Fusion, or open **Utilities → Add-Ins → Scripts and Add-Ins** (Shift+S), select **djr_cutoptimizer**, click **Run**, and tick **Run on startup**.
4. In the **Manufacture** workspace, select an operation in the browser and click **Optimize feeds & speeds** in the **Actions** panel.

Your limit profiles are kept outside the add-in folder (`%APPDATA%\djr_cutoptimizer\` on Windows, `~/Library/Application Support/djr_cutoptimizer/` on Mac), so upgrading keeps them.

**Parameter dump script (optional):** `djr_dump_cam_params-v{version}.zip` is a Fusion *script* that lists every parameter of the selected operations. Unzip it, then in Scripts and Add-Ins open the **Scripts** tab, click **+** and pick the unzipped folder.

> Results are planning values. Check every new cut conservatively before running it at full speed.

Full history: [CHANGELOG.md](https://github.com/jayem1427/djr_cutoptimizer/blob/main/CHANGELOG.md)
