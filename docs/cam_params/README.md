# CAM parameter dumps

Output of `scripts/djr_dump_cam_params` goes here: one `.txt` per operation plus `summary.json`.

Needed before the add-in's parameter names can be trusted: one **adaptive**, one **2D contour** and one **slot** operation. Note the Fusion version in each file; it's printed at the top.

Then update `OP_NAMES`, `TOOL_NAMES` and `INTERNAL_TO_CALC` in `commands/optimizer/cam_mapping.py` to match, and add a test using a real dump.
