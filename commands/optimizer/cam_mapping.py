"""
Pure mapping from Fusion CAM parameters to the calculator's inputs (mm, rpm, mm/min).
No adsk import, so it runs under pytest.

**The parameter names below are unverified.** They come from the handoff and common
Fusion naming. Run fusion/scripts/djr_dump_cam_params on an adaptive, a 2D contour and
a slot, commit the output to docs/cam_params/, then fix these tables to match.
"""
from __future__ import annotations

import math
import re
from typing import Optional

# Candidate parameter names, in order of preference.
OP_NAMES = {
    'n':  ['tool_spindleSpeed'],
    'vf': ['tool_feedCutting'],
    'fz': ['tool_feedPerTooth'],
    'vc': ['tool_surfaceSpeed'],
    'ae': ['optimalLoad', 'stepover', 'maximumStepover'],
    'ap': ['maximumStepdown', 'stepdown'],
}
TOOL_NAMES = {
    'D':        ['tool_diameter'],
    'z':        ['tool_numberOfFlutes'],
    'fluteLen': ['tool_fluteLength'],
    'stickout': ['tool_bodyLength', 'tool_shoulderLength', 'tool_overallLength'],
    'helix':    ['tool_helixAngle'],
    'type':     ['tool_type'],
}
# Text fields shown on the operation card (not used in the math).
TOOL_TEXT = {
    'number':      ['tool_number'],
    'description': ['tool_description', 'tool_comment'],
}
STRATEGY_LABEL = {
    'adaptive2d': '2D Adaptive', 'adaptive': '3D Adaptive', 'contour2d': '2D Contour', 'pocket2d': '2D Pocket',
    'slot': 'Slot', 'face': 'Face', 'contour': '3D Contour', 'pocket': '3D Pocket', 'drill': 'Drill',
    'bore': 'Bore', 'circular': 'Circular', 'thread': 'Thread', 'chamfer2d': 'Chamfer', 'engrave': 'Engrave',
    'parallel': 'Parallel', 'scallop': 'Scallop', 'pencil': 'Pencil', 'radial': 'Radial', 'spiral': 'Spiral',
    'morphed_spiral': 'Morphed Spiral', 'steep_and_shallow': 'Steep and Shallow', 'flow': 'Flow',
    'contour3d': '3D Contour',
}


def strategy_label(strategy: str) -> str:
    s = (strategy or '').lower()
    return STRATEGY_LABEL.get(s, strategy or '?')


def read_text(params: dict, names: list) -> Optional[str]:
    """A text or integer parameter as display text: quotes stripped, '12.0' -> '12'."""
    for name in names:
        if name not in params:
            continue
        expr, internal = params[name]
        if isinstance(expr, str) and expr.strip():
            t = expr.strip().strip('\'"').strip()
            if t:
                return t
        if isinstance(internal, (int, float)) and not isinstance(internal, bool):
            return str(int(internal)) if float(internal).is_integer() else str(internal)
        if isinstance(internal, str) and internal.strip():
            return internal.strip()
    return None

# What kind of quantity each field is, for unit parsing.
KIND = {'n': 'rpm', 'vf': 'feed', 'fz': 'len', 'vc': 'speed', 'ae': 'len', 'ap': 'len',
        'D': 'len', 'fluteLen': 'len', 'stickout': 'len', 'helix': 'deg', 'z': 'count'}

# Fusion API values are in internal units. Used only when the expression can't be
# parsed (for example, when it references other parameters). Length: cm.
# Feed and speed internal units are UNVERIFIED; confirm against the dump.
INTERNAL_TO_CALC = {'len': 10.0, 'feed': 10.0, 'speed': 1.0, 'rpm': 1.0, 'deg': 180.0 / math.pi, 'count': 1.0}

_UNIT = {
    'len':   {'mm': 1.0, 'cm': 10.0, 'm': 1000.0, 'in': 25.4, '"': 25.4, 'ft': 304.8},
    'feed':  {'mm/min': 1.0, 'cm/min': 10.0, 'm/min': 1000.0, 'in/min': 25.4, 'ipm': 25.4, 'ft/min': 304.8,
              'mm/s': 60.0, 'in/s': 1524.0},
    'speed': {'m/min': 1.0, 'ft/min': 0.3048, 'sfm': 0.3048, 'mm/min': 0.001},
    'rpm':   {'rpm': 1.0},
    'deg':   {'deg': 1.0, '°': 1.0, 'rad': 180.0 / math.pi},
    'count': {'': 1.0},
}

