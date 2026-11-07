# Validation of this artifact

Verified with Python 3.12.14, NumPy 2.3.5, pandas 2.2.3, and Matplotlib 3.10.8.

- Full CSV reproduction completed: 225 LLM cases, nine HITL cases / 698 telemetry pairs.
- Default deception metrics match Table II of the supplied paper.
- All 27 tests passed, including seven independent notebook-result comparisons, the EFSM ground-truth check, and seven few-shot ablation tests (run selection, plan operations, bundled-data totals). This latest run used Python 3.10.12, NumPy 2.2.6, pandas 2.3.3, and Matplotlib 3.10.9; the log is `docs/test_results.txt`.
- Few-shot ablation: 39 of 44 runs selected; 54 / 42 / 52 / 57 cases for full / ab1 / ab2 / ab3.
- The continuous paper-formula profile completed separately; it changes LC/class outcomes as documented.
- Fifteen PNG figures and their vector PDF counterparts were generated. Main figures were visually checked; all PNG files passed image-integrity checks.
- All 37 Python files compiled successfully.
- Optional raw-log parsing passed synthetic accepted-mission-upload and heartbeat-interval checks. Original HP/SITL recordings were not available for real-log validation.

Re-run `python -m unittest discover -s tests -v` from the artifact root. Raw-log tests are skipped unless the optional dependency is installed. The bundled data and original-notebook hashes are recorded in `reference/provenance.json`; run settings/input hashes are recorded alongside outputs.
