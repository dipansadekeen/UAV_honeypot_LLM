"""3D ENU straight/taken path efficiency, retaining notebook completion rules."""
from pathlib import Path
import math
import numpy as np
import pandas as pd
from .common import sf, pick, sortg
from .completion import states

def xyz(lat, lon, alt, lat0, lon0, alt0):
    v = list(map(sf, [lat, lon, alt, lat0, lon0, alt0]))
    if any((pd.isna(x) for x in v)):
        return np.array([np.nan] * 3)
    lat, lon, alt, lat0, lon0, alt0 = v
    R = 6371000.0
    n = math.radians(lat / 10000000.0 - lat0 / 10000000.0) * R
    e = math.radians(lon / 10000000.0 - lon0 / 10000000.0) * R * math.cos(math.radians(lat0 / 10000000.0))
    return np.array([e, n, alt - alt0])

def trajectory(task, g, done):
    s = states(g)
    r = s.iloc[0]
    lat0, lon0 = (pick(r, 'input_gpi_lat', '_lat'), pick(r, 'input_gpi_lon', '_lon'))
    a0 = pick(r, 'input_gpi_relative_alt', '_alt')
    if any((pd.isna(x) for x in [lat0, lon0, a0])):
        return np.nan
    alt0 = a0 / 1000
    if task == 'LAND':
        tlat, tlon, talt = (lat0, lon0, 0.0)
    elif task == 'TAKEOFF':
        tlat, tlon, talt = (lat0, lon0, pick(r, 'target_alt', 'param7'))
    elif task == 'RTL':
        tlat, tlon, talt = (pick(r, 'target_lat', 'param5'), pick(r, 'target_lon', 'param6'), alt0)
    else:
        tlat, tlon, talt = (pick(r, 'target_lat', 'param5'), pick(r, 'target_lon', 'param6'), pick(r, 'target_alt', 'param7'))
    B = xyz(tlat, tlon, talt, lat0, lon0, alt0)
    if np.isnan(B).any():
        return np.nan
    straight = np.linalg.norm(B)
    pts = []
    for _, x in s.dropna(subset=['_lat', '_lon', '_alt']).iterrows():
        p = xyz(x._lat, x._lon, sf(x._alt) / 1000, lat0, lon0, alt0)
        if not np.isnan(p).any():
            pts.append(p)
    taken = 0.0
    prev = np.zeros(3)
    for p in pts:
        taken += np.linalg.norm(p - prev)
        prev = p
    return straight / taken * 100 if done and straight > 0 and (taken > 0) else np.nan

def evaluate_trajectory(evaluated, out, gate='sa'):
    if gate not in {'sa', 'salc'}:
        raise ValueError('trajectory gate must be sa or salc')
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    results = evaluated['cases'].set_index('Case ID')
    rows = []
    for i in evaluated['keep']:
        x = evaluated['incidents'][i]
        if x['Operation'] in ['ARM', 'DISARM']:
            continue
        r = results.loc[i]
        admitted = bool(r.SA) if gate == 'sa' else r.Class == 'SALC'
        efficiency = trajectory(x['Operation'], sortg(x['g']), admitted)
        rows.append({'Model': x['Model'], 'Operation': x['Operation'], 'Case': x['Case'], 'SA': bool(r.SA), 'LC': bool(r.LC), 'Class': r.Class, 'Efficiency (%)': efficiency, 'Gate': gate})
    table = pd.DataFrame(rows)
    summary = table.groupby(['Model', 'Operation'], sort=False).agg(Cases=('Case', 'count'), Eligible_Trajectories=('Efficiency (%)', 'count'), Efficiency=('Efficiency (%)', 'mean')).reset_index()
    table.to_csv(out / 'trajectory_cases.csv', index=False)
    summary.to_csv(out / 'trajectory_summary.csv', index=False)
    return (table, summary)
