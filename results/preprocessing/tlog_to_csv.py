"""Convert a MAVLink tlog to the experiment CSV schema.
Ported from notebook cell 14. Requires optional pymavlink dependency.
The CLI settings are process-local; this converter is not a threaded API.
"""
import csv
import glob
import math
import os
import sys
from datetime import datetime, timezone
from pymavlink import mavutil
from pymavlink.dialects.v20 import common as mavlink20
from pymavlink.generator.mavcrc import x25crc
from collections import Counter
import json
INPUT_TLOG = 'HITL.tlog'
OUTPUT_CSV = 'HITL1_converted.csv'
DT = 0.5
GENERATED = 'next'
RUNS = 'all'
TRIM = False
PAD = 10.0
TARGET_LATLON = 'int'
MISSION_NAME = 'qgc_uploaded_mission'
MODEL_NAME = ''
SYSID = 1
COMPID = 1
RECOVER_ZERO_TRIMMED_CRC = True
PARSE_DIAGNOSTICS = {}
MISSION_EVENTS = []
COLUMNS = ['mission_run_id', 'mission_name', 'timestamp', 'mission_seq', 'mission_status', 'command_id', 'command_name', 'frame', 'current', 'autocontinue', 'param1', 'param2', 'param3', 'param4', 'param5', 'param6', 'param7', 'target_lat', 'target_lon', 'target_alt', 'llm_call_id', 'llm_step_index', 'dt', 'llm_latency_ms', 'llm_model_name', 'input_hb_base_mode', 'input_hb_custom_mode', 'input_hb_system_status', 'input_gpi_lat', 'input_gpi_lon', 'input_gpi_alt', 'input_gpi_relative_alt', 'input_gpi_vx', 'input_gpi_vy', 'input_gpi_vz', 'input_gpi_hdg', 'input_roll', 'input_pitch', 'input_yaw', 'input_vfr_groundspeed', 'input_vfr_heading', 'input_vfr_throttle', 'input_vfr_alt', 'input_vfr_climb', 'input_battery_remaining', 'input_voltage_battery', 'input_load', 'input_gps_fix_type', 'generated_gpi_lat', 'generated_gpi_lon', 'generated_gpi_alt', 'generated_gpi_relative_alt', 'generated_gpi_vx', 'generated_gpi_vy', 'generated_gpi_vz', 'generated_gpi_hdg', 'generated_att_roll', 'generated_att_pitch', 'generated_att_yaw', 'generated_vfr_groundspeed', 'generated_vfr_heading', 'generated_vfr_throttle', 'generated_vfr_alt', 'generated_vfr_climb', 'generated_sys_battery_remaining', 'generated_sys_voltage_battery', 'generated_sys_load', 'generated_gps_fix_type']
STATE_PAIRS = [('input_gpi_lat', 'generated_gpi_lat'), ('input_gpi_lon', 'generated_gpi_lon'), ('input_gpi_alt', 'generated_gpi_alt'), ('input_gpi_relative_alt', 'generated_gpi_relative_alt'), ('input_gpi_vx', 'generated_gpi_vx'), ('input_gpi_vy', 'generated_gpi_vy'), ('input_gpi_vz', 'generated_gpi_vz'), ('input_gpi_hdg', 'generated_gpi_hdg'), ('input_roll', 'generated_att_roll'), ('input_pitch', 'generated_att_pitch'), ('input_yaw', 'generated_att_yaw'), ('input_vfr_groundspeed', 'generated_vfr_groundspeed'), ('input_vfr_heading', 'generated_vfr_heading'), ('input_vfr_throttle', 'generated_vfr_throttle'), ('input_vfr_alt', 'generated_vfr_alt'), ('input_vfr_climb', 'generated_vfr_climb'), ('input_battery_remaining', 'generated_sys_battery_remaining'), ('input_voltage_battery', 'generated_sys_voltage_battery'), ('input_load', 'generated_sys_load'), ('input_gps_fix_type', 'generated_gps_fix_type')]
MAV_MODE_FLAG_SAFETY_ARMED = 128
STATE_TYPES = ('HEARTBEAT', 'GLOBAL_POSITION_INT', 'ATTITUDE', 'VFR_HUD', 'SYS_STATUS', 'GPS_RAW_INT', 'MISSION_CURRENT')

def clean(v):
    """MAVLink NaN means 'unspecified' -- emit empty, not the string 'nan'."""
    if v is None:
        return ''
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return ''
    return v

