import json
import time

from typing import List, Dict, Any, Optional
from pymavlink import mavutil

from module_historybuffer_commonstate import CommonState
# ============================
# RAG LOADER (command transitions)
# ============================
def load_command_rag_jsonl(path: str) -> List[Dict[str, Any]]:
    rows = []
    try:
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except Exception as e:
        print(f"[RAG] failed to load {path}: {e}", flush=True)
    print(f"[RAG] loaded {len(rows)} examples from {path}", flush=True)
    return rows



def rag_retrieve_examples(rows: List[Dict[str, Any]], command_id: int, k: int = 3) -> List[Dict[str, Any]]:
    out = []
    for ex in rows:
        if not isinstance(ex, dict):
            continue

        cmd = ex.get("command", {})

        # cmd can be dict OR int depending on jsonl format
        if isinstance(cmd, dict):
            ex_id = cmd.get("id") or cmd.get("command") or ex.get("command_id") or ex.get("cmd_id")
        else:
            # cmd is int/str
            ex_id = cmd

        try:
            if int(ex_id) == int(command_id):
                out.append(ex)
        except Exception:
            pass

        if len(out) >= k:
            break
    return out


# ============================
# ACK mapping (LLM string -> MAV_RESULT)
# ============================
ACK_RESULT_MAP = {
    "ACCEPTED": mavutil.mavlink.MAV_RESULT_ACCEPTED,
    "DENIED": mavutil.mavlink.MAV_RESULT_DENIED,
    "UNSUPPORTED": mavutil.mavlink.MAV_RESULT_UNSUPPORTED,
    "TEMPORARILY_REJECTED": mavutil.mavlink.MAV_RESULT_TEMPORARILY_REJECTED,
}
#  ////// commands ends ///////

# ============================================================
# TIME UPDATE FUNCTION (from your code)
# ============================================================

def update_time_fields(state: CommonState, boot_time: float):
    dt = max(0.0, time.monotonic() - boot_time)
    state.time_boot_ms = int(dt * 1000)
    state.time_usec = int(dt * 1_000_000.0)   # <-- ADDing this for telemetry GPS

# ============================================================
# HEARTBEAT BUILDER (from your code)
# ============================================================

def make_heartbeat(mav, state: CommonState):
    return mav.heartbeat_encode(
        int(state.hb_type),
        int(state.hb_autopilot),
        int(state.base_mode),
        int(state.custom_mode),
        int(state.system_status),
    )

def extract_json(text: str):
    """
    Extract first JSON object from LLM response.
    Handles cases where model adds extra text.
    """
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return json.loads(text[start:end])
    except Exception as e:
        print(f"[JSON EXTRACT ERROR] {e}")
        return None


# ////////// telemetry //////////
def make_sys_status(mav, s: CommonState):
    return mav.sys_status_encode(
        int(s.onboard_control_sensors_present),
        int(s.onboard_control_sensors_enabled),
        int(s.onboard_control_sensors_health),
        int(s.load),
        int(s.voltage_battery),
        int(s.current_battery),
        int(s.battery_remaining),
        int(s.drop_rate_comm),
        int(s.errors_comm),
        int(s.errors_count1),
        int(s.errors_count2),
        int(s.errors_count3),
        int(s.errors_count4),
    )

def make_gps_raw_int(mav, s: CommonState):
    return mav.gps_raw_int_encode(
        int(s.time_usec),
        int(s.gps_fix_type),
        int(s.gps_lat),
        int(s.gps_lon),
        int(s.gps_alt),
        int(s.gps_eph),
        int(s.gps_epv),
        int(s.gps_vel),
        int(s.gps_cog),
        int(s.gps_satellites_visible),
    )

def make_global_position_int(mav, s: CommonState):
    return mav.global_position_int_encode(
        int(s.time_boot_ms),
        int(s.gpi_lat),
        int(s.gpi_lon),
        int(s.gpi_alt),
        int(s.gpi_relative_alt),
        int(s.gpi_vx),
        int(s.gpi_vy),
        int(s.gpi_vz),
        int(s.gpi_hdg),
    )

def make_attitude(mav, s: CommonState):
    return mav.attitude_encode(
        int(s.time_boot_ms),
        float(s.roll),
        float(s.pitch),
        float(s.yaw),
        float(s.rollspeed),
        float(s.pitchspeed),
        float(s.yawspeed),
    )