# Strategies the side-milling model covers, and ones it must refuse.
SUPPORTED = {
    'adaptive2d': 'adaptive', 'adaptive': 'adaptive', 'contour2d': 'contour', 'pocket2d': 'pocket',
    'slot': 'slot', 'contour': 'contour', 'pocket': 'pocket', 'face': 'face',
}
REFUSED = {
    'drill': 'Drilling isn’t side milling; the model doesn’t cover it.',
    'bore': 'Boring is helical interpolation with a different chip geometry; not covered.',
    'circular': 'Circular milling isn’t covered yet.',
    'thread': 'Thread milling isn’t covered.',
    'chamfer2d': 'Chamfer milling isn’t covered: the engagement depends on the chamfer tool’s angle.',
    'engrave': 'Engraving isn’t covered.',
    'parallel': '3D finishing with a ball end mill isn’t covered.',
    'scallop': '3D finishing isn’t covered.',
    'pencil': '3D finishing isn’t covered.',
    'radial': '3D finishing isn’t covered.',
    'spiral': '3D finishing isn’t covered.',
    'morphed_spiral': '3D finishing isn’t covered.',
    'steep_and_shallow': '3D finishing isn’t covered.',
    'flow': '3D finishing isn’t covered.',
    'contour3d': '3D finishing isn’t covered.',
}

_NUM_UNIT = re.compile(r'^\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*([^\d\s][^\s]*)?\s*$')


def parse_quantity(expression: str, kind: str) -> Optional[float]:
    """'1200 mm/min' -> 1200.0 (in calculator units). None if it isn't a plain literal."""
    if not isinstance(expression, str):
        return None
    m = _NUM_UNIT.match(expression.replace(' ', ' '))
    if not m:
        return None
    value, unit = float(m.group(1)), (m.group(2) or '').strip().lower()
    table = _UNIT.get(kind, {})
    if unit == '':
        return value if kind in ('count', 'rpm', 'deg') else None
    if unit in table:
        return value * table[unit]
    return None


def read_value(params: dict, names: list, kind: str) -> Optional[float]:
    """params: name -> (expression, internal_value). First candidate that resolves wins."""
    for name in names:
        if name not in params:
            continue
        expr, internal = params[name]
        v = parse_quantity(expr, kind)
        if v is None and isinstance(internal, (int, float)) and not isinstance(internal, bool):
            v = float(internal) * INTERNAL_TO_CALC.get(kind, 1.0)
        if v is not None and math.isfinite(v):
            return v
    return None


def strategy_status(strategy: str) -> tuple[bool, str]:
    s = (strategy or '').lower()
    if s in SUPPORTED:
        return True, SUPPORTED[s]
    if s in REFUSED:
        return False, REFUSED[s]
    return False, f'The “{strategy}” strategy isn’t one the model covers (it covers adaptive, contour, pocket, slot and face).'


def build_payload(strategy: str, op_params: dict, tool_params: dict, op_name: str = '',
                  material: Optional[str] = None) -> dict:
    """Everything the palette needs to fill in the calculator, or a reason it can't."""
    ok, kind_or_reason = strategy_status(strategy)
    label = strategy_label(strategy)
    card = {k: read_text(tool_params, names) for k, names in TOOL_TEXT.items()}
    if not ok:
        return {'ok': False, 'reason': kind_or_reason, 'operation': op_name, 'strategy': strategy,
                'strategyLabel': label, 'toolNumber': card['number']}

    tool = {k: read_value(tool_params, names, KIND.get(k, 'len')) for k, names in TOOL_NAMES.items() if k != 'type'}
    op = {k: read_value(op_params, names, KIND[k]) for k, names in OP_NAMES.items()}

    if tool.get('z') is not None:
        tool['z'] = int(round(tool['z']))
    if not tool.get('D') or tool['D'] <= 0:
        return {'ok': False, 'reason': 'Couldn’t read the tool diameter from this operation’s tool.',
                'operation': op_name, 'strategy': strategy}

    # A slot is full-width whatever the stepover parameter says.
    if kind_or_reason == 'slot':
        op['ae'] = tool['D']
    # Fill fz from feed and rpm when it isn't given directly.
    if op.get('fz') is None and op.get('vf') and op.get('n') and tool.get('z'):
        op['fz'] = op['vf'] / (op['n'] * tool['z'])

    missing = [k for k in ('D', 'z') if tool.get(k) is None] + [k for k in ('n', 'vf', 'ae', 'ap') if op.get(k) is None]
    return {'ok': True, 'operation': op_name, 'strategy': strategy, 'strategyLabel': label, 'kind': kind_or_reason,
            'toolNumber': card['number'], 'toolDesc': card['description'],
            'tool': tool, 'op': op, 'material': material, 'missing': missing}


def params_to_dict(params) -> dict:
    """Turn a Fusion CAMParameters collection into name -> (expression, internal_value)."""
    def _s(fn, default=None):
        try:
            return fn()
        except Exception:
            return default
    out = {}
    count = _s(lambda: params.count, 0) or 0
    for i in range(count):
        p = params.item(i)
        name = _s(lambda: p.name)
        if not name:
            continue
        val = _s(lambda: p.value)
        out[name] = (_s(lambda: p.expression, ''), _s(lambda: val.value) if val is not None else None)
    return out
