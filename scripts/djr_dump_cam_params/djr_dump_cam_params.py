"""
djr_dump_cam_params: list every CAM operation parameter and tool parameter.

Run from Fusion (Utilities > Add-Ins > Scripts and Add-Ins > Scripts > +, point at
this folder, then Run) with a document open in Manufacture.

Select the operations to dump in the CAM browser first (an adaptive, a 2D contour
with stock to leave ticked, a 2D pocket and a slot are what the optimizer needs). With nothing selected, every operation
in the document is dumped.

Writes one text file per operation, plus summary.json, into a folder you pick.
Commit those to docs/cam_params/ so the add-in codes against verified names.
"""
import json
import os
import re
import traceback

import adsk.core
import adsk.cam

TITLE = "Dump CAM parameters"


def _safe(fn, default=""):
    try:
        return fn()
    except Exception:
        return default


def _param_rows(params):
    rows = []
    for i in range(params.count):
        p = params.item(i)
        val = _safe(lambda: p.value)
        rows.append({
            "name": _safe(lambda: p.name),
            "title": _safe(lambda: p.title),
            "expression": _safe(lambda: p.expression),
            "value": _safe(lambda: val.value) if val != "" else "",
            "valueType": _safe(lambda: val.objectType) if val != "" else "",
            "isEditable": _safe(lambda: p.isEditable),
            "isEnabled": _safe(lambda: p.isEnabled),
        })
    return rows


def _fmt(rows):
    w = max([len(r["name"]) for r in rows] + [4])
    lines = [f'{"name".ljust(w)}  {"expression":<30}  {"value":<22}  editable  title', "-" * (w + 90)]
    for r in rows:
        lines.append(f'{r["name"].ljust(w)}  {str(r["expression"])[:30]:<30}  {str(r["value"])[:22]:<22}  {str(r["isEditable"]):<8}  {r["title"]}')
    return "\n".join(lines)


def _operations(cam, ui):
    picked = []
    sel = ui.activeSelections
    for i in range(sel.count):
        ent = sel.item(i).entity
        if getattr(ent, "objectType", "") == adsk.cam.Operation.classType():
            picked.append(adsk.cam.Operation.cast(ent))
    if picked:
        return picked
    return [cam.allOperations.item(i) for i in range(cam.allOperations.count)]


def run(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        doc = app.activeDocument
        product = doc.products.itemByProductType("CAMProductType") if doc else None
        cam = adsk.cam.CAM.cast(product) if product else None
        if cam is None:
            ui.messageBox("Open a document with Manufacture (CAM) data first.", TITLE)
            return
        ops = _operations(cam, ui)
        if not ops:
            ui.messageBox("No operations found.", TITLE)
            return

        dlg = ui.createFolderDialog()
        dlg.title = "Folder for the parameter dump"
        if dlg.showDialog() != adsk.core.DialogResults.DialogOK:
            return
        out = dlg.folder

        summary = {"fusionVersion": app.version, "document": doc.name, "operations": []}
        for op in ops:
            name = _safe(lambda: op.name, "op")
            strategy = _safe(lambda: op.strategy)
            op_rows = _param_rows(op.parameters)
            tool = _safe(lambda: op.tool, None)
            tool_rows = _param_rows(tool.parameters) if tool is not None else []
            preset = _safe(lambda: op.toolPreset, None)
            preset_rows = _param_rows(preset.parameters) if preset is not None else []
            entry = {"name": name, "strategy": strategy, "objectType": _safe(lambda: op.objectType),
                     "operation": op_rows, "tool": tool_rows, "toolPreset": preset_rows}
            summary["operations"].append(entry)
            stem = re.sub(r"[^\w.-]+", "_", f"{strategy}_{name}")
            with open(os.path.join(out, stem + ".txt"), "w", encoding="utf-8") as f:
                f.write(f"Operation: {name}\nStrategy: {strategy}\nFusion: {app.version}\n\n")
                f.write(f"== operation.parameters ({len(op_rows)}) ==\n{_fmt(op_rows)}\n\n")
                f.write(f"== operation.tool.parameters ({len(tool_rows)}) ==\n{_fmt(tool_rows) if tool_rows else '(no tool)'}\n\n")
                if preset_rows:
                    f.write(f"== operation.toolPreset.parameters ({len(preset_rows)}) ==\n{_fmt(preset_rows)}\n")
        with open(os.path.join(out, "summary.json"), "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=1, default=str)
        ui.messageBox(f"Dumped {len(ops)} operation(s) to\n{out}", TITLE)
    except Exception:
        if ui:
            ui.messageBox("Failed:\n{}".format(traceback.format_exc()), TITLE)
