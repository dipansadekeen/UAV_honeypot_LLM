"""Few-shot example ablation: run selection, plan-based cases, per-setting scoring.

Settings (module_llmhoneypot.py, prompt assembly):
  full  sequence + transition examples
  ab1   transition examples only (sequence examples removed)
  ab2   sequence examples only (transition examples removed)
  ab3   neither

Each run is one section of the CSV, headed by a marker row such as `#120b-ab2-3`.
Run selection, per (setting, model) in file order: keep runs until two successful
ones are kept; a failed run (marker contains "fail") met before that is kept too.
Exact duplicate sections are counted once.
"""
import re
from pathlib import Path
import numpy as np
import pandas as pd
from config.settings import Settings, MODEL_MAP, MODELS, CLASSES
from .llm import evaluate_llm

SETTINGS = ['full', 'ab1', 'ab2', 'ab3']
SETTING_LABELS = {'full': 'Sequence + transition', 'ab1': 'Transition only',
                  'ab2': 'Sequence only', 'ab3': 'No examples'}
# Ablation runs of gpt-oss-20b and one nemotron-nano run used local, not cloud, tags.
LOCAL_MODEL_MAP = {'gpt-oss:20b': 'gpt-oss-20b', 'nemotron-3-nano:30b': 'nemotron-nano'}
KEY = ['mission_run_id', 'mission_seq', 'llm_call_id', 'llm_step_index']
TAKEOFF, WAYPOINT, RTL, LAND, CHANGE_SPEED = 22, 16, 20, 21, 178
ALT_CHANGE_M = 0.5


def read_runs(path):
    """Return (dataframe, list of run dicts) in file order."""
    df = pd.read_csv(path, low_memory=False, encoding='utf-8-sig')
    df['row_index'] = df.index
    ids = df.mission_run_id.astype(str)
    marker = df.mission_run_id.notna() & ~ids.str.startswith('mission_')
    starts = df.index[marker].tolist() + [len(df)]
    runs = []
    for a, b in zip(starts, starts[1:]):
        title = re.sub(r'\s+', ' ', str(df.at[a, 'mission_run_id'])).strip(' #.\t\r\n')
        g = df.iloc[a + 1:b]
        g = g[g.mission_run_id.astype(str).str.startswith('mission_')]
        if g.empty:
            continue  # comment-only marker, e.g. "# ab1 starts here"
        tags = g.llm_model_name.dropna().astype(str).unique()
        if len(tags) != 1:
            raise ValueError(f'Run {title!r} mixes model tags {list(tags)}')
        model = MODEL_MAP.get(tags[0], LOCAL_MODEL_MAP.get(tags[0]))
        if model not in MODELS:
            raise ValueError(f'Unmapped model tag {tags[0]!r} in run {title!r}')
        m = re.search(r'ab\s*-?\s*([123])', title.lower())
        setting = 'ab' + m.group(1) if m else 'full' if 'full' in title.lower() else None
        if setting is None:
            raise ValueError(f'Cannot tell the ablation setting of run {title!r}')
        runs.append({'setting': setting, 'model': model, 'model_tag': tags[0], 'title': title,
                     'marker_line': a + 2, 'mission_run_id': ', '.join(g.mission_run_id.unique()),
                     'failed': 'fail' in title.lower(), 'rows': len(g),
                     'last_seq': int(pd.to_numeric(g.mission_seq, errors='coerce').max()), 'g': g})
    return df, runs


def select_runs(runs, top=2):
    """Mark each run selected or not, with the reason; returns the same list."""
    seen, successes = [], {}
    for r in runs:
        body = r['g'].drop(columns='row_index').reset_index(drop=True)
        if any(body.equals(s) for s in seen):
            r['selected'], r['reason'] = False, 'exact duplicate of an earlier section'
            continue
        seen.append(body)
        k = (r['setting'], r['model'])
        n = successes.get(k, 0)
        if n >= top:
            r['selected'], r['reason'] = False, f'after the first {top} successful runs'
            continue
        r['selected'] = True
        r['reason'] = 'failed run before the 2nd success' if r['failed'] else f'successful run {n + 1}'
        if not r['failed']:
            successes[k] = n + 1
    return runs


