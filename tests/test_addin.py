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

    cam.CAM = CAM
    cam.Operation = Operation
    adsk.core, adsk.cam = core, cam
    sys.modules.update({'adsk': adsk, 'adsk.core': core, 'adsk.cam': cam})


_install_fake_adsk()

from djr_cutoptimizer.commands.optimizer import cam_mapping, profiles  # noqa: E402
from djr_cutoptimizer.commands.optimizer.palette_command import OptimizerCommand  # noqa: E402
import sync_web  # noqa: E402


class _Param:
    def __init__(self, name, expression, value):
        self.name, self.expression, self.value = name, expression, types.SimpleNamespace(value=value)


class _Params:
    def __init__(self, rows):
        self._rows = [_Param(*r) for r in rows]

    @property
    def count(self):
        return len(self._rows)

    def item(self, i):
        return self._rows[i]


class _Attrs:
    def __init__(self):
        self.store = {}

    def itemByName(self, group, name):
        v = self.store.get((group, name))
        return types.SimpleNamespace(value=v) if v is not None else None

    def add(self, group, name, value):
        self.store[(group, name)] = value


def _fake_op(strategy='adaptive2d', tool_rows=None, op_rows=None):
    setup = types.SimpleNamespace(name='Setup1', attributes=_Attrs())
    tool = types.SimpleNamespace(parameters=_Params(tool_rows if tool_rows is not None else [
        ('tool_diameter', '6 mm', 0.6), ('tool_numberOfFlutes', '4', 4), ('tool_fluteLength', '18 mm', 1.8),
        ('tool_bodyLength', '20 mm', 2.0)]))
    return types.SimpleNamespace(
        objectType='adsk::cam::Operation', name='Adaptive1', strategy=strategy, tool=tool, parentSetup=setup,
        parameters=_Params(op_rows if op_rows is not None else [
            ('tool_spindleSpeed', '24000 rpm', 24000), ('tool_feedCutting', '6278 mm/min', 627.8),
            ('optimalLoad', '1.67 mm', 0.167), ('maximumStepdown', '15 mm', 1.5)]))


def _cam_doc():
    cam = types.SimpleNamespace(is_cam=True)
    return types.SimpleNamespace(products=types.SimpleNamespace(itemByProductType=lambda t: cam))


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

    def test_page_has_fusion_bridge(self):
        with open(os.path.join(ROOT, 'web', 'index.html'), encoding='utf-8') as f:
            html = f.read()
        for needle in ('fusionJavaScriptHandler', 'fusionSendData', 'src="optimizer.js"'):
            self.assertIn(needle, html)


if __name__ == '__main__':
    unittest.main()
