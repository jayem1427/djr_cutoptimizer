"""
"Optimize feeds & speeds": a Manufacture toolbar button that opens the compact
optimizer panel (web/panel.html) and keeps it in step with the CAM selection.

Bridge:
  JS -> Python: adsk.fusionSendData(action, json)  -> incomingFromHTML (returnData answers)
  Python -> JS: palette.sendInfoToHTML(action, json) -> window.fusionJavaScriptHandler.handle
Actions from the page: ready, readOps, getLimits, saveLimits, setMaterial, apply, revert.
Actions to the page:   selectionChanged (same shape as readOps), fusionStatus.
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


def _op_id(setup_name: str, op_name: str) -> str:
    return f'{setup_name}␟{op_name}'


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
    _ops: dict = {}               # op id -> operation, from the last read (for apply)
    _last_apply: list = []        # [{id, op, snap}] from the last apply (for revert)

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
        cls._setups, cls._ops, cls._last_apply = {}, {}, []

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
        elif action == 'apply':
            args.returnData = json.dumps(cls.apply(data.get('items'), data.get('clearance')))
        elif action == 'revert':
            args.returnData = json.dumps(cls.revert())
        elif action == 'savePreset':
            args.returnData = json.dumps(cls.save_preset(data))
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
            op_name=name, material=material,
            tool_json=_safe(lambda: tool.toJson()))
        payload['setup'] = setup_name
        payload['preset'] = _safe(lambda: op.toolPreset.name) or None
        payload['id'] = _op_id(setup_name, name)
        cls._ops[payload['id']] = op
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
            cls._setups, cls._ops = {}, {}
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
        """The first readable selected operation (single-op shape)."""
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

    # ---------------------------------------------------------------- writing
    @classmethod
    def _find_op(cls, cam, op_id):
        op = cls._ops.get(op_id)
        if op is not None and _safe(lambda: op.isValid, True):
            return op
        all_ops = _safe(lambda: cam.allOperations)
        for i in range(_safe(lambda: all_ops.count, 0) or 0):
            o = all_ops.item(i)
            if _op_id(_safe(lambda: o.parentSetup.name, ''), _safe(lambda: o.name, '')) == op_id:
                return o
        return None

    @staticmethod
    def _restore(op, snap):
        """Put parameters back as they were, newest write first."""
        for name, kind, old_expr, old_value in reversed(snap):
            p = _safe(lambda: op.parameters.itemByName(name))
            if p is None:
                continue
            if kind == 'bool':
                _safe(lambda: setattr(p.value, 'value', bool(old_value)))
            else:
                _safe(lambda: setattr(p, 'expression', old_expr))

    @staticmethod
    def _write_one(op, name, expr, kind, target, snap):
        """Write one parameter and read it back. Returns an error message, or None."""
        p = _safe(lambda: op.parameters.itemByName(name))
        if p is None:
            return f'parameter {name} not found'
        if _safe(lambda: p.isEditable, True) is False:
            return f'{name} isn’t editable (is it locked or driven by another setting?)'
        old_expr, old_value = _safe(lambda: p.expression, ''), _safe(lambda: p.value.value)
        snap.append((name, kind, old_expr, old_value))
        try:
            if kind == 'bool':
                p.value.value = bool(target)
            else:
                p.expression = expr
        except Exception as e:
            return f'Fusion refused {name} = {expr} ({e})'
        new_expr, new_value = _safe(lambda: p.expression, ''), _safe(lambda: p.value.value)
        if not cam_mapping.write_matches(kind, target, new_expr, new_value):
            return f'{name} reads back as “{new_expr}” instead of {expr}'
        return None

    @classmethod
    def _generate(cls, cam, op_list) -> bool:
        try:
            coll = adsk.core.ObjectCollection.create()
            for op in op_list:
                coll.add(op)
            cam.generateToolpath(coll)
            return True
        except Exception:
            Utils.handleError('generateToolpath')
            return False

    @classmethod
    def apply(cls, items, clearance) -> dict:
        """Write the panel's feeds and speeds (and finishing stock) to operations, then
        regenerate them. Each op is all-or-nothing: on any failure it is put back."""
        try:
            cam, reason = cls._cam()
            if cam is None:
                return {'ok': False, 'reason': reason, 'results': []}
            if not isinstance(items, list) or not items:
                return {'ok': False, 'reason': 'Nothing to apply.', 'results': []}
            results, changed, undo = [], [], []
            for it in items:
                if not isinstance(it, dict):
                    continue
                op_id = str(it.get('id', ''))
                res = {'id': op_id, 'ok': False}
                results.append(res)
                op = cls._find_op(cam, op_id)
                if op is None:
                    res['reason'] = 'Operation not found. Was it renamed or deleted? Reselect it.'
                    continue
                payload = cls._read_op(op)              # fresh read: where each value lives now
                if not payload.get('ok'):
                    res['reason'] = payload.get('reason', 'Couldn’t read the operation.')
                    continue
                try:
                    plan = cam_mapping.plan_writes(payload['src'], it, clearance, payload.get('stockSrc'),
                                                   payload['op'].get('aeMax'), payload.get('rampSrc'))
                except ValueError as e:
                    res['reason'] = str(e)
                    continue
                snap, err = [], None
                for name, expr, kind, target in plan:
                    err = cls._write_one(op, name, expr, kind, target, snap)
                    if err:
                        break
                if err:
                    cls._restore(op, snap)
                    res['reason'] = err[:1].upper() + err[1:] + '. Put back as it was.'
                    continue
                res.update(ok=True, written=[f'{name} = {expr}' for name, expr, _, _ in plan])
                undo.append({'id': op_id, 'op': op, 'snap': snap})
                changed.append(op)
            if undo:
                cls._last_apply = undo
            generating = cls._generate(cam, changed) if changed else False
            n_ok = len(changed)
            return {'ok': n_ok > 0, 'results': results, 'applied': n_ok, 'failed': len(results) - n_ok,
                    'generating': generating, 'canRevert': bool(cls._last_apply),
                    'reason': '' if n_ok else 'No operation was changed.'}
        except Exception:
            Utils.handleError('apply')
            return {'ok': False, 'reason': 'Apply failed. See the Text Command window for details.', 'results': []}

    # ---------------------------------------------------------------- presets
    @staticmethod
    def _set_preset_values(preset, writes) -> list:
        """Write the values into a preset. Returns a list of problems (empty when all went in)."""
        problems = []
        for name, expr, kind, target in writes:
            p = _safe(lambda: preset.parameters.itemByName(name))
            if p is None:
                problems.append(f'{name} isn’t a preset parameter')
                continue
            try:
                p.expression = expr
            except Exception as e:
                problems.append(f'Fusion refused {name} = {expr} ({e})')
                continue
            if not cam_mapping.write_matches(kind, target, _safe(lambda: p.expression, ''), _safe(lambda: p.value.value)):
                problems.append(f'{name} reads back as “{_safe(lambda: p.expression, "")}”')
        return problems

    @staticmethod
    def _preset_on(tool, name):
        """The preset called `name` on this tool, created if it doesn't exist yet."""
        presets = tool.presets
        found = _safe(lambda: presets.itemsByName(name))
        if found:
            for i in range(len(found)):
                if (_safe(lambda: found[i].name) or '').lower() == name.lower():   # Fusion matches names case-insensitively
                    found[i].name = name
                    return found[i], False
        preset = presets.add()
        preset.name = name
        return preset, True

    @staticmethod
    def _library_tool(lib, guid):
        """The tool with this guid in a tool library (or document tool library), else None."""
        for i in range(_safe(lambda: lib.count, 0) or 0):
            t = _safe(lambda: lib.item(i))
            if t is not None and cam_mapping.tool_guid(_safe(lambda: t.toJson())) == guid:
                return t
        return None

    @classmethod
    def _save_to_libraries(cls, guid, name, writes) -> str:
        """Add the preset to the same tool in the user's local and cloud tool libraries."""
        try:
            libs = adsk.cam.CAMManager.get().libraryManager.toolLibraries
        except Exception as e:
            return f'tool libraries aren’t reachable from the API ({e})'
        urls, stack = [], []
        for loc in ('LocalLibraryLocation', 'CloudLibraryLocation'):
            where = getattr(adsk.cam.LibraryLocations, loc, None)
            root = _safe(lambda: libs.urlByLocation(where)) if where is not None else None
            if root is not None:
                stack.append(root)
        while stack:
            url = stack.pop()
            for i in range(_safe(lambda: len(libs.childAssetURLs(url)), 0) or 0):
                urls.append(libs.childAssetURLs(url)[i])
            for i in range(_safe(lambda: len(libs.childFolderURLs(url)), 0) or 0):
                stack.append(libs.childFolderURLs(url)[i])
        saved = []
        for url in urls:
            lib = _safe(lambda: libs.toolLibraryAtURL(url))
            tool = cls._library_tool(lib, guid) if lib is not None else None
            if tool is None:
                continue
            try:
                preset, _ = cls._preset_on(tool, name)
                problems = cls._set_preset_values(preset, writes)
                if problems:
                    return f'{_safe(lambda: url.leafName, "library")}: ' + '; '.join(problems)
                if not libs.updateToolLibrary(url, lib):
                    return f'Fusion didn’t save {_safe(lambda: url.leafName, "the library")}'
                saved.append(_safe(lambda: url.leafName, 'library') or 'library')
            except Exception as e:
                return f'couldn’t write to {_safe(lambda: url.leafName, "the library")} ({e})'
        if not saved:
            return 'this tool isn’t in any of your local or cloud tool libraries'
        return 'saved to ' + ', '.join(saved)

    @classmethod
    def save_preset(cls, item) -> dict:
        """Save an optimized cut as a preset on the operation's tool.

        item: {id, name, values: {n, vf, rampN?, rampVf?, ae?, ap?}, assign?, library?}.
        The preset is added to (or updates) the tool in this document; `assign` makes the
        operation use it; `library` also adds it to the same tool in the user's tool libraries.
        """
        try:
            cam, reason = cls._cam()
            if cam is None:
                return {'ok': False, 'reason': reason}
            item = item if isinstance(item, dict) else {}
            name = str(item.get('name') or '').strip()[:80]
            if not name:
                return {'ok': False, 'reason': 'Give the preset a name.'}
            try:
                writes = cam_mapping.preset_writes(item.get('values') or {})
            except ValueError as e:
                return {'ok': False, 'reason': str(e)}
            op = cls._find_op(cam, str(item.get('id', '')))
            if op is None:
                return {'ok': False, 'reason': 'Operation not found. Reselect it.'}
            op_tool = _safe(lambda: op.tool)
            if op_tool is None or _safe(lambda: op_tool.presets) is None:
                return {'ok': False, 'reason': 'This Fusion version can’t add tool presets from an add-in.'}
            guid = cam_mapping.tool_guid(_safe(lambda: op_tool.toJson()))
            doc_lib = _safe(lambda: cam.documentToolLibrary)
            tool = (cls._library_tool(doc_lib, guid) if doc_lib is not None and guid else None) or op_tool
            preset, created = cls._preset_on(tool, name)
            problems = cls._set_preset_values(preset, writes)
            if problems:
                return {'ok': False, 'reason': 'The preset wasn’t saved: ' + '; '.join(problems)}
            if doc_lib is not None and tool is not op_tool:
                try:
                    doc_lib.update(tool)
                except TypeError:
                    doc_lib.update(tool, False)
            out = {'ok': True, 'name': name, 'created': created, 'saved': [f'{k} = {e}' for k, e, _, _ in writes]}
            if item.get('assign'):
                fresh = _safe(lambda: op.tool)
                found = _safe(lambda: fresh.presets.itemsByName(name))
                target = found[0] if found else None
                ok = False
                if target is not None:
                    try:
                        op.toolPreset = target
                        ok = _safe(lambda: op.toolPreset.name) == name
                    except Exception:
                        ok = False
                out['assigned'] = ok
            if item.get('library'):
                out['library'] = cls._save_to_libraries(guid, name, writes) if guid else 'the tool has no id to match in a library'
            return out
        except Exception as e:
            return {'ok': False, 'reason': f'Saving the preset failed ({e})'}

    @classmethod
    def revert(cls) -> dict:
        """Undo the last apply: every parameter it wrote goes back to its old expression."""
        try:
            if not cls._last_apply:
                return {'ok': False, 'reason': 'Nothing to revert.'}
            cam, reason = cls._cam()
            done = []
            for entry in cls._last_apply:
                op = entry['op'] if _safe(lambda: entry['op'].isValid, True) else (
                    cls._find_op(cam, entry['id']) if cam else None)
                if op is None:
                    continue
                cls._restore(op, entry['snap'])
                done.append(op)
            cls._last_apply = []
            if cam is not None and done:
                cls._generate(cam, done)
            return {'ok': bool(done), 'reverted': len(done),
                    'reason': '' if done else 'The operations from the last apply are gone.'}
        except Exception:
            Utils.handleError('revert')
            return {'ok': False, 'reason': 'Revert failed. See the Text Command window for details.'}
