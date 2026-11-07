# Test harness

Tools for driving the honeypot during tests.

| File | Purpose |
|---|---|
| `master_mission_deception_test.plan` | The QGroundControl mission used in the deception test |
| `gcs_controller.py` | A desktop GCS dashboard that sends individual commands to the honeypot and shows its heartbeat and telemetry live |

## Mission

`master_mission_deception_test.plan` is a QGroundControl plan (6 items, home
47.39795 N, 8.54618 E, the PX4 SITL default location):

| Seq | Command | Parameters |
|---|---|---|
| 0 | TAKEOFF (22) | 50 m |
| 1 | WAYPOINT (16) | 47.39871, 8.54336, 60.7 m |
| 2 | WAYPOINT (16) | 47.39763, 8.54223, 50 m |
| 3 | DO_CHANGE_SPEED (178) | ground speed 5 m/s |
| 4 | WAYPOINT (16) | 47.39668, 8.54252, 50 m |
| 5 | RETURN_TO_LAUNCH (20) | |

To fly it against the honeypot, start the honeypot (`python module_main.py`
from the repository root), open the plan in QGroundControl (Plan view →
Open), upload it, then arm and start the mission. QGroundControl must listen
on UDP 14550, the address the honeypot sends to.

## GCS controller

```bash
pip install pymavlink matplotlib     # tkinter ships with most Python installs
python results/test_harness/gcs_controller.py
```

The dashboard listens on `127.0.0.1:14550` and sends `COMMAND_LONG` as
system/component 255/190 to the honeypot at `127.0.0.1:14551` (change with
`--listen-ip`, `--listen-port`, `--target-ip`, `--target-port`). It has buttons
for ARM, DISARM, TAKEOFF, GO TO WAYPOINT, LAND, RTL and REQUEST HEARTBEAT, and
shows the decoded PX4 mode, arm state, `COMMAND_ACK` results, battery, landed
state, position, and a live plot of `custom_mode` and altitude.

It sends single commands only and does not upload missions; use
QGroundControl for the `.plan` above. Because both bind UDP 14550, close
QGroundControl before starting the dashboard. To run both, pass another
`--listen-port` and change `gcs_port` in the `UDPConnection(...)` call in
`module_llmhoneypot.py` to match.
