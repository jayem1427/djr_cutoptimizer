"""
"Optimize feeds & speeds": a Manufacture toolbar button that opens the calculator
in a palette and fills it from the selected CAM operation (phase 2: read-only).

Bridge:
  JS -> Python: adsk.fusionSendData(action, json)  -> incomingFromHTML (returnData answers)
  Python -> JS: palette.sendInfoToHTML(action, json) -> window.fusionJavaScriptHandler.handle
Actions from the page: ready, readSelection, getLimits, saveLimits, setMaterial.
Actions to the page:   loadCut, fusionStatus.
"""
from __future__ import annotations

import json
import os

import adsk.core
import adsk.cam

from . import cam_mapping, config, profiles
from ...lib.fusionAddInUtils.general_utils import Utils
from ...lib.fusionAddInUtils.event_utils import Events

_HERE = os.path.dirname(os.path.abspath(__file__))
_ICON_FOLDER = os.path.join(_HERE, 'resources', '')
_HTML = os.path.join(os.path.dirname(os.path.dirname(_HERE)), 'web', 'index.html')


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


class OptimizerCommand:

    _local_handlers = []
    _palette_handlers = []
    _last_setup = None

    # ------------------------------------------------------------------ setup
    @classmethod
    def start(cls):
        ui = adsk.core.Application.get().userInterface
        old = ui.commandDefinitions.itemById(config.CMD_ID)
        if old:
            _safe(old.deleteMe)
        cmd_def = ui.commandDefinitions.addButtonDefinition(config.CMD_ID, config.CMD_NAME, config.CMD_DESCRIPTION, _ICON_FOLDER)
        Events.add(cmd_def.commandCreated, cls.commandCreated)

        panel = cls._panel(ui)
        if panel is None:
            Utils.log('djr_cutoptimizer: Manufacture actions panel not found.', adsk.core.LogLevels.WarningLogLevel)
            return
        old_control = panel.controls.itemById(config.CMD_ID)
        if old_control:
            _safe(old_control.deleteMe)
        control = panel.controls.addCommand(cmd_def)
        control.isPromoted = True

    @classmethod
    def stop(cls):
        ui = adsk.core.Application.get().userInterface
        panel = cls._panel(ui)
        if panel is not None:
            control = panel.controls.itemById(config.CMD_ID)
            if control:
                control.deleteMe()
        definition = ui.commandDefinitions.itemById(config.CMD_ID)
        if definition:
            definition.deleteMe()
        palette = ui.palettes.itemById(config.PALETTE_ID)
        if palette:
            palette.deleteMe()
        cls._palette_handlers = []
        cls._last_setup = None

    @staticmethod
    def _panel(ui):
        ws = ui.workspaces.itemById(config.CAM_WORKSPACE_ID)
        return ws.toolbarPanels.itemById(config.CAM_ACTIONS_PANEL_ID) if ws else None

    # ---------------------------------------------------------------- command
    @classmethod
    def commandCreated(cls, args: adsk.core.CommandCreatedEventArgs):
        # No inputs: execute fires immediately, with no dialog.
        Events.add(args.command.execute, cls.commandExecute, local_handlers=cls._local_handlers)
        Events.add(args.command.destroy, lambda a: cls._local_handlers.clear(), local_handlers=cls._local_handlers)

    @classmethod
    def commandExecute(cls, args):
        palette = cls._palette()
        palette.isVisible = True
        # The page asks for the selection itself on "ready"; when the palette is
        # already open, push the current selection straight away.
        cls._push_selection(palette)

    @classmethod
    def _palette(cls):
        ui = adsk.core.Application.get().userInterface
        palette = ui.palettes.itemById(config.PALETTE_ID)
        if palette is None:
            palette = ui.palettes.add(config.PALETTE_ID, config.PALETTE_NAME, _HTML, True, True, True,
                                      config.PALETTE_WIDTH, config.PALETTE_HEIGHT)
            _safe(lambda: setattr(palette, 'dockingState', adsk.core.PaletteDockingStates.PaletteDockStateRight))
            cls._palette_handlers = []
            Events.add(palette.incomingFromHTML, cls.onHTML, local_handlers=cls._palette_handlers)
        return palette

    # ------------------------------------------------------------------ bridge
    @classmethod
    def onHTML(cls, args: adsk.core.HTMLEventArgs):
        action = args.action
        try:
            data = json.loads(args.data) if args.data else {}
        except ValueError:
            data = {}
        if action in ('ready', 'readSelection'):
            payload = cls.read_selection()
            args.returnData = json.dumps(payload)
        elif action == 'getLimits':
            args.returnData = json.dumps(profiles.load())
        elif action == 'saveLimits':
            try:
                profiles.save(data.get('items', {}))
                args.returnData = json.dumps({'ok': True})
            except Exception as e:
                args.returnData = json.dumps({'ok': False, 'reason': str(e)})
        elif action == 'setMaterial':
            args.returnData = json.dumps(cls.set_material(data.get('material')))
        else:
            args.returnData = json.dumps({'ok': False, 'reason': f'unknown action {action}'})

    @classmethod
    def _push_selection(cls, palette):
        _safe(lambda: palette.sendInfoToHTML('loadCut', json.dumps(cls.read_selection())))

    # ---------------------------------------------------------------- reading
    @classmethod
    def read_selection(cls) -> dict:
        """The selected operation as calculator inputs, or {ok: False, reason}. Never raises."""
        try:
            app = adsk.core.Application.get()
            doc = app.activeDocument
            if doc is None:
                return {'ok': False, 'reason': 'No document is open.'}
            product = _safe(lambda: doc.products.itemByProductType(config.CAM_PRODUCT_ID))
            cam = adsk.cam.CAM.cast(product) if product else None
            if cam is None:
                return {'ok': False, 'reason': 'This document has no Manufacture (CAM) data.'}

            op = None
            sel = app.userInterface.activeSelections
            for i in range(sel.count):
                ent = sel.item(i).entity
                if getattr(ent, 'objectType', '') == adsk.cam.Operation.classType():
                    op = adsk.cam.Operation.cast(ent)
                    break
            if op is None:
                return {'ok': False, 'reason': 'Select an operation in the CAM browser, then press “Read selected operation”.'}

            strategy = _safe(lambda: op.strategy, '') or ''
            tool = _safe(lambda: op.tool)
            if tool is None:
                return {'ok': False, 'reason': f'“{op.name}” has no tool.'}
            setup = _safe(lambda: op.parentSetup)
            cls._last_setup = setup
            material = None
            if setup is not None:
                attr = _safe(lambda: setup.attributes.itemByName(config.ATTR_GROUP, config.ATTR_MATERIAL))
                material = attr.value if attr else None

            payload = cam_mapping.build_payload(
                strategy,
                cam_mapping.params_to_dict(op.parameters),
                cam_mapping.params_to_dict(tool.parameters),
                op_name=op.name, material=material)
            payload['setup'] = _safe(lambda: setup.name, '')
            return payload
        except Exception:
            Utils.handleError('read_selection')
            return {'ok': False, 'reason': 'Couldn’t read the operation. See the Text Command window for details.'}

    @classmethod
    def set_material(cls, material) -> dict:
        setup = cls._last_setup
        if setup is None or not isinstance(material, str) or not material:
            return {'ok': False, 'reason': 'No setup to store the material on. Read an operation first.'}
        try:
            setup.attributes.add(config.ATTR_GROUP, config.ATTR_MATERIAL, material)
            return {'ok': True, 'setup': setup.name}
        except Exception:
            Utils.handleError('set_material')
            return {'ok': False, 'reason': 'Couldn’t save the material on the setup.'}
