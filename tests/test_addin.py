"""
Add-in tests that run without Fusion. Stdlib only:

    python -m pytest            (or: python -m unittest discover -s tests -v)

A small fake of adsk.core / adsk.cam covers the "never crash" paths: no document,
no CAM, nothing selected, unsupported operation.
"""
import json
import os
import sys
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                      # the repo is the add-in folder, named djr_cutoptimizer
# Import the add-in as the package `djr_cutoptimizer` from the parent folder. The repo
# root itself must not be on the path, or djr_cutoptimizer.py would shadow the package.
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != ROOT]
sys.path.insert(0, os.path.dirname(ROOT))
sys.path.insert(0, os.path.join(ROOT, 'tools'))


# ----------------------------------------------------------------- fake Fusion
class _State:
    document = None
    selections = []


class _Selections:
    @property
    def count(self):
        return len(_State.selections)

    def item(self, i):
        return types.SimpleNamespace(entity=_State.selections[i])


class _App:
    @staticmethod
    def get():
        return _App()

    @property
    def activeDocument(self):
        return _State.document

    @property
    def userInterface(self):
        return types.SimpleNamespace(activeSelections=_Selections(), messageBox=lambda *a, **k: None)

    def log(self, *a, **k):
        pass


def _install_fake_adsk():
    adsk = types.ModuleType('adsk')
    core = types.ModuleType('adsk.core')
    cam = types.ModuleType('adsk.cam')
    core.Application = _App
    core.LogLevels = types.SimpleNamespace(InfoLogLevel=0, WarningLogLevel=1, ErrorLogLevel=2)
    core.LogTypes = types.SimpleNamespace(FileLogType=0, ConsoleLogType=1)
    core.Event = object
    core.CommandCreatedEventArgs = object
    core.HTMLEventArgs = object
    core.PaletteDockingStates = types.SimpleNamespace(PaletteDockStateRight=1)

    class CAM:
        @staticmethod
        def cast(obj):
            return obj if getattr(obj, 'is_cam', False) else None

    class Operation:
        @staticmethod
        def classType():
            return 'adsk::cam::Operation'

        @staticmethod
        def cast(obj):
            return obj

    class ObjectCollection(list):
        @staticmethod
        def create():
            return ObjectCollection()

        def add(self, x):
            self.append(x)

    core.ObjectCollection = ObjectCollection
    cam.CAM = CAM
    cam.Operation = Operation
    adsk.core, adsk.cam = core, cam
    sys.modules.update({'adsk': adsk, 'adsk.core': core, 'adsk.cam': cam})


_install_fake_adsk()

from djr_cutoptimizer.commands.optimizer import cam_mapping, profiles  # noqa: E402
from djr_cutoptimizer.commands.optimizer.palette_command import OptimizerCommand, palette_url  # noqa: E402
import sync_web  # noqa: E402


class _Param:
    """A CAM parameter. Setting `expression` behaves like Fusion: the value follows, and an
    expression in `refuse` raises (as Fusion does for a bad unit)."""
    refuse = set()

    def __init__(self, name, expression, value, editable=True):
        self.name, self._expr, self.value, self.isEditable = name, expression, types.SimpleNamespace(value=value), editable

    @property
    def expression(self):
        return self._expr

    @expression.setter
    def expression(self, e):
        if e in _Param.refuse:
            raise RuntimeError('bad expression')
        self._expr = e
        num = cam_mapping.parse_quantity(e, 'len')
        if num is not None:
            self.value.value = num / 10.0          # internal cm, like Fusion


class _Params:
    def __init__(self, rows):
        self._rows = [_Param(*r) for r in rows]

    @property
    def count(self):
        return len(self._rows)

    def item(self, i):
        return self._rows[i]

    def itemByName(self, name):
        return next((p for p in self._rows if p.name == name), None)

    def expr(self, name):
        return self.itemByName(name).expression


