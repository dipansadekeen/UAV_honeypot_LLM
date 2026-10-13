"""Original terminal-state completion rules, evaluated independently of LC."""
import numpy as np
import pandas as pd
from .common import sf, pick, sortg

def states(g):
    g = sortg(g).copy()
    for out, name in [('_lat', 'lat'), ('_lon', 'lon'), ('_alt', 'relative_alt')]:
        cur = np.nan
        values = []
        for _, r in g.iterrows():
            if pd.isna(cur):
                cur = sf(r.get('input_gpi_' + name))
            value = sf(r.get('generated_gpi_' + name))
            if pd.notna(value):
                cur = value
            values.append(cur)
        g[out] = values
    return g

def complete(task, g, cfg):
    ALT_TOL, LAND_ALT, LATLON_TOL = (cfg.altitude_tol_mm, cfg.land_altitude_mm, cfg.latlon_tol)
    s = states(g)
    if s.empty:
        return False
    f, l = (s.iloc[0], s.iloc[-1])
    if task == 'TAKEOFF':
        t = pick(f, 'target_alt', 'param7')
        return bool(pd.notna(t) and pd.notna(l._alt) and (abs(l._alt - t * 1000) <= ALT_TOL))
    if task == 'LAND':
        return bool(pd.notna(l._alt) and l._alt <= LAND_ALT)
    lat, lon = (pick(f, 'target_lat', 'param5'), pick(f, 'target_lon', 'param6'))
    if any((pd.isna(v) for v in [lat, lon, l._lat, l._lon])):
        return False
    pos = abs(l._lat - lat) <= LATLON_TOL and abs(l._lon - lon) <= LATLON_TOL
    if task == 'RTL':
        return bool(pos)
    alt = pick(f, 'target_alt', 'param7')
    return bool(pos and pd.notna(alt) and pd.notna(l._alt) and (abs(l._alt - alt * 1000) <= ALT_TOL))
