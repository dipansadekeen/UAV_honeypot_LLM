"""Generate Figure 9 from additional offline HP and SITL tlogs."""
from _bootstrap import ROOT
from pathlib import Path
import argparse
from preprocessing.connectivity import analyze_connectivity

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--hp',required=True,type=Path)
    p.add_argument('--sitl',required=True,type=Path)
    p.add_argument('--out',type=Path,default=ROOT/'results/connectivity')
    p.add_argument('--sysid',type=int,default=1);p.add_argument('--compid',type=int,default=1)
    args=p.parse_args()
    analyze_connectivity(args.hp,args.sitl,args.out,args.sysid,args.compid)
