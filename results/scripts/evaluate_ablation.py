"""Score the few-shot example ablation (full / ab1 / ab2 / ab3) with the LLM case checks."""
from _bootstrap import ROOT
from scripts._arguments import parser, settings
from evaluation.ablation import evaluate_ablation

if __name__ == '__main__':
    p = parser(__doc__, ROOT, 'ablation_dataset.csv', 'ablation_fewshot', max_cases=None)
    p.add_argument('--top', type=int, default=2, help='successful runs kept per setting and model')
    args = p.parse_args()
    result = evaluate_ablation(args.input, args.out, settings(args, max_cases=None), args.top)
    s = result['summary']
    print(s[s.Model == 'All'].drop(columns='Model').round(1).to_string(index=False))
    print(f'Saved results to {args.out.resolve()}')
