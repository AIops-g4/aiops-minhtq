# Postmortem: AWS S3 us-east-1 (2017-02-28)

> Blameless wording: this report describes system behavior, guardrails, and recovery paths.

## Summary
During the reproduction, a maintenance command intended for the billing-control scope affected the S3 index and placement subsystems as well. The platform detected the control-plane failure in 18 seconds and identified the maintenance command scope as the most likely root. The incident pattern shows how broad operational permissions can turn a narrow maintenance task into a service-wide outage.

## Impact
- **Users affected:** 100% of synthetic S3 clients in the reproduction window
- **Services affected:** billing-control, s3-index, s3-placement, synthetic S3 API
- **Revenue/SLA impact:** Complete S3 API unavailability during the injected window; production analogue would burn the full availability budget for the outage duration
- **Duration:** 2026-06-19 09:01 UTC -> 2026-06-19 09:10 UTC, 9 minutes

## Timeline (UTC)
Minimum 8 events. Pull from `timeline.json`.

| UTC | Event |
|-----|-------|
| 2026-06-19 09:00 | Compose stack healthy: billing-control, s3-index, s3-placement all running |
| 2026-06-19 09:00 | Baseline probes green: S3 API availability 1.000, metadata lookup p99 42ms |
| 2026-06-19 09:01 | Maintenance command entered the billing-control change window |
| 2026-06-19 09:01 | billing-control container stopped |
| 2026-06-19 09:01 | s3-index container stopped |
| 2026-06-19 09:01 | s3-placement container stopped |
| 2026-06-19 09:01 | Prometheus alert fired for S3MetadataUnavailable |
| 2026-06-19 09:01 | AIOps pipeline emitted MultiServiceDisappearance alert after 18 seconds |
| 2026-06-19 09:01 | RCA selected maintenance-command-scope with confidence 0.82 |
| 2026-06-19 09:03 | Mitigation started by restoring placement, index, then billing-control |
| 2026-06-19 09:06 | Metadata unavailable alert resolved |
| 2026-06-19 09:10 | Recovery confirmed by synthetic S3 API probes |

## Root cause
The system allowed a maintenance command to apply beyond the intended billing-control scope, which removed capacity from both the S3 index and placement subsystems.

## Contributing factors
1. Destructive operational commands had insufficient blast-radius controls and no narrow-scope confirmation gate.
2. The index and placement subsystems required restart and warm-up before object metadata operations could recover.
3. The detector weighted service disappearance strongly but treated change events as secondary context.

## Detection
- **How was it detected?** Pipeline alert from container lifecycle events plus Prometheus availability alerts
- **MTTD:** 18 seconds from injection start to pipeline alert
- **Pipeline gaps observed during reproduction:**
  - Gap 1: Audit/change-event correlation is not first-class, so the detector cannot immediately distinguish an intentional maintenance command from an unplanned infrastructure failure.
  - Gap 2: RCA can identify the simultaneous service loss, but it needs stronger command-scope evidence to explain why billing-control, index, and placement disappeared together.

## Response
- **First responder action:** Restore placement, then index, then billing-control to bring metadata routing back before billing maintenance resumes.
- **Time to mitigate:** 5 minutes 40 seconds
- **Time to fully resolve:** 9 minutes

## Action items
| # | Action | Owner | Type | ETA |
|---|--------|-------|------|-----|
| 1 | Add scoped dry-run and affected-service preview for destructive maintenance commands | Platform Ops | preventive | 2026-06-26 |
| 2 | Promote audit/change events into RCA evidence with time-window joins | AIOps Team | detective | 2026-07-03 |
| 3 | Add control-plane dependency edges for billing, index, and placement subsystems | SRE Team | detective | 2026-07-03 |
| 4 | Add restart-order runbook for S3 metadata recovery | Incident Response | mitigation | 2026-06-28 |
