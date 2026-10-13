"""HITL operation selection; speed-change context belongs to the following WP."""
from pathlib import Path
import math, os, json
import numpy as np
import pandas as pd
from config.settings import OPERATIONS
CSV_DIAGNOSTICS = {}
CASE_PICK = {'ARM': 1, 'DISARM': 1, 'TAKEOFF': 1, 'LAND': -1, 'RTL': 1, 'WP': 1, 'WP+ALT': 1, 'WP+YAW': 1, 'WP+SPEED': 1}
ALT_CHANGE_EPS = YAW_CHANGE_EPS = 0.01
OP_OVERRIDES = {}

def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None

def classify_item(items, seq, rid):
    """Classify actual mission targets; do not assume fixed seq 2/3 meanings."""
    item = items[seq]
    cid = number(item.get('command'))
    override = OP_OVERRIDES.get((rid, seq))
    if override is not None:
        if override not in OPERATIONS:
            raise ValueError('Unknown operation override: ' + override)
        return (override, 'explicit OP_OVERRIDES')
    if cid in (22, 21, 20):
        return ({22: 'TAKEOFF', 21: 'LAND', 20: 'RTL'}[cid], 'mission command')
    if cid != 16:
        return (None, 'not an evaluated navigation command')
    if number(items.get(seq - 1, {}).get('command')) == 178:
        return ('WP+SPEED', 'waypoint immediately after CHANGE SPEED')
    earlier = [items[k] for k in sorted(items) if k < seq and number(items[k].get('command')) in (16, 22)]
    prev = earlier[-1] if earlier else {}
    yaw, prev_yaw = (number(item.get('param4')), number(prev.get('param4')))
    if yaw is not None and (prev_yaw is None or abs((yaw - prev_yaw + 180) % 360 - 180) > YAW_CHANGE_EPS):
        return ('WP+YAW', 'explicit changed waypoint yaw target')
    alt, prev_alt = (number(item.get('z')), number(prev.get('z')))
    same_frame = item.get('frame') is None or prev.get('frame') is None or item.get('frame') == prev.get('frame')
    if same_frame and alt is not None and (prev_alt is not None) and (abs(alt - prev_alt) > ALT_CHANGE_EPS):
        return ('WP+ALT', 'changed waypoint altitude target')
    return ('WP', 'ordinary waypoint target')

def selected_candidates(candidates, max_cases=1):
    MAX_CASES = max_cases
    selected = []
    coverage = []
    for op in OPERATIONS:
        available = sorted([x for x in candidates if x['Operation'] == op], key=lambda x: x['start'])
        if MAX_CASES is None:
            chosen = available
        elif available:
            if not isinstance(MAX_CASES, int) or MAX_CASES < 1:
                raise ValueError('MAX_CASES must be a positive integer or None.')
            pick = CASE_PICK.get(op, 1)
            idx = pick - 1 if pick > 0 else pick
            if pick == 0 or not -len(available) <= idx < len(available):
                raise ValueError(f'{op}: CASE_PICK is outside the {len(available)} available cases.')
            idx = idx if idx >= 0 else len(available) + idx
            chosen = available[idx:idx + MAX_CASES]
        else:
            chosen = []
        selected.extend(chosen)
        coverage.append({'Operation': op, 'Available_Cases': len(available), 'Selected_Cases': len(chosen), 'Status': 'selected' if chosen else 'not present in source'})
    return (selected, pd.DataFrame(coverage))

