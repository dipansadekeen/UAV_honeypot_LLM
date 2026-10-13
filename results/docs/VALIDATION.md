# Validation of this artifact

Verified with Python 3.12.14, NumPy 2.3.5, pandas 2.2.3, and Matplotlib 3.10.8.

- Full CSV reproduction completed: 225 LLM cases, nine HITL cases / 698 telemetry pairs.
- Default deception metrics match Table II of the supplied paper.
- All 19 tests passed, including seven independent notebook-result comparisons.
- The continuous paper-formula profile completed separately; it changes LC/class outcomes as documented.
- Fifteen PNG figures and their vector PDF counterparts were generated. Main figures were visually checked; all PNG files passed image-integrity checks.
- All 37 Python files compiled successfully.
- Optional raw-log parsing passed synthetic accepted-mission-upload and heartbeat-interval checks. Original HP/SITL recordings were not available for real-log validation.

Re-run `python -m unittest discover -s tests -v` from the artifact root. Raw-log tests are skipped unless the optional dependency is installed. The bundled data and original-notebook hashes are recorded in `reference/provenance.json`; run settings/input hashes are recorded alongside outputs.