class _Attrs:
    def __init__(self):
        self.store = {}

    def itemByName(self, group, name):
        v = self.store.get((group, name))
        return types.SimpleNamespace(value=v) if v is not None else None

    def add(self, group, name, value):
        self.store[(group, name)] = value


class _Coll:
    def __init__(self, items):
        self._items = items

    @property
    def count(self):
        return len(self._items)

    def item(self, i):
        return self._items[i]


def _fake_setup(name='Setup1', ops=()):
    setup = types.SimpleNamespace(objectType='adsk::cam::Setup', name=name, attributes=_Attrs())
    for op in ops:
        op.parentSetup = setup
    setup.allOperations = _Coll(list(ops))
    return setup


def _fake_op(strategy='adaptive2d', tool_rows=None, op_rows=None, name='Adaptive1', setup=None):
    setup = setup or types.SimpleNamespace(name='Setup1', attributes=_Attrs())
    tool = types.SimpleNamespace(parameters=_Params(tool_rows if tool_rows is not None else [
        ('tool_diameter', '6 mm', 0.6), ('tool_numberOfFlutes', '4', 4), ('tool_fluteLength', '18 mm', 1.8),
        ('tool_bodyLength', '20 mm', 2.0), ('tool_number', '12', 12), ('tool_description', "'6mm 4FL flat'", '')]))
    return types.SimpleNamespace(
        objectType='adsk::cam::Operation', name=name, strategy=strategy, tool=tool, parentSetup=setup,
        parameters=_Params(op_rows if op_rows is not None else [
            ('tool_spindleSpeed', '24000 rpm', 24000), ('tool_feedCutting', '6278 mm/min', 627.8),
            ('optimalLoad', '1.67 mm', 0.167), ('maximumStepdown', '15 mm', 1.5)]))


def _cam_doc():
    cam = types.SimpleNamespace(is_cam=True, generated=[])
    cam.generateToolpath = lambda coll: cam.generated.extend(coll)
    return types.SimpleNamespace(products=types.SimpleNamespace(itemByProductType=lambda t: cam), cam=cam)


# An op with stock-to-leave parameters (names as the mapping expects them).
_FINISH_ROWS = [
    ('tool_spindleSpeed', '18000 rpm', 18000), ('tool_feedCutting', '1500 mm/min', 150.0),
    ('optimalLoad', '0.5 mm', 0.05), ('maximumStepdown', '10 mm', 1.0),
    ('stockToLeave', 'false', False), ('radialStockToLeave', '0.3 mm', 0.03), ('axialStockToLeave', '0.2 mm', 0.02)]


# ----------------------------------------------------------------------- tests
class ParseQuantity(unittest.TestCase):
    def test_units(self):
        P = cam_mapping.parse_quantity
        self.assertAlmostEqual(P('1200 mm/min', 'feed'), 1200)
        self.assertAlmostEqual(P('50 in/min', 'feed'), 1270)
        self.assertAlmostEqual(P('0.25 in', 'len'), 6.35)
        self.assertAlmostEqual(P('6mm', 'len'), 6)
        self.assertAlmostEqual(P('1000 ft/min', 'speed'), 304.8)
        self.assertAlmostEqual(P('24000 rpm', 'rpm'), 24000)
        self.assertAlmostEqual(P('4', 'count'), 4)

    def test_not_literal(self):
        self.assertIsNone(cam_mapping.parse_quantity('tool_feedCutting * 0.5', 'feed'))
        self.assertIsNone(cam_mapping.parse_quantity('12', 'len'))       # length without a unit is ambiguous

    def test_internal_fallback(self):
        params = {'tool_feedPlunge': ('tool_feedCutting * 0.5', 300.0)}
        self.assertAlmostEqual(cam_mapping.read_value(params, ['tool_feedPlunge'], 'feed'), 3000.0)


