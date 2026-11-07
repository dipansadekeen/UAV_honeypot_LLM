#!/usr/bin/env python3
"""Check the honeypot EFSM against PX4 SITL ground truth.

Every row of ack_capture.csv with purpose == "test" records a PX4 source state
(armed bit, landed state, relative altitude), the command sent, and the
COMMAND_ACK that PX4 returned. This script rebuilds that source state, calls
the honeypot's `state_automata_ack` (module_helper_functions.py at the
repository root) with the same command and parameters, and compares the ACKs.

No PX4, network, or LLM is needed.

Usage:
  python results/efsm/check_efsm.py
  python results/efsm/check_efsm.py --out efsm_check.csv
Exit status is 0 when every test row matches, 1 otherwise.
"""
import argparse
import csv
import sys
from collections import OrderedDict
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(REPO_ROOT))

from pymavlink import mavutil  # noqa: E402
from module_helper_functions import state_automata_ack  # noqa: E402


def result_name(code):
    try:
        return mavutil.mavlink.enums["MAV_RESULT"][int(code)].name.replace("MAV_RESULT_", "")
    except (KeyError, ValueError):
        return str(code)


def check(ack_csv):
    rows = []
    with open(ack_csv, newline="") as f:
        for r in csv.DictReader(f):
            if r["purpose"] != "test":
                continue
            state = SimpleNamespace(
                base_mode=int(r["pre_base_mode"]),
                landed_state=int(r["pre_landed"]),
                gpi_relative_alt=float(r["pre_alt"]) * 1000.0,  # m -> mm
            )
            params = {f"param{i}": float(r[f"param{i}"]) for i in range(1, 8)}
            efsm_result, reason = state_automata_ack(int(r["command"]), params, state)
            rows.append({
                "timestamp": r["timestamp"],
                "pre_state": r["pre_state"],
                "operation": r["operation"],
                "command": r["command"],
                "px4_ack": result_name(r["ack_result"]),
                "efsm_ack": result_name(efsm_result),
                "match": int(int(efsm_result) == int(r["ack_result"])),
                "efsm_reason": reason,
            })
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, default=HERE / "ack_capture.csv",
                        help="PX4 ACK capture (default: %(default)s)")
    parser.add_argument("--out", type=Path, help="optional per-row CSV report")
    args = parser.parse_args()

    rows = check(args.input)
    if not rows:
        sys.exit(f"No purpose == 'test' rows in {args.input}")

    summary = OrderedDict()
    for r in rows:
        key = (r["pre_state"], r["operation"], r["px4_ack"], r["efsm_ack"])
        summary[key] = summary.get(key, 0) + 1

    print(f"{'source state':<12} {'operation':<14} {'PX4 ACK':<22} {'EFSM ACK':<22} {'n':>3}  ok")
    for (state, op, px4, efsm), n in summary.items():
        print(f"{state:<12} {op:<14} {px4:<22} {efsm:<22} {n:>3}  {'yes' if px4 == efsm else 'NO'}")

    matched = sum(r["match"] for r in rows)
    print(f"\n{matched}/{len(rows)} PX4 test rows match the EFSM ({100.0 * matched / len(rows):.1f}%)")

    if args.out:
        with open(args.out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"Per-row report: {args.out}")

    sys.exit(0 if matched == len(rows) else 1)


if __name__ == "__main__":
    main()
