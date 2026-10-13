# Paper-to-code map

| Paper item | Entry point | Output |
|---|---|---|
| Table II: deception metrics | `scripts/evaluate_llm.py` | `llm/modelwise_metrics.csv` |
| Table III: mean component scores | `scripts/evaluate_llm.py` | `llm/model_component_means.csv` |
| Appendix operation/component table | `scripts/evaluate_llm.py` | `llm/component_compliance.csv` |
| Table IV: trajectory efficiency | `scripts/evaluate_llm.py` | `llm/trajectory/trajectory_summary.csv` |
| Figure 6: SALC/SANLC/FALC/FANLC | `scripts/evaluate_llm.py` | `llm/figures/fig06_deception_categories.*` |
| Figure 7: operation realism | `scripts/evaluate_llm.py` | `llm/figures/fig07_operation_realism.*` |
| Figure 8a: velocity | `scripts/plot_missions.py` | `missions/figures/fig08a_velocity_components.*` |
| Figure 8b: trajectory | `scripts/plot_missions.py` | `missions/figures/fig08b_trajectory_2d.*` |
| Figure 8c: heading | `scripts/plot_missions.py` | `missions/figures/fig08c_heading.*` |
| Figure 9: connectivity | `scripts/analyze_connectivity.py` | Requires HP and SITL tlogs |
| Figure 10: latency | `scripts/analyze_latency.py` | `latency/figures/fig10_model_latency.*` |
| HITL calibration/comparison | `scripts/evaluate_hitl.py` | `hitl/component_compliance_fractions.csv` |
| Appendix A heartbeat prompt | `prompts/heartbeat.py` | `PROMPT`, `build_prompt(...)` |
| Appendix A telemetry prompt | `prompts/telemetry.py` | `PROMPT`, `build_prompt(...)` |

Paths above assume individual scripts with default output directories.
`run_all.py` places the same outputs under `results/notebook/`; it writes
trajectory tables in `results/notebook/trajectory/`. Asterisk means PNG and PDF.

The default notebook profile reproduces the supplied notebook's numerical
results and Table II. Figure styles have been standardized for readability.
The continuous profile implements Equation (8) as a separate alternative.
Table V prompt/token statistics need missing request logs. Architecture and
state-automata diagrams are paper illustrations rather than CSV analyses.