class BuildPayload(unittest.TestCase):
    def test_adaptive(self):
        op = _fake_op()
        p = cam_mapping.build_payload('adaptive2d', cam_mapping.params_to_dict(op.parameters),
                                      cam_mapping.params_to_dict(op.tool.parameters), 'Adaptive1')
        self.assertTrue(p['ok'])
        self.assertEqual(p['tool']['z'], 4)
        self.assertAlmostEqual(p['tool']['D'], 6)
        self.assertAlmostEqual(p['op']['ae'], 1.67)
        self.assertAlmostEqual(p['op']['fz'], 6278 / (24000 * 4), places=6)
        self.assertEqual(p['missing'], [])

    def _flutes(self, tool_json=None):
        rows = [('tool_diameter', '9.525 mm', 0.9525), ('tool_numberOfFlutes', '1', 1),
                ('tool_description', "'3 FLUTE 3/8\" FLAT'", '')]
        op = _fake_op(tool_rows=rows)
        return cam_mapping.build_payload('adaptive', cam_mapping.params_to_dict(op.parameters),
                                         cam_mapping.params_to_dict(op.tool.parameters), 'R2', tool_json=tool_json)['tool']['z']

    def test_flutes_trust_library_not_description(self):
        self.assertEqual(self._flutes(), 1)

    def test_flutes_from_tool_json_first(self):
        self.assertEqual(self._flutes('{"geometry": {"NOF": 3}}'), 3)
        self.assertEqual(self._flutes('not json'), 1)

    def test_slot_is_full_width(self):
        op = _fake_op()
        p = cam_mapping.build_payload('slot', cam_mapping.params_to_dict(op.parameters),
                                      cam_mapping.params_to_dict(op.tool.parameters))
        self.assertAlmostEqual(p['op']['ae'], 6)

    def test_refused(self):
        for s in ('drill', 'thread', 'parallel', 'some_new_thing'):
            p = cam_mapping.build_payload(s, {}, {})
            self.assertFalse(p['ok'])
            self.assertTrue(p['reason'])

    def test_no_diameter(self):
        p = cam_mapping.build_payload('adaptive2d', {}, {})
        self.assertFalse(p['ok'])
        self.assertIn('diameter', p['reason'])


class ReadSelection(unittest.TestCase):
    def setUp(self):
        _State.document, _State.selections = None, []

    def test_no_document(self):
        r = OptimizerCommand.read_selection()
        self.assertFalse(r['ok'])
        self.assertIn('No document', r['reason'])

    def test_not_cam(self):
        _State.document = types.SimpleNamespace(products=types.SimpleNamespace(itemByProductType=lambda t: None))
        self.assertIn('Manufacture', OptimizerCommand.read_selection()['reason'])

    def test_nothing_selected(self):
        _State.document = _cam_doc()
        self.assertIn('Select an operation', OptimizerCommand.read_selection()['reason'])

    def test_non_operation_selected(self):
        _State.document = _cam_doc()
        _State.selections = [types.SimpleNamespace(objectType='adsk::cam::Setup')]
        self.assertFalse(OptimizerCommand.read_selection()['ok'])

    def test_unsupported_operation(self):
        _State.document = _cam_doc()
        _State.selections = [_fake_op('drill')]
        r = OptimizerCommand.read_selection()
        self.assertFalse(r['ok'])
        self.assertIn('Drilling', r['reason'])

    def test_reads_and_stores_material(self):
        _State.document = _cam_doc()
        op = _fake_op()
        _State.selections = [op]
        r = OptimizerCommand.read_selection()
        self.assertTrue(r['ok'], r)
        self.assertIsNone(r['material'])
        self.assertTrue(OptimizerCommand.set_material('Aluminium (wrought)')['ok'])
        self.assertEqual(OptimizerCommand.read_selection()['material'], 'Aluminium (wrought)')
        json.dumps(r)  # the payload must serialize for sendInfoToHTML

    def test_broken_operation_does_not_raise(self):
        _State.document = _cam_doc()
        bad = types.SimpleNamespace(objectType='adsk::cam::Operation', name='Bad', strategy='adaptive2d', tool=None)
        _State.selections = [bad]
        self.assertFalse(OptimizerCommand.read_selection()['ok'])


