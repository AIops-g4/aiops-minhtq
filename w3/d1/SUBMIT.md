# W3-D1 Submission - minhtq

## 3 things I learned

1. A good SLI should reflect user pain, not internal saturation. CPU or memory can explain a problem, but they should not be the main SLO signal when users are still receiving successful and fast responses.
2. Error budget makes the SLO decision concrete. For the API, a 99.9% target on 20,737,800 monthly requests allows about 20,738 failures, which is much easier to reason about than the percentage alone.
3. Multi-window multi-burn-rate alerting reduces noisy alerts because both a long window and a short window must breach together. In my validation, MWMBR reduced alert firings from 22 to 3.

## 1 thing still unclear

I am still unsure how aggressive the first production SLO should be when the available baseline includes known incident periods. The generated API fail rate is 0.3488%, or about 99.65% availability, but the assignment asks us to reason about a 99.9% target. I treated 99.9% as a stretch objective for the next operating period, not as a statement that the current service already meets it.

## 1 SLO trade-off I am unsure about

The trade-off I am least certain about is the frontend target. I chose 98% because the measured RUM success rate is 98.61%, which leaves a small buffer while still being meaningful. A higher target would force faster reliability work, but it might also burn budget too often because the SLI combines slow DOM ready, JS errors, and network errors into one user-facing signal.

## Validation report

- noise_reduction_pct: 86.4%
- mttd_delta_s: 0s
- false_negative: 0
- verdict: pass