def csv_candidates(path):
    source = pd.read_csv(path, low_memory=False)
    extras = [c for c in source if str(c).startswith('Unnamed:')]
    appended = ['input_landed_state', 'generated_timestamp', 'Operation', 'Case', 'case_id', 'case_origin', 'event_timestamp', 'generated_hb_base_mode', 'generated_hb_custom_mode', 'generated_hb_system_status', 'generated_landed_state']
    known = set(OPERATIONS + ['CHANGE SPEED'])
    if len(extras) == 11 and source[extras[2]].dropna().astype(str).isin(known).all() and source[extras[2]].notna().any():
        for old, new in zip(extras, appended):
            if new in source:
                source[new] = source[new].combine_first(source[old])
            else:
                source[new] = source[old]
        source = source.drop(columns=extras)
    else:
        populated = [c for c in extras if source[c].notna().any()]
        if populated:
            raise ValueError('Unrecognized populated unnamed columns: ' + str(populated))
        source = source.drop(columns=extras)
    required = {'mission_run_id', 'timestamp', 'mission_seq', 'command_id'}
    if not required.issubset(source):
        raise ValueError('Converted CSV is missing: ' + str(required - set(source)))
    source['_source_row'] = np.arange(len(source))
    for c in ['timestamp', 'mission_seq', 'command_id', 'param1', 'param4', 'target_alt', 'param7', 'frame']:
        if c not in source:
            source[c] = np.nan
        source[c] = pd.to_numeric(source[c], errors='coerce')
    valid = source.mission_run_id.astype(str).str.fullmatch('mission_\\d{8}_\\d{6}', na=False) & source.timestamp.notna()
    source = source.loc[valid].copy()
    if 'Operation' not in source:
        source['Operation'] = np.nan
    source['Operation'] = source.Operation.map(lambda v: str(v).strip().upper().replace('WP+ALTITUDE', 'WP+ALT') if pd.notna(v) else np.nan)
    if 'case_id' not in source:
        source['case_id'] = np.nan
    candidates = []
    for rid, run in source.groupby('mission_run_id', sort=False):
        items = {}
        for seq, g in run.dropna(subset=['mission_seq']).groupby('mission_seq', sort=True):
            first = g.iloc[0]
            items[int(seq)] = {'command': first.command_id, 'param4': number(first.param4), 'z': number(first.get('target_alt')) if number(first.get('target_alt')) is not None else number(first.get('param7')), 'frame': number(first.get('frame'))}
        classified = []
        for _, r in run.iterrows():
            label = r.Operation
            why = 'provided operation metadata'
            if pd.isna(label):
                cid, seq = (number(r.command_id), number(r.mission_seq))
                if cid == 400:
                    p = number(r.param1)
                    label = 'ARM' if p == 1 else 'DISARM' if p == 0 else None
                    why = 'ARM/DISARM command parameter'
                elif seq is not None and int(seq) in items:
                    label, why = classify_item(items, int(seq), rid)
                else:
                    label = None
                    why = 'unclassified source row'
            classified.append((label, why))
        run['Operation'] = [x[0] for x in classified]
        run['_classification'] = [x[1] for x in classified]
        run = run[run.Operation.isin(OPERATIONS)].copy()
        run['_key'] = [str(r.case_id) if pd.notna(r.case_id) else f'{rid}:{r.Operation}:seq={r.mission_seq}' for _, r in run.iterrows()]
        for (op, key), g in run.groupby(['Operation', '_key'], sort=False):
            g = g.sort_values(['timestamp', '_source_row'], kind='stable').copy()
            candidates.append({'Operation': op, 'start': float(g.timestamp.min()), 'end': float(g.timestamp.max()), 'rid': rid, 'seq': number(g.mission_seq.iloc[0]), 'origin': g._classification.iloc[0], 'source_key': key, 'data': g})
    CSV_DIAGNOSTICS.clear()
    CSV_DIAGNOSTICS.update(source_csv=os.path.basename(path), source_rows=int(len(source)), input_convention='Each row already contains input and post-state telemetry; dt is preserved.')
    return candidates

def extract_hitl(path, output, max_cases=1):
    specs, coverage = selected_candidates(csv_candidates(path), max_cases)
    rows, manifest = ([], [])
    for case, spec in enumerate(specs, 1):
        op, rid = (spec['Operation'], spec['rid'])
        case_id = f'{rid}-C{case:02d}-{op}'
        block = spec['data'].drop(columns=['_source_row', '_classification', '_key'], errors='ignore').copy()
        block['source_case_id'] = spec['source_key']
        block['case_id'], block['Case'] = (case_id, case)
        block['Operation'], block['llm_model_name'] = (op, 'HITL')
        block['case_origin'] = spec['origin']
        if 'dt' not in block:
            raise ValueError('HITL input/post-state pairs require an elapsed dt column')
        rows.extend(block.to_dict('records'))
        manifest.append(dict(Case=case, case_id=case_id, Operation=op, mission_run_id=rid, mission_seq=spec['seq'], Start=spec['start'], End=spec['end'], Telemetry_Rows=len(block), Origin=spec['origin']))
    if not rows:
        raise ValueError('No evaluated HITL operation cases found')
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output, index=False)
    pd.DataFrame(manifest).to_csv(output.with_name(output.stem + '_selected_cases.csv'), index=False)
    coverage.to_csv(output.with_name(output.stem + '_coverage.csv'), index=False)
    output.with_name(output.stem + '_diagnostics.json').write_text(json.dumps(CSV_DIAGNOSTICS, indent=2))
    return output