class PaletteUrl(unittest.TestCase):
    def test_windows_path_has_no_backslashes(self):
        # v0.1.0 bug: Fusion showed ERR_INVALID_URL for file:///C:/%5CUsers%5C...
        p = 'C:\\Users\\me\\AppData\\Roaming\\Autodesk\\Autodesk Fusion 360\\API\\AddIns\\djr_cutoptimizer\\web\\index.html'
        self.assertEqual(palette_url(p),
                         'C:/Users/me/AppData/Roaming/Autodesk/Autodesk Fusion 360/API/AddIns/djr_cutoptimizer/web/index.html')

    def test_posix_path_unchanged(self):
        p = '/Users/me/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/djr_cutoptimizer/web/index.html'
        self.assertEqual(palette_url(p), p)


class ReadOps(unittest.TestCase):
    def setUp(self):
        _State.document, _State.selections = _cam_doc(), []

    def test_card_fields(self):
        _State.selections = [_fake_op()]
        r = OptimizerCommand.read_ops()
        self.assertTrue(r['ok'])
        p = r['ops'][0]
        self.assertEqual(p['toolNumber'], '12')
        self.assertEqual(p['toolDesc'], '6mm 4FL flat')
        self.assertEqual(p['strategyLabel'], '2D Adaptive')
        self.assertEqual(p['setup'], 'Setup1')

    def test_empty_selection_is_flagged(self):
        r = OptimizerCommand.read_ops()
        self.assertFalse(r['ok'])
        self.assertTrue(r['empty'])

    def test_setup_expands_to_its_operations(self):
        a, b, d = _fake_op(name='R1'), _fake_op('contour2d', name='F1'), _fake_op('drill', name='D1')
        setup = _fake_setup('Op1', [a, b, d])
        _State.selections = [setup]
        r = OptimizerCommand.read_ops()
        self.assertEqual([p['operation'] for p in r['ops']], ['R1', 'F1', 'D1'])
        self.assertEqual([p['ok'] for p in r['ops']], [True, True, False])
        self.assertIn('Drilling', r['ops'][2]['reason'])
        json.dumps(r)

    def test_op_and_its_setup_both_selected_is_deduplicated(self):
        a = _fake_op(name='R1')
        setup = _fake_setup('Op1', [a])
        _State.selections = [a, setup]
        self.assertEqual(len(OptimizerCommand.read_ops()['ops']), 1)

    def test_material_saved_on_every_setup(self):
        a, b = _fake_op(name='R1'), _fake_op(name='R2')
        s1, s2 = _fake_setup('S1', [a]), _fake_setup('S2', [b])
        _State.selections = [s1, s2]
        OptimizerCommand.read_ops()
        r = OptimizerCommand.set_material('Aluminium (wrought)', ['S1', 'S2'])
        self.assertTrue(r['ok'])
        self.assertEqual(sorted(r['setups']), ['S1', 'S2'])
        self.assertEqual([p['material'] for p in OptimizerCommand.read_ops()['ops']], ['Aluminium (wrought)'] * 2)


