"""Notebook parity and boundary-condition tests using the standard library."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config.settings import Settings,COMPONENTS
from evaluation.telemetry import errors,component_scores
from evaluation.common import adiff
from evaluation.heartbeat import heartbeat_checks
from evaluation.completion import complete
from evaluation.llm import evaluate_llm
from evaluation.hitl import evaluate_hitl
from evaluation.latency import evaluate_latency
from evaluation.trajectory import evaluate_trajectory
from prompts.validation import validate_heartbeat,validate_telemetry
from preprocessing.hitl_cases import csv_candidates,selected_candidates

class FormulaTests(unittest.TestCase):
    def test_binary_and_paper_scores_have_explicitly_different_meaning(self):
        values=pd.DataFrame({name:[0,t,t*2,np.nan] for name,t in Settings().tolerances.items()})
        a=component_scores(values,Settings());b=component_scores(values,Settings(profile='paper'))
        np.testing.assert_array_equal(a['H-Speed'][:3],[1,1,0])
        np.testing.assert_array_equal(b['H-Speed'][:3],[1,0,0])
        self.assertTrue(a.iloc[3].isna().all() and b.iloc[3].isna().all())

    def test_sequential_errors_never_cross_calls(self):
        rows=[]
        for i,call in enumerate(['a','a','b']):
            rows.append(dict(row_index=i,mission_run_id='mission',mission_seq=1,
                llm_call_id=call,llm_step_index=1 if call=='b' else i+1,
                generated_gpi_lat=400000000,generated_gpi_lon=-700000000,
                generated_gpi_relative_alt=1000,generated_gpi_vx=0,
                generated_gpi_vy=0,generated_gpi_vz=0,
                generated_vfr_groundspeed=0,generated_vfr_heading=0,
                generated_vfr_climb=0,generated_att_yaw=0,
                generated_att_roll=0,generated_att_pitch=0))
        e=errors(pd.DataFrame(rows),Settings())
        self.assertTrue(np.isnan(e['Vel-Disp'].iloc[0]))
        self.assertEqual(e['Vel-Disp'].iloc[1],0)
        self.assertTrue(np.isnan(e['Vel-Disp'].iloc[2]))
        self.assertTrue(e.Heading.isna().all())

    def test_wrapped_angle(self):
        self.assertEqual(adiff(359,1),2)
        self.assertEqual(adiff(1,359),2)

    def test_ned_climb_sign(self):
        r=dict(row_index=0,mission_run_id='mission',mission_seq=1,llm_call_id='a',llm_step_index=1,
            generated_gpi_vx=0,generated_gpi_vy=0,generated_gpi_vz=-100,
            generated_vfr_groundspeed=0,generated_vfr_heading=0,generated_vfr_climb=1)
        self.assertEqual(errors(pd.DataFrame([r]),Settings())['V-Speed'].iloc[0],0)

    def test_partial_heartbeat_never_passes(self):
        g=pd.DataFrame({'row_index':[0,1],'input_hb_base_mode':[128,np.nan],
            'input_hb_custom_mode':[50593792,50593792],'input_hb_system_status':[4,4]})
        checks,prefix=heartbeat_checks('ARM',g,Settings())
        self.assertFalse(checks.to_numpy().all())
        self.assertEqual(prefix,'input_hb_')

    def test_future_generated_heartbeat_has_priority(self):
        g=pd.DataFrame({'row_index':[0],'input_hb_base_mode':[0],
            'generated_hb_base_mode':[128],'generated_hb_custom_mode':[50593792],
            'generated_hb_system_status':[4]})
        checks,prefix=heartbeat_checks('ARM',g,Settings())
        self.assertTrue(checks.to_numpy().all());self.assertEqual(prefix,'generated_hb_')

    def test_speed_waypoint_selection(self):
        candidates=csv_candidates(ROOT/'data/HITL1_converted.csv')
        selected,coverage=selected_candidates(candidates,1)
        self.assertEqual(len(selected),9)
        speed=next(x for x in selected if x['Operation']=='WP+SPEED')
        self.assertTrue(pd.to_numeric(speed['data'].command_id).eq(16).all())
        source=pd.read_csv(ROOT/'data/HITL1_converted.csv',low_memory=False)
        prior=source[(source.mission_run_id==speed['rid']) &
                     pd.to_numeric(source.mission_seq,errors='coerce').eq(speed['seq']-1)]
        self.assertTrue(pd.to_numeric(prior.command_id,errors='coerce').eq(178).any())

class PromptTests(unittest.TestCase):
    def test_armed_bit_preserved_for_non_arm_command(self):
        response={'heartbeat_patch':{'base_mode':128,'custom_mode':0,'system_status':4},'reason':'test'}
        with self.assertRaises(ValueError): validate_heartbeat(response,16,{'base_mode':0})
        self.assertEqual(validate_heartbeat(response,400,{'base_mode':0})['base_mode'],128)

    def valid_telemetry(self):
        return {'telemetry_series':[{'dt':dt,'fields':{'SYS_STATUS':{'battery_remaining':100}}}
            for dt in [.5,1.,1.5,2.,2.5]],'reason':'test'}

    def test_offsets_and_unknown_fields(self):
        value=self.valid_telemetry();self.assertEqual(len(validate_telemetry(json.dumps(value))),5)
        invalid=copy.deepcopy(value);invalid['telemetry_series'][0]['dt']=0.6
        with self.assertRaises(ValueError): validate_telemetry(invalid)
        invalid=copy.deepcopy(value);invalid['telemetry_series'][0]['fields']['PRIVATE']={'x':0}
        with self.assertRaises(ValueError): validate_telemetry(invalid)

    def test_nan_and_bool_rejected(self):
        for v in [float('nan'),True]:
            value=self.valid_telemetry();value['telemetry_series'][0]['fields']['SYS_STATUS']['battery_remaining']=v
            with self.assertRaises(ValueError): validate_telemetry(value)

class NotebookParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.out=Path(cls.tmp.name)
        cls.llm=evaluate_llm(ROOT/'data/mission_llm_generation_v2_final_mission_wise.csv',cls.out/'llm')
        cls.hitl=evaluate_hitl(ROOT/'data/HITL1_converted.csv',cls.out/'hitl')
        _,cls.latency=evaluate_latency(ROOT/'data/mission_llm_generation_v2_final_mission_wise.csv',cls.out/'latency')
        _,cls.trajectory=evaluate_trajectory(cls.llm,cls.out/'trajectory')
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def compare_csv(self,actual,name,drop=()):
        actual=actual.drop(columns=list(drop),errors='ignore')
        # CSV round trip aligns nullable/bool/category dtypes with the independent reference.
        temporary=self.out/'actual.csv';actual.to_csv(temporary,index=False)
        got=pd.read_csv(temporary);expected=pd.read_csv(ROOT/f'reference/{name}.csv')
        got=got.reindex(columns=expected.columns)
        keys=[x for x in ['Model','Operation','Case','Case ID'] if x in got.columns]
        if keys:
            got=got.sort_values(keys).reset_index(drop=True)
            expected=expected.sort_values(keys).reset_index(drop=True)
        assert_frame_equal(got,expected,check_dtype=False,rtol=1e-12,atol=1e-12)

    def test_llm_metrics(self): self.compare_csv(self.llm['metrics'],'modelwise_metrics',('Score_Profile',))
    def test_all_225_case_scores(self): self.compare_csv(self.llm['cases'],'casewise_scores',('Score_Profile',))
    def test_component_compliance(self): self.compare_csv(self.llm['components'],'component_compliance')
    def test_hitl_components(self): self.compare_csv(self.hitl['components'],'hitl_components')
    def test_hitl_heartbeat(self): self.compare_csv(self.hitl['heartbeat'],'hitl_heartbeat')
    def test_latency_summary(self): self.compare_csv(self.latency,'latency_summary')
    def test_trajectory_summary(self):
        self.compare_csv(self.trajectory.rename(columns={'Eligible_Trajectories':'Successful_Trajectories'}),'trajectory_summary')

if __name__=='__main__': unittest.main()
