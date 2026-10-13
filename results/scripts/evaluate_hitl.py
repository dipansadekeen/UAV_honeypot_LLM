"""Select HITL operation cases and evaluate input-to-post-state compliance."""
from _bootstrap import ROOT
from scripts._arguments import parser,settings
from evaluation.hitl import evaluate_hitl
from plotting.results import plot_hitl

if __name__=='__main__':
    args=parser(__doc__,ROOT,'HITL1_converted.csv','hitl',max_cases=1).parse_args()
    tables=evaluate_hitl(args.input,args.out,settings(args))
    plot_hitl(tables,args.out/'figures')
    print(tables['components'].round(3).to_string(index=False))
    print(f'Saved results to {args.out.resolve()}')
