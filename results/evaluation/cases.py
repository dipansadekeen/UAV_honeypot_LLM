"""Read section markers and extract the experiment's operation cases."""
import re
import numpy as np
import pandas as pd
from config.settings import MODEL_MAP, MODELS

def extract_llm_cases(path, max_cases=5):
    CSV, MM = (path, MODEL_MAP)
    df = pd.read_csv(CSV, low_memory=False)
    df['row_index'] = df.index
    marker = df.mission_run_id.notna() & ~df.mission_run_id.astype(str).str.startswith('mission_')
    mi = df.index[marker].tolist()
    blocks = []
    for n, i in enumerate(mi):
        end = mi[n + 1] if n + 1 < len(mi) else len(df)
        title = re.sub('\\s+', ' ', str(df.at[i, 'mission_run_id']).replace('\\\\\t', ' ')).strip(' #.\t\r\n')
        g = df.iloc[i + 1:end].copy()
        mods = g.llm_model_name.dropna().astype(str)
        if mods.empty:
            continue
        model = MM.get(mods.iloc[0], mods.iloc[0])
        z = title.lower()
        kind = 'ARM' if 'arm-disarm' in z or ('arm' in z and 'disarm' in z) else 'LAND' if 'land' in z else 'SPEED' if 'waypoint-speed' in z or ('waypoint' in z and 'speed' in z) else 'FULL'
        blocks.append((i, title, model, kind, g))
    INC = []

    def add(model, op, case, g, order):
        if len(g):
            INC.append({'Model': model, 'Operation': op, 'Case': case, 'Order': order, 'g': g.copy()})
    for base, title, model, kind, g in blocks:
        cmd = pd.to_numeric(g.command_id, errors='coerce')
        seq = pd.to_numeric(g.mission_seq, errors='coerce')
        if kind == 'FULL':
            for op, cid, ss in [('TAKEOFF', 22, [0]), ('WP', 16, [1]), ('WP+ALT', 16, [2]), ('WP+YAW', 16, [3]), ('RTL', 20, None)]:
                x = g[cmd == cid]
                if ss is not None:
                    x = x[pd.to_numeric(x.mission_seq, errors='coerce').isin(ss)]
                for s, q in x.groupby('mission_seq', sort=False, dropna=False):
                    add(model, op, f'{title} | seq {s}', q, base + (0 if pd.isna(s) else float(s) / 100))
        elif kind == 'LAND':
            add(model, 'LAND', title, g[cmd == 21], base)
        elif kind == 'ARM':
            p = pd.to_numeric(g.param1, errors='coerce')
            add(model, 'ARM', title, g[(cmd == 400) & (p == 1)], base)
            add(model, 'DISARM', title, g[(cmd == 400) & (p == 0)], base + 0.001)
        else:
            for s, _ in g[cmd == 178].groupby('mission_seq', sort=False, dropna=False):
                if pd.notna(s):
                    add(model, 'WP+SPEED', f'{title} | {int(s)}->{int(s + 1)}', g[(cmd == 16) & (seq == s + 1)], base + float(s) / 100)
    if not INC:
        raise ValueError('No cases found; check CSV section markers.')
    manifest = pd.DataFrame([{k: v for k, v in x.items() if k != 'g'} for x in INC])
    unknown = set(manifest.Model) - set(MODELS)
    if unknown:
        raise ValueError('Unmapped model names: ' + str(sorted(unknown)))
    ordered = manifest.sort_values('Order', kind='stable')
    selected = ordered.groupby(['Model', 'Operation'], sort=False).head(max_cases) if max_cases is not None else ordered
    keep = selected.index.tolist()
    return (INC, keep, manifest)
