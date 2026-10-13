"""Count one latency observation per LLM call and generate Figure 10."""
from _bootstrap import ROOT
from pathlib import Path
import argparse
from evaluation.latency import evaluate_latency
from plotting.results import plot_latency

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,default=ROOT/'data/mission_llm_generation_v2_final_mission_wise.csv')
    p.add_argument('--out',type=Path,default=ROOT/'results/latency')
    args=p.parse_args(); _,summary=evaluate_latency(args.input,args.out)
    plot_latency(summary,args.out/'figures')
    print(summary.round(3).to_string(index=False))
