# Kế Hoạch Phân Tích Metrics Và Log Parsing

## Mục Tiêu

Xây bước tiền xử lý để biến raw metrics và raw logs trong mỗi incident thành các bằng chứng nghi vấn có format thống nhất. Đầu ra của bước này phục vụ cho bước correlation/gom cluster sau đó, nhưng plan này chưa xử lý correlation.

Pipeline của bước này:

`incident JSON -> metric anomaly detection -> log parsing/template extraction -> evidence candidates -> artifact trung gian`

Điểm thiết kế chính: metrics và logs không nên xuất ra hai schema hoàn toàn khác nhau. Cả hai nên được quy về cùng một envelope `evidence candidate`; các field đặc thù của metric hoặc log đặt trong `details`.

## Input Cần Xử Lý

- `metrics_window.samples`:
  - Key có dạng `service.metric`, ví dụ `payment-svc.latency_p99_ms`.
  - Value là list time series `[[timestamp, value], ...]`, thường khoảng 100 samples.
  - Mỗi incident chỉ có vài metric series liên quan, không phải toàn bộ monitoring history.

- `logs`:
  - Mỗi dòng có `ts`, `svc`, `level`, `msg`.
  - `msg` là raw message, có nhiều giá trị động như số ms, id, phần trăm, revision, target.
  - Trong eval thường có khoảng 500 dòng, nhiều dòng lặp lại cùng bản chất lỗi.

- `detected_at` và `trigger_alert`:
  - `detected_at` dùng để chia vùng trước/sau alert.
  - `trigger_alert.service` là service phát alert, dùng làm context nhưng không được xem là root cause mặc định.

- Nguồn dữ liệu trong lab:
  - Metrics, logs và traces đều nằm trong file incident JSON như `eval/E01.json`.
  - Không giả định có Prometheus, Loki hoặc OpenTelemetry thật.
  - `source_ref.system` nên dùng `"incident_json"` để phản ánh đúng nguồn dữ liệu của lab.

## Schema Output Chung: Evidence Candidate

Tất cả bằng chứng nghi vấn, dù đến từ metrics hay logs, đều nên dùng envelope chung sau:

```json
{
  "schema_version": "1.0",
  "evidence_id": "metric:E01:payment-svc.latency_p99_ms",
  "evidence_type": "metric",
  "incident_id": "E01",
  "service": "payment-svc",
  "timestamp_start": "2026-06-10T14:08:00Z",
  "timestamp_end": "2026-06-10T15:22:15Z",
  "score": 0.91,
  "score_meaning": "0..1, càng cao càng đáng nghi",
  "summary": "latency_p99_ms tăng mạnh sau alert",
  "signals": ["metric_increase", "latency_anomaly", "post_alert"],
  "source_ref": {
    "system": "incident_json",
    "file": "eval/E01.json",
    "path": "metrics_window.samples.payment-svc.latency_p99_ms"
  },
  "details": {}
}
```

Quy ước bắt buộc:

- `schema_version`: luôn có, bắt đầu bằng `"1.0"` để dễ maintain khi pipeline thay đổi.
- `evidence_id`: unique trong một incident, nên có dạng `<type>:<incident_id>:<entity>`.
- `evidence_type`: dùng `"metric"` hoặc `"log"` trong bước này.
- `incident_id`: dùng basename file như `E01`, không dùng raw `incident_id` dài trong JSON.
- `service`: service chính mà evidence đang nói tới.
- `timestamp_start` và `timestamp_end`: khoảng thời gian evidence xuất hiện hoặc được tính.
- `score`: normalize về range `0..1`, cùng ý nghĩa cho mọi loại evidence.
- `score_meaning`: ghi rõ quy ước score để tránh hiểu nhầm giữa metric score và log score.
- `summary`: mô tả ngắn cho người đọc.
- `signals`: list nhãn máy đọc được, dùng cho bước clustering/correlation sau.
- `source_ref`: nơi truy ngược dữ liệu gốc trong incident JSON.
- `details`: field đặc thù theo loại evidence.

## Quy Ước Score Chung

`score` phải có cùng ý nghĩa trên cả metric và log:

```text
score nằm trong [0, 1]
score càng cao -> evidence càng đáng nghi
```

Không được để metric score là z-score thô còn log score là burst count thô, vì clustering sau đó sẽ bị bias. Mọi detector phải normalize về `0..1`.

Gợi ý mức diễn giải:

- `0.00 - 0.30`: tín hiệu yếu hoặc nhiễu nền.
- `0.30 - 0.60`: có dấu hiệu đáng chú ý nhưng chưa mạnh.
- `0.60 - 0.80`: nghi vấn rõ.
- `0.80 - 1.00`: nghi vấn rất mạnh, nên nổi lên top.

## Phân Tích Metrics