def plan_operations(g):
    """Map mission_seq -> operation from the uploaded plan (command_id, param4, param7)."""
    plan = g.drop_duplicates('mission_seq').copy()
    plan['seq'] = pd.to_numeric(plan.mission_seq, errors='coerce')
    plan['cmd'] = pd.to_numeric(plan.command_id, errors='coerce')
    plan = plan.sort_values('seq')
    ops, prev_cmd, prev_alt = {}, None, np.nan
    for _, p in plan.iterrows():
        alt = pd.to_numeric(p.param7, errors='coerce')
        yaw = pd.to_numeric(p.param4, errors='coerce')
        if p.cmd == TAKEOFF:
            ops[p.seq] = 'TAKEOFF'
        elif p.cmd == RTL:
            ops[p.seq] = 'RTL'
        elif p.cmd == LAND:
            ops[p.seq] = 'LAND'
        elif p.cmd == WAYPOINT:
            ops[p.seq] = ('WP+SPEED' if prev_cmd == CHANGE_SPEED else
                          'WP+ALT' if pd.notna(prev_alt) and abs(alt - prev_alt) > ALT_CHANGE_M else
                          'WP+YAW' if pd.notna(yaw) and yaw != 0 else 'WP')
        if p.cmd in (TAKEOFF, WAYPOINT):
            prev_alt = alt
        prev_cmd = p.cmd
    return ops


def build_cases(runs, setting):
    """(incidents, keep, manifest) for the selected runs of one setting."""
    inc = []
    for r in runs:
        if r['setting'] != setting or not r['selected']:
            continue
        g = r['g']
        ops = plan_operations(g)
        seq = pd.to_numeric(g.mission_seq, errors='coerce')
        for s, op in ops.items():
            q = g[seq == s]
            if len(q):
                inc.append({'Model': r['model'], 'Operation': op, 'Case': f"{r['title']} | seq {int(s)}",
                            'Order': r['marker_line'] + s / 100, 'Setting': setting, 'Run': r['title'],
                            'mission_run_id': r['mission_run_id'], 'Failed_Run': r['failed'], 'g': q.copy()})
    if not inc:
        raise ValueError(f'No selected cases for setting {setting}')
    manifest = pd.DataFrame([{k: v for k, v in x.items() if k != 'g'} for x in inc])
    return inc, list(range(len(inc))), manifest


def class_metrics(d):
    S, SN, F, FN = [int(d.Class.eq(c).sum()) for c in CLASSES]
    N = len(d)
    pct = lambda a, b: np.nan if b == 0 else 100 * a / b
    return {'Cases': N, 'SALC': S, 'SANLC': SN, 'FALC': F, 'FANLC': FN,
            'ASR (%)': pct(S + SN, N), 'LC (%)': pct(S + F, N), 'SALC (%)': pct(S, N),
            'Precision (%)': pct(S, S + SN), 'Mean Compliance': d['Mean Compliance'].mean()}


def evaluate_ablation(path, out, cfg=None, top=2):
    cfg = cfg or Settings(max_cases=None)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    runs = select_runs(read_runs(path)[1], top)
    results, summary, by_op = {}, [], []
    for s in SETTINGS:
        tables = evaluate_llm(path, out / s, cfg, cases=build_cases(runs, s))
        cases = tables['cases']
        results[s] = cases
        for model in [m for m in MODELS if m in set(cases.Model)] + ['All']:
            d = cases if model == 'All' else cases[cases.Model == model]
            summary.append({'Setting': s, 'Examples': SETTING_LABELS[s], 'Model': model, **class_metrics(d)})
        for op, d in cases.groupby('Operation', sort=False):
            by_op.append({'Setting': s, 'Operation': op, **class_metrics(d)})
    run_table = pd.DataFrame([{k: v for k, v in r.items() if k != 'g'} for r in runs])
    for r_i, r in run_table.iterrows():
        if not r.selected:
            continue
        land = results[r.setting]
        land = land[(land.Case.str.startswith(r.title + ' | ')) & (land.Operation == 'LAND')]
        run_table.at[r_i, 'landed'] = bool(len(land) and land.SA.any())
    run_table.to_csv(out / 'runs.csv', index=False)
    summary = pd.DataFrame(summary)
    summary.to_csv(out / 'ablation_summary.csv', index=False)
    pd.DataFrame(by_op).to_csv(out / 'ablation_by_operation.csv', index=False)
    return {'runs': run_table, 'summary': summary, 'cases': results}
