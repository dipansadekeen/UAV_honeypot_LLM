"""Few-shot ablation: run-selection rule, plan-based operations, and bundled-data totals."""
import sys
import tempfile
import unittest
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.ablation import plan_operations, select_runs, read_runs, evaluate_ablation

DATA = ROOT / 'data' / 'ablation_dataset.csv'


def run(title, failed, mission, setting='ab2', model='gpt-oss-120b'):
    g = pd.DataFrame({'mission_run_id': [mission], 'row_index': [0]})
    return {'setting': setting, 'model': model, 'title': title, 'failed': failed, 'g': g}


class SelectionTests(unittest.TestCase):
    def test_top_two_successes_keep_failures_in_between(self):
        runs = select_runs([run('a', False, 'm1'), run('b-fail', True, 'm2'), run('c', False, 'm3'),
                            run('d-fail', True, 'm4'), run('e', False, 'm5')])
        self.assertEqual([r['selected'] for r in runs], [True, True, True, False, False])

    def test_limit_is_per_setting_and_model(self):
        runs = select_runs([run('a', False, 'm1'), run('b', False, 'm2'), run('c', False, 'm3', model='gemma4'),
                            run('d', False, 'm4', setting='ab3'), run('e', False, 'm5')])
        self.assertEqual([r['selected'] for r in runs], [True, True, True, True, False])

    def test_exact_duplicate_section_counted_once(self):
        runs = select_runs([run('a-fail', True, 'm1'), run('a-fail', True, 'm1'), run('b', False, 'm2')])
        self.assertEqual([r['selected'] for r in runs], [True, False, True])


class PlanTests(unittest.TestCase):
    def test_ablation_mission_plan(self):
        plan = pd.DataFrame({'mission_seq': range(7), 'command_id': [22, 16, 16, 178, 16, 20, 21],
                             'param4': [None, None, None, 0, 0, 0, 0],
                             'param7': [50, 60.67, 50.0, 0, 50, 50, 0]})
        self.assertEqual(list(plan_operations(plan).values()),
                         ['TAKEOFF', 'WP+ALT', 'WP+ALT', 'WP+SPEED', 'RTL', 'LAND'])

    def test_level_and_yaw_waypoints(self):
        plan = pd.DataFrame({'mission_seq': range(3), 'command_id': [22, 16, 16],
                             'param4': [None, None, 90], 'param7': [50, 50, 50]})
        self.assertEqual(list(plan_operations(plan).values()), ['TAKEOFF', 'WP', 'WP+YAW'])


@unittest.skipUnless(DATA.exists(), 'bundled ablation dataset missing')
class BundledDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.result = evaluate_ablation(DATA, cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_run_selection(self):
        r = self.result['runs']
        self.assertEqual((len(r), int(r.selected.sum())), (44, 39))
        dropped = set(r.loc[~r.selected, 'mission_run_id'])
        self.assertEqual(dropped, {'mission_20261030_175714', 'mission_20261030_211731', 'mission_20261031_200008',
                                   'mission_20261103_172829', 'mission_20261103_173411'})

    def test_case_totals(self):
        s = self.result['summary'].set_index(['Setting', 'Model'])
        self.assertEqual([int(s.loc[(k, 'All'), 'Cases']) for k in ['full', 'ab1', 'ab2', 'ab3']], [54, 42, 52, 57])
        self.assertEqual([int(s.loc[(k, 'All'), 'SALC']) for k in ['full', 'ab1', 'ab2', 'ab3']], [31, 26, 33, 32])


if __name__ == '__main__':
    unittest.main()
