"""Score LLM cases and generate Figures 6/7 and model-performance plots."""
from _bootstrap import ROOT
from scripts._arguments import parser,settings
from evaluation.llm import evaluate_llm
from evaluation.trajectory import evaluate_trajectory
from plotting.results import plot_llm

if __name__=='__main__':
    p=parser(__doc__,ROOT,'mission_llm_generation_v2_final_mission_wise.csv','llm')
    p.add_argument('--trajectory-gate',choices=['sa','salc'],default='sa')
    args=p.parse_args()
    tables=evaluate_llm(args.input,args.out,settings(args))
    evaluate_trajectory(tables,args.out/'trajectory',args.trajectory_gate)
    plot_llm(tables,args.out/'figures')
    print(tables['metrics'].round(3).to_string(index=False))
    print(f'Saved results to {args.out.resolve()}')
