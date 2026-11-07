# Ablations

Two ablations of the honeypot:

1. **EFSM ablation**: command ACKs with and without the EFSM (`fsm_ablation_cases.json`).
2. **Few-shot example ablation**: telemetry generation with and without the
   sequence and transition examples (`../data/ablation_dataset.csv`, scored by
   `../scripts/evaluate_ablation.py`).

## 1. EFSM ablation

`fsm_ablation_cases.json` compares the honeypot with and without the EFSM
(`state_automata_ack` in `module_helper_functions.py`) on ten command
sequences, using `gpt-oss:20b`.

- **With EFSM:** the automaton decides every `COMMAND_ACK` and whether the
  command is executed (sent to the LLM).
- **Without EFSM:** every command is ACCEPTED and executed. This is the
  ablation switch below the `state_automata_ack` call in
  `module_llmhoneypot.py` (commented out by default).

### Results

| | ACK matches PX4 | Logically consistent | LLM calls | LLM time |
|---|---|---|---|---|
| With EFSM | 10/10 | 10/10 | 31 | 898.65 s |
| Without EFSM | 8/10 | 3/10 | 61 | 1636.17 s |

| Case | Command sequence | With EFSM | Without EFSM |
|---|---|---|---|
| 1 | LAND without ARM or TAKEOFF | consistent | consistent |
| 2 | RTL without ARM, TAKEOFF or flight | consistent | D |
| 3 | WAYPOINT without ARM or TAKEOFF | consistent | D; ACK ACCEPTED instead of UNSUPPORTED |
| 4 | TAKEOFF without ARM | consistent | A |
| 5 | ARM → TAKEOFF → LAND | consistent | consistent |
| 6 | ARM → DISARM (→ ARM) | consistent | S |
| 7 | TAKEOFF → DISARM (no ARM) | consistent | A, D |
| 8 | DISARM without ARM | consistent | consistent |
| 9 | ARM → TAKEOFF → WAYPOINT → RTL → DISARM in flight | consistent | D; DISARM in flight ACCEPTED instead of TEMPORARILY_REJECTED |
| 10 | TAKEOFF → ARM | consistent | A |

Logical-consistency violations:

- **A**: heartbeat reports armed without a received ARM command
- **D**: relative altitude > 0.2 m or speed > 0.2 m/s while disarmed
- **S**: ARM/DISARM changes altitude or position (vehicle not stationary)

The expected ACK for each case is the PX4 SITL behaviour in `../efsm/`.

### File format

Each entry in `cases` has `with_fsm` and `without_fsm` blocks containing:

- `ack_log`: the raw rx/tx records from `logs/mavlink_rx_tx.jsonl`
- `fsm_log`: relevant honeypot console lines (EFSM decision, skipped LLM calls)
- `llm_calls`: one entry per LLM request, with latency, the heartbeat
  (`base_mode,custom_mode,system_status`) at receipt, the vehicle state at
  receipt, and the five generated steps (t = 0.5 … 2.5 s)
- `lc`, `violations`, and, where relevant, `ack_mismatch` and `note`

State strings are comma-separated values of the 20 fields listed in
`row_format.state_fields`; an empty value means the LLM omitted that field.
`summary` holds the totals above.

## 2. Few-shot example ablation

The telemetry prompt carries two kinds of few-shot examples
(`module_llmhoneypot.py`, prompt assembly): **sequence** examples (consecutive
telemetry within a command) and **transition** examples (telemetry across a
command change).

| Setting | Examples in the prompt |
|---|---|
| `full` | sequence + transition |
| `ab1` | transition only (sequence removed) |
| `ab2` | sequence only (transition removed) |
| `ab3` | none |

Every run flies the same uploaded mission: TAKEOFF to 50 m, a waypoint
climbing to 60.7 m, a waypoint descending to 50 m, DO_CHANGE_SPEED, a
waypoint, RTL, and LAND.

