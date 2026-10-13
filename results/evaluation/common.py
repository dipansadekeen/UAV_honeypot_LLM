"""Numeric helpers shared by telemetry and trajectory evaluation."""
import math
import numpy as np
import pandas as pd

def sf(x):
    try:
        return float(x) if pd.notna(x) and np.isfinite(float(x)) else np.nan
    except (TypeError, ValueError):
        return np.nan

def pick(r, *names):
    for name in names:
        value = sf(r.get(name, np.nan))
        if pd.notna(value):
            return value
    return np.nan

def adiff(a, b):
    return abs((a - b + 180) % 360 - 180) if pd.notna(a) and pd.notna(b) else np.nan

def hav(a, b, c, d):
    values = [sf(x) for x in [a, b, c, d]]
    if any((pd.isna(x) for x in values)):
        return np.nan
    a, b, c, d = [x / 10000000.0 for x in values]
    p1, p2 = (math.radians(a), math.radians(c))
    q = np.clip(math.sin(math.radians(c - a) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(d - b) / 2) ** 2, 0, 1)
    return 2 * 6371000 * math.atan2(math.sqrt(q), math.sqrt(1 - q))

def sortg(g):
    g = g.copy()
    g['_call_order'] = g.groupby('llm_call_id', sort=False).row_index.transform('min')
    g['_step'] = pd.to_numeric(g.llm_step_index, errors='coerce')
    return g.sort_values(['_call_order', '_step', 'row_index']).reset_index(drop=True)

def cname(sa, lc):
    return 'SALC' if sa and lc else 'SANLC' if sa else 'FALC' if lc else 'FANLC'
