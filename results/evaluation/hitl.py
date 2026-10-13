"""HITL input-to-post-state checks. This uses each row's actual elapsed dt."""
from pathlib import Path
from .provenance import write_provenance
import math, os
import numpy as np
import pandas as pd
from config.settings import Settings, OPERATIONS
from preprocessing.hitl_cases import extract_hitl

def evaluate_hitl(path, out, cfg=None):
    cfg = cfg or Settings(max_cases=1)
    OUT = Path(out)
    OUT.mkdir(parents=True, exist_ok=True)
    write_provenance(path, OUT, cfg)
    CSV = extract_hitl(path, OUT / 'selected_telemetry.csv', cfg.max_cases)
    MAX = cfg.max_cases
    COMP = ['H-Speed', 'V-Speed', 'Vel-Disp', 'Gnd-Disp', 'Vert-Disp', 'Heading', 'Roll', 'Pitch', 'Yaw']
    TOL, MODELS, OPS = (cfg.tolerances, ['HITL'], OPERATIONS)
    raw = pd.read_csv(CSV, low_memory=False)
    raw['row_index'] = raw.index
    if not {'Operation', 'Case'}.issubset(raw.columns):
        raise ValueError('The selected CSV must contain Operation and Case columns.')
    valid = raw.mission_run_id.astype(str).str.fullmatch('mission_\\d{8}_\\d{6}', na=False)
    d = raw.loc[valid].copy()
    cols = ['generated_' + c for c in ['gpi_lat', 'gpi_lon', 'gpi_relative_alt', 'gpi_vx', 'gpi_vy', 'gpi_vz', 'gpi_hdg', 'att_roll', 'att_pitch', 'att_yaw', 'vfr_groundspeed', 'vfr_heading', 'vfr_climb']]
    inputs = ['input_gpi_' + c for c in ['lat', 'lon', 'relative_alt', 'vx', 'vy', 'vz']]
    for name in cols + inputs + ['mission_seq', 'command_id', 'param1', 'dt']:
        if name not in d:
            d[name] = np.nan
        d[name] = pd.to_numeric(d[name], errors='coerce')
    if d.empty:
        raise ValueError('No valid telemetry rows.')
    d['Model'] = 'HITL'
    d = d[d.Operation.isin(OPS)].copy()
    index = d.groupby(['Model', 'Operation', 'Case'], sort=False).agg(Source_Row_Start=('row_index', 'min'), Telemetry_Rows=('row_index', 'size')).reset_index()
    keep = index.sort_values('Source_Row_Start').groupby(['Model', 'Operation'], sort=False).head(MAX).index if MAX is not None else index.index
    selected = d[d.Case.isin(index.loc[keep, 'Case'])].copy()
    d = selected.reset_index(drop=True)
    p = d[inputs].rename(columns=lambda name: name.replace('input_', 'generated_'))
    dt = d.dt.where(np.isfinite(d.dt) & (d.dt > 0))
    finite = lambda *s: np.logical_and.reduce([x.notna() & np.isfinite(x) for x in s])
    angle = lambda a, b: abs((a - b + 180) % 360 - 180)
    vx, vy, vz = [d['generated_gpi_' + name] / 100 for name in ['vx', 'vy', 'vz']]
    vxy = np.hypot(vx, vy)
    gs, climb = (d.generated_vfr_groundspeed, d.generated_vfr_climb)
    a, b, c, e = (p.generated_gpi_lat / 10000000.0, p.generated_gpi_lon / 10000000.0, d.generated_gpi_lat / 10000000.0, d.generated_gpi_lon / 10000000.0)
    q = (np.sin(np.radians(c - a) / 2) ** 2 + np.cos(np.radians(a)) * np.cos(np.radians(c)) * np.sin(np.radians(e - b) / 2) ** 2).clip(0, 1)
    disp = 2 * 6371000 * np.arctan2(np.sqrt(q), np.sqrt(1 - q))
    dalt = (d.generated_gpi_relative_alt - p.generated_gpi_relative_alt) / 1000
    gh, vh, yaw = (d.generated_gpi_hdg / 100, d.generated_vfr_heading % 360, d.generated_att_yaw)
    aN, aE, aD = [(d['generated_gpi_' + name] - p['generated_gpi_' + name]) / 100 / dt for name in ['vx', 'vy', 'vz']]
    af, ar, vc = (aN * np.cos(yaw) + aE * np.sin(yaw), -aN * np.sin(yaw) + aE * np.cos(yaw), 9.80665 - aD)
    pe, re = (np.arctan2(-af, vc), np.arctan2(ar, np.sqrt(vc ** 2 + af ** 2)))
    pos = d.generated_gpi_lat.ne(p.generated_gpi_lat) | d.generated_gpi_lon.ne(p.generated_gpi_lon)
    alt = d.generated_gpi_relative_alt.ne(p.generated_gpi_relative_alt)
    hk = d.generated_gpi_hdg.ne(65535)
    rp = finite(dt, p.generated_gpi_vx, p.generated_gpi_vy, p.generated_gpi_vz, vx, vy, vz, d.generated_att_roll, d.generated_att_pitch, yaw, aN, aE, aD)
    checks = [('H-Speed', abs(vxy - gs), finite(vx, vy, gs)), ('V-Speed', abs(vz + climb), finite(vz, climb)), ('Vel-Disp', abs(disp - vxy * dt), finite(a, b, c, e, vxy, dt) & pos), ('Gnd-Disp', abs(disp - gs * dt), finite(a, b, c, e, gs, dt) & pos), ('Vert-Disp', abs(dalt + vz * dt), finite(dalt, vz, dt) & alt), ('Heading', angle(gh, vh), finite(gh, vh) & hk), ('Roll', angle(np.degrees(d.generated_att_roll), np.degrees(re)), rp), ('Pitch', angle(np.degrees(d.generated_att_pitch), np.degrees(pe)), rp), ('Yaw', angle(np.degrees(yaw) % 360, gh % 360), finite(yaw, gh) & hk)]
    parts = []
    for name, error, mask in checks:
        mask &= finite(error)
        x = d.loc[mask, ['row_index', 'Model', 'Operation', 'Case', 'mission_run_id', 'mission_seq']].copy()
        x['check'], x['error'], x['tolerance'] = (name, error.loc[mask], TOL[name])
        x['passed'] = x.error <= TOL[name]
        x['score'] = x.passed.astype(float) if cfg.profile == 'notebook' else (1 - x.error.abs() / TOL[name]).clip(0, 1)
        parts.append(x)
    DETAILS = pd.concat(parts, ignore_index=True)
    SUMMARY = DETAILS.groupby(['Model', 'Operation', 'check']).passed.agg(Applicable='size', Passing='sum').reset_index()
    SUMMARY['Breaches'] = SUMMARY.Applicable - SUMMARY.Passing
    SUMMARY['Compliance'] = SUMMARY.Passing / SUMMARY.Applicable
    case_keys = ['Model', 'Operation', 'Case']
    case_index = pd.MultiIndex.from_frame(selected[case_keys].drop_duplicates())
    RESULTS = DETAILS.groupby(case_keys + ['check']).score.mean().unstack('check').reindex(index=case_index, columns=COMP).reset_index()
    OPS_COMP = OPS
    COMP_TABLE = RESULTS.groupby(['Model', 'Operation'], sort=False)[COMP].mean().reindex(pd.MultiIndex.from_product([MODELS, OPS], names=['Model', 'Operation'])).reset_index()
    COMP_TABLE.loc[COMP_TABLE.Operation.isin(['TAKEOFF', 'LAND']), 'Heading'] = np.nan
    COMP_TABLE['Model'] = pd.Categorical(COMP_TABLE.Model, MODELS, ordered=True)
    COMP_TABLE['Operation'] = pd.Categorical(COMP_TABLE.Operation, OPS_COMP, ordered=True)
    COMP_TABLE = COMP_TABLE.sort_values(['Model', 'Operation']).reset_index(drop=True)
    AVERAGES = COMP_TABLE.set_index(['Model', 'Operation'])[COMP].mean(axis=1).unstack().reindex(index=MODELS, columns=OPS_COMP)
    os.makedirs(OUT, exist_ok=True)
    DETAILS.to_csv(str(OUT) + '/details.csv', index=False)
    SUMMARY.to_csv(str(OUT) + '/pooled_sample_counts.csv', index=False)
    RESULTS.to_csv(str(OUT) + '/case_component_compliance.csv', index=False)
    COMP_TABLE.to_csv(str(OUT) + '/component_compliance_fractions.csv', index=False)
    AVERAGES.to_csv(str(OUT) + '/operation_average_compliance.csv')
    index.loc[keep].to_csv(str(OUT) + '/selected_cases.csv', index=False)
    arm_status = []
    for (operation, case), g in d[d.Operation.isin(['ARM', 'DISARM'])].groupby(['Operation', 'Case'], sort=False):
        base = pd.to_numeric(g.get('generated_hb_base_mode', pd.Series(np.nan, index=g.index)), errors='coerce')
        valid_base = base.notna() & np.isfinite(base) & base.between(0, 255) & base.mod(1).eq(0)
        hb_pass = (base.loc[valid_base].astype('int64') & 128 != 0) == (operation == 'ARM')
        checks_ground = []

        def add_ground(values, tolerance):
            values = pd.to_numeric(values, errors='coerce')
            if values.notna().any():
                checks_ground.append(bool((values.dropna().abs() <= tolerance).all()))
        for name, tolerance in [('generated_vfr_groundspeed', 0.2), ('generated_vfr_climb', 0.2), ('generated_gpi_vx', 20), ('generated_gpi_vy', 20), ('generated_gpi_vz', 20), ('generated_gpi_relative_alt', 200)]:
            if name in g:
                add_ground(g[name], tolerance)
        if g.generated_gpi_vx.notna().any() and g.generated_gpi_vy.notna().any():
            add_ground(np.hypot(g.generated_gpi_vx, g.generated_gpi_vy), 20)
        for axis in ['lat', 'lon']:
            generated = g['generated_gpi_' + axis]
            reference = g['input_gpi_' + axis].dropna()
            if generated.notna().any():
                if reference.empty:
                    checks_ground.append(False)
                else:
                    add_ground(generated - reference.iloc[0], 20)
        has_motion = bool(checks_ground)
        motion_pass = all(checks_ground) if has_motion else np.nan
        heartbeat_pass = bool(valid_base.all() and hb_pass.all()) if len(hb_pass) else False
        arm_status.append(dict(Operation=operation, Case=case, Heartbeat_Samples=len(hb_pass), Heartbeat_Passing=int(hb_pass.sum()), Heartbeat_Pass=heartbeat_pass, Has_Motion=has_motion, Ground_Motion_Pass=motion_pass, Pass=heartbeat_pass and (bool(motion_pass) if has_motion else True)))
    ARM_DISARM_STATUS = pd.DataFrame(arm_status, columns=['Operation', 'Case', 'Heartbeat_Samples', 'Heartbeat_Passing', 'Heartbeat_Pass', 'Has_Motion', 'Ground_Motion_Pass', 'Pass'])
    ARM_DISARM_STATUS.to_csv(str(OUT) + '/arm_disarm_status.csv', index=False)
    return {'components': COMP_TABLE, 'cases': RESULTS, 'details': DETAILS, 'summary': SUMMARY, 'heartbeat': ARM_DISARM_STATUS}
