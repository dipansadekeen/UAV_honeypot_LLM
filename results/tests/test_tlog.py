"""Optional synthetic tlog checks; these do not replace real-log validation."""
import importlib.util,struct,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

@unittest.skipUnless(importlib.util.find_spec('pymavlink'),'Install requirements-tlog.txt to test raw-log tools')
class TlogTests(unittest.TestCase):
    def make_log(self,path):
        from pymavlink.dialects.v20 import common as m
        gcs=m.MAVLink(None,srcSystem=255,srcComponent=190)
        vehicle=m.MAVLink(None,srcSystem=1,srcComponent=1)
        frames=[
            (0.,gcs,m.MAVLink_mission_count_message(1,1,1)),
            (.1,gcs,m.MAVLink_mission_item_int_message(1,1,0,3,22,1,1,0,0,0,0,400000000,-700000000,5)),
            (.2,vehicle,m.MAVLink_mission_ack_message(255,190,0)),
        ]
        for i in range(7):
            base=128 if i<6 else 0
            frames.extend([
                (1.+i,vehicle,m.MAVLink_heartbeat_message(2,12,base,(4<<16)|(4<<24),4,3)),
                (1.01+i,vehicle,m.MAVLink_global_position_int_message(i*1000,400000000,-700000000,500000,5000,0,0,0,0)),
                (1.02+i,vehicle,m.MAVLink_attitude_message(i*1000,0,0,0,0,0,0)),
                (1.03+i,vehicle,m.MAVLink_vfr_hud_message(0,0,0,0,5,0)),
                (1.04+i,vehicle,m.MAVLink_mission_current_message(0)),
            ])
        frames.append((3.1,vehicle,m.MAVLink_mission_item_reached_message(0)))
        with path.open('wb') as f:
            for offset,encoder,msg in sorted(frames,key=lambda x:x[0]):
                f.write(struct.pack('>Q',int((1700000000+offset)*1e6)))
                f.write(msg.pack(encoder))

    def test_upload_and_vehicle_timeline(self):
        from preprocessing.tlog_to_csv import parse_tlog,build_rows
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'synthetic.tlog';self.make_log(path)
            runs,timeline,bad=parse_tlog(str(path))
            self.assertEqual(bad,0);self.assertEqual(len(runs),1)
            self.assertTrue(runs[0].flown)
            self.assertTrue(build_rows(runs[0],timeline))

    def test_heartbeat_intervals(self):
        from preprocessing.connectivity import read_tlog
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'synthetic.tlog';self.make_log(path)
            rows=read_tlog(path)
            hb=rows[rows.message_type=='HEARTBEAT']
            self.assertEqual(len(hb),7)
            self.assertTrue(hb.timestamp.diff().dropna().eq(1.).all())

if __name__=='__main__': unittest.main()
