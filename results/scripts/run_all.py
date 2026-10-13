"""Reproduce all analyses possible from the two bundled CSV datasets."""
from _bootstrap import ROOT
from pathlib import Path
from dataclasses import asdict
import argparse,hashlib,json,platform,sys
import numpy,pandas,matplotlib
from config.settings import Settings
from scripts._arguments import case_limit
from evaluation.llm import evaluate_llm
from evaluation.hitl import evaluate_hitl
from evaluation.latency import evaluate_latency
from evaluation.trajectory import evaluate_trajectory
from plotting.results import plot_llm,plot_hitl,plot_latency
from plotting.missions import prepare_missions,plot_missions

def sha256(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--llm',type=Path,default=ROOT/'data/mission_llm_generation_v2_final_mission_wise.csv')
    p.add_argument('--hitl',type=Path,default=ROOT/'data/HITL1_converted.csv')
    p.add_argument('--out',type=Path,default=ROOT/'results/notebook')
    p.add_argument('--profile',choices=['notebook','paper'],default='notebook')
    p.add_argument('--max-cases',type=case_limit,default=5)
    p.add_argument('--hitl-max-cases',type=case_limit,default=1)
    p.add_argument('--trajectory-gate',choices=['sa','salc'],default='sa')
    p.add_argument('--missions',type=Path,help='JSON mapping of models to selected mission IDs')
    p.add_argument('--no-plots',action='store_true')
    args=p.parse_args()
    llm_cfg=Settings(profile=args.profile,max_cases=args.max_cases)
    hitl_cfg=Settings(profile=args.profile,max_cases=args.hitl_max_cases)
    args.out.mkdir(parents=True,exist_ok=True)
    print('Evaluating LLM cases...',flush=True)
    llm=evaluate_llm(args.llm,args.out/'llm',llm_cfg)
    evaluate_trajectory(llm,args.out/'trajectory',args.trajectory_gate)
    print('Evaluating HITL input/post-state pairs...',flush=True)
    hitl=evaluate_hitl(args.hitl,args.out/'hitl',hitl_cfg)
    print('Summarizing per-call latency...',flush=True)
    _,latency=evaluate_latency(args.llm,args.out/'latency')
    if not args.no_plots:
        print('Rendering paper figures...',flush=True)
        plot_llm(llm,args.out/'llm/figures')
        plot_hitl(hitl,args.out/'hitl/figures')
        plot_latency(latency,args.out/'latency/figures')
        missions=json.loads(args.missions.read_text()) if args.missions else None
        avg,default=prepare_missions(args.llm,args.out/'missions',missions)
        plot_missions(avg,default,args.out/'missions/figures')
    manifest={'python':platform.python_version(),'numpy':numpy.__version__,
        'pandas':pandas.__version__,'matplotlib':matplotlib.__version__,
        'inputs':{str(path.resolve()):sha256(path) for path in [args.llm,args.hitl]},
        'llm_settings':asdict(llm_cfg),'hitl_settings':asdict(hitl_cfg),
        'trajectory_gate':args.trajectory_gate,'command':sys.argv,
        'case_count':len(llm['cases']),'hitl_selected_case_count':len(hitl['cases'])}
    (args.out/'run_manifest.json').write_text(json.dumps(manifest,indent=2,default=lambda x:sorted(x) if isinstance(x,set) else str(x)))
    print(llm['metrics'].round(3).to_string(index=False))
    print(f'Finished. Results: {args.out.resolve()}')

if __name__=='__main__': main()
