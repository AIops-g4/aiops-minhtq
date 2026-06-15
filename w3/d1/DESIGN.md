# W3-D1 Design Notes

## 1. Frontend SLI choice

I chose a frontend RUM success SLI: a page-load event is good when `dom_ready_ms < 3000`, `js_error = false`, and `network_error = false`. This is more user-centered than looking at one frontend signal alone. The generated baseline has 518,400 RUM events over 3 days, or 172,800 events/day, with 7,204 bad events and a measured success rate of 98.61%. The p99 DOM ready value is 1,430 ms, so a 3,000 ms cutoff is not too close to normal tail behavior. I did not choose page load time or DOM ready alone because a page can be fast but broken by JavaScript. I did not choose JS error rate alone because it misses network failures. I did not choose network error rate alone because it misses slow or broken rendering. The combined SLI is closer to actual page usability.

## 2. API SLO target

I set the API target to 99.9% availability over 30 days. The generated API baseline has 2,073,780 requests over 3 days, 7,234 counted failures, and a fail rate of 0.3488%, which is about 99.65% availability during a period that includes injected incidents. A 99% SLO would allow about 207,378 failed requests per month from 20,737,800 monthly requests, which is too loose for an e-commerce API because checkout and order paths are core user journeys. A 99.99% SLO would allow only about 2,074 failures per month, which is tighter than the observed incident-heavy baseline and would imply multi-AZ automation and stronger operational cost. The 99.9% target allows about 20,738 failures per month, or roughly 43 minutes of equivalent full outage at sampled traffic, making it a useful stretch goal without pretending the service is already four-nines reliable.

## 3. API latency threshold

I use 500 ms as the latency threshold for the API good-event definition. The measured API latency distribution from `access_log.jsonl` is:

| Percentile | Latency ms |
| --- | ---: |
| p50 | 45 |
| p95 | 104 |
| p99 | 156 |
| max | 2553 |

The p99 latency is only 156 ms across 2,073,780 sampled requests, so a 200 ms threshold would be close to the normal tail and could make the SLI too sensitive to small shifts. A 1 second threshold would be too loose because users would already feel checkout or cart operations as slow before the SLI notices. The 500 ms cutoff leaves room above normal p99 while still detecting severe slowdowns, especially the incident windows where latency increases together with server errors. This makes it suitable for an SLO SLI rather than a low-level capacity metric.

## 4. 4xx exclusion

I exclude non-429 4xx responses from the API failure count because they usually represent caller-side or bot behavior, not service-side unavailability. In the generated API log, the counted service failures are 5xx and 429 only, totaling 7,234 events and a 0.3488% fail rate. Non-429 4xx responses are much more common but are spread evenly across endpoints: `/api/cart` has 2.04%, `/api/products` has 2.02%, `/api/orders` has 2.02%, `/api/checkout` has 2.01%, and `/api/user` has 1.98%. No endpoint has a non-429 4xx rate above 5%, so there is no strong evidence of a system bug hidden behind client errors. Counting these as SLO failures would let invalid requests or scraping activity burn the error budget even when valid user requests are being served correctly.

## 5. MWMBR tuning

I started with the Google-style MWMBR defaults: Tier 1 uses 1h and 5m windows with burn rate 14.4, Tier 2 uses 6h and 30m with burn rate 6, and Tier 3 uses 3d and 6h with burn rate 1. The first validation passed by the script but had an `mttd_delta_s` of exactly 60 seconds, which is too close to the assignment threshold. I tuned only the API Tier 1 threshold from 14.4 to 12, leaving the windows and the other tiers unchanged. The final validation report shows the static baseline fired 22 times with 19 false positives, while MWMBR fired 3 times with 0 false positives and 0 false negatives. Noise reduction is 86.4%, `mttd_delta_s` is 0, and the verdict is `pass`. This is a minimal tuning because it improves detection margin without increasing alert noise.
