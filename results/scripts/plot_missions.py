"""Generate Figure 8 with reproducible selected mission IDs."""
from _bootstrap import ROOT
from pathlib import Path
import argparse,json
from plotting.missions import prepare_missions,plot_missions

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,default=ROOT/'data/mission_llm_generation_v2_final_mission_wise.csv')
    p.add_argument('--out',type=Path,default=ROOT/'results/missions')
    p.add_argument('--missions',type=Path,help='JSON mapping canonical model names to mission ID lists')
    p.add_argument('--npts',type=int,default=200)
    args=p.parse_args()
    if args.npts<2: p.error('--npts must be at least 2')
    missions=json.loads(args.missions.read_text()) if args.missions else None
    averages,default=prepare_missions(args.input,args.out,missions,args.npts)
    plot_missions(averages,default,args.out/'figures')
    print(f'Saved mission figures to {args.out.resolve()}')
