A Fusion add-in that picks **feeds, speeds, stepover and stepdown** for your CAM operations. It finds the **highest removal rate** that stays inside limits you set: peak cutting force, how sharply the force rises as each flute enters the cut, chip thickness, tool deflection and your machine's spindle and feed limits.

Click an operation in the Manufacture browser, and a panel shows the current cut next to the best one. Select several operations (or a whole setup), and **Apply** writes the new feeds and speeds to all of them and regenerates the toolpaths.

| One operation | All selected |
|---|---|
| ![The panel for one operation: limits, current vs optimized, force over one revolution](https://raw.githubusercontent.com/jayem1427/djr_cutoptimizer/v{version}/docs/images/panel-operation.png) | ![The bulk view: one row per operation with removal rate now, best, gain and what limits it](https://raw.githubusercontent.com/jayem1427/djr_cutoptimizer/v{version}/docs/images/panel-bulk.png) |

<sub>Renderings of the panel with a sample setup (a 1/4" 3-flute tool in 6061), not Fusion screenshots.</sub>