class PlanWrites(unittest.TestCase):
    SRC = {'n': 'tool_spindleSpeed', 'vf': 'tool_feedCutting', 'ae': 'optimalLoad', 'ap': 'maximumStepdown'}
    STOCK = {'radial': 'radialStockToLeave', 'axial': 'axialStockToLeave', 'flag': 'stockToLeave'}

    def test_rough_writes_rpm_and_feed_only(self):
        w = cam_mapping.plan_writes(self.SRC, {'n': 17999.7, 'vf': 3456.9, 'pass': 'rough'}, 0.05, self.STOCK)
        self.assertEqual([(n, e) for n, e, _, _ in w],
                         [('tool_spindleSpeed', '17999 rpm'), ('tool_feedCutting', '3456 mm/min')])   # rounded down

    def test_rough_with_geometry(self):
        w = cam_mapping.plan_writes(self.SRC, {'n': 18000, 'vf': 3000, 'ae': 0.61234, 'ap': 12}, 0.05)
        self.assertIn(('optimalLoad', '0.6123 mm'), [(n, e) for n, e, _, _ in w])
        self.assertIn(('maximumStepdown', '12 mm'), [(n, e) for n, e, _, _ in w])

    def test_wall_finish_leaves_clearance_on_floor(self):
        w = {n: e for n, e, _, _ in cam_mapping.plan_writes(self.SRC, {'n': 18000, 'vf': 2000, 'pass': 'wall'}, 0.05, self.STOCK)}
        self.assertEqual(w['radialStockToLeave'], '0 mm')
        self.assertEqual(w['axialStockToLeave'], '0.05 mm')
        self.assertEqual(w['stockToLeave'], 'true')
        self.assertNotIn('optimalLoad', w)                  # finish passes never change the engagement

    def test_floor_finish_leaves_clearance_on_wall(self):
        w = {n: e for n, e, _, _ in cam_mapping.plan_writes(self.SRC, {'n': 18000, 'vf': 2000, 'pass': 'floor'}, 0.05, self.STOCK)}
        self.assertEqual(w['radialStockToLeave'], '0.05 mm')
        self.assertEqual(w['axialStockToLeave'], '0 mm')

    def test_refuses_rather_than_half_apply(self):
        P = cam_mapping.plan_writes
        with self.assertRaises(ValueError):
            P(self.SRC, {'n': 18000, 'vf': 2000, 'pass': 'wall'}, 0.05, {'radial': None, 'axial': None})
        with self.assertRaises(ValueError):
            P(dict(self.SRC, ae=None), {'n': 18000, 'vf': 2000, 'ae': 1.0}, 0.05)
        with self.assertRaises(ValueError):
            P(self.SRC, {'n': 0, 'vf': 2000}, 0.05)
        with self.assertRaises(ValueError):
            P(self.SRC, {'n': 18000, 'vf': 2000, 'pass': 'chamfer'}, 0.05)
        with self.assertRaises(ValueError):
            P(self.SRC, {'n': 18000, 'vf': 2000, 'pass': 'wall'}, -1, self.STOCK)

    def test_write_matches(self):
        M = cam_mapping.write_matches
        self.assertTrue(M('rpm', 18000, '18000 rpm', 18000))
        self.assertTrue(M('feed', 2000, '2000 mm/min', 200))
        self.assertTrue(M('feed', 2540, '100 in/min', None))
        self.assertFalse(M('feed', 2000, '200 mm/min', 20))
        self.assertTrue(M('len', 0.0, '0 mm', 0.0))
        self.assertFalse(M('len', 0.05, '0.5 mm', 0.05))
        self.assertTrue(M('bool', True, 'true', True))
        self.assertFalse(M('bool', True, 'false', False))