def make_vfr_hud(mav, s: CommonState):
    return mav.vfr_hud_encode(
        float(s.vfr_airspeed),
        float(s.vfr_groundspeed),
        int(s.vfr_heading),
        int(s.vfr_throttle),
        float(s.vfr_alt),
        float(s.vfr_climb),
    )

# new jul
def make_extended_sys_state(mav, s: CommonState):
    return mav.extended_sys_state_encode(
        int(getattr(s, "vtol_state", 0)),
        int(getattr(s, "landed_state", 1)),
    )

# new
def make_battery_status(mav, s: CommonState):
    return mav.battery_status_encode(
        0,
        0,
        0,
        0,
        [4050, 4050, 4050, 4050, 65535, 65535, 65535, 65535, 65535, 65535],
        -1,
        -1,
        -1,
        int(s.battery_remaining)   # 👈 reuse existing value
    )


# new 2
def make_home_position(mav, s: CommonState):
    if not s.home_initialized and s.gpi_lat != 0 and s.gpi_lon != 0:
        s.home_lat = s.gpi_lat
        s.home_lon = s.gpi_lon
        s.home_alt = s.gpi_alt
        s.home_initialized = True

    return mav.home_position_encode(
        int(s.home_lat),
        int(s.home_lon),
        int(s.home_alt),
        0, 0, 0,
        [1, 0, 0, 0],
        0.0, 0.0, 0.0
    )


# mission helper | current mission # new
def make_mission_current(mav, s: CommonState):
    return mav.mission_current_encode(
        int(s.mission_seq)
    )

TELEM_BUILDERS = {
    "SYS_STATUS": make_sys_status,
    "GPS_RAW_INT": make_gps_raw_int,
    "GLOBAL_POSITION_INT": make_global_position_int,
    "ATTITUDE": make_attitude,
    "VFR_HUD": make_vfr_hud,
    "BATTERY_STATUS": make_battery_status, #new
    "HOME_POSITION": make_home_position, # new 2
    "MISSION_CURRENT": make_mission_current, # current mission # new

    # QGC uses this to decide flying/landing UI state  | new jul
    "EXTENDED_SYS_STATE": make_extended_sys_state,
}
# ////////// telemetry //////////

# # ////////////// for commands /////////////
# def load_rag_transitions(self, path: str) -> None:
#     self.rag_transitions = []
#     with open(path, "r") as f:
#         for line in f:
#             line = line.strip()
#             if not line:
#                 continue
#             try:
#                 self.rag_transitions.append(json.loads(line))
#             except Exception:
#                 continue

# def rag_retrieve(self, command_id: int, k: int = 3) -> list:
#     # simplest: filter by command id/name field that exists in your jsonl
#     out = []
#     for ex in getattr(self, "rag_transitions", []):
#         cmd = ex.get("command", {})
#         # adjust this based on your dataset field names:
#         ex_id = cmd.get("id") or cmd.get("command") or cmd.get("name")
#         if ex_id == command_id:
#             out.append(ex)
#         if len(out) >= k:
#             break
#     return out

#  /////////// commands //////////