def cmd_name(cmd_id):
    try:
        return mavutil.mavlink.enums['MAV_CMD'][cmd_id].name
    except (KeyError, AttributeError):
        return f'MAV_CMD_UNKNOWN_{cmd_id}'

def px4_is_auto(custom_mode):
    """PX4 packs custom_mode as (sub_mode << 24) | (main_mode << 16).
    main_mode 4 = AUTO. Any AUTO sub-mode counts as executing the plan:
    MISSION (4) flies the waypoints, RTL (5) flies a NAV_RETURN_TO_LAUNCH
    item, LOITER (3) holds at one. Narrowing this to MISSION alone would
    label the whole RTL leg as merely 'armed'."""
    return custom_mode >> 16 & 255 == 4

def run_id_from_ts(ts):
    return 'mission_' + datetime.fromtimestamp(ts, timezone.utc).strftime('%Y%m%d_%H%M%S')

def resolve_input():
    if not os.path.isfile(INPUT_TLOG):
        raise FileNotFoundError(INPUT_TLOG)
    return INPUT_TLOG

class Run:
    """One uploaded mission and the window of time it was the active plan."""

    def __init__(self, t_start, items):
        self.t_start = t_start
        self.t_end = None
        self.items = items
        self.armed_windows = []
        self.max_seq_reached = -1
        self.reached_events = []

    @property
    def flown(self):
        """Armed alone is not enough -- a run can sit armed for an hour and
        never progress (failed preflight, no GCS link). Require that the
        vehicle actually reached at least one mission item."""
        return bool(self.armed_windows) and self.max_seq_reached >= 0

    def duration(self):
        return (self.t_end or self.t_start) - self.t_start

def recover_zero_trimmed_frame(msg, decoder, cache):
    """Recover unsigned MAVLink 2 frames with a zero-trimming/CRC mismatch.

    Some stored frames retain the CRC for the original longer payload.
    Only append zero bytes and restore the length; never bypass the CRC.
    Frames with unknown schemas, signatures, or other corruption are skipped.
    """
    if not RECOVER_ZERO_TRIMMED_CRC or 'CRC' not in str(getattr(msg, 'reason', '')):
        return None
    packet = bytes(msg.data)
    if len(packet) < 12 or packet[0] != 253 or packet[2] != 0:
        return None
    size = packet[1]
    if len(packet) != size + 12:
        return None
    ident = int.from_bytes(packet[7:10], 'little')
    schema = mavlink20.mavlink_map.get(ident)
    if schema is None:
        return None
    key = (ident, size)
    lengths = list(range(size + 1, schema.unpacker.size + 1))
    if key in cache and cache[key] in lengths:
        lengths.remove(cache[key])
        lengths.insert(0, cache[key])
    for length in lengths:
        header = bytearray(packet[:10])
        header[1] = length
        restored = header + packet[10:-2] + bytes(length - size)
        crc = x25crc(restored[1:])
        crc.accumulate(bytes([schema.crc_extra]))
        if crc.crc != int.from_bytes(packet[-2:], 'little'):
            continue
        try:
            repaired = decoder.decode(restored + packet[-2:])
        except Exception:
            continue
        repaired._timestamp = msg._timestamp
        cache[key] = length
        return repaired
    return None

