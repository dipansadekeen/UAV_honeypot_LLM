"""Box plots of LLM-generated vx/vy/vz per model for the selected missions."""
from _bootstrap import ROOT
from pathlib import Path
import argparse,json
from plotting.velocity import plot_velocity_boxplots

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,default=ROOT/'data/mission_llm_generation_v2_final_mission_wise.csv')
    p.add_argument('--out',type=Path,default=ROOT/'results/velocity')
    p.add_argument('--missions',type=Path,help='JSON mapping canonical model names to mission ID lists')
    args=p.parse_args()
    missions=json.loads(args.missions.read_text()) if args.missions else None
    summary=plot_velocity_boxplots(args.input,args.out/'figures',missions)
    print(summary.round(3).to_string(index=False))
    print(f'Saved velocity box plots to {(args.out/"figures").resolve()}')