# retrieval for commands////////
def extract_heartbeat_transition_examples(rows: List[Dict[str, Any]], command_id: int, k: int = 2) -> List[Dict[str, Any]]:
    """
    Extract command-centered heartbeat transition examples:
      prev HEARTBEAT -> COMMAND_LONG -> optional COMMAND_ACK -> next HEARTBEAT
    """

    out = []
    n = len(rows)

    def msg_type(ex: Dict[str, Any]) -> str:
        return str(ex.get("mavpackettype") or ex.get("_type") or "").upper()

    def is_heartbeat(ex: Dict[str, Any]) -> bool:
        return msg_type(ex) == "HEARTBEAT"

    def is_command_long(ex: Dict[str, Any], cmd_id: int) -> bool:
        if msg_type(ex) != "COMMAND_LONG":
            return False
        try:
            return int(ex.get("command", -1)) == int(cmd_id)
        except Exception:
            return False

    def is_command_ack(ex: Dict[str, Any], cmd_id: int) -> bool:
        if msg_type(ex) != "COMMAND_ACK":
            return False
        try:
            return int(ex.get("command", -1)) == int(cmd_id)
        except Exception:
            return False

    def compact_heartbeat(ex: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "base_mode": ex.get("base_mode"),
            "custom_mode": ex.get("custom_mode"),
            "system_status": ex.get("system_status"),
            "type": ex.get("type"),
            "autopilot": ex.get("autopilot"),
            "mavlink_version": ex.get("mavlink_version"),
            "_ts": ex.get("_ts"),
        }

    def compact_command(ex: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "command": ex.get("command"),
            "param1": ex.get("param1"),
            "param2": ex.get("param2"),
            "param3": ex.get("param3"),
            "param4": ex.get("param4"),
            "param5": ex.get("param5"),
            "param6": ex.get("param6"),
            "param7": ex.get("param7"),
            "_ts": ex.get("_ts"),
        }

    def compact_ack(ex: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "command": ex.get("command"),
            "result": ex.get("result"),
            "progress": ex.get("progress"),
            "result_param2": ex.get("result_param2"),
            "_ts": ex.get("_ts"),
        }

    for i, ex in enumerate(rows):
        if not is_command_long(ex, command_id):
            continue

        prev_hb = None
        next_hb = None
        ack = None

        # nearest previous heartbeat
        for j in range(i - 1, -1, -1):
            if is_heartbeat(rows[j]):
                prev_hb = compact_heartbeat(rows[j])
                break

        # nearest next ack and next heartbeat
        for j in range(i + 1, n):
            if ack is None and is_command_ack(rows[j], command_id):
                ack = compact_ack(rows[j])

            if next_hb is None and is_heartbeat(rows[j]):
                next_hb = compact_heartbeat(rows[j])
                break

        out.append({
            "command": compact_command(ex),
            "prev_heartbeat": prev_hb,
            "ack": ack,
            "next_heartbeat": next_hb,
        })

        if len(out) >= k:
            break

    return out

# helpers: handling for telemetry//////////
TELEM_GROUPS = {

    "GLOBAL_POSITION_INT": ["lat", "lon", "alt", "relative_alt", "vx", "vy", "vz", "hdg", ],

    "ATTITUDE": ["roll", "pitch", "yaw", ],

    "VFR_HUD": ["groundspeed", "heading", "throttle", "alt", "climb", ],

    "SYS_STATUS": ["battery_remaining", "voltage_battery", "load", ],

    "GPS_RAW_INT": [ "fix_type", ],
}
TELEM_GROUPS_SET = {k: set(v) for k, v in TELEM_GROUPS.items()}

INTERNAL_TO_CANONICAL = {
    "gpi_lat": ("GLOBAL_POSITION_INT", "lat"),
    "gpi_lon": ("GLOBAL_POSITION_INT", "lon"),
    "gpi_alt": ("GLOBAL_POSITION_INT", "alt"),
    "gpi_relative_alt": ("GLOBAL_POSITION_INT", "relative_alt"),
    "gpi_vx": ("GLOBAL_POSITION_INT", "vx"),
    "gpi_vy": ("GLOBAL_POSITION_INT", "vy"),
    "gpi_vz": ("GLOBAL_POSITION_INT", "vz"),
    "gpi_hdg": ("GLOBAL_POSITION_INT", "hdg"),

    "roll": ("ATTITUDE", "roll"),
    "pitch": ("ATTITUDE", "pitch"),
    "yaw": ("ATTITUDE", "yaw"),

    "vfr_groundspeed": ("VFR_HUD", "groundspeed"),
    "vfr_heading": ("VFR_HUD", "heading"),
    "vfr_throttle": ("VFR_HUD", "throttle"),
    "vfr_alt": ("VFR_HUD", "alt"),
    "vfr_climb": ("VFR_HUD", "climb"),

    "battery_remaining": ("SYS_STATUS", "battery_remaining"),
    "voltage_battery": ("SYS_STATUS", "voltage_battery"),
    "load": ("SYS_STATUS", "load"),

    "gps_fix_type": ("GPS_RAW_INT", "fix_type"),
}