def parse_tlog(path, sysid=SYSID):
    """Read accepted flight-mission uploads and CRC-verified vehicle states."""
    global PARSE_DIAGNOSTICS, MISSION_EVENTS
    conn = mavutil.mavlink_connection(path)
    decoder = mavlink20.MAVLink(None)
    cache, recovered, accepted, rejected = ({}, Counter(), Counter(), Counter())
    runs, timeline, MISSION_EVENTS = ([], [], [])
    pending, pending_t, expected_count, uploader = ({}, None, None, None)
    active_run = None
    armed, arm_t, armed_windows = (False, None, [])
    last_ts = None

    def vehicle(msg):
        return msg.get_srcSystem() == sysid and msg.get_srcComponent() == COMPID

    def to_vehicle(msg):
        return getattr(msg, 'target_system', None) in (0, sysid) and getattr(msg, 'target_component', 0) in (0, COMPID)
    try:
        while True:
            msg = conn.recv_match()
            if msg is None:
                break
            if msg.get_type() == 'BAD_DATA':
                repaired = recover_zero_trimmed_frame(msg, decoder, cache)
                if repaired is None:
                    reason = str(getattr(msg, 'reason', 'unknown'))
                    rejected['CRC mismatch' if 'CRC' in reason else reason] += 1
                    continue
                msg = repaired
                recovered[msg.get_type()] += 1
            mtype = msg.get_type()
            ts = getattr(msg, '_timestamp', None)
            if ts is None or not math.isfinite(ts):
                continue
            last_ts = ts
            accepted[mtype] += 1
            flight_plan = getattr(msg, 'mission_type', 0) == 0
            src = (msg.get_srcSystem(), msg.get_srcComponent())
            if mtype == 'MISSION_COUNT' and (not vehicle(msg)) and to_vehicle(msg) and flight_plan:
                if not (pending_t == ts and uploader == src and (expected_count == msg.count)):
                    pending, pending_t, expected_count, uploader = ({}, ts, msg.count, src)
                continue
            if mtype == 'MISSION_ITEM_INT':
                if not vehicle(msg) and to_vehicle(msg) and flight_plan:
                    if uploader is None:
                        uploader, pending_t = (src, ts)
                    if src == uploader:
                        pending[msg.seq] = msg.to_dict()
                continue
            if mtype == 'MISSION_ACK' and vehicle(msg) and flight_plan and pending:
                ack_target = (msg.target_system, msg.target_component)
                complete = expected_count is not None and set(pending) == set(range(expected_count))
                addressed = uploader is not None and ack_target[0] == uploader[0] and (ack_target[1] in (0, uploader[1]))
                if msg.type == 0 and complete and addressed:
                    if active_run is not None and active_run.t_end is None:
                        active_run.t_end = ts
                    active_run = Run(ts, pending.copy())
                    runs.append(active_run)
                pending, pending_t, expected_count, uploader = ({}, None, None, None)
                continue
            if mtype == 'MISSION_CLEAR_ALL' and (not vehicle(msg)) and to_vehicle(msg) and flight_plan:
                if active_run is not None:
                    active_run.t_end = ts
                    active_run = None
                pending, pending_t, expected_count, uploader = ({}, None, None, None)
                continue
            if not vehicle(msg):
                continue
            if mtype == 'HEARTBEAT':
                now_armed = bool(msg.base_mode & MAV_MODE_FLAG_SAFETY_ARMED)
                if now_armed and (not armed):
                    arm_t = ts
                elif armed and (not now_armed) and (arm_t is not None):
                    armed_windows.append((arm_t, ts))
                    arm_t = None
                armed = now_armed
            if mtype in ('MISSION_CURRENT', 'MISSION_ITEM_REACHED') and active_run is not None:
                item = active_run.items.get(msg.seq, {})
                MISSION_EVENTS.append({'timestamp': ts, 'mission_run_id': run_id_from_ts(active_run.t_start), 'event': mtype, 'mission_seq': msg.seq, 'command_id': item.get('command', ''), 'command_name': cmd_name(item['command']) if 'command' in item else '', 'param1': item.get('param1'), 'param2': item.get('param2'), 'param4': item.get('param4'), 'target_lat': item.get('x'), 'target_lon': item.get('y'), 'target_alt': item.get('z')})
            if mtype == 'MISSION_ITEM_REACHED' and active_run is not None:
                active_run.max_seq_reached = max(active_run.max_seq_reached, msg.seq)
                active_run.reached_events.append((ts, msg.seq))
                continue
            if mtype in STATE_TYPES:
                timeline.append((ts, mtype, msg.to_dict()))
    finally:
        conn.close()
    timeline.sort(key=lambda event: event[0])
    end_ts = timeline[-1][0] if timeline else last_ts
    if active_run is not None and active_run.t_end is None:
        active_run.t_end = end_ts if end_ts is not None else active_run.t_start
    if armed and arm_t is not None and (end_ts is not None):
        armed_windows.append((arm_t, end_ts))
    for run in runs:
        if run.t_end is None:
            run.t_end = run.t_start
        run.armed_windows = [(max(a, run.t_start), min(b, run.t_end)) for a, b in armed_windows if max(a, run.t_start) < min(b, run.t_end)]
    PARSE_DIAGNOSTICS = {'source_tlog': os.path.basename(path), 'dt': DT, 'recovery': 'Restore trailing zero bytes and original length; verify original CRC before decoding', 'recovered_packets': sum(recovered.values()), 'recovered_by_type': dict(recovered), 'unrecoverable_packets': sum(rejected.values()), 'rejected_reasons': dict(rejected), 'decoded_by_type': dict(accepted), 'mission_runs': len(runs), 'vehicle_state_messages': len(timeline)}
    return (runs, timeline, sum(rejected.values()))