```bash
python scripts/evaluate_ablation.py          # writes results/ablation_fewshot/
```

### Run selection

`ablation_dataset.csv` holds 44 runs, each headed by a marker row such as
`#120b-ab2-3`. A run is *failed* when its marker contains "fail". For each
setting and model, runs are taken in file order until **two successful runs**
are kept. A failed run that comes before the second success is kept as well.
Thirty-nine runs are kept (`runs.csv` lists every run and the reason it was
kept or dropped):

| Setting | Runs kept | Failed runs kept | Runs that landed |
|---|---|---|---|
| full | 9 | 0 | 9 |
| ab1 | 7 | 0 | 7 |
| ab2 | 10 | 3 | 6 |
| ab3 | 13 | 4 | 8 |

Dropped: the third successful run of gpt-oss-20b and nemotron-super in full,
of gpt-oss-120b in ab2, and of nemotron-super in ab3 (the second section
labelled `nemo-super-ab3-3`, `mission_20261103_173411`); and a second,
byte-identical copy of the `nemo-super-ab3-2--fail` section. Some settings have
fewer than two runs for a model (for example ab1 has one run of gpt-oss-20b,
gemma4 and nemotron-nano).

### Cases and scoring

Each mission item of a kept run is one case. Operations come from the
uploaded plan: TAKEOFF, the two altitude-changing waypoints as WP+ALT, the
waypoint after DO_CHANGE_SPEED as WP+SPEED, RTL, and LAND. A failed run only
contributes cases for the items it reached. Scoring is the unchanged
`evaluate_llm` check set (notebook profile by default; `--profile paper` for
Equation (8)), so SA, LC and the classes mean the same as in Table II.

### Results (all models, notebook profile)

| Setting | Cases | SALC | SANLC | FALC | FANLC | ASR (%) | LC (%) |
|---|---|---|---|---|---|---|---|
| full | 54 | 31 | 21 | 1 | 1 | 96.3 | 59.3 |
| ab1 | 42 | 26 | 14 | 1 | 1 | 95.2 | 64.3 |
| ab2 | 52 | 33 | 14 | 3 | 2 | 90.4 | 69.2 |
| ab3 | 57 | 32 | 17 | 2 | 6 | 86.0 | 59.6 |

ASR (operation success) falls as examples are removed, and falls most when
the transition examples are removed (ab2, ab3). In ab3, TAKEOFF succeeds in
8 of 13 cases (61.5%). LC does not follow the same order. Removing the
transition examples (ab2, ab3) also produces the failed runs that never reach
LAND. Per-model results are in `ablation_summary.csv`; per-operation results
are in `ablation_by_operation.csv`.

### Output files (`results/ablation_fewshot/`)

| File | Content |
|---|---|
| `runs.csv` | every run: setting, model, marker, mission ID, failed, last mission item reached, selected, reason, landed |
| `ablation_summary.csv` | classes, ASR, LC, precision and mean compliance per setting and model (`All` = pooled) |
| `ablation_by_operation.csv` | the same per setting and operation |
| `<setting>/` | the full `evaluate_llm` output for that setting (case scores, check details, selected cases, settings and input hash) |

### Data notes

- The gpt-oss-20b runs and `#nemo-nano-ab3` used local model tags
  (`gpt-oss:20b`, `nemotron-3-nano:30b`); they are mapped to `gpt-oss-20b`
  and `nemotron-nano`.
- `#nemo-super-ab3 -4` contains `nemotron-3-nano:30b-cloud` data; runs are
  grouped by the model column, not the marker.
- Two runs are not marked failed but did not finish the mission:
  `#120b-ab2-2` stops at the DO_CHANGE_SPEED item, and `#gemma ab3-3` only
  has TAKEOFF calls. They count as successful runs under the marker rule.
- File order and time order differ once: in ab3, the nemotron-super failed run
  (`mission_20261103_172829`) is placed before `mission_20261031_160953`.