CANONICAL_TO_INTERNAL = {
    ("GLOBAL_POSITION_INT", "lat"): "gpi_lat",
    ("GLOBAL_POSITION_INT", "lon"): "gpi_lon",
    ("GLOBAL_POSITION_INT", "alt"): "gpi_alt",
    ("GLOBAL_POSITION_INT", "relative_alt"): "gpi_relative_alt",
    ("GLOBAL_POSITION_INT", "vx"): "gpi_vx",
    ("GLOBAL_POSITION_INT", "vy"): "gpi_vy",
    ("GLOBAL_POSITION_INT", "vz"): "gpi_vz",
    ("GLOBAL_POSITION_INT", "hdg"): "gpi_hdg",

    ("ATTITUDE", "roll"): "roll",
    ("ATTITUDE", "pitch"): "pitch",
    ("ATTITUDE", "yaw"): "yaw",

    ("VFR_HUD", "groundspeed"): "vfr_groundspeed",
    ("VFR_HUD", "heading"): "vfr_heading",
    ("VFR_HUD", "throttle"): "vfr_throttle",
    ("VFR_HUD", "alt"): "vfr_alt",
    ("VFR_HUD", "climb"): "vfr_climb",

    ("SYS_STATUS", "battery_remaining"): "battery_remaining",
    ("SYS_STATUS", "voltage_battery"): "voltage_battery",
    ("SYS_STATUS", "load"): "load",

    ("GPS_RAW_INT", "fix_type"): "gps_fix_type",
}

def canonicalize_grouped_snapshot(snapshot: dict) -> dict:
    """
    Input example:
    {
        "GLOBAL_POSITION_INT": {...},
        "ATTITUDE": {...},
        "GPS_RAW_INT": {...}
    }

    Output:
    same grouped structure, but only allowed telemetry groups/fields.
    """
    if not isinstance(snapshot, dict):
        return {}

    out = {}

    for msg_name, fields in snapshot.items():
        if msg_name not in TELEM_GROUPS_SET:
            continue
        if not isinstance(fields, dict):
            continue

        allowed = TELEM_GROUPS_SET[msg_name]
        kept = {k: v for k, v in fields.items() if k in allowed}

        if kept:
            out[msg_name] = kept

    return out


def canonicalize_followup_message(msg: dict) -> dict:
    """
    Input example:
    {"type": "GLOBAL_POSITION_INT", "lat": ..., "lon": ..., "vx": ...}

    Output:
    {"GLOBAL_POSITION_INT": {"lat": ..., "lon": ..., "vx": ...}}
    """
    if not isinstance(msg, dict):
        return {}

    msg_type = msg.get("type") or msg.get("mavpackettype") or msg.get("_type")
    if msg_type not in TELEM_GROUPS_SET:
        return {}

    allowed = TELEM_GROUPS_SET[msg_type]
    kept = {k: v for k, v in msg.items() if k in allowed}

    if not kept:
        return {}

    return {msg_type: kept}

def canonicalize_internal_history_fields(fields: dict) -> dict:
    """
    Convert your live HistoryBuffer flat internal fields into grouped canonical format.
    """
    if not isinstance(fields, dict):
        return {}

    out = {}

    for k, v in fields.items():
        mapped = INTERNAL_TO_CANONICAL.get(k)
        if not mapped:
            continue

        msg_name, field_name = mapped
        if msg_name not in out:
            out[msg_name] = {}

        out[msg_name][field_name] = v

    return out


def translate_canonical_fields_to_internal(grouped_fields: dict) -> dict:
    """
    Input:
    {
        "GLOBAL_POSITION_INT": {"lat": ..., "vx": ...},
        "ATTITUDE": {"roll": ...}
    }

    Output:
    {
        "gpi_lat": ...,
        "gpi_vx": ...,
        "roll": ...
    }
    """
    if not isinstance(grouped_fields, dict):
        return {}

    out = {}

    for raw_msg_name, msg_fields in grouped_fields.items():
        msg_name = str(raw_msg_name).upper()

        if msg_name not in TELEM_GROUPS_SET:
            continue
        if not isinstance(msg_fields, dict):
            continue

        for field_name, value in msg_fields.items():
            key = (msg_name, field_name)
            internal_name = CANONICAL_TO_INTERNAL.get(key)
            if internal_name:
                out[internal_name] = value

    return out

def translate_canonical_series_to_internal(series: list) -> list:
    """
    Input:
    [
        {"dt": 0.0, "fields": {"GLOBAL_POSITION_INT": {"vx": 100}}},
        ...
    ]

    Output:
    [
        {"dt": 0.0, "fields": {"gpi_vx": 100}},
        ...
    ]
    """
    if not isinstance(series, list):
        return []

    out = []

    for step in series:
        if not isinstance(step, dict):
            continue

        dt = float(step.get("dt", 0.0))
        grouped_fields = step.get("fields", {})
        flat_fields = translate_canonical_fields_to_internal(grouped_fields)

        out.append({
            "dt": dt,
            "fields": flat_fields,
        })

    return out



