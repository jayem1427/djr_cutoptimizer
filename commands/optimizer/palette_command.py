"""
"Optimize feeds & speeds": a Manufacture toolbar button that opens the compact
optimizer panel (web/panel.html) and keeps it in step with the CAM selection.

Bridge:
  JS -> Python: adsk.fusionSendData(action, json)  -> incomingFromHTML (returnData answers)
  Python -> JS: palette.sendInfoToHTML(action, json) -> window.fusionJavaScriptHandler.handle
Actions from the page: ready, readOps, readSelection (first op only; the full
calculator uses it), getLimits, saveLimits, setMaterial.
Actions to the page:   selectionChanged (same shape as readOps), loadCut, fusionStatus.
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
_WEB = os.path.join(os.path.dirname(os.path.dirname(_HERE)), 'web')
_HTML = os.path.join(_WEB, 'panel.html')

_OPERATION = 'adsk::cam::Operation'
_SETUP = 'adsk::cam::Setup'
_FOLDER = 'adsk::cam::CAMFolder'
_PATTERN = 'adsk::cam::CAMPattern'
MAX_OPS = 60


def palette_url(path: str) -> str:
    """The page path as Fusion's palette wants it. Fusion turns a Windows path with
    backslashes into the invalid URL file:///C:/%5CUsers%5C..., so use forward slashes."""
    return path.replace('\\', '/')


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def _children_ops(container):
    """All operations under a setup, folder or pattern."""
    ops = _safe(lambda: container.allOperations)
    if ops is None:
        return []
    return [ops.item(i) for i in range(_safe(lambda: ops.count, 0) or 0)]