- Chuẩn hóa metric series:
  - Parse key `service.metric` thành `service` và `metric`.
  - Sort samples theo timestamp.
  - Ép value sang float.
  - Bỏ qua hoặc đánh dấu series thiếu dữ liệu, NaN, hoặc ít hơn số sample tối thiểu.

- Chia baseline và incident window:
  - Ưu tiên dùng phần trước `detected_at` làm baseline nếu có đủ sample.
  - Nếu không đủ, dùng 30% đầu của time window làm baseline.
  - Phần còn lại là vùng cần kiểm tra anomaly.

- Tính feature thống kê cho từng series:
  - `baseline_mean`, `baseline_std`.
  - `baseline_median`, `baseline_mad` để chống outlier.
  - `start_value`, `end_value`, `min_value`, `max_value`.
  - `absolute_delta = end_value - start_value`.
  - `ratio = end_value / start_value` nếu start khác 0.
  - `slope` đơn giản theo hồi quy tuyến tính hoặc delta trên thời gian.
  - `post_alert_peak_z` hoặc robust z-score lớn nhất sau alert.

- Detector nên dùng:
  - Rolling/standard z-score cho spike rõ.
  - Robust z-score bằng median/MAD cho dữ liệu lệch hoặc có outlier.
  - Delta/ratio cho drift tăng dần như memory leak, replica lag, pool usage.
  - Không cần STL/Isolation Forest ở bước đầu vì mỗi eval incident có ít series và window ngắn; dùng detector giải thích được là đủ.

- Rule gắn cờ metric anomaly:
  - Spike/drop: `abs(robust_z) >= 3.5` hoặc `abs(z) >= 3.0`.
  - Drift: ratio lớn, slope rõ, hoặc end value lệch mạnh so với baseline.
  - Metric dạng error/latency/lag/gc/memory/pool nếu tăng mạnh thì score cao hơn.
  - Metric bất thường phải giữ chiều biến động: `increase`, `decrease`, hoặc `spike`.

- Normalize metric score:
  - Chuyển z-score, ratio, slope và post-alert deviation về các score con `0..1`.
  - Kết hợp các score con thành một `score` cuối cùng.
  - Không đưa z-score thô vào `score`; z-score thô chỉ nằm trong `details`.

Ví dụ metric evidence candidate:

```json
{
  "schema_version": "1.0",
  "evidence_id": "metric:E01:payment-svc.latency_p99_ms",
  "evidence_type": "metric",
  "incident_id": "E01",
  "service": "payment-svc",
  "timestamp_start": "2026-06-10T14:08:00Z",
  "timestamp_end": "2026-06-10T15:22:15Z",
  "score": 0.91,
  "score_meaning": "0..1, càng cao càng đáng nghi",
  "summary": "payment-svc latency_p99_ms tăng mạnh so với baseline",
  "signals": ["metric_increase", "latency_anomaly", "post_alert"],
  "source_ref": {
    "system": "incident_json",
    "file": "eval/E01.json",
    "path": "metrics_window.samples.payment-svc.latency_p99_ms"
  },
  "details": {
    "metric": "latency_p99_ms",
    "series_key": "payment-svc.latency_p99_ms",
    "direction": "increase",
    "baseline_mean": 410.2,
    "baseline_std": 35.1,
    "start_value": 405.0,
    "end_value": 1800.0,
    "ratio": 4.44,
    "z_score": 5.8,
    "reason": "p99 latency tăng mạnh so với baseline"
  }
}
```

## Log Parsing

- Mục tiêu parsing:
  - Không dùng raw `msg` trực tiếp để so sánh.
  - Chuyển mỗi raw log thành `template` ổn định và `params` động.
  - Template phải gần với `log_signatures` trong `incidents_history.json`.

- Tiền xử lý mỗi log:
  - Giữ nguyên `ts`, `svc`, `level`, `msg`.
  - Normalize `msg` thành lowercase cho matching phụ, nhưng vẫn lưu bản template readable.
  - Thay các giá trị động bằng token:
    - số nguyên/thập phân -> `<num>`
    - thời lượng như `5000ms`, `12s` -> `<duration>`
    - phần trăm như `98%` -> `<percent>`
    - id/order/product/revision/attempt -> `<id>`
    - path hoặc endpoint nếu quá cụ thể -> `<path>`
    - version như `v3.1` -> `<version>`
  - Không thay các từ khóa kỹ thuật quan trọng như `ConnectionPool`, `timeout`, `pool exhausted`, `OutOfMemoryError`, `TLS`, `DNS`, `replica lag`.