def state_snapshot(latest):
    """Flatten the held messages into the input_* half of a row."""
    hb = latest.get('HEARTBEAT', {})
    gpi = latest.get('GLOBAL_POSITION_INT', {})
    att = latest.get('ATTITUDE', {})
    vfr = latest.get('VFR_HUD', {})
    sysst = latest.get('SYS_STATUS', {})
    gps = latest.get('GPS_RAW_INT', {})
    return {'input_hb_base_mode': hb.get('base_mode'), 'input_hb_custom_mode': hb.get('custom_mode'), 'input_hb_system_status': hb.get('system_status'), 'input_gpi_lat': gpi.get('lat'), 'input_gpi_lon': gpi.get('lon'), 'input_gpi_alt': gpi.get('alt'), 'input_gpi_relative_alt': gpi.get('relative_alt'), 'input_gpi_vx': gpi.get('vx'), 'input_gpi_vy': gpi.get('vy'), 'input_gpi_vz': gpi.get('vz'), 'input_gpi_hdg': gpi.get('hdg'), 'input_roll': att.get('roll'), 'input_pitch': att.get('pitch'), 'input_yaw': att.get('yaw'), 'input_vfr_groundspeed': vfr.get('groundspeed'), 'input_vfr_heading': vfr.get('heading'), 'input_vfr_throttle': vfr.get('throttle'), 'input_vfr_alt': vfr.get('alt'), 'input_vfr_climb': vfr.get('climb'), 'input_battery_remaining': sysst.get('battery_remaining'), 'input_voltage_battery': sysst.get('voltage_battery'), 'input_load': sysst.get('load'), 'input_gps_fix_type': gps.get('fix_type')}

def mission_status(latest, run, reached_so_far):
    """reached_so_far is the highest mission item reached *as of this row* --
    using the run-level max would label pre-flight rows 'complete'."""
    hb = latest.get('HEARTBEAT', {})
    base = hb.get('base_mode', 0) or 0
    custom = hb.get('custom_mode', 0) or 0
    if base & MAV_MODE_FLAG_SAFETY_ARMED:
        return 'active' if px4_is_auto(custom) else 'armed'
    if run.items and reached_so_far >= max(run.items):
        return 'complete'
    return 'inactive'

def build_rows(run, timeline):
    """Walk the dt grid across one run, holding the last-seen value of each
    message (that is what the autopilot's own consumers see between updates).

    Consumes `timeline` with a single advancing cursor, so runs must be
    processed in chronological order.
    """
    lo, hi = (run.t_start, run.t_end)
    if TRIM and run.armed_windows:
        lo = max(lo, run.armed_windows[0][0] - PAD)
        hi = min(hi, run.armed_windows[-1][1] + PAD)
    latest = {}
    idx = 0
    n = len(timeline)
    while idx < n and timeline[idx][0] <= lo:
        latest[timeline[idx][1]] = timeline[idx][2]
        idx += 1
    run_id = run_id_from_ts(run.t_start)
    reached = sorted(run.reached_events)
    r_idx = 0
    reached_so_far = -1
    while r_idx < len(reached) and reached[r_idx][0] <= lo:
        reached_so_far = max(reached_so_far, reached[r_idx][1])
        r_idx += 1
    rows = []
    t = lo
    step = 0
    while t <= hi:
        while idx < n and timeline[idx][0] <= t:
            latest[timeline[idx][1]] = timeline[idx][2]
            idx += 1
        while r_idx < len(reached) and reached[r_idx][0] <= t:
            reached_so_far = max(reached_so_far, reached[r_idx][1])
            r_idx += 1
        seq = (latest.get('MISSION_CURRENT') or {}).get('seq')
        item = run.items.get(seq, {})
        lat_i, lon_i = (item.get('x'), item.get('y'))
        if TARGET_LATLON == 'deg':
            lat = lat_i / 10000000.0 if lat_i is not None else None
            lon = lon_i / 10000000.0 if lon_i is not None else None
        else:
            lat, lon = (lat_i, lon_i)
        alt = item.get('z')
        row = {c: '' for c in COLUMNS}
        row.update({'mission_run_id': run_id, 'mission_name': MISSION_NAME, 'timestamp': t, 'mission_seq': seq, 'mission_status': mission_status(latest, run, reached_so_far), 'command_id': item.get('command'), 'command_name': cmd_name(item['command']) if 'command' in item else '', 'frame': item.get('frame'), 'current': item.get('current'), 'autocontinue': item.get('autocontinue'), 'param1': item.get('param1'), 'param2': item.get('param2'), 'param3': item.get('param3'), 'param4': item.get('param4'), 'param5': lat, 'param6': lon, 'param7': alt, 'target_lat': lat, 'target_lon': lon, 'target_alt': alt, 'llm_step_index': step, 'dt': DT, 'llm_model_name': MODEL_NAME})
        row.update(state_snapshot(latest))
        rows.append(row)
        t += DT
        step += 1
    if GENERATED == 'next':
        for i, row in enumerate(rows):
            if i + 1 >= len(rows):
                continue
            nxt = rows[i + 1]
            for src, dst in STATE_PAIRS:
                row[dst] = nxt[src]
    return rows