class Apply(unittest.TestCase):
    def setUp(self):
        _Param.refuse = set()
        _State.document = _cam_doc()
        OptimizerCommand._last_apply = []

    def _select(self, *ops):
        _State.selections = list(ops)
        r = OptimizerCommand.read_ops()
        self.assertTrue(r['ok'], r)
        return {p['operation']: p for p in r['ops']}

    def test_payload_has_sources_and_stock(self):
        p = self._select(_fake_op('contour2d', op_rows=list(_FINISH_ROWS), name='Wall'))['Wall']
        self.assertEqual(p['src']['ae'], 'optimalLoad')
        self.assertAlmostEqual(p['stock']['radial'], 0.3)
        self.assertEqual(p['stockSrc'], {'radial': 'radialStockToLeave', 'axial': 'axialStockToLeave', 'flag': 'stockToLeave'})
        json.dumps(p)

    def test_apply_wall_finish_and_revert(self):
        op = _fake_op('contour2d', op_rows=list(_FINISH_ROWS), name='Wall')
        p = self._select(op)['Wall']
        r = OptimizerCommand.apply([{'id': p['id'], 'n': 20000, 'vf': 2400.6, 'pass': 'wall'}], 0.05)
        self.assertTrue(r['ok'], r)
        self.assertEqual(r['applied'], 1)
        self.assertTrue(r['generating'])
        self.assertEqual(_State.document.cam.generated, [op])
        P = op.parameters
        self.assertEqual(P.expr('tool_spindleSpeed'), '20000 rpm')
        self.assertEqual(P.expr('tool_feedCutting'), '2400 mm/min')
        self.assertEqual(P.expr('radialStockToLeave'), '0 mm')
        self.assertEqual(P.expr('axialStockToLeave'), '0.05 mm')
        self.assertIs(P.itemByName('stockToLeave').value.value, True)
        self.assertEqual(P.expr('optimalLoad'), '0.5 mm')        # engagement untouched

        rv = OptimizerCommand.revert()
        self.assertTrue(rv['ok'], rv)
        self.assertEqual(P.expr('tool_spindleSpeed'), '18000 rpm')
        self.assertEqual(P.expr('radialStockToLeave'), '0.3 mm')
        self.assertIs(P.itemByName('stockToLeave').value.value, False)
        self.assertFalse(OptimizerCommand.revert()['ok'])        # nothing left to revert

    def test_failed_write_puts_the_op_back(self):
        op = _fake_op('contour2d', op_rows=list(_FINISH_ROWS), name='Wall')
        p = self._select(op)['Wall']
        _Param.refuse = {'0.05 mm'}                                  # Fusion refuses the last write
        r = OptimizerCommand.apply([{'id': p['id'], 'n': 20000, 'vf': 2400, 'pass': 'wall'}], 0.05)
        self.assertFalse(r['ok'])
        self.assertIn('Fusion refused axialStockToLeave', r['results'][0]['reason'])
        self.assertIn('Put back', r['results'][0]['reason'])
        self.assertEqual(op.parameters.expr('tool_spindleSpeed'), '18000 rpm')
        self.assertEqual(op.parameters.expr('radialStockToLeave'), '0.3 mm')
        self.assertIs(op.parameters.itemByName('stockToLeave').value.value, False)
        self.assertEqual(_State.document.cam.generated, [])

    def test_locked_parameter_is_reported(self):
        rows = [r for r in _FINISH_ROWS if r[0] != 'tool_feedCutting'] + [('tool_feedCutting', '1500 mm/min', 150.0, False)]
        op = _fake_op('adaptive2d', op_rows=rows, name='R')
        p = self._select(op)['R']
        r = OptimizerCommand.apply([{'id': p['id'], 'n': 20000, 'vf': 2400}], 0.05)
        self.assertFalse(r['ok'])
        self.assertIn('editable', r['results'][0]['reason'])
        self.assertEqual(op.parameters.expr('tool_spindleSpeed'), '18000 rpm')

    def test_finish_without_stock_params_is_refused_but_others_apply(self):
        rough = _fake_op('adaptive2d', name='Rough')                 # default rows: no stock params
        wall = _fake_op('contour2d', name='Wall')
        ps = self._select(rough, wall)
        r = OptimizerCommand.apply([{'id': ps['Rough']['id'], 'n': 20000, 'vf': 5000, 'pass': 'rough'},
                                    {'id': ps['Wall']['id'], 'n': 20000, 'vf': 2000, 'pass': 'wall'}], 0.05)
        self.assertEqual(r['applied'], 1)
        self.assertEqual(r['failed'], 1)
        self.assertIn('stock-to-leave', r['results'][1]['reason'])
        self.assertEqual(rough.parameters.expr('tool_spindleSpeed'), '20000 rpm')
        self.assertEqual(wall.parameters.expr('tool_spindleSpeed'), '24000 rpm')

    def test_unknown_op_and_bad_input(self):
        self._select(_fake_op())
        r = OptimizerCommand.apply([{'id': 'nope␟gone', 'n': 1, 'vf': 1}], 0.05)
        self.assertIn('not found', r['results'][0]['reason'])
        self.assertFalse(OptimizerCommand.apply([], 0.05)['ok'])
        self.assertFalse(OptimizerCommand.apply(None, 0.05)['ok'])

    def test_bridge_actions(self):
        op = _fake_op('contour2d', op_rows=list(_FINISH_ROWS), name='Wall')
        p = self._select(op)['Wall']
        args = types.SimpleNamespace(action='apply', returnData='',
                                     data=json.dumps({'items': [{'id': p['id'], 'n': 19000, 'vf': 2000, 'pass': 'floor'}], 'clearance': 0.05}))
        OptimizerCommand.onHTML(args)
        self.assertTrue(json.loads(args.returnData)['ok'])
        self.assertEqual(op.parameters.expr('radialStockToLeave'), '0.05 mm')
        args = types.SimpleNamespace(action='revert', returnData='', data='')
        OptimizerCommand.onHTML(args)
        self.assertTrue(json.loads(args.returnData)['ok'])
        self.assertEqual(op.parameters.expr('radialStockToLeave'), '0.3 mm')