- Cách tạo template:
  - Dùng Drain3 làm parser chính để gom raw logs thành template ổn định.
  - Trước khi đưa log vào Drain3, vẫn phải normalize số/id/path/duration/percent/version để tránh template explosion.
  - Cấu hình Drain3 theo hướng bảo thủ: không tách quá vụn các log chỉ khác tham số động, nhưng cũng không gộp các message khác bản chất lỗi.
  - Fallback rule-based chỉ dùng khi môi trường thiếu dependency Drain3; output fallback vẫn phải giữ cùng schema.
  - Template cuối cùng nên đủ giống historical signatures, ví dụ:
    - Raw: `ConnectionPool: timeout acquiring connection (waited 5000ms) attempt=7092`
    - Template: `ConnectionPool: timeout acquiring connection (waited <duration>) attempt=<id>`
    - Match được history signature: `ConnectionPool: timeout acquiring connection`

- Quy trình Drain3 trong lab:
  - Input cho Drain3 là message đã normalize, không phải raw `msg` nguyên bản.
  - Parser chạy trên từng incident độc lập để tạo `template_id`, `template` và params cho từng dòng log.
  - Sau khi Drain3 sinh template, group theo `svc`, `level`, `template_id` để tính `count`, `first_seen`, `last_seen`, `burst_score`.
  - Lưu `raw_index` và `raw_examples` để truy ngược lại dòng log gốc trong `incident_json`.

- Feature log theo template:
  - `template_id`: hash ổn định của normalized template.
  - `template`: template readable.
  - `svc`: service phát log.
  - `level`: severity của log.
  - `count`: số lần xuất hiện trong incident.
  - `first_seen`, `last_seen`.
  - `burst_score`: mức tăng tập trung sau `detected_at`.
  - `history_match`: historical `log_signatures` nào match gần nhất.
  - `keyword_score`: điểm từ khóa lỗi như timeout, exhausted, OOM, TLS, DNS, 5xx, throttled, lag.

- Rule chọn log nghi vấn:
  - `level` là `ERROR` hoặc `WARN` được ưu tiên hơn `INFO`.
  - Template xuất hiện nhiều lần hoặc bùng lên sau alert.
  - Template match với historical `log_signatures`.
  - Template chứa keyword lỗi có ý nghĩa vận hành.
  - Service của log có metric anomaly tương ứng thì tăng score, nhưng chưa gom cluster ở bước này.
  - Log `INFO` chỉ được giữ nếu nó mô tả tín hiệu bất thường rõ, ví dụ `latency_p50 increasing trend`.

- Normalize log score:
  - `severity_score`, `frequency_score`, `burst_score`, `history_match_score`, `keyword_score`, `metric_link_score` đều phải nằm trong `0..1`.
  - `score` cuối cùng là score tổng hợp đã normalize.
  - Count thô, burst thô và keyword match chi tiết chỉ nằm trong `details`.

Ví dụ log evidence candidate:

```json
{
  "schema_version": "1.0",
  "evidence_id": "log:E01:payment-svc:tpl_8f31",
  "evidence_type": "log",
  "incident_id": "E01",
  "service": "payment-svc",
  "timestamp_start": "2026-06-10T14:20:01Z",
  "timestamp_end": "2026-06-10T14:28:50Z",
  "score": 0.94,
  "score_meaning": "0..1, càng cao càng đáng nghi",
  "summary": "ConnectionPool timeout lặp lại nhiều lần ở payment-svc",
  "signals": ["error_log", "template_burst", "history_signature_match"],
  "source_ref": {
    "system": "incident_json",
    "file": "eval/E01.json",
    "path": "logs",
    "raw_indices": [12, 18, 44]
  },
  "details": {
    "template_id": "tpl_8f31",
    "template": "ConnectionPool: timeout acquiring connection (waited <duration>) attempt=<id>",
    "level": "ERROR",
    "count": 84,
    "history_match": "ConnectionPool: timeout acquiring connection",
    "keyword_score": 0.95,
    "raw_examples": [
      "ConnectionPool: timeout acquiring connection (waited 5000ms) attempt=7092"
    ]
  }
}
```

## Cách Tính Điểm Nghi Vấn Cho Log

- `severity_score`:
  - `ERROR = 1.0`
  - `WARN = 0.6`
  - `INFO = 0.2`

- `frequency_score`:
  - Dựa trên `count` của template trong incident.
  - Dùng log scale để template 100 dòng không áp đảo hoàn toàn template 20 dòng.

- `burst_score`:
  - So sánh số log trước và sau `detected_at`.
  - Template chỉ tăng sau alert thì đáng nghi hơn template nền ổn định.

- `history_match_score`:
  - Cao nếu template chứa hoặc gần giống `log_signatures` trong history.
  - Có thể dùng substring/token overlap trước, chưa cần embedding.

- `metric_link_score`:
  - Cao nếu cùng service có metric anomaly mạnh.
  - Nếu service không có metric series nhưng log rất mạnh, vẫn giữ candidate.