def main():
    if not isinstance(DT, (int, float)) or not math.isfinite(DT) or DT <= 0:
        raise ValueError('DT must be a finite positive number of seconds.')
    if GENERATED not in {'next', 'blank'}:
        raise ValueError('GENERATED must be "next" or "blank".')
    if RUNS not in {'all', 'flown'}:
        raise ValueError('RUNS must be "all" or "flown".')
    if TARGET_LATLON not in {'int', 'deg'}:
        raise ValueError('TARGET_LATLON must be "int" or "deg".')
    path = resolve_input()
    runs, timeline, bad = parse_tlog(path, sysid=SYSID)
    if not runs:
        raise RuntimeError('No completed mission upload in this tlog -- nothing to key rows to.')
    if not timeline:
        raise RuntimeError(f'No state messages from system {SYSID}.')
    print(f'{os.path.basename(path)}: {len(timeline)} state msgs, {bad} bad frames, {len(runs)} run(s)')
    for r in runs:
        flag = '' if r.flown else '   <-- aborted, never reached an item'
        print(f'  {run_id_from_ts(r.t_start)}  {len(r.items)} items  {r.duration():7.1f}s  armed={len(r.armed_windows)}x  max_seq_reached={r.max_seq_reached}{flag}')
    keep = [r for r in runs if r.flown] if RUNS == 'flown' else runs
    if not keep:
        raise RuntimeError('No flown runs (never armed, or never reached a mission item).')
    if RUNS == 'flown' and len(keep) < len(runs):
        print(f"  RUNS='flown' -> dropped {len(runs) - len(keep)} aborted run(s)")
    all_rows = []
    for r in keep:
        all_rows.extend(build_rows(r, timeline))
    with open(OUTPUT_CSV, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction='ignore', lineterminator='\n')
        w.writeheader()
        for row in all_rows:
            w.writerow({k: clean(v) for k, v in row.items()})
    print(f'wrote {len(all_rows)} rows x {len(COLUMNS)} cols -> {OUTPUT_CSV}')
    print(f"CRC-verified recovery: {PARSE_DIAGNOSTICS['recovered_packets']:,} packets; unrecoverable: {PARSE_DIAGNOSTICS['unrecoverable_packets']:,}")
    for name in ('MISSION_CURRENT', 'MISSION_ITEM_REACHED', 'VFR_HUD', 'GLOBAL_POSITION_INT'):
        print(f"  {name}: {PARSE_DIAGNOSTICS['decoded_by_type'].get(name, 0):,} decoded")
    stem = os.path.splitext(OUTPUT_CSV)[0]
    columns = ['timestamp', 'mission_run_id', 'event', 'mission_seq', 'command_id', 'command_name', 'param1', 'param2', 'param4', 'target_lat', 'target_lon', 'target_alt']
    with open(stem + '_mission_events.csv', 'w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for event in MISSION_EVENTS:
            writer.writerow({key: clean(value) for key, value in event.items()})
    with open(stem + '_diagnostics.json', 'w') as handle:
        json.dump(PARSE_DIAGNOSTICS, handle, indent=2)
    print('Saved mission events and decoding diagnostics alongside the sampled CSV.')

def cli():
    """Offline conversion only. No network connection to a UAV is opened."""
    import argparse
    from pathlib import Path
    global INPUT_TLOG, OUTPUT_CSV, DT, RUNS, SYSID, COMPID, GENERATED, TARGET_LATLON
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--dt', type=float, default=0.5)
    p.add_argument('--runs', choices=['all', 'flown'], default='flown')
    p.add_argument('--sysid', type=int, default=1)
    p.add_argument('--compid', type=int, default=1)
    args = p.parse_args()
    INPUT_TLOG, OUTPUT_CSV = (str(args.input), str(args.output))
    DT, RUNS, SYSID, COMPID = (args.dt, args.runs, args.sysid, args.compid)
    GENERATED, TARGET_LATLON = ('next', 'int')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    main()
if __name__ == '__main__':
    cli()