#  /////////// command_ack //////////
# ----------------------------------------
# Rule based ACK logic
# ----------------------------------------
def _is_armed(state) -> bool:
    # PX4: armed flag is base_mode bit 7 (0x80)
    return (int(getattr(state, "base_mode", 0)) & 0x80) != 0

def _alt_m(state) -> float:
    # Prefer relative altitude in mm if you have it; else use vfr_alt; else 0
    if hasattr(state, "gpi_relative_alt"):
        return float(getattr(state, "gpi_relative_alt", 0)) / 1000.0
    if hasattr(state, "vfr_alt"):
        return float(getattr(state, "vfr_alt", 0.0))
    if hasattr(state, "gps_alt"):
        return float(getattr(state, "gps_alt", 0)) / 1000.0
    return 0.0

def state_automata_ack(cmd, params, state, *, with_effect=False):
    """
    Table-driven command-decision automaton (EFSM).

    Default return:
        (result, reason)

    With with_effect=True:
        (result, reason, execute)

    The current phase is observed from the supplied vehicle state.
    The selected transition describes the requested action.

    This function does not update telemetry or call the LLM.
    The caller handles execution after receiving the decision.
    """
    import math

    mav = mavutil.mavlink

    ACCEPT = mav.MAV_RESULT_ACCEPTED
    TEMP = mav.MAV_RESULT_TEMPORARILY_REJECTED
    DENY = mav.MAV_RESULT_DENIED
    UNSUPPORTED = mav.MAV_RESULT_UNSUPPORTED

    # ---------------------------------------------------------
    # 1. Automaton states
    # ---------------------------------------------------------
    DG = "DISARMED_GROUND"
    AG = "ARMED_GROUND"
    TO = "TAKING_OFF"
    FL = "FLYING"
    LD = "LANDING"
    BAD = "INCONSISTENT"

    alt = _alt_m(state)
    armed = _is_armed(state)
    landed = int(getattr(
        state, "landed_state", mav.MAV_LANDED_STATE_UNDEFINED
    ))

    # Observe the current state using your existing classification.
    if not math.isfinite(alt):
        phase = BAD
    elif not armed:
        phase = (
            DG
            if landed == mav.MAV_LANDED_STATE_ON_GROUND and alt < 0.5
            else BAD
        )
    elif landed == mav.MAV_LANDED_STATE_TAKEOFF:
        phase = TO
    elif landed == mav.MAV_LANDED_STATE_LANDING:
        phase = LD
    elif landed == mav.MAV_LANDED_STATE_IN_AIR or alt > 0.5:
        phase = FL
    else:
        phase = AG

    # ---------------------------------------------------------
    # 2. Input values used by transition guards
    # ---------------------------------------------------------
    def number(key, default):
        try:
            return float(params.get(key, default))
        except (TypeError, ValueError):
            return float("nan")

    arm = (
        number("param1", 0.0)
        if cmd == mav.MAV_CMD_COMPONENT_ARM_DISARM
        else float("nan")
    )

    target_alt = (
        number("param7", 3.0)
        if cmd == mav.MAV_CMD_NAV_TAKEOFF
        else float("nan")
    )

    def always():
        return True

    # ---------------------------------------------------------
    # 3. Transition relation
    #
    # Each transition contains:
    # (
    #     source_states,
    #     guard,
    #     target_state,
    #     ACK_result,
    #     reason,
    #     execute
    # )
    #
    # source_states=None: match any current state.
    # target_state=None: remain in the current state.
    #
    # Priority is top to bottom: select the FIRST enabled edge.
    # ---------------------------------------------------------
    transitions = {
        mav.MAV_CMD_COMPONENT_ARM_DISARM: (
            (
                None, lambda: arm not in (0.0, 1.0),
                None, DENY,
                "invalid arm/disarm parameter", False
            ),
            (
                (DG,), lambda: arm == 1.0,
                AG, ACCEPT,
                "{source} -> {target}", True
            ),
            (
                (BAD,), lambda: arm == 1.0,
                None, DENY,
                "inconsistent vehicle state", False
            ),
            (
                None, lambda: arm == 1.0,
                None, ACCEPT,
                "already armed; no new action", False
            ),
            (
                (DG,), always,
                None, ACCEPT,
                "already disarmed; no new action", False
            ),
            (
                # (AG,), lambda: alt < 0.2, 
                (AG,), lambda: alt <= 0.013,  # old: alt < 0.2
                DG, ACCEPT,
                "{source} -> {target}", True
            ),
            (
                (LD,), always,
                None, ACCEPT,
                "landing in progress; disarm not yet applied", False
            ),
            (
                None, always,
                None, TEMP,
                "cannot disarm before landing", False
            ),
        ),

        mav.MAV_CMD_NAV_TAKEOFF: (
            (
                None,
                lambda: not math.isfinite(target_alt) or target_alt <= 0,
                None, DENY,
                "invalid takeoff altitude", False
            ),
            (
                (DG,), always,
                None, ACCEPT,
                "disarmed takeoff acknowledged; no flight", False
            ),
            (
                (TO,), always,
                None, ACCEPT,
                "takeoff already in progress", False
            ),
            (
                # (AG,), lambda: alt < 0.3 and target_alt <= 0.5,
                 (AG,), lambda: alt <= 0.016 and target_alt <= 0.448,  # old: alt < 0.3 and target_alt <= 0.5
                None, ACCEPT,
                "low takeoff target acknowledged; no flight", False
            ),
            (
                # (AG,), lambda: alt < 0.3,
                (AG,), lambda: alt <= 0.016,  # old: alt < 0.3
                TO, ACCEPT,
                "{source} -> {target}", True
            ),
            (
                None, always,
                None, DENY,
                "takeoff preconditions failed", False
            ),
        ),

        mav.MAV_CMD_NAV_LAND: (
            (
                (DG, AG, LD), always,
                None, ACCEPT,
                "{source}: land acknowledged; no new action", False
            ),
            (
                (TO, FL), always,
                LD, ACCEPT,
                "{source} -> {target}", True
            ),
            (
                None, always,
                None, TEMP,
                "not in flight", False
            ),
        ),

        # RTL, WAYPOINT, and REPOSITION are flight actions.
        # They do not introduce additional flight-phase states.
        mav.MAV_CMD_NAV_RETURN_TO_LAUNCH: (
            (
                (DG, AG), always,
                None, ACCEPT,
                "{source}: RTL acknowledged; no flight", False
            ),
            (
                # (TO, FL), lambda: alt > 0.5,
                (TO, FL), lambda: alt >= 1.465,  # old: alt > 0.5
                FL, ACCEPT,
                "{source} -> RTL", True
            ),
            (
                None, always,
                None, TEMP,
                "RTL requires active flight", False
            ),
        ),

        mav.MAV_CMD_NAV_WAYPOINT: (
            (
                (FL,), always,
                FL, ACCEPT,
                "FLYING -> WAYPOINT", True
            ),
            (
                (DG, TO), always,
                None, UNSUPPORTED,
                "waypoint unsupported during {source}", False
            ),
            (
                None, always,
                None, DENY,
                "waypoint requires active flight ({source})", False
            ),
        ),

        getattr(mav, "MAV_CMD_DO_REPOSITION", 192): (
            (
                (FL,), always,
                FL, ACCEPT,
                "FLYING -> REPOSITION", True
            ),
            (
                (DG, TO), always,
                None, UNSUPPORTED,
                "reposition unsupported during {source}", False
            ),
            (
                None, always,
                None, TEMP,
                "reposition requires active flight ({source})", False
            ),
        ),
    }

    fallback = (
        (
            None, always,
            None, UNSUPPORTED,
            "unsupported command", False
        ),
    )

    # ---------------------------------------------------------
    # 4. Generic automaton engine
    # ---------------------------------------------------------
    for transition in transitions.get(cmd, fallback):
        sources, guard, target, result, reason, execute = transition

        # Does this transition leave the current state?
        if sources is not None and phase not in sources:
            continue

        # Is its guard satisfied?
        if not guard():
            continue

        # Select the transition and produce its output.
        next_phase = phase if target is None else target
        reason = reason.format(source=phase, target=next_phase)

        if with_effect:
            return result, reason, execute

        return result, reason

    raise RuntimeError("Automaton has no matching transition")

#  /////////// command_ack //////////

def init_home_once(state: CommonState):
    if not state.home_initialized and state.gpi_lat != 0 and state.gpi_lon != 0:
        state.home_lat = state.gpi_lat
        state.home_lon = state.gpi_lon
        state.home_alt = state.gpi_alt
        state.home_initialized = True