Công thức gợi ý:

```text
log_suspicion_score =
  0.25 * severity_score +
  0.20 * frequency_score +
  0.20 * burst_score +
  0.25 * history_match_score +
  0.10 * metric_link_score
```

## Quan Hệ Giữa Metrics Và Logs Trong Bước Này

- Metrics trả lời câu hỏi: service/metric nào có hành vi bất thường về số liệu.
- Logs trả lời câu hỏi: service nào phát sinh thông điệp lỗi nào, template nào lặp lại bất thường.
- Ở bước này chỉ liên kết nhẹ bằng `details.linked_metric_anomalies` hoặc signal như `metric_linked`, chưa gom thành cluster.
- Bước correlation sau chỉ cần đọc envelope chung:
  - `evidence_type`
  - `service`
  - `timestamp_start`
  - `timestamp_end`
  - `score`
  - `signals`
  - `source_ref`
- Khi cần giải thích sâu, bước sau mới mở `details`.

Ví dụ:

- E01: `payment-svc.latency_p99_ms` tăng, logs `ConnectionPool timeout` và `pool exhausted` ở `payment-svc` nên log candidates của `payment-svc` được ưu tiên.
- E03: `esb.mem_mb` và `esb.gc_pause_ms` tăng, logs `OutOfMemoryError` và `GC pause` ở `esb` nên nghi vấn mạnh.
- E07: logs ở `inventory-svc` rất mạnh nhưng pattern lạ; bước sau có thể dùng để quyết định OOD/escalate.
- E08: metric root nằm ở `t24-service`, logs lỗi lan qua `esb`, `datapower`, `bb-edge`; bước này chỉ xuất các candidate riêng, chưa quyết định cascade/root.

## Artifact Nên Lưu

- `evidence_candidates.json`:
  - Artifact chính cho bước sau.
  - Chứa cả metric evidence và log evidence trong cùng một list.
  - Mỗi item tuân theo schema `evidence candidate`.

- `metric_anomalies.json`:
  - Artifact phụ để debug metric detector.
  - Có score, direction, delta/ratio, baseline stats.
  - Có thể giữ cùng schema evidence candidate hoặc giữ bản chi tiết riêng.

- `parsed_logs.jsonl`:
  - Một dòng cho mỗi raw log sau parsing.
  - Có `template_id`, `template`, `params`, `svc`, `level`, `ts`, `raw_index`.

- `suspicious_logs.json`:
  - Artifact phụ để debug log parser.
  - Danh sách template/service nghi vấn đã rank.
  - Nội dung nên tương thích hoặc có thể chuyển trực tiếp sang `evidence_candidates.json`.

Ví dụ artifact chính:

```json
{
  "schema_version": "1.0",
  "incident_id": "E01",
  "evidence_candidates": [
    {
      "schema_version": "1.0",
      "evidence_id": "metric:E01:payment-svc.latency_p99_ms",
      "evidence_type": "metric",
      "incident_id": "E01",
      "service": "payment-svc",
      "timestamp_start": "2026-06-10T14:08:00Z",
      "timestamp_end": "2026-06-10T15:22:15Z",
      "score": 0.91,
      "score_meaning": "0..1, càng cao càng đáng nghi",
      "summary": "payment-svc latency_p99_ms tăng mạnh so với baseline",
      "signals": ["metric_increase", "latency_anomaly", "post_alert"],
      "source_ref": {
        "system": "incident_json",
        "file": "eval/E01.json",
        "path": "metrics_window.samples.payment-svc.latency_p99_ms"
      },
      "details": {
        "metric": "latency_p99_ms",
        "series_key": "payment-svc.latency_p99_ms",
        "direction": "increase"
      }
    }
  ]
}
```

## Tiêu Chí Hoàn Thành

- Với mỗi eval incident, tạo được `evidence_candidates` chứa cả metric candidates và log candidates.
- Metrics và logs dùng chung envelope, khác biệt đặc thù nằm trong `details`.
- Mọi `score` đều normalize về `0..1` và cùng nghĩa là “càng cao càng đáng nghi”.
- Mọi evidence đều có `schema_version` và `source_ref` để truy ngược dữ liệu gốc trong incident JSON.
- Log candidates không còn phụ thuộc vào raw message đầy đủ, mà dựa trên template.
- Các log nhiễu như request accepted, stock check bình thường phải có score thấp.
- Các log lỗi rõ như `pool exhausted`, `OutOfMemoryError`, `TLS handshake failed`, `DNS NXDOMAIN`, `API throttled`, `replica lag` phải nổi lên top.
- Output có đủ thông tin để bước correlation sau này nối theo `service`, `timestamp_start`, `timestamp_end`, `evidence_type`, `score`, `signals`, `source_ref`.
