# W3-D3 Submission - minhtq

## Outage chosen
- ID: 1
- Name: AWS S3 us-east-1 2017-02-28
- Why this one: I chose this outage because it demonstrates how a small operational control-plane action can become a broad availability incident. The pattern is useful for AIOps because the raw symptoms are simultaneous service loss, while the real lesson is command scope, blast radius, and change correlation.
- Failure mode: operator

## 3 things I learned from this outage
1. A fast detector is not enough if RCA cannot connect alerts to the change window that created them.
2. Blast-radius controls should be visible before a destructive command runs, not only after an alert fires.
3. Index and placement dependencies are critical because losing both turns a local control-plane issue into user-visible S3 API unavailability.

## 1 thing my pipeline would still miss if this outage happened for real
- Pattern: A maintenance command with a valid change ticket but an unexpectedly broad service scope.
- Why miss: The current pipeline sees lifecycle and availability events, but audit/change events are not yet mandatory RCA inputs.
- Mitigation idea: Ingest audit logs, command previews, and deploy/change windows into the same incident graph as metrics and alerts.

## 1 ADR decision I am not completely sure about
I chose topology-aware RCA with change-event correlation in ADR-001. I am not fully sure how much operational overhead this creates because the approach depends on accurate topology and complete audit-event ingestion. The decision is still the best fit for this outage pattern, but stale dependency data could make RCA confidently wrong.

## Cost model verdict for my stack
- ROI: 0.53
- Payback: inf months
- Verdict: not_worth_it
