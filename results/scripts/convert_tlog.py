"""Offline MAVLink tlog conversion; see --help for explicit paths."""
from _bootstrap import ROOT
from preprocessing.tlog_to_csv import cli
if __name__=='__main__': cli()