class Profiles(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(profiles.load(d), {})
            items = {'LemonTart 6061': {'limits': {'Fmax': 30, 'slopeMax': 2.5}, 'usePow': True}}
            profiles.save(items, d)
            self.assertEqual(profiles.load(d), items)

    def test_corrupt_file(self):
        with tempfile.TemporaryDirectory() as d:
            with open(profiles.profiles_path(d), 'w') as f:
                f.write('{nope')
            self.assertEqual(profiles.load(d), {})


class WebCopy(unittest.TestCase):
    def test_bundled_page_is_present(self):
        for f in sync_web.FILES:
            self.assertTrue(os.path.isfile(os.path.join(ROOT, 'web', f)), f)

    @unittest.skipUnless(os.path.isdir(sync_web.SOURCE), 'cutcalculator checkout not next to this repo')
    def test_in_sync_with_calculator(self):
        self.assertEqual(sync_web.stale(), [], 'run python tools/sync_web.py')

    def test_panel_is_the_palette_page(self):
        from djr_cutoptimizer.commands.optimizer import palette_command
        self.assertTrue(palette_command._HTML.endswith('panel.html'))
        with open(palette_command._HTML, encoding='utf-8') as f:
            html = f.read()
        for needle in ('selectionChanged', 'readOps', 'src="optimizer.js"', 'fusionJavaScriptHandler'):
            self.assertIn(needle, html)
        self.assertNotIn('index.html', html)       # the full calculator isn't bundled any more

    def test_material_chip_table_is_complete(self):
        import re
        with open(os.path.join(ROOT, 'web', 'panel.html'), encoding='utf-8') as f:
            html = f.read()
        rows = re.findall(r'"([^"]+)":\s*\{ kc1:(\d+),\s*mc:([\d.]+), hexD:([\d.]+),\s*hmMin:([\d.]+) \}', html)
        self.assertGreaterEqual(len(rows), 15)
        for name, kc1, mc, hexd, hmmin in rows:
            self.assertTrue(0.001 <= float(hexd) <= 0.02, name)
            self.assertTrue(0.002 <= float(hmmin) <= 0.03, name)
        al = dict((r[0], r) for r in rows)['Aluminium (wrought)']
        self.assertEqual(al[1], '295')
        # 1/4" tool in aluminium: about 0.002" (0.05 mm) per tooth, as in common chip-load charts
        self.assertAlmostEqual(float(al[3]) * 6.35, 0.0508, places=3)


if __name__ == '__main__':
    unittest.main()
