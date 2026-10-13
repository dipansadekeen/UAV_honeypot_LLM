"""LLM sequential error checks. Predecessors never cross an LLM call boundary."""
import math
import numpy as np
import pandas as pd
from .common import sf, pick, adiff, hav, sortg

def errors(g, cfg):
    DT, SPEED_GATE, G = (cfg.dt, cfg.speed_gate, 9.80665)
    g = sortg(g)
    rows = []
    for i, r in g.iterrows():
        same = i > 0 and all((r[k] == g.iloc[i - 1][k] for k in ['mission_run_id', 'mission_seq', 'llm_call_id']))
        p = g.iloc[i - 1] if same else None
        vx, vy, vz = [sf(r.get('generated_gpi_' + k)) for k in ['vx', 'vy', 'vz']]
        gs, hdg, climb = [sf(r.get('generated_vfr_' + k)) for k in ['groundspeed', 'heading', 'climb']]
        roll, pitch, yaw = [sf(r.get('generated_att_' + k)) for k in ['roll', 'pitch', 'yaw']]
        vxy = math.hypot(vx / 100, vy / 100)
        travel = math.degrees(math.atan2(vy, vx)) % 360 if pd.notna(vxy) and vxy >= SPEED_GATE else np.nan
        e = {'H-Speed': abs(vxy - gs), 'V-Speed': abs(vz / 100 + climb), 'Heading': adiff(hdg, travel), 'Yaw': adiff(math.degrees(yaw) % 360, hdg), 'Vel-Disp': np.nan, 'Gnd-Disp': np.nan, 'Vert-Disp': np.nan, 'Roll': np.nan, 'Pitch': np.nan}
        if p is not None:
            disp = hav(p.get('generated_gpi_lat'), p.get('generated_gpi_lon'), r.get('generated_gpi_lat'), r.get('generated_gpi_lon'))
            alt = pick(r, 'generated_gpi_relative_alt', 'generated_gpi_alt')
            palt = pick(p, 'generated_gpi_relative_alt', 'generated_gpi_alt')
            e['Vel-Disp'] = abs(disp - vxy * DT)
            e['Gnd-Disp'] = abs(disp - gs * DT)
            e['Vert-Disp'] = abs((alt - palt) / 1000 + vz / 100 * DT)
            pvx, pvy, pvz = [sf(p.get('generated_gpi_' + k)) for k in ['vx', 'vy', 'vz']]
            if all((pd.notna(v) for v in [vx, vy, vz, pvx, pvy, pvz, yaw])):
                aN, aE, aD = ((vx - pvx) / 100 / DT, (vy - pvy) / 100 / DT, (vz - pvz) / 100 / DT)
                af = aN * math.cos(yaw) + aE * math.sin(yaw)
                ar = -aN * math.sin(yaw) + aE * math.cos(yaw)
                vc = G - aD
                pe = math.atan2(-af, vc)
                re_ = math.atan2(ar, math.sqrt(vc ** 2 + af ** 2))
                e['Roll'] = adiff(math.degrees(roll), math.degrees(re_))
                e['Pitch'] = adiff(math.degrees(pitch), math.degrees(pe))
        rows.append({'row_index': r.row_index, **e})
    return pd.DataFrame(rows)

def component_scores(errors, cfg):
    """Missing dependencies remain NaN; pass counts are exported separately."""
    tolerances = pd.Series(cfg.tolerances)
    if cfg.profile == 'notebook':
        return errors.le(tolerances).astype(float).where(errors.notna())
    return (1 - errors.abs().div(tolerances)).clip(lower=0, upper=1)
