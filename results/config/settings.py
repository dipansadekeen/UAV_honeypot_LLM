"""Experiment constants and explicit scoring profiles; no hidden notebook state."""
from dataclasses import dataclass, field
import math

COMPONENTS = ['H-Speed', 'V-Speed', 'Vel-Disp', 'Gnd-Disp', 'Vert-Disp', 'Heading', 'Yaw', 'Roll', 'Pitch']
OPERATIONS = ['ARM', 'DISARM', 'TAKEOFF', 'LAND', 'RTL', 'WP', 'WP+ALT', 'WP+YAW', 'WP+SPEED']
MODELS = ['gpt-oss-20b', 'gpt-oss-120b', 'nemotron-super', 'nemotron-nano', 'gemma4']
MODEL_MAP = {
    'gpt-oss:20b-cloud': 'gpt-oss-20b', 'gpt-oss:120b-cloud': 'gpt-oss-120b',
    'gemma4:31b-cloud': 'gemma4', 'nemotron-3-super:cloud': 'nemotron-super',
    'nemotron-3-nano:30b-cloud': 'nemotron-nano',
}
MISSIONS = {
    'gpt-oss-20b': ['mission_20260916_213308'],
    'gpt-oss-120b': ['mission_20260911_145555'],
    'gemma4': ['mission_20260910_145238'],
    'nemotron-super': ['mission_20260909_213041'],
    'nemotron-nano': ['mission_20260909_234208'],
}
CLASSES = ['SALC', 'SANLC', 'FALC', 'FANLC']

@dataclass(frozen=True)
class Settings:
    """notebook = binary pass fractions; paper = clipped linear error scores."""
    profile: str = 'notebook'
    max_cases: int | None = 5
    dt: float = 0.5
    speed_gate: float = 0.2
    lc_threshold: float = 0.5
    latlon_tol: float = 200.0  # units: degrees * 1e7
    altitude_tol_mm: float = 1500.0
    land_altitude_mm: float = 500.0
    heartbeat_prefix: str = 'input_hb_'
    tolerances: dict = field(default_factory=lambda: dict(zip(
        COMPONENTS, [2., 2., 2.8, 2.8, 2.8, 45., 45., 24., 24.])))
    expected_custom_modes: dict = field(default_factory=lambda: {
        'ARM': {50593792}, 'DISARM': {0, 50593792}})

    def __post_init__(self):
        if self.profile not in {'notebook', 'paper'}:
            raise ValueError('profile must be notebook or paper')
        if self.max_cases is not None and self.max_cases < 1:
            raise ValueError('max_cases must be positive or None (all)')
        if not math.isfinite(self.dt) or self.dt <= 0:
            raise ValueError('dt must be finite and positive')
        if not 0 <= self.lc_threshold <= 1:
            raise ValueError('lc_threshold must lie in [0, 1]')
        if set(self.tolerances) != set(COMPONENTS) or any(
            not math.isfinite(v) or v <= 0 for v in self.tolerances.values()):
            raise ValueError('Every component needs a finite positive tolerance')
