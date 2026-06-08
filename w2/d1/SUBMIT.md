# W2/D1 Alert Correlation Submission

## Design choices

I chose `gap_sec = 120` because the sample incident is a compact burst. Most alerts arrive within seconds of each other, and a two-minute session window keeps the payment incident together without using a window so large that unrelated incidents hours apart would be merged. If `gap_sec = 30`, the same incident can be split just because one symptom arrives slightly late. If `gap_sec = 600`, the correlator becomes too permissive and may merge separate incidents that only happen near the same time.

I chose `max_hop = 2` because one-hop topology is too strict for cascades. For example, `payment-svc` affects `checkout-svc`, and `checkout-svc` can affect `edge-lb`. Two hops captures this propagation path. More than two hops would be risky in this graph because `edge-lb` connects to many services and can accidentally pull unrelated services into the main cluster.

The explicit misses are `a-0013` and `a-0016`. `a-0013` is `recommender-svc` CPU utilization and its note says it is an unrelated concurrent batch retrain. `a-0016` is `search-svc` query latency and its note says independent slow query. The code treats these note hints as a guard against false correlation, so they become standalone clusters even though time and topology alone might connect them.

If there were 10000 alerts instead of 20, the slowest part would be pairwise service comparison inside topology grouping and repeated shortest-path checks. The cost is acceptable for this lab because the number of unique services in each session is small. In production, I would precompute all-pairs service distance for the topology graph, cache fingerprints, and process sessions incrementally instead of recomputing every cluster from scratch.

## EOD checkpoint

Fingerprint should not include timestamp or value because those fields change every time an alert fires. If timestamp were included, two repeated `payment-svc latency_p99_ms crit` alerts at different seconds would produce different fingerprints, so dedup would fail. If value were included, the same metric crossing the same threshold with values 1840 and 1900 would look like different alert types.

A duplicate alert is the same alert type firing again, such as repeated `payment-svc|latency_p99_ms|crit`. A correlated alert is different but related by time and topology, such as `payment-svc latency_p99_ms` and `checkout-svc downstream_payment_error_rate`. Duplicate means same symptom repeated. Correlated means separate symptoms likely belong to the same incident workload.

With `gap_sec = 30`, the output would probably have more clusters because late symptoms get split away from the main incident. With `gap_sec = 600`, the output would probably have fewer clusters, but with higher false correlation risk because unrelated alerts in a ten-minute span can be merged.

In the main payment pool exhaustion scenario, the correlator should not merge `recommender-svc` into the main cluster. It happens in the same time range, but the dataset marks it as an unrelated batch retrain. Also, topology-aware correlation is only a reduction step, not root cause analysis. Merging recommender would create a noisy cluster and hide the useful signal that the payment path is the real operational workload.

The biggest limitation of topology grouping is that graph distance alone does not understand direction, edge type, or runtime context. An undirected two-hop rule can connect services that are close in the static graph but unrelated in the incident. A practical fix is to add edge semantics, such as sync versus async, request traces, recent deployment events, and metric-specific rules before allowing a topology merge.
