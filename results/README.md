# UAV Honeypot Paper Artifact

A modular Python artifact for the analyses in **LLM for UAV Honeypot**.
This version reproduces the supplied `HP_Final_Eval.ipynb` using the two
bundled CSV datasets. All execution code is in `.py` files; Colab and Jupyter
are not required. No model account or API key is needed for CSV evaluation.

## Quick start

Use Python 3.12 (Python 3.11+ syntax is supported; the verified environment is
Python 3.12.14). From the extracted `uav_honeypot_artifact` folder:

```bash
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell instead: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts/run_all.py
python -m unittest discover -s tests -v
```

The default run writes CSV tables, PNG figures, vector PDF figures, and a
configuration/input-hash manifest under `results/notebook/`. A verified
example run is already included there.

## Folder layout

| Folder | Purpose |
|---|---|
| `config/` | Tolerances, budgets of cases, model aliases, selected mission IDs, scoring profiles |
| `evaluation/` | LLM/HITL checks, heartbeat policy, completion, trajectory efficiency, latency |
| `plotting/` | Publication figures and component heatmaps |
| `preprocessing/` | HITL case selection, CSV header repair, optional tlog conversion/connectivity |
| `prompts/` | Appendix prompt builders and offline response validation |
| `scripts/` | Command-line entry points |
| `tests/` | Numerical parity and boundary-condition checks |
| `data/` | The two supplied CSV inputs, copied without modification |
| `reference/` | Results captured independently by executing the original notebook cells |
| `results/notebook/` | Verified example results and generated figures |
| `docs/` | Methodology, figure mapping, and reproducibility notes |

## Run individual pieces

```bash
python scripts/evaluate_llm.py
python scripts/evaluate_hitl.py
python scripts/analyze_latency.py
python scripts/plot_missions.py
```

Each command accepts `--input` and `--out`; use `--help` for its other options.
Paths are resolved from the script location for bundled inputs, so scripts
also work when invoked from another working directory.

```bash
# Change the selected case budget; keep each run in a separate directory.
python scripts/evaluate_llm.py --max-cases 10 --out results/top10
python scripts/evaluate_llm.py --max-cases all --out results/all_cases

# Equation (8) profile: recompute continuous scores explicitly.
python scripts/run_all.py --profile paper --out results/paper_formula

# Restrict trajectory efficiency to SALC cases instead of the notebook's SA gate.
python scripts/evaluate_llm.py --trajectory-gate salc --out results/salc_trajectory

# Recompute tables without rendering figures.
python scripts/run_all.py --no-plots --out results/tables_only
```

`--max-cases 10` selects up to ten available cases; it does not invent cases.
The attached experiment has five LLM cases per model/operation. HITL defaults
to one case per operation, including the last observed LAND phase.

## What is reproduced

The default `notebook` profile matches all **225 LLM cases**, the five models'
performance metrics, component tables, HITL component scores, trajectory
summaries, and call-level latency summaries. The reproduced deception metrics
match Table II in the supplied paper. HITL selects **nine cases / 698 telemetry
pairs** from the 728-row supplied file.

The reference tests compare the refactored modules with CSV outputs captured
from original notebook cells 0, 3, 4, and 17. The tests also cover missing
heartbeat samples, call boundaries, wrapped angles, NED climb signs, the
speed-change/waypoint relationship, and prompt-response validation.

## Scoring choice that must remain explicit

The notebook implements `score = 1` when `error <= tolerance`, else `0`.
The paper's Equation (8) describes `score = clip(1 - abs(error)/tolerance, 0, 1)`.
These produce different results. The default preserves the notebook and its
Table II results; `--profile paper` enables the continuous formula while
retaining case selection and completion rules. The second profile is an
alternative calculation, not a claim to reproduce the published tables.

For movement operations, LC requires every **applicable** component's average
score to reach 0.5. Missing dependencies remain N/A. ARM/DISARM retain the
strict heartbeat and optional grounded-telemetry gates in both profiles.

See [docs/REPRODUCIBILITY.md](docs/REPRODUCIBILITY.md) for conventions and
[docs/PAPER_MAPPING.md](docs/PAPER_MAPPING.md) for figure/table entry points.

## Optional raw-log tools

The original HP/SITL `.tlog` recordings were not supplied. Install the
optional dependency and provide those files to generate connectivity results:

```bash
python -m pip install -r requirements-tlog.txt
python scripts/convert_tlog.py --input path/to/HITL.tlog --output results/converted/HITL.csv
python scripts/analyze_connectivity.py --hp path/to/HP.tlog --sitl path/to/SITL.tlog
```

The converter retains the notebook's CRC-verified recovery, vehicle identity
filtering, accepted-upload detection, resampling, and mission-event export.
Connectivity filters vehicle system/component IDs (default 1/1), includes zero
message-count seconds, and correctly labels heartbeat **intervals** in seconds.
Both operate on offline logs.

## Prompt templates and artifact scope

`prompts/heartbeat.py` and `prompts/telemetry.py` expose `build_prompt(...)`
functions; they append structured JSON context to the Appendix A templates.
`prompts/validation.py` checks response structure, timing, field names/types,
and armed-bit preservation. The PDF transcription is preserved in
`docs/appendix_prompt_transcription.txt`.

This is an **evaluation and prompt artifact**. The provided attachments do not
contain the original UDP honeypot engine, EFSM acknowledgment implementation,
provider client, scheduling/state-buffer implementation, or few-shot example
database. Those components are therefore not presented as recovered code.
Live response generation and end-to-end honeypot deployment require the
original runtime sources and examples. Table V token counts also require
request/token logs that were not supplied.

