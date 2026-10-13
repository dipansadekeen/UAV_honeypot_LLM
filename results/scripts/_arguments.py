"""Shared explicit CLI options."""
import argparse
from pathlib import Path
from config.settings import Settings

def case_limit(value):
    if value.lower()=='all': return None
    number=int(value)
    if number<1: raise argparse.ArgumentTypeError('Use a positive integer or all')
    return number


def parser(description,root,default_input,default_out,max_cases=5):
    p=argparse.ArgumentParser(description=description)
    p.add_argument('--input',type=Path,default=root/'data'/default_input)
    p.add_argument('--out',type=Path,default=root/'results'/default_out)
    p.add_argument('--profile',choices=['notebook','paper'],default='notebook')
    p.add_argument('--max-cases',type=case_limit,default=max_cases)
    p.add_argument('--dt',type=float,default=.5,help='LLM sequential interval; HITL preserves row dt')
    p.add_argument('--lc-threshold',type=float,default=.5)
    return p


def settings(args,max_cases=None):
    return Settings(profile=args.profile,max_cases=args.max_cases if max_cases is None else max_cases,
                    dt=args.dt,lc_threshold=args.lc_threshold)
