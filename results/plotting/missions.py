"""Figure 8 mission averages from explicitly selected mission IDs.
Normalized progress is row-based, not elapsed time. Altitude uses VFR_HUD.alt
as in the notebook; this is not mixed with relative altitude for these plots.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from config.settings import MISSIONS
from .common import plt, save, COLORS, MODEL_COLORS

def prepare_missions(path, out, missions=None, npts=200):
    missions = missions or MISSIONS
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    TARGET_CMDS = [22, 16, 20, 21]
    used = missions
    id2model = {mid: m for m, ids in used.items() for mid in ids}
    raw = pd.read_csv(path, low_memory=False)
    missing = set(id2model) - set(raw.mission_run_id.dropna().astype(str))
    if missing:
        raise ValueError('Selected missions absent from input: ' + str(sorted(missing)))
    df = raw[raw.mission_run_id.astype(str).isin(id2model)].copy()
    df['Model'] = df.mission_run_id.map(id2model)
    for c in ['command_id', 'mission_seq', 'target_lat', 'target_lon', 'target_alt', 'generated_gpi_lat', 'generated_gpi_lon', 'generated_gpi_vx', 'generated_gpi_vy', 'generated_gpi_vz', 'generated_gpi_hdg', 'generated_vfr_alt', 'generated_vfr_groundspeed', 'generated_vfr_climb']:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors='coerce')
    progress = np.linspace(0, 1, npts)
    mission_series = []
    default_rows = []

    def interp(y):
        y = np.asarray(y, dtype=float)
        x = np.arange(len(y))
        ok = np.isfinite(y)
        if ok.sum() < 2:
            return np.full(npts, np.nan)
        return np.interp(progress, np.linspace(0, 1, ok.sum()), y[ok])

    def circmean_deg(A):
        A = np.radians(np.asarray(A, dtype=float))
        return np.degrees(np.arctan2(np.nanmean(np.sin(A), axis=0), np.nanmean(np.cos(A), axis=0))) % 360
    for (model, mid), g in df.groupby(['Model', 'mission_run_id'], sort=False):
        g = g.reset_index(drop=True)
        lat = g['generated_gpi_lat'].to_numpy(float) / 10000000.0
        lon = g['generated_gpi_lon'].to_numpy(float) / 10000000.0
        good = np.isfinite(lat) & np.isfinite(lon) & ~((lat == 0) & (lon == 0))
        if good.sum() < 2:
            continue
        lat0, lon0 = (lat[good][0], lon[good][0])
        mlat = 111320.0
        mlon = 111320.0 * np.cos(np.radians(lat0))
        E = (lon - lon0) * mlon
        N = (lat - lat0) * mlat
        alt = g['generated_vfr_alt'].to_numpy(float)
        vx = g['generated_gpi_vx'].to_numpy(float) / 100.0
        vy = g['generated_gpi_vy'].to_numpy(float) / 100.0
        vz = g['generated_gpi_vz'].to_numpy(float) / 100.0
        gs = g['generated_vfr_groundspeed'].to_numpy(float)
        climb = g['generated_vfr_climb'].to_numpy(float)
        speed = np.hypot(vx, vy)
        vh = np.degrees(np.arctan2(vy, vx)) % 360
        rh = g['generated_gpi_hdg'].to_numpy(float) / 100.0 % 360
        bad_hdg = (g['generated_gpi_hdg'].to_numpy(float) < 0) | (g['generated_gpi_hdg'].to_numpy(float) > 35999)
        rh[bad_hdg] = np.nan
        mission_series.append({'Model': model, 'Mission': mid, 'E': interp(E), 'N': interp(N), 'alt': interp(alt), 'gs': interp(gs), 'climb': interp(climb), 'vx': interp(vx), 'vy': interp(vy), 'vz': interp(vz), 'speed': interp(speed), 'vh': interp(vh), 'rh': interp(rh), 'max_alt': np.nanmax(alt), 'mean_speed': np.nanmean(gs), 'rows': len(g), 'items': g['mission_seq'].nunique()})
        x = g[g['command_id'].isin(TARGET_CMDS)].copy().drop_duplicates(['command_id', 'mission_seq']).sort_values('mission_seq')
        for _, r in x.iterrows():
            cid = int(r['command_id'])
            seq = int(r['mission_seq']) if pd.notna(r['mission_seq']) else -1
            talt = pd.to_numeric(r.get('target_alt', np.nan), errors='coerce')
            if cid == 22:
                default_rows.append({'Seq': seq - 0.1, 'tE': 0.0, 'tN': 0.0, 'tAlt': 0.0})
                if pd.notna(talt):
                    default_rows.append({'Seq': seq, 'tE': 0.0, 'tN': 0.0, 'tAlt': talt})
                continue
            tlat = pd.to_numeric(r.get('target_lat', np.nan), errors='coerce')
            tlon = pd.to_numeric(r.get('target_lon', np.nan), errors='coerce')
            if pd.isna(tlat) or pd.isna(tlon) or (tlat == 0 and tlon == 0):
                continue
            tE = (tlat * 0 + tlon / 10000000.0 - lon0) * mlon
            tN = (tlat / 10000000.0 - lat0) * mlat
            if cid == 21:
                talt = 0.0
            if pd.notna(talt):
                default_rows.append({'Seq': seq, 'tE': tE, 'tN': tN, 'tAlt': talt})
    AVG = {}
    for model in used:
        S = [x for x in mission_series if x['Model'] == model]
        if not S:
            continue
        stack = lambda k: np.vstack([x[k] for x in S])
        AVG[model] = {'n': len(S), 'E': np.nanmean(stack('E'), axis=0), 'N': np.nanmean(stack('N'), axis=0), 'alt': np.nanmean(stack('alt'), axis=0), 'gs': np.nanmean(stack('gs'), axis=0), 'climb': np.nanmean(stack('climb'), axis=0), 'vx': np.nanmean(stack('vx'), axis=0), 'vy': np.nanmean(stack('vy'), axis=0), 'vz': np.nanmean(stack('vz'), axis=0), 'speed': np.nanmean(stack('speed'), axis=0), 'vh': circmean_deg(stack('vh')), 'rh': circmean_deg(stack('rh')), 'max_alt': np.nanmean([x['max_alt'] for x in S]), 'mean_speed': np.nanmean([x['mean_speed'] for x in S]), 'rows': np.nanmean([x['rows'] for x in S]), 'items': np.nanmean([x['items'] for x in S])}
    DEFAULT = pd.DataFrame(default_rows)
    DEFAULT_AVG = DEFAULT.groupby('Seq', sort=True)[['tE', 'tN', 'tAlt']].mean().reset_index().sort_values('Seq') if not DEFAULT.empty else pd.DataFrame()
    records = []
    for model, a in AVG.items():
        for j, p in enumerate(progress):
            records.append({'Model': model, 'Progress (%)': p * 100, 'Missions': a['n'], **{k: a[k][j] for k in ['E', 'N', 'alt', 'vx', 'vy', 'vz', 'gs', 'climb', 'speed', 'rh', 'vh']}})
    pd.DataFrame(records).to_csv(out / 'averaged_mission_samples.csv', index=False)
    DEFAULT_AVG.to_csv(out / 'default_target_path.csv', index=False)
    (out / 'selected_missions.json').write_text(json.dumps(missions, indent=2))
    pd.DataFrame([{'Model': m, 'Cases Averaged': a['n'], 'Avg Samples': a['rows'], 'Avg Items': a['items'], 'Max altitude (m)': a['max_alt'], 'Mean speed (m/s)': a['mean_speed']} for m, a in AVG.items()]).to_csv(out / 'average_mission_summary.csv', index=False)
    return (AVG, DEFAULT_AVG)

def plot_missions(averages, default, out, speed_gate=1.0):
    progress = np.linspace(0, 100, len(next(iter(averages.values()))['E']))
    fig, ax = plt.subplots(figsize=(9, 7))
    for i, (model, a) in enumerate(averages.items()):
        ax.plot(a['E'], a['N'], label=model, color=MODEL_COLORS.get(model, COLORS[i % len(COLORS)]), lw=2)
    if not default.empty:
        ax.plot(default.tE, default.tN, 'k:x', label='Default path', lw=2, ms=7)
    ax.set_xlabel('East (m)')
    ax.set_ylabel('North (m)')
    ax.set_aspect('equal', adjustable='datalim')
    ax.grid(alpha=0.3)
    ax.legend()
    save(fig, out, 'fig08b_trajectory_2d')
    fig = plt.figure(figsize=(10, 7))
    ax = fig.add_subplot(111, projection='3d')
    for i, (model, a) in enumerate(averages.items()):
        ax.plot(a['E'], a['N'], a['alt'], label=model, color=MODEL_COLORS.get(model, COLORS[i % len(COLORS)]), lw=2)
    if not default.empty:
        ax.plot(default.tE, default.tN, default.tAlt, 'k:x', label='Default path', lw=2)
    ax.set_xlabel('East (m)', labelpad=12)
    ax.set_ylabel('North (m)', labelpad=12)
    ax.set_zlabel('Altitude (m)', labelpad=12)
    ax.view_init(25, -55)
    ax.legend(loc='upper left')
    save(fig, out, 'trajectory_3d')
    for keys, labels, name in [(['vx', 'vy', 'vz'], ['North velocity (m/s)', 'East velocity (m/s)', 'Down velocity (m/s)'], 'fig08a_velocity_components'), (['alt', 'gs', 'climb'], ['Altitude (m)', 'Groundspeed (m/s)', 'Climb (m/s)'], 'flight_performance')]:
        fig, axs = plt.subplots(1, 3, figsize=(16, 4.8))
        for i, (model, a) in enumerate(averages.items()):
            for ax, key in zip(axs, keys):
                ax.plot(progress, a[key], color=MODEL_COLORS.get(model, COLORS[i % len(COLORS)]), lw=2, label=model)
        for ax, label in zip(axs, labels):
            ax.set_xlabel('Mission progress (%)')
            ax.set_ylabel(label)
            ax.grid(alpha=0.25)
        axs[0].legend(fontsize=9)
        save(fig, out, name)
    fig, ax = plt.subplots(figsize=(8, 7))
    for i, (model, a) in enumerate(averages.items()):
        valid = np.isfinite(a['rh']) & np.isfinite(a['vh']) & (a['speed'] >= speed_gate)
        ax.scatter(a['rh'][valid], a['vh'][valid], label=model, color=MODEL_COLORS.get(model, COLORS[i % len(COLORS)]), s=25, alpha=0.65)
    ax.plot([0, 360], [0, 360], 'k--', label='Ideal agreement')
    ax.set(xlim=(0, 360), ylim=(0, 360), xlabel='Reported heading (deg)', ylabel='Velocity direction (deg)')
    ax.grid(alpha=0.25)
    ax.legend()
    save(fig, out, 'fig08c_heading')
