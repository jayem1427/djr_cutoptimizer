"""
Pure mapping from Fusion CAM parameters to the calculator's inputs (mm, rpm, mm/min),
and the reverse: which parameters Apply writes (plan_writes) and how to check them
(write_matches). No adsk import, so it runs under pytest.

**The parameter names below are unverified.** They come from the handoff and common
Fusion naming. Run fusion/scripts/djr_dump_cam_params on an adaptive, a 2D contour and
a slot, commit the output to docs/cam_params/, then fix these tables to match.
"""
from __future__ import annotations

import json
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
    'z':        ['tool_numberOfFlutes', 'tool_fluteCount', 'tool_flutes'],
    'fluteLen': ['tool_fluteLength'],
    'stickout': ['tool_bodyLength', 'tool_shoulderLength', 'tool_overallLength'],
    'helix':    ['tool_helixAngle'],
    'type':     ['tool_type'],
}
# Stock to leave, written for finishing passes. Verified against a Fusion 2706 dump
# (docs/cam_params): "Radial Stock to Leave" is stockToLeave, "Axial Stock to Leave" is
# verticalStockToLeave, and the "Stock to Leave" checkbox is useStockToLeave.
STOCK_NAMES = {
    'radial': ['stockToLeave'],
    'axial':  ['verticalStockToLeave'],
}
# Adaptive clearing: Fusion refuses to generate when optimal load + load deviation is over
# 99 % of the tool diameter. Verified: loadDeviation defaults to an expression of the optimal
# load, "(optimalLoad<(tool_diameter-optimalLoad*0.20))?(optimalLoad*0.10):(...)", i.e. 10 %.
LOAD_DEV_NAMES = ['loadDeviation']
MAX_LOAD_FRACTION = 0.99
# Used when the deviation can't be read: assume 20 % of the diameter, so the cap is 0.79 D.
FALLBACK_DEV_FRACTION = 0.20
# Helical ramp (entry) of adaptives and pockets. Verified (Fusion 2706): rampType is 'helix',
# 'profile', ...; rampAngle is stored in degrees; helicalRampDiameter is usually an
# expression, max((D - 2 r) * 0.95, D * 0.25), so it's read from its internal value (cm).
RAMP_NAMES = {
    'vf':    ['tool_feedRamp'],
    'n':     ['tool_rampSpindleSpeed'],
    'angle': ['rampAngle'],
    'dia':   ['helicalRampDiameter'],
}
RAMP_KIND = {'vf': 'feed', 'n': 'rpm', 'angle': 'deg', 'dia': 'len'}
RAMP_TYPE = ['rampType']
# The "Stock to Leave" checkbox that enables the two values (a boolean parameter).
STOCK_FLAG = ['useStockToLeave']
PASSES = ('rough', 'wall', 'floor')
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
        expr, internal = params[name][:2]
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

# Fusion API values are in internal units. Used only when the expression can't be parsed
# (for example, when it references other parameters). Verified against a Fusion 2706 dump:
# lengths in cm (optimalLoad "1 mm" -> 0.1), feeds in mm/min ("7220 mm/min" -> 7220.0),
# angles in degrees (rampAngle "1.2deg" -> 1.2). Surface speed is unverified.
INTERNAL_TO_CALC = {'len': 10.0, 'feed': 1.0, 'speed': 1.0, 'rpm': 1.0, 'deg': 1.0, 'count': 1.0}

