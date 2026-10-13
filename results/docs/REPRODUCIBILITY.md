# Reproducibility conventions

## Authoritative inputs and selection

The attached notebook and CSV files define this artifact's numerical defaults.
The paper defines the intended terminology and formulas. `reference/provenance.json`
records SHA-256 hashes of both datasets and the original notebook.

LLM cases are extracted from section-marker rows in the CSV. Full missions use
sequence 0 for TAKEOFF, 1 for WP, 2 for WP+ALT, 3 for WP+YAW, and command 20
for RTL. Separate sections supply LAND and ARM/DISARM. A command 178 speed
change supplies context; its following command 16 waypoint is WP+SPEED.
This fixed sequence layout is specific to the recorded LLM experiment.
The first five cases in source order are selected per model/operation.

HITL extraction uses supplied operation metadata when available; otherwise it
classifies actual command/target changes. It repairs the eleven appended,
unnamed metadata columns in the supplied merged HITL CSV only when their
layout is recognized. Unknown populated unnamed columns produce an error.
The default selects one case for each operation, choosing the last LAND case.
LAND may be an observed phase of command 20 RTL; command IDs remain intact.

## Units and physical checks

- Latitude/longitude: integer degrees multiplied by 1e7.
- GPI altitude and relative altitude: millimeters.
- GPI vx/vy/vz: centimeters per second, NED; positive vz means descent.
- ATTITUDE roll/pitch/yaw: radians.
- VFR speed and climb: meters per second; climb is positive upward.
- GPI heading: centidegrees; 65535 is unknown. VFR heading: degrees.

Tolerances: speed 2 m/s; displacement 2.8 m; heading/yaw 45 degrees;
roll/pitch 24 degrees. Roll/pitch compare generated attitude with motion-derived
estimates using NED acceleration and gravity 9.80665 m/s^2. They are not a
fixed 0.25-radian attitude bound in this notebook version.

LLM displacement and acceleration use the previous generated state only within
the same mission/sequence/call. The first step in every call has no predecessor
for these checks. LLM dt stays fixed at 0.5 s because the recorded dt column is
a cumulative future offset. Direction is applicable at horizontal speed >=0.2 m/s.
HITL compares each row's input with its post-state and uses the row's elapsed dt.
HITL Heading compares GPI with VFR; LLM Heading compares VFR with velocity
direction. HITL Yaw uses GPI heading; LLM Yaw uses VFR heading. HITL displacement
checks mask unchanged position/altitude, preserving the notebook applicability.
HITL does not apply a timing fallback to invalid dt; dependent checks become N/A.

Case scores average samples per component; operation scores average cases
equally. Heading is hidden in TAKEOFF/LAND component display tables only;
raw heading checks remain included in LLM LC. `model_component_means.csv`
replicates the notebook's Table III aggregation after that display masking.
The pooled HITL counts are also exported separately; they are not the same
weighting as equally weighted case means.

## SA, LC, and metrics

SA uses terminal state: TAKEOFF within 1500 mm of requested altitude; LAND
relative altitude <=500 mm; waypoint within 200 units in each lat/lon axis and
1500 mm altitude; RTL lat/lon position only. These are the supplied completion
rules, including the RTL altitude convention and lack of a negative-altitude
LAND rejection. They are retained for numerical parity.

LC for movement operations requires every applicable component average >=0.5.
Cases with no applicable component fail LC. SALC=SA and LC; SANLC=SA and not LC;
FALC=not SA and LC; FANLC=neither. Applicability is a property of available
fields; an N/A field is not a successful physical check. The existing policy
can classify a case with some missing components as LC; it does not require
all nine components to be present.

Precision=SALC/(SALC+SANLC); Temptation=SALC/(SALC+FALC);
ASR=(SALC+SANLC)/N; Accuracy=(SALC+FALC)/N. Thus Accuracy is the LC fraction,
not classification accuracy against independently labeled ground truth.
TCR repeats the SA fraction, equal to ASR in this evaluation.

The `notebook` profile averages binary error<=tolerance checks. The `paper`
profile averages clip(1-|error|/tolerance,0,1) scores. Both retain raw errors
and binary pass/fail detail counts. Continuous scores are not substituted into
the strict ARM/DISARM gates.

## Heartbeat conventions

For the supplied LLM export, `input_hb_*` stores the applied LLM heartbeat;
this is the original notebook's stated convention. If any `generated_hb_*`
columns exist, those are used instead; incomplete generated heartbeat groups
fail required checks. The experiment requires ARM base_mode armed bit set,
custom_mode 50593792, system_status 4; DISARM armed bit clear, custom_mode
0 or 50593792, system_status 3. These are experiment policies, not universal
MAVLink requirements. Optional grounded telemetry must pass all applicable
checks. A heartbeat-only response is permitted.

HITL ARM/DISARM uses post-state `generated_hb_base_mode`, checks the armed bit
and supplied grounded motion fields, and exports a separate status table.
Invalid/missing HB base-mode samples now prevent passage of the whole case;
the notebook had discarded invalid samples before its all-pass check. This
hardening does not change any result on the supplied HITL data.

## Trajectory and latency conventions

Trajectory efficiency=100*straight 3D ENU distance/taken 3D ENU distance.
The default gate is SA, matching notebook cell 4, including the RTL convention
of target altitude equal to initial altitude. `--trajectory-gate salc` adds LC
eligibility explicitly. These summaries exclude ARM/DISARM; unavailable or
zero-length paths remain N/A. Efficiency is not capped at 100%, preserving the
original formula when completion tolerances allow a path shorter than the
straight distance to the exact target.

Latency includes all recorded model calls, not just selected scoring cases.
It counts one value per model/LLM-call ID; repeated telemetry rows do not add
observations. Conflicting values or ID reuse across missions produce an error.
Standard-deviation error bars are shown; they are not confidence intervals.

Figure 8 uses the five mission IDs in `config/settings.py`, one mission per
model by default. Mission progress is normalized sample order, not elapsed
wall-clock time. Linear interpolation of finite samples and circular averaging
of headings across missions follow the notebook. Heading interpolation itself
is linear in degrees and can interpolate across the 0/360 wrap; raw error checks
use wrapped differences. The target path averages mission target points in the
same local frame, following the notebook. VFR altitude is used for Figure 8,
whereas efficiency uses GPI relative altitude. No fixed axis limits hide curves.

## Prompt provenance and missing inputs

Prompt bodies were transcribed from Appendix A of the supplied PDF in column
order. Executable telemetry text restores omitted multiplication symbols in
relative_alt=alt*1000 and hdg=heading*100. The PDF says groundspeed `810`;
the readable template interprets it as **8-10 m/s**. This range interpretation
requires author confirmation before claiming byte-identical original prompts.
The raw extracted transcription is included for review. Context serialization
is supplied by this artifact because the original prompt/client source is absent.

The response validator enforces JSON structure, five 0.5-second offsets,
allowed field groups, finite numeric values, integer fields, battery presence,
and armed-bit preservation. It is a schema checker, not a complete physical
validator or the missing original scheduling/runtime engine.

No raw HP/SITL/HITL logs, request token logs, production EFSM code, or retrieved
few-shot example database were attached. Optional log tools cannot reproduce
Figure 9 without those recordings; token Table V and online behavior cannot
be independently reproduced from the bundled inputs.
