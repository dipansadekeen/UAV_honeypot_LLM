"""Experiment-specific heartbeat policy and optional grounded telemetry checks."""
import math
import numpy as np
import pandas as pd
from .common import sf

def heartbeat_checks(task, g, cfg):
    HB_PREFIX, EXPECTED_CUSTOM_MODES = (cfg.heartbeat_prefix, cfg.expected_custom_modes)
    cols = ['generated_hb_' + k for k in ['base_mode', 'custom_mode', 'system_status']]
    prefix = 'generated_hb_' if any((c in g for c in cols)) else HB_PREFIX

    def numeric(name):
        return pd.to_numeric(g.get(prefix + name, pd.Series(np.nan, index=g.index)), errors='coerce')
    bm, cm, st = [numeric(k) for k in ['base_mode', 'custom_mode', 'system_status']]
    integer_bm = bm.notna() & np.isfinite(bm) & bm.between(0, 255) & bm.eq(bm.round())
    armed = bm.where(integer_bm, 0).astype(int).map(lambda v: bool(v & 128))
    checks = pd.DataFrame(index=g.row_index.to_numpy())
    checks.index.name = 'row_index'
    checks['HB-Base-Mode'] = (integer_bm & armed.eq(task == 'ARM')).to_numpy()
    checks['HB-Custom-Mode'] = cm.isin(EXPECTED_CUSTOM_MODES[task]).to_numpy()
    checks['HB-System-Status'] = st.eq(4 if task == 'ARM' else 3).to_numpy()
    return (checks, prefix)

def arm_telemetry_checks(g, cfg):
    TOL = cfg.tolerances
    checks = []

    def record(r, name, error, tolerance):
        checks.append({'row_index': r.row_index, 'check': name, 'error': error, 'tolerance': tolerance, 'passed': bool(np.isfinite(error) and error <= tolerance)})
    motion = {'gpi_vx': 20.0, 'gpi_vy': 20.0, 'gpi_vz': 20.0, 'vfr_groundspeed': 0.2, 'vfr_climb': 0.2}
    bounds = {'gpi_lat': (-900000000, 900000000), 'gpi_lon': (-1800000000, 1800000000), 'gpi_hdg': (0, 35999), 'vfr_heading': (0, 360), 'vfr_throttle': (0, 100), 'sys_battery_remaining': (-1, 100), 'sys_voltage_battery': (0, 65535), 'sys_load': (0, 1000), 'gps_fix_type': (0, 8)}
    anchor = {'gpi_lat': 20.0, 'gpi_lon': 20.0, 'gpi_relative_alt': 200.0, 'gpi_alt': 200.0, 'vfr_alt': 0.2}
    for _, call in g.groupby(['mission_run_id', 'mission_seq', 'llm_call_id'], sort=False, dropna=False):
        origins = {}
        for _, r in call.iterrows():
            for c in g.columns:
                if not c.startswith('generated_') or c.startswith('generated_hb_') or pd.isna(r[c]):
                    continue
                key = c[len('generated_'):]
                v = sf(r[c])
                record(r, 'Telemetry-Numeric:' + key, 0.0 if pd.notna(v) else np.inf, 0.0)
                if pd.isna(v):
                    continue
                if key in motion:
                    record(r, 'No-Motion:' + key, abs(v), motion[key])
                if key in ['att_roll', 'att_pitch']:
                    record(r, 'Ground-Attitude:' + key, abs(math.degrees(v)), TOL['Roll' if key == 'att_roll' else 'Pitch'])
                if key in bounds:
                    lo, hi = bounds[key]
                    record(r, 'Telemetry-Range:' + key, 0.0 if lo <= v <= hi else 1.0, 0.0)
                if key in anchor:
                    if key not in origins:
                        input_value = sf(r.get('input_' + key))
                        origins[key] = input_value if pd.notna(input_value) else v
                    record(r, 'No-Position-Change:' + key, abs(v - origins[key]), anchor[key])
            vx, vy = (sf(r.get('generated_gpi_vx')), sf(r.get('generated_gpi_vy')))
            if pd.notna(vx) and pd.notna(vy):
                record(r, 'No-Motion:horizontal-speed', math.hypot(vx, vy), 20.0)
    return pd.DataFrame(checks, columns=['row_index', 'check', 'error', 'tolerance', 'passed'])
