# EFSM ground truth (PX4 SITL)

The honeypot answers every `COMMAND_LONG` / `COMMAND_INT` with a `COMMAND_ACK`
decided by an extended finite-state machine (EFSM), `state_automata_ack` in
[`module_helper_functions.py`](../../module_helper_functions.py). This folder holds the
PX4 SITL recordings the EFSM was built from and a script that checks the EFSM
against them.

| File | Purpose |
|---|---|
| `ack_capture.csv` | One row per command sent to PX4 SITL: source state, command and parameters, PX4 `COMMAND_ACK`, and the state after the command |
| `heartbeat_capture.csv` | Every PX4 `HEARTBEAT` received during the capture (mode, status, armed bit, landed state, altitude) |
| `GCS_for_rules_capture.py` | The GCS script that produced both CSVs |
| `check_efsm.py` | Replays the PX4 test rows through the honeypot EFSM and compares the ACKs |

## Check the EFSM (no PX4 needed)

From the repository root:

```bash
pip install -r results/requirements-tlog.txt   # pymavlink
python results/efsm/check_efsm.py
```

Expected result: `117/117 PX4 test rows match the EFSM (100.0%)`, followed by
a table of source state × operation × ACK. Add `--out efsm_check.csv` for a
per-row report. The same check runs as part of the `results/` test suite
(`tests/test_efsm.py`).

## Data

`ack_capture.csv` contains 266 rows from five capture sessions:

- **`purpose == "test"` (117 rows)** are the ground truth. Each one is a single
  command sent from a known source state.
- **`purpose == "setup"` (149 rows)** only move the vehicle between states
  (forced disarm with `param2 = 21196`, landing, setup takeoff). They are not
  used for the EFSM.

Source states, as classified by the capture script:

| State | Meaning |
|---|---|
| `DG` | disarmed on the ground |
| `AG` | armed on the ground |
| `TAKEOFF` | `EXTENDED_SYS_STATE.landed_state` = TAKEOFF (climbing) |
| `AIR` | armed and in the air |
| `LANDING` | `landed_state` = LANDING |

Commands covered: DISARM, ARM (again), TAKEOFF (0.2, 0.5, 1 and 10 m targets;
again while airborne), LAND, RTL, WAYPOINT (16), REPOSITION (192), and an
unsupported command ID (31000). `TAKEOFF` `param7` is AMSL altitude, as PX4
expects; `nan` parameters tell PX4 to use the current position.

## Re-run the capture (optional)

Requires a local PX4 SITL instance and pymavlink. Start PX4 SITL (for example
`make px4_sitl gz_x500` in PX4-Autopilot) so that it sends MAVLink to
`127.0.0.1:14550`, then:

```bash
python results/efsm/GCS_for_rules_capture.py \
    --px4-commander /path/to/PX4-Autopilot/build/px4_sitl_default/bin/px4-commander
```

The script writes `ack_capture_new.csv` and `heartbeat_capture_new.csv` and
never modifies the shipped CSVs. `px4-commander` is used only for the forced
arm during setup, because PX4 runs preflight checks on MAVLink arm commands
even when forced. The script refuses to force-arm anything other than a local
SITL connection (`udpin:127.0.0.1:*`). A full capture takes about 10 minutes.
Check the new capture with `python results/efsm/check_efsm.py --input ack_capture_new.csv`.