class OptimizerCommand:

    _local_handlers = []
    _palette_handlers = []
    _selection_handler = None
    _setups: dict = {}            # setup name -> setup, from the last read (for setMaterial)

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
        if cls._selection_handler is not None:
            _safe(lambda: ui.activeSelectionChanged.remove(cls._selection_handler))
            cls._selection_handler = None
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
        cls._setups = {}

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
        # The page asks for the selection on "ready"; if it's already open, push it now.
        cls._push_selection(palette)

    @classmethod
    def _palette(cls):
        ui = adsk.core.Application.get().userInterface
        palette = ui.palettes.itemById(config.PALETTE_ID)
        if palette is None:
            palette = ui.palettes.add(config.PALETTE_ID, config.PALETTE_NAME, palette_url(_HTML), True, True, True,
                                      config.PALETTE_WIDTH, config.PALETTE_HEIGHT)
            _safe(lambda: setattr(palette, 'dockingState', adsk.core.PaletteDockingStates.PaletteDockStateRight))
            cls._palette_handlers = []
            Events.add(palette.incomingFromHTML, cls.onHTML, local_handlers=cls._palette_handlers)
        if cls._selection_handler is None:
            # Follow the CAM browser selection while the panel is open.
            cls._selection_handler = _safe(lambda: Events.add(ui.activeSelectionChanged, cls.onSelectionChanged,
                                                              local_handlers=cls._palette_handlers))
        return palette

    @classmethod
    def onSelectionChanged(cls, args):
        ui = adsk.core.Application.get().userInterface
        palette = ui.palettes.itemById(config.PALETTE_ID)
        if palette is None or not palette.isVisible:
            return
        result = cls.read_ops()
        # An empty selection (e.g. clicking into the panel) keeps what's shown.
        if not result.get('ok') and result.get('empty'):
            return
        _safe(lambda: palette.sendInfoToHTML('selectionChanged', json.dumps(result)))

    # ------------------------------------------------------------------ bridge
    @classmethod
    def onHTML(cls, args: adsk.core.HTMLEventArgs):
        action = args.action
        try:
            data = json.loads(args.data) if args.data else {}
        except ValueError:
            data = {}
        if action in ('ready', 'readOps'):
            args.returnData = json.dumps(cls.read_ops())
        elif action == 'readSelection':
            args.returnData = json.dumps(cls.read_selection())
        elif action == 'getLimits':
            args.returnData = json.dumps(profiles.load())
        elif action == 'saveLimits':
            try:
                profiles.save(data.get('items', {}))
                args.returnData = json.dumps({'ok': True})
            except Exception as e:
                args.returnData = json.dumps({'ok': False, 'reason': str(e)})
        elif action == 'setMaterial':
            args.returnData = json.dumps(cls.set_material(data.get('material'), data.get('setups')))
        else:
            args.returnData = json.dumps({'ok': False, 'reason': f'unknown action {action}'})

    @classmethod
    def _push_selection(cls, palette):
        _safe(lambda: palette.sendInfoToHTML('selectionChanged', json.dumps(cls.read_ops())))

    # ---------------------------------------------------------------- reading
    @classmethod
    def _cam(cls):
        app = adsk.core.Application.get()
        doc = app.activeDocument
        if doc is None:
            return None, 'No document is open.'
        product = _safe(lambda: doc.products.itemByProductType(config.CAM_PRODUCT_ID))
        cam = adsk.cam.CAM.cast(product) if product else None
        if cam is None:
            return None, 'This document has no Manufacture (CAM) data.'
        return cam, None

    @classmethod
    def _selected_operations(cls):
        """Selected operations, expanding selected setups, folders and patterns. Deduplicated, in order."""
        sel = adsk.core.Application.get().userInterface.activeSelections
        ops, seen = [], set()
        for i in range(sel.count):
            ent = sel.item(i).entity
            kind = getattr(ent, 'objectType', '')
            if kind == _OPERATION:
                found = [adsk.cam.Operation.cast(ent)]
            elif kind in (_SETUP, _FOLDER, _PATTERN):
                found = _children_ops(ent)
            else:
                continue
            for op in found:
                key = (_safe(lambda: op.parentSetup.name, ''), _safe(lambda: op.name, ''))
                if key not in seen:
                    seen.add(key)
                    ops.append(op)
        return ops

    @classmethod
    def _read_op(cls, op) -> dict:
        name = _safe(lambda: op.name, '?') or '?'
        strategy = _safe(lambda: op.strategy, '') or ''
        setup = _safe(lambda: op.parentSetup)
        setup_name = _safe(lambda: setup.name, '') or ''
        if setup is not None:
            cls._setups[setup_name] = setup
        tool = _safe(lambda: op.tool)
        if tool is None:
            return {'ok': False, 'operation': name, 'setup': setup_name, 'strategy': strategy,
                    'strategyLabel': cam_mapping.strategy_label(strategy), 'reason': 'No tool.'}
        material = None
        if setup is not None:
            attr = _safe(lambda: setup.attributes.itemByName(config.ATTR_GROUP, config.ATTR_MATERIAL))
            material = _safe(lambda: attr.value) if attr else None
        payload = cam_mapping.build_payload(
            strategy,
            cam_mapping.params_to_dict(op.parameters),
            cam_mapping.params_to_dict(tool.parameters),
            op_name=name, material=material)
        payload['setup'] = setup_name
        payload['id'] = f'{setup_name}\u241f{name}'
        return payload

    @classmethod
    def read_ops(cls) -> dict:
        """Every selected operation (setups expand to their operations). Never raises."""
        try:
            cam, reason = cls._cam()
            if cam is None:
                return {'ok': False, 'reason': reason, 'ops': []}
            ops = cls._selected_operations()
            if not ops:
                return {'ok': False, 'empty': True, 'ops': [],
                        'reason': 'Select an operation in the CAM browser. Select several, or a whole setup, to optimize them together.'}
            cls._setups = {}
            out = [cls._read_op(op) for op in ops[:MAX_OPS]]
            result = {'ok': True, 'ops': out}
            if len(ops) > MAX_OPS:
                result['note'] = f'Showing the first {MAX_OPS} of {len(ops)} operations.'
            return result
        except Exception:
            Utils.handleError('read_ops')
            return {'ok': False, 'reason': 'Couldn’t read the selection. See the Text Command window for details.', 'ops': []}

    @classmethod
    def read_selection(cls) -> dict:
        """The first readable selected operation, in the full calculator's single-op shape."""
        result = cls.read_ops()
        if not result.get('ok'):
            return {'ok': False, 'reason': result.get('reason', '')}
        for p in result['ops']:
            if p.get('ok'):
                return p
        first = result['ops'][0]
        return {'ok': False, 'reason': f'“{first.get("operation")}”: {first.get("reason")}'}

    @classmethod
    def set_material(cls, material, setups=None) -> dict:
        names = setups if isinstance(setups, list) and setups else list(cls._setups)
        targets = [cls._setups[n] for n in names if n in cls._setups]
        if not targets or not isinstance(material, str) or not material:
            return {'ok': False, 'reason': 'No setup to store the material on. Select an operation first.'}
        try:
            for s in targets:
                s.attributes.add(config.ATTR_GROUP, config.ATTR_MATERIAL, material)
            return {'ok': True, 'setups': [_safe(lambda: s.name, '') for s in targets],
                    'setup': _safe(lambda: targets[0].name, '')}
        except Exception:
            Utils.handleError('set_material')
            return {'ok': False, 'reason': 'Couldn’t save the material on the setup.'}