_UNIT = {
    'len':   {'mm': 1.0, 'cm': 10.0, 'm': 1000.0, 'in': 25.4, '"': 25.4, 'ft': 304.8},
    'feed':  {'mm/min': 1.0, 'mmpm': 1.0, 'cm/min': 10.0, 'm/min': 1000.0, 'in/min': 25.4, 'inpm': 25.4,
              'ipm': 25.4, 'ft/min': 304.8, 'mm/s': 60.0, 'in/s': 1524.0},
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

# Fusion writes numbers like "16000." and "1.in/min", so a trailing point is allowed.
_NUM_UNIT = re.compile(r'^\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*([^\d\s.][^\s]*)?\s*$')


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
        expr, internal = params[name][:2]
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


def flutes_from_json(tool_json: Optional[str]) -> Optional[int]:
    """The flute count from Tool.toJson() (the tool library's own record: geometry.NOF)."""
    try:
        z = json.loads(tool_json)['geometry']['NOF']
        z = int(round(float(z)))
    except Exception:
        return None
    return z if 1 <= z <= 16 else None


def build_payload(strategy: str, op_params: dict, tool_params: dict, op_name: str = '',
                  material: Optional[str] = None, tool_json: Optional[str] = None) -> dict:
    """Everything the palette needs to fill in the calculator, or a reason it can't."""
    ok, kind_or_reason = strategy_status(strategy)
    label = strategy_label(strategy)
    card = {k: read_text(tool_params, names) for k, names in TOOL_TEXT.items()}
    if not ok:
        return {'ok': False, 'reason': kind_or_reason, 'operation': op_name, 'strategy': strategy,
                'strategyLabel': label, 'toolNumber': card['number']}

    tool = {k: read_value(tool_params, names, KIND.get(k, 'len')) for k, names in TOOL_NAMES.items() if k != 'type'}
    op = {k: read_value(op_params, names, KIND[k]) for k, names in OP_NAMES.items()}

    # The tool library's own record first, then the tool's parameters.
    z = flutes_from_json(tool_json)
    if z is None and tool.get('z') is not None and tool['z'] >= 1:
        z = int(round(tool['z']))
    tool['z'] = z
    if not tool.get('D') or tool['D'] <= 0:
        return {'ok': False, 'reason': 'Couldn’t read the tool diameter from this operation’s tool.',
                'operation': op_name, 'strategy': strategy}

    # A slot is full-width whatever the stepover parameter says.
    if kind_or_reason == 'slot':
        op['ae'] = tool['D']
    # Fill fz from feed and rpm when it isn't given directly.
    if op.get('fz') is None and op.get('vf') and op.get('n') and tool.get('z'):
        op['fz'] = op['vf'] / (op['n'] * tool['z'])

    # Which parameter each value came from, so Apply writes back to exactly that one.
    src = {k: found_name(op_params, OP_NAMES[k], KIND[k]) for k in ('n', 'vf', 'ae', 'ap')}
    # A stepover or stepdown Fusion has switched off (a single-pass contour's maximumStepover,
    # maximumStepdown with multiple depths off) isn't the cut's engagement, and 0 isn't one either:
    # leave it unknown so the panel asks for it, and never write to it.
    for k in ('ae', 'ap'):
        name = src.get(k)
        if name and (not editable(op_params, name) or not (op.get(k) or 0) > 0):
            op[k], src[k] = None, None
    if kind_or_reason == 'slot':
        op['ae'] = tool['D']
    missing = [k for k in ('D', 'z') if tool.get(k) is None] + [k for k in ('n', 'vf', 'ae', 'ap') if op.get(k) is None]
    if kind_or_reason == 'slot':
        src['ae'] = None                 # a slot's width is the tool; nothing to write
    if src.get('ae') == 'optimalLoad':
        op['aeMax'] = max_optimal_load(op_params, tool['D'], op.get('ae'))
    ramp = {k: read_value(op_params, names, RAMP_KIND[k]) for k, names in RAMP_NAMES.items()}
    ramp['type'] = read_text(op_params, RAMP_TYPE)
    ramp_src = {k: found_name(op_params, RAMP_NAMES[k], RAMP_KIND[k]) for k in ('vf', 'n')}
    stock = {k: read_value(op_params, names, 'len') for k, names in STOCK_NAMES.items()}
    stock_src = {k: found_name(op_params, names, 'len') for k, names in STOCK_NAMES.items()}
    stock_src['flag'] = next((n for n in STOCK_FLAG if n in op_params and isinstance(op_params[n][1], bool)), None)
    return {'ok': True, 'operation': op_name, 'strategy': strategy, 'strategyLabel': label, 'kind': kind_or_reason,
            'toolNumber': card['number'], 'toolDesc': card['description'],
            'tool': tool, 'op': op, 'material': material, 'missing': missing,
            'src': src, 'stock': stock, 'stockSrc': stock_src,
            'ramp': ramp, 'rampSrc': ramp_src}


def max_optimal_load(op_params: dict, D: Optional[float], ae_now: Optional[float]) -> Optional[float]:
    """The largest optimal load Fusion will generate: load + deviation <= 99 % of D.

    None when the operation has no optimal load (not an adaptive). A deviation written as an
    expression of the optimal load scales with it, so the cap is 0.99 D / (1 + ratio);
    a fixed deviation gives 0.99 D - deviation. Rounded down to 0.001 mm.
    """
    if 'optimalLoad' not in op_params or not D or D <= 0:
        return None
    top = MAX_LOAD_FRACTION * D
    name = next((n for n in LOAD_DEV_NAMES if n in op_params), None)
    dev = read_value(op_params, [name], 'len') if name else None
    expr = str(op_params[name][0]) if name else ''
    if dev is None or dev < 0:
        cap = top - FALLBACK_DEV_FRACTION * D
    elif 'optimalLoad' in expr and ae_now and ae_now > 0:
        cap = top / (1 + dev / ae_now)
    else:
        cap = top - dev
    cap = math.floor(cap * 1000 + 1e-6) / 1000
    return cap if cap > 0 else None


def editable(params: dict, name: str) -> bool:
    """False when Fusion has the field switched off (greyed out). Unknown counts as editable."""
    row = params.get(name)
    return not (row is not None and len(row) > 2 and row[2] is False)


def found_name(params: dict, names: list, kind: str) -> Optional[str]:
    """The first candidate parameter that exists and holds a readable value."""
    for name in names:
        if name in params and read_value(params, [name], kind) is not None:
            return name
    return None


def _num(v) -> Optional[float]:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _fmt(v: float) -> str:
    return f'{round(v, 4):g}'


def plan_writes(src: dict, item: dict, clearance: float, stock_src: Optional[dict] = None,
                ae_max: Optional[float] = None, ramp_src: Optional[dict] = None) -> list:
    """The parameter writes for one operation: [(name, expression, kind, target)].

    item: {n, vf, pass, ae?, ap?} from the panel (rpm, mm/min, mm). ae/ap are written only
    when given; ae_max caps an adaptive's optimal load (see max_optimal_load). rampVf/rampN
    (helical ramp feed and spindle speed) are written when given and the operation has those
    parameters; an op without them still gets its cutting feeds. Finishing passes also set stock to leave: a wall finish leaves `clearance`
    on the floor (axial) and none on the wall; a floor finish the other way round.
    Raises ValueError when something needed is missing, so the op is skipped as a whole:
    half-applied feeds and speeds are worse than none.
    """
    n, vf = _num(item.get('n')), _num(item.get('vf'))
    if not (n and n > 0 and vf and vf > 0):
        raise ValueError('No valid spindle speed and feed to write.')
    if not src.get('n') or not src.get('vf'):
        raise ValueError('Couldn’t find this operation’s spindle speed or cutting feed parameter.')
    rpm, feed = math.floor(n), math.floor(vf)          # round down: never above a limit
    writes = [(src['n'], f'{rpm} rpm', 'rpm', float(rpm)),
              (src['vf'], f'{feed} mm/min', 'feed', float(feed))]
    for k, label in (('ae', 'stepover'), ('ap', 'stepdown')):
        if item.get(k) is None:
            continue
        v = _num(item[k])
        if not (v and v > 0):
            raise ValueError(f'Invalid {label}.')
        if not src.get(k):
            raise ValueError(f'Couldn’t find this operation’s {label} parameter, so the optimized '
                             f'{label} can’t be written. Tick Keep {label} and apply again.')
        if k == 'ae' and ae_max and v > ae_max + 1e-6:
            raise ValueError(f'Optimal load {_fmt(v)} mm plus the load deviation would be over 99 % of the '
                             f'tool diameter, which Fusion refuses. The most this operation allows is '
                             f'{_fmt(ae_max)} mm. Reselect it so the panel picks that up, or tick Keep stepover.')
        writes.append((src[k], f'{_fmt(v)} mm', 'len', round(v, 4)))

    ramp_src = ramp_src or {}
    for k, kind, unit in (('rampN', 'rpm', 'rpm'), ('rampVf', 'feed', 'mm/min')):
        if item.get(k) is None:
            continue
        v = _num(item[k])
        if not (v and v > 0):
            raise ValueError('Invalid ramp ' + ('spindle speed.' if kind == 'rpm' else 'feed.'))
        name = ramp_src.get('n' if k == 'rampN' else 'vf')
        if name:
            v = math.floor(v)
            writes.append((name, f'{v} {unit}', kind, float(v)))

    p = item.get('pass') or 'rough'
    if p not in PASSES:
        raise ValueError(f'Unknown pass “{p}”.')
    if p != 'rough':
        c = _num(clearance)
        if c is None or not 0 <= c <= 2:
            raise ValueError('Finish clearance must be between 0 and 2 mm.')
        stock_src = stock_src or {}
        if not stock_src.get('radial') or not stock_src.get('axial'):
            raise ValueError('This operation has no radial/axial stock-to-leave parameters, so the '
                             'finishing rule can’t be applied. Set it to Rough, or set the stock by hand.')
        radial, axial = (0.0, c) if p == 'wall' else (c, 0.0)
        if stock_src.get('flag'):
            writes.append((stock_src['flag'], 'true', 'bool', True))
        writes.append((stock_src['radial'], f'{_fmt(radial)} mm', 'len', radial))
        writes.append((stock_src['axial'], f'{_fmt(axial)} mm', 'len', axial))
    return writes


# Tool preset parameters (verified in the dump's operation.toolPreset.parameters).
PRESET_NAMES = {'n': 'tool_spindleSpeed', 'vf': 'tool_feedCutting', 'rampN': 'tool_rampSpindleSpeed',
                'rampVf': 'tool_feedRamp', 'ae': 'tool_stepover', 'ap': 'tool_stepdown'}


def preset_writes(values: dict) -> list:
    """What a tool preset gets from an optimized cut: [(name, expression, kind, target)].

    values: {n, vf, rampN?, rampVf?, ae?, ap?} (rpm, mm/min, mm). Speed and feeds round down,
    like Apply. Raises ValueError without a valid spindle speed and feed."""
    n, vf = _num(values.get('n')), _num(values.get('vf'))
    if not (n and n > 0 and vf and vf > 0):
        raise ValueError('No valid spindle speed and feed to save.')
    out = []
    for k, kind, unit in (('n', 'rpm', 'rpm'), ('vf', 'feed', 'mm/min'), ('rampN', 'rpm', 'rpm'),
                          ('rampVf', 'feed', 'mm/min'), ('ae', 'len', 'mm'), ('ap', 'len', 'mm')):
        v = _num(values.get(k))
        if not (v and v > 0):
            continue
        if kind == 'len':
            out.append((PRESET_NAMES[k], f'{_fmt(v)} {unit}', kind, round(v, 4)))
        else:
            v = math.floor(v)
            out.append((PRESET_NAMES[k], f'{v} {unit}', kind, float(v)))
    return out


def tool_guid(tool_json: Optional[str]) -> Optional[str]:
    """The tool's guid from Tool.toJson(), used to find the same tool in a library."""
    try:
        g = json.loads(tool_json).get('guid')
    except Exception:
        return None
    return str(g) if g else None


_TOL = {'rpm': 0.5, 'feed': 0.5, 'len': 1e-4}


def write_matches(kind: str, target, expression, internal) -> bool:
    """Whether a parameter read back after writing holds the intended value."""
    if kind == 'bool':
        return internal is True or str(expression).strip().lower() == 'true'
    got = read_value({'x': (expression, internal)}, ['x'], kind)
    if got is None:
        return False
    return abs(got - target) <= max(_TOL.get(kind, 1e-6), 1e-3 * abs(target))


def params_to_dict(params) -> dict:
    """Turn a Fusion CAMParameters collection into name -> (expression, internal_value, editable).

    editable is False for fields Fusion has switched off (greyed out in the dialog), e.g. a 2D
    contour's maximumStepover when multiple stepovers are off."""
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
        out[name] = (_s(lambda: p.expression, ''), _s(lambda: val.value) if val is not None else None,
                     _s(lambda: p.isEditable, True) is not False)
    return out
