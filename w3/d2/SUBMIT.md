# W3-D2 Submission - minhtq

## 3 things I learned about my AIOps pipeline
1. Detection coverage is not the same as service coverage. The pipeline detected most app and DB faults, but missed `log_collector_disk_fill` because meta-monitoring was not represented.
2. RCA can detect a fault and still choose the wrong root. The DNS latency experiment fired an alert, but RCA selected `api-gateway` because the symptom appeared there.
3. Synthetic probes are useful as an external steady-state signal. During the chaos run, the probe showed user-visible impact while the pipeline separately measured detection and RCA behavior.

## 1 fault I expected the pipeline to catch but it missed
- Experiment: `log_collector_disk_fill`
- Why I expected detection: log ingestion lag should be a first-class signal for an AIOps platform because losing logs can hide future incidents.
- Why pipeline missed: the lightweight detector has no meta-monitoring metric for log queue lag, disk usage, or collector write failures.

## 1 trade-off in pipeline design I want to rethink
The main trade-off is between a small, simple RCA model and topology-aware accuracy. A simple model is easy to run and debug, but DNS latency showed that symptom-heavy services can outrank quieter upstream dependencies. I would add dependency-specific evidence before adding a more complex model.

## Scoreboard summary
- detected: 9/10
- rca_correct: 8/9
- mttd_p50: 3s
- false_alarms: 0
- verdict: pass

## Submitted artifacts
- `w3/d2/w3-d2-pack/docker-compose.yml`
- `w3/d2/w3-d2-pack/experiments.yaml`
- `w3/d2/w3-d2-pack/chaos_runner.py`
- `w3/d2/w3-d2-pack/chaos_results.json`
- `w3/d2/w3-d2-pack/probe.log`
- `w3/d2/w3-d2-pack/baseline.json`
- `w3/d2/chaos_report.md`
