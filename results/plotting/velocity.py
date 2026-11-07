"""Per-model distributions of LLM-generated GLOBAL_POSITION_INT velocities.

One box plot per velocity component (vx North, vy East, vz Down), drawn from
the same selected mission IDs as Figure 8. Each box shows the generated values
of one model, with every sample overlaid as a jittered dot. The shaded band
marks the plausible range for a multirotor (horizontal +/-12 m/s, vertical
-3 to 1.5 m/s, down-positive). For vz, exact zeros (hover/ground) are dropped
and a symmetric-log axis is used so small and large rates are both visible.
"""
from pathlib import Path
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter, NullLocator
from config.settings import MISSIONS, MODELS
from .common import plt

BOX_COLORS = ['#9ecae1', '#fdae6b', '#a1d99b', '#d4b9da', '#fdd0a2']
DOT_COLORS = ['#1f77b4', '#d95f0e', '#238b45', '#8056a9', '#a66a2e']

# column, y-axis label, plausible band (m/s), output name
COMPONENTS = [
    ('generated_gpi_vx', r'$v_x$ (North) (m/s)', (-12, 12), 'vx_boxplot'),
    ('generated_gpi_vy', r'$v_y$ (East) (m/s)', (-12, 12), 'vy_boxplot'),
    ('generated_gpi_vz', r'$v_z$ (Down) (m/s)', (-3, 1.5), 'vz_boxplot'),
]


def velocity_samples(path, missions=None):
    """Return {component column: [array of m/s values per model in MODELS order]}."""
    missions = missions or MISSIONS
    id2model = {mid: m for m, ids in missions.items() for mid in ids}
    raw = pd.read_csv(path, low_memory=False)
    missing = set(id2model) - set(raw.mission_run_id.dropna().astype(str))
    if missing:
        raise ValueError('Selected missions absent from input: ' + str(sorted(missing)))
    df = raw[raw.mission_run_id.astype(str).isin(id2model)].copy()
    df['Model'] = df.mission_run_id.astype(str).map(id2model)
    models = [m for m in MODELS if m in missions]
    samples = {}
    for col, _, _, _ in COMPONENTS:
        per_model = []
        for m in models:
            a = (pd.to_numeric(df.loc[df.Model == m, col], errors='coerce') / 100).dropna().to_numpy()  # cm/s -> m/s
            if col == 'generated_gpi_vz':
                a = a[a != 0]
            per_model.append(a)
        samples[col] = per_model
    return models, samples


def plot_velocity_boxplots(path, out, missions=None):
    """Write vx/vy/vz box plots (PNG at 300 dpi and PDF) and a summary CSV to `out`."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    models, samples = velocity_samples(path, missions)
    xs = np.arange(1, len(models) + 1)
    summary = []

    for col, ylabel, band, name in COMPONENTS:
        values = samples[col]
        fig, ax = plt.subplots(figsize=(12, 5))

        if col == 'generated_gpi_vz':
            ax.set_yscale('symlog', linthresh=0.1, linscale=1.1)
            ax.set_ylim(-29, 29)
            ax.set_yticks([-20, -1, -.1, 0, .1, 1, 20])  # +/-5 omitted: overlaps +/-20 at this font size
            # symlog would otherwise label only decades (10^0, 10^-1); show the chosen ticks as plain numbers
            ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:g}'))
            ax.yaxis.set_minor_locator(NullLocator())
        ax.axhspan(*band, color='#9ecae1', alpha=.18)
        for limit in band:
            ax.axhline(limit, color='#3077b7', ls='--', lw=1.3)
        ax.axhline(0, color='black', lw=1.2)

        bp = ax.boxplot(
            values, positions=xs, widths=.55,
            patch_artist=True, showfliers=False,
            medianprops=dict(color='black', lw=3),
            boxprops=dict(color='#333333', lw=2.5),
            whiskerprops=dict(color='#333333', lw=2.5),
            capprops=dict(color='#333333', lw=2.5),
        )

        for i, (box, a) in enumerate(zip(bp['boxes'], values)):
            box.set_facecolor(BOX_COLORS[i])
            box.set_alpha(.75)
            rng = np.random.default_rng(100 + i)  # fixed seed: reproducible jitter
            jitter = rng.uniform(-.16, .16, len(a))
            ax.scatter(xs[i] + jitter, a, s=24, color=DOT_COLORS[i], alpha=.8,
                       edgecolors='white', linewidth=.3, zorder=3)
            inside = np.mean((a >= band[0]) & (a <= band[1])) if len(a) else np.nan
            summary.append({'Component': name.split('_')[0], 'Model': models[i], 'n': len(a),
                            'median_mps': np.median(a) if len(a) else np.nan,
                            'q1_mps': np.percentile(a, 25) if len(a) else np.nan,
                            'q3_mps': np.percentile(a, 75) if len(a) else np.nan,
                            'min_mps': a.min() if len(a) else np.nan,
                            'max_mps': a.max() if len(a) else np.nan,
                            'band_low_mps': band[0], 'band_high_mps': band[1],
                            'fraction_in_band': inside})

        ax.set_xticks(xs)
        ax.set_xticklabels(models, rotation=35, ha='right', fontsize=22)
        ax.set_ylabel(ylabel, fontsize=22)
        ax.tick_params(axis='both', labelsize=22)
        ax.grid(axis='y', alpha=.25)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

        fig.tight_layout()
        fig.savefig(out / f'{name}.pdf', bbox_inches='tight')
        fig.savefig(out / f'{name}.png', dpi=300, bbox_inches='tight')
        plt.close(fig)

    pd.DataFrame(summary).to_csv(out.parent / 'velocity_summary.csv', index=False)
    return pd.DataFrame(summary)
