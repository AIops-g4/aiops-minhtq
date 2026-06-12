# Slide Content - Evidence-Driven Remediation

## Tổng Quan Pipeline

Mục tiêu project là xây dựng một AIOps remediation engine chạy local bằng Python CLI. Engine nhận một incident JSON gồm metrics, logs, traces và topology; sau đó trả về một remediation action có confidence score và evidence chain có thể audit.

Pipeline:

```text
Incident JSON
-> 001 Detection & Triage
-> 002 Alert Correlation
-> 003 RCA RRF Ranking
-> 004 LLM Remediation Decision
-> Decision JSON + audit.jsonl
```

Nguyên tắc thiết kế:
- Không map trực tiếp `root_cause_class` sang action.
- Không xem `trigger_alert.service` là culprit mặc định; service phát alert có thể chỉ là victim.
- Logs và traces là first-class signals, không chỉ dựa vào metrics.
- Nếu evidence mới, yếu hoặc không đủ an toàn thì escalate bằng `page_oncall`.
- Mọi output đều giữ evidence chain để truy vết: `evidence_id`, `source_ref`, score, signals và audit fields.

Cách đọc culprit/victim trong project:
- **Culprit**: service gây ra lỗi gốc, là target chính của RCA/remediation.
- **Victim**: service bị ảnh hưởng và có thể phát alert/log/metric anomaly, nhưng không nhất thiết là nguyên nhân gốc.
- Ví dụ: `payment-svc` pool exhausted làm `checkout-svc` latency tăng. Khi đó `payment-svc` là culprit, `checkout-svc` là victim.

---

## Feature 001 - Detection & Triage

### Vai Trò

Chuyển raw incident evidence thành danh sách evidence candidates đã chuẩn hóa và chấm điểm. Đây là lớp phát hiện tín hiệu bất thường đầu tiên của pipeline.

### Input

Nguồn input là một live incident JSON từ `data-pack/eval/E*.json`.

Các trường chính:
- `incident_id`: định danh incident hiện tại, ví dụ `E01`. Biến này giúp toàn bộ pipeline join đúng detection, correlation, RCA, decision và audit artifacts về cùng một sự cố. Về sau, khi cần debug hoặc replay incident, chỉ cần dùng `incident_id` để truy toàn bộ evidence chain.
- `detected_at`: mốc thời gian alert được phát hiện, ví dụ `2026-06-10T14:23:00Z`. Hiện tại dùng để tách baseline và post-alert window; về sau giúp RCA biết tín hiệu nào xảy ra trước/sau alert, tránh nhầm noise trước incident với dấu hiệu victim bị ảnh hưởng thật.
- `trigger_alert.service`: service phát alert ban đầu, ví dụ `checkout-svc`. Biến này chỉ là điểm bắt đầu điều tra, không được xem là culprit. Về sau nó giúp so sánh RCA top service với alert service, từ đó phát hiện quan hệ victim/culprit như `checkout-svc` bị ảnh hưởng bởi `payment-svc`.
- `trigger_alert.rule_id`: loại alert ban đầu, ví dụ `latency_p99_high`. Hiện tại giúp gắn ngữ cảnh cho metric/log scoring; về sau có thể dùng để ưu tiên loại evidence liên quan, ví dụ latency alert thì chú ý trace latency và timeout logs.
- `metrics_window.samples`: time series theo key `service.metric`, ví dụ `payment-svc.latency_p99_ms`. Hiện tại dùng để tính anomaly; về sau dùng lại cho timestamp ranker và causal-lag ranker trong RCA.
- `logs`: log raw gồm `ts`, `svc`, `level`, `msg`. Hiện tại dùng để mining log template; về sau template này được dùng cho historical retrieval và LLM evidence explanation.

Biến/trường xử lý metrics:
- `service`, `metric`: tách từ key `service.metric`, ví dụ `payment-svc.latency_p99_ms` thành `service = payment-svc`, `metric = latency_p99_ms`. Hiện tại giúp gom evidence theo service; về sau là join key cho correlation, RCA và action params.
- `baseline_mean`, `baseline_std`, `baseline_median`, `baseline_mad`: thống kê hành vi bình thường trước alert. Hiện tại là nền để tính anomaly; về sau giúp giải thích vì sao một metric bị xem là bất thường, ví dụ latency tăng từ baseline `417ms` lên gần `1966ms`.
- `post_mean`, `start_value`, `end_value`, `min_value`, `max_value`: mô tả trạng thái sau alert và biên độ toàn window. Hiện tại giúp phát hiện spike/drift; về sau giúp LLM hoặc SRE đọc nhanh mức độ nghiêm trọng mà không cần xem raw time series.
- `absolute_delta`, `ratio`, `slope`: mô tả hướng và tốc độ thay đổi của metric.
  - `absolute_delta = end_value - baseline_mean`. Nếu dương thì metric tăng so với baseline, nếu âm thì metric giảm. Ví dụ latency baseline `417ms`, end value `1966ms` thì `absolute_delta ~= 1549ms`, cho thấy degradation rất mạnh.
  - `ratio = end_value / baseline_mean` với safe divide. Ví dụ `1966 / 417 ~= 4.71`, nghĩa là latency cuối window cao hơn baseline khoảng 4.7 lần. Biến này giúp so sánh mức tăng tương đối giữa các metric khác đơn vị, như CPU `%` và latency `ms`.
  - `slope = (last_value - first_value) / (number_of_samples - 1)`. Đây là tốc độ thay đổi trung bình trên mỗi sample. Slope lớn và cùng chiều xấu cho thấy metric không chỉ spike một điểm mà đang drift/degrade kéo dài.
  - Trong scoring hiện tại, `ratio_signal = abs(ratio - 1.0)` và `slope_signal = abs(slope) / abs(baseline_mean)` được đưa vào anomaly score. Về sau timestamp ranker và RCA có thể dùng slope/shift để xác định service nào bắt đầu degrade sớm hơn, hỗ trợ phân biệt culprit với victim.
- `post_alert_peak_z`, `post_alert_low_z`, `robust_z`: đo độ lệch của metric so với baseline theo thang chuẩn hóa.
  - `post_alert_peak_z = (post_peak - baseline_mean) / baseline_std`. Biến này bắt spike tăng sau alert. Hữu ích với metric “xấu khi tăng” như latency, error rate, CPU, memory.
  - `post_alert_low_z = (post_low - baseline_mean) / baseline_std`. Biến này bắt drop mạnh sau alert. Hữu ích với metric “xấu khi giảm” như availability, success rate, throughput nếu hệ thống có loại metric đó.
  - `robust_z = (end_value - baseline_median) / (1.4826 * baseline_mad)`. Đây là z-score robust dùng median/MAD thay vì mean/std, nên ít bị lệch nếu baseline có vài điểm outlier.
  - Trong scoring hiện tại, hệ thống lấy directional z theo hướng metric xấu đi, rồi so cùng `robust_z`, drift, ratio và slope để tạo `score` trong `[0, 1]`. Nhờ các z-score này, ranking có thể so sánh CPU, latency, error rate, memory trên cùng một thang đo thay vì phụ thuộc đơn vị gốc.

Biến/trường xử lý logs:
- `template_id`, `template`: log template sau khi normalize token động, ví dụ `ConnectionPool: timeout acquiring connection (waited <duration>) attempt=<id>`. Hiện tại giúp gom các log cùng pattern; về sau dùng làm fingerprint để retrieval tìm incident lịch sử tương tự dù ID/request khác nhau.
- `svc`, `level`, `count`: service, severity và tần suất, ví dụ `payment-svc`, `ERROR`, `84`. Hiện tại dùng để chấm log suspicion; về sau giúp decision layer phân biệt signal mạnh như nhiều `ERROR` với background `INFO`.
- `first_seen`, `last_seen`: khoảng thời gian template xuất hiện. Hiện tại dùng để tính burst; về sau giúp correlation đặt log vào đúng time cluster và RCA so sánh thứ tự xuất hiện giữa services.
- `burst_score`, `keyword_score`, `metric_link_score`: điểm thành phần của log. Hiện tại giúp score minh bạch hơn; về sau giúp giải thích vì sao log được chọn, ví dụ log có keyword `pool exhausted` và trùng service với metric anomaly nên đáng tin hơn.
- `severity_score`, `frequency_score`: `severity_score` đến từ log level như ERROR/WARN/INFO, còn `frequency_score` tăng khi template xuất hiện nhiều. Hai biến này là nguyên liệu trực tiếp của `log_score` ở slide score.
- `raw_indices`, `raw_examples`: vị trí và ví dụ log raw. Hiện tại phục vụ audit; về sau giúp SRE/LLM kiểm tra evidence gốc mà không phải quét toàn bộ log.

Ví dụ biến metric/log sau khi xử lý:

```json
{
  "service": "payment-svc",
  "metric": "latency_p99_ms",
  "baseline_mean": 417.47,
  "end_value": 1966.72,
  "ratio": 4.71,
  "post_alert_peak_z": 137.78,
  "template": "ConnectionPool: timeout acquiring connection (waited <duration>) attempt=<id>",
  "count": 84,
  "keyword_score": 0.85
}
```

### Output

Output của Feature 001 là một object chuẩn hóa để Feature 002 đọc trực tiếp:

```json
{
  "schema_version": "1.0",
  "incident_id": "E01",
  "evidence_candidates": []
}
```

Ý nghĩa tổng thể:
- `schema_version`: version contract của detection output, giúp stage sau đọc đúng format.
- `incident_id`: incident đã được normalize theo file eval, ví dụ `E01`.
- `evidence_candidates`: danh sách signals đáng nghi đã được chuẩn hóa từ metric branch và log branch.

Mỗi candidate đại diện cho **một evidence đáng nghi**:
- Metric candidate: một service/metric bất thường, ví dụ `payment-svc.latency_p99_ms`.
- Log candidate: một service/log template bất thường, ví dụ connection pool timeout trên `payment-svc`.
- Candidate không phải final root cause và không phải action. Nó chỉ là một signal đã có score và có thể audit.

Mỗi `evidence_candidates[]` có các field:
- `evidence_id`: ID duy nhất, ví dụ `metric:E01:payment-svc.cpu`. Hiện tại dùng để tránh trùng evidence; về sau correlation, RCA và audit dùng ID này để chỉ chính xác evidence nào dẫn tới quyết định.
- `evidence_type`: `metric` hoặc `log`. Hiện tại giúp xử lý đúng loại evidence; về sau LLM prompt có thể trình bày metric/log theo cách khác nhau.
- `service`: service liên quan. Đây là join key quan trọng cho topology grouping, RCA candidate và action target.
- `detected_at`, `timestamp_start`, `timestamp_end`: mốc phát hiện và range evidence. Hiện tại giúp time grouping; về sau hỗ trợ timeline RCA và incident narrative.
- `score`: điểm nghi vấn đã normalize trong `[0, 1]`. Hiện tại dùng để rank evidence; về sau correlation dùng `min_score`, RCA/LLM dùng top evidence thay vì toàn bộ noise.
- `score_meaning`: ý nghĩa của score. Giúp người đọc/audit hiểu score không phải confidence action mà là mức suspiciousness của evidence.
- `summary`: tóm tắt evidence. Hiện tại giúp debug; về sau có thể đưa thẳng vào LLM prompt hoặc slide incident summary.
- `signals`: tag giải thích như `metric_spike`, `latency_anomaly`, `pool_anomaly`. Hiện tại dùng để hiểu vì sao evidence đáng nghi; về sau dùng cho dominant signals, historical retrieval và guardrails.
- `source_ref`: đường dẫn ngược về incident JSON. Đây là bằng chứng truy xuất nguồn gốc, giúp audit quyết định không bị “black box”.
- `details`: thông tin debug và feature riêng của metric/log. Về sau các module có thể lấy `details.metric` hoặc `details.template_id` để tạo fingerprint ổn định.

Cách các field được dùng ở stage sau:
- Feature 002 Correlation dùng `score`, `service`, `detected_at`, `timestamp_start/end`, `evidence_id`.
- Feature 003 RCA dùng `service`, `evidence_id`, `signals`, `details.metric`.
- Feature 004 Decision/LLM dùng `summary`, `signals`, `source_ref`, `details.template_id`, `details.raw_examples`.

Ví dụ evidence candidate:

```json
{
  "evidence_id": "log:E01:payment-svc:0b879767bd",
  "evidence_type": "log",
  "service": "payment-svc",
  "score": 0.8242,
  "signals": ["log_template", "log_level_error", "pool_anomaly", "timeout_anomaly", "metric_linked"],
  "summary": "payment-svc emitted 84 ERROR logs matching connection pool timeout",
  "source_ref": {
    "system": "incident_json",
    "path": "logs"
  },
  "details": {
    "template_id": "b0454ec747",
    "count": 84
  }
}
```

Với ví dụ trên, `signals` được sinh như sau:
- `log_template`: log raw đã được normalize và group thành template.
- `log_level_error`: field `level` của log là `ERROR`.
- `pool_anomaly`: template chứa token như `ConnectionPool`, `pool`, hoặc `exhausted`.
- `timeout_anomaly`: template chứa keyword `timeout`.
- `metric_linked`: service `payment-svc` cũng có metric anomaly trong cùng incident, nên log evidence được tăng độ tin cậy.

### Logic Xử Lý

Luồng tổng của Feature 001:

```text
incident JSON
-> parse metrics_window.samples + logs
-> split into 2 parallel branches:
   |-> metric anomaly branch
   |-> log template anomaly branch
-> merge + sort evidence_candidates
-> output JSON cho correlation/RCA
```

Feature này có 2 nhánh xử lý song song: metric detection và log detection. Hai nhánh cùng nhận dữ liệu từ incident JSON, chạy độc lập theo logic riêng, rồi mới merge ở cuối. Vì vậy không hiểu là metric branch chạy xong rồi log branch mới chạy; điểm chung duy nhất là cả hai đều emit cùng một schema `EvidenceCandidate`.

#### Score được tính như thế nào?

`score` trong Feature 001 là **độ đáng nghi của evidence**, không phải confidence của remediation action. Score này được normalize về `[0, 1]` để Feature 002 có thể dùng `min_score` filter bớt noise.

Metric score và log score được tính khác nhau:

```text
Metric score:
raw_score = max(
  abs(directional_z) / 8,
  abs(robust_z) / 10,
  drift / 6,
  abs(ratio - 1) / 2.5,
  slope_signal * 20
)
score = clamp01(raw_score + operational_metric_bonus)
```

Ý nghĩa:
- Metric score lấy tín hiệu anomaly mạnh nhất, vì một incident có thể biểu hiện bằng spike, drift, ratio tăng mạnh hoặc robust z-score lớn.
- Dùng `max(...)` để không bỏ sót metric chỉ bất thường theo một chiều tín hiệu.
- Operational metric như latency, error rate, memory, pool, replica lag được cộng bonus nhỏ vì các metric này có ý nghĩa vận hành cao.

```text
Log score =
  0.25 * severity_score +
  0.20 * frequency_score +
  0.20 * burst_score +
  0.25 * keyword_score +
  0.10 * metric_link_score
```

Ý nghĩa:
- Log score là weighted sum vì log anomaly thường là tổng hợp của nhiều yếu tố.
- `severity_score` cho biết ERROR/WARN/INFO nặng nhẹ ra sao.
- `frequency_score` và `burst_score` cho biết pattern có lặp nhiều và dồn dập không.
- `keyword_score` bắt keyword vận hành như timeout, pool exhausted, DNS, TLS, OOM.
- `metric_link_score` tăng độ tin cậy nếu service có log bất thường đồng thời cũng có metric anomaly.

Sau khi tính score:
- Metric evidence yếu sẽ bị bỏ qua ở Feature 001 nếu score dưới ngưỡng detector.
- Log evidence yếu cũng bị bỏ qua nếu score dưới ngưỡng log detector.
- Evidence còn lại đi sang Feature 002, nơi correlation tiếp tục dùng `min_score` để filter trước khi group cluster.

#### Signals được gán như thế nào?

`signals` là các tag rule-based để giải thích evidence thuộc loại bất thường nào. Khác với `score`, signals không phải số; chúng là nhãn để correlation, RCA, retrieval và guardrails hiểu ý nghĩa vận hành của evidence.

Metric signals:

```text
signals = [
  "metric_increase" hoặc "metric_decrease",
  anomaly_type_from_metric_name,
  "metric_spike",
  "post_alert"
]
```

Cách gán:
- Nếu `absolute_delta >= 0` thì thêm `metric_increase`, ngược lại thêm `metric_decrease`.
- Nhìn token trong tên metric để gán anomaly type:
  - chứa `latency` -> `latency_anomaly`
  - chứa `error` -> `error_rate_anomaly`
  - chứa `memory` hoặc `gc` -> `memory_anomaly`
  - chứa `pool` -> `pool_anomaly`
  - chứa `lag` -> `replication_lag_anomaly`
  - chứa `tls` -> `tls_anomaly`
  - chứa `dns` -> `dns_anomaly`
  - chứa `throttle` -> `throttling_anomaly`
- Thêm `metric_spike` vì evidence được emit khi metric có mức anomaly đủ mạnh.
- Thêm `post_alert` để đánh dấu signal nằm trong context sau alert.

Ví dụ:

```text
metric = payment-svc.latency_p99_ms
absolute_delta > 0
=> signals = [
  "metric_increase",
  "latency_anomaly",
  "metric_spike",
  "post_alert"
]
```

Log signals:

```text
signals = [
  "log_template",
  "log_level_<level>",
  keyword_signals,
  optional "metric_linked"
]
```

Cách gán:
- Luôn thêm `log_template` vì log đã được normalize và group theo template.
- Thêm log level signal:
  - `ERROR` -> `log_level_error`
  - `WARN` -> `log_level_warn`
  - `INFO` -> `log_level_info`
- Nhìn keyword trong template để gán anomaly type:
  - `pool`, `connectionpool`, `exhausted` -> `pool_anomaly`
  - `timeout` -> `timeout_anomaly`
  - `outofmemory`, `oom` -> `memory_anomaly`
  - `tls`, `x509`, `certificate` -> `tls_anomaly`
  - `dns`, `nxdomain` -> `dns_anomaly`
  - `throttl` -> `throttling_anomaly`
  - `replica lag`, `lag` -> `replication_lag_anomaly`
- Nếu service của log cũng có metric anomaly thì thêm `metric_linked`.

Ví dụ:

```text
template = "ConnectionPool: timeout acquiring connection ..."
level = ERROR
service = payment-svc, service này có metric anomaly
=> signals = [
  "log_template",
  "log_level_error",
  "pool_anomaly",
  "timeout_anomaly",
  "metric_linked"
]
```

#### 1. Metric anomaly branch

Input chính:
- `metrics_window.samples`
- `detected_at`
- `incident_id`
- `source_file`

Logic chi tiết:
1. Duyệt từng time series trong `metrics_window.samples`.
   - Key có dạng `service.metric`, ví dụ `payment-svc.latency_p99_ms`.
   - Tách thành `service = payment-svc`, `metric = latency_p99_ms`.
   - Ý nghĩa: `service` là join key cho correlation/RCA/action; `metric` giúp gán signal đúng loại như latency, CPU, memory.

2. Chuẩn hóa sample.
   - Sort samples theo timestamp.
   - Convert value sang float.
   - Giữ timestamp đầu/cuối để điền `timestamp_start`, `timestamp_end`.
   - Ý nghĩa: mọi phép tính delta, slope, z-score đều cần sample theo đúng thứ tự thời gian.

3. Tách baseline và post-alert bằng `detected_at`.
   - Baseline = samples trước `detected_at`.
   - Post-alert = samples sau hoặc tại `detected_at`.
   - Nếu baseline quá ít, fallback dùng khoảng 30% đầu của window làm baseline.
   - Ý nghĩa: baseline đại diện cho trạng thái bình thường; post-alert là vùng cần kiểm tra degradation.

4. Tính thống kê baseline và post-alert.
   - Baseline: `baseline_mean`, `baseline_std`, `baseline_median`, `baseline_mad`.
   - Post/full window: `post_mean`, `start_value`, `end_value`, `min_value`, `max_value`.
   - Ý nghĩa: các biến này giải thích được vì sao một metric bị coi là abnormal, không chỉ trả về score cuối.

5. Tính các feature mô tả mức thay đổi.
   - `absolute_delta = end_value - baseline_mean`.
   - `ratio = end_value / baseline_mean`.
   - `slope = (last_value - first_value) / (number_of_samples - 1)`.
   - `post_alert_peak_z = (post_peak - baseline_mean) / baseline_std`.
   - `post_alert_low_z = (post_low - baseline_mean) / baseline_std`.
   - `robust_z = (end_value - baseline_median) / (1.4826 * baseline_mad)`.
   - Ý nghĩa: delta cho biết đổi bao nhiêu, ratio cho biết gấp mấy lần, slope cho biết xấu đi nhanh hay chậm, z-score giúp so sánh các metric khác đơn vị trên cùng thang.

6. Xác định hướng xấu của metric.
   - Với latency, error rate, CPU, memory, pool usage: tăng thường là xấu.
   - Với các metric kiểu availability/success rate nếu có: giảm mới là xấu.
   - Hệ thống lấy `directional_z` theo hướng metric xấu đi.
   - Ý nghĩa: không phải mọi metric tăng đều xấu và không phải mọi metric giảm đều tốt.

7. Tính metric anomaly score.
   - Score lấy tín hiệu mạnh nhất từ directional z, robust z, drift, ratio signal và slope signal.
   - Công thức logic trong implementation:

```text
raw_score = max(
  abs(directional_z) / 8,
  abs(robust_z) / 10,
  drift / 6,
  abs(ratio - 1) / 2.5,
  slope_signal * 20
)
```

   - Nếu metric là operational metric như latency, error rate, memory, pool, replica lag thì cộng thêm bonus nhỏ.
   - Sau đó clamp score về `[0, 1]`.
   - Ý nghĩa: score phản ánh mức suspiciousness của metric, không phải confidence của action.

8. Gán metric signals.
   - Signals được gán theo direction, token trong tên metric và context post-alert.
   - Ví dụ: `metric_increase`, `metric_decrease`, `metric_spike`, `latency_anomaly`, `memory_anomaly`, `pool_anomaly`, `post_alert`.
   - Ý nghĩa: signals giúp stage sau hiểu loại bất thường mà không cần đọc lại raw metric.

9. Emit metric evidence candidate nếu score đủ cao.
   - `evidence_type = metric`.
   - `evidence_id = metric:{incident_id}:{service.metric}`.
   - `details` chứa toàn bộ biến tính toán như baseline, delta, ratio, z-score.
   - Ý nghĩa: metric evidence vừa có score để ranking, vừa có details để audit và giải thích.

Ví dụ luồng metric cho E01:

```text
payment-svc.latency_p99_ms
baseline_mean ~= 417ms
end_value ~= 1966ms
ratio ~= 4.71
post_alert_peak_z ~= 137.78
=> score cao
=> signals: metric_increase, latency_anomaly, metric_spike, post_alert
=> emit metric:E01:payment-svc.latency_p99_ms
```

#### 2. Log template anomaly branch

Input chính:
- `logs`
- `detected_at`
- `metric_services`: tập service đã có metric anomaly
- `incident_id`
- `source_file`

Logic chi tiết:
1. Duyệt từng log line.
   - Đọc `ts`, `svc`, `level`, `msg`.
   - Giữ index của raw log để đưa vào `raw_indices`.
   - Ý nghĩa: raw index giúp truy ngược evidence về log gốc khi audit.

2. Normalize log message thành template.
   - Number -> `<num>`.
   - Duration như `5000ms`, `12s` -> `<duration>`.
   - Percent -> `<percent>`.
   - ID/order ID/product ID/attempt -> `<id>`.
   - Path/endpoint -> `<path>`.
   - Version như `v3.1` -> `<version>`.
   - Giữ keyword vận hành như `timeout`, `pool exhausted`, `OutOfMemoryError`, `TLS`, `DNS`, `NXDOMAIN`, `replica lag`.
   - Ý nghĩa: gom các log cùng pattern dù giá trị động khác nhau, đồng thời không làm mất keyword quan trọng cho RCA/decision.

3. Group log theo `(svc, level, template)`.
   - Ví dụ nhiều dòng:

```text
ConnectionPool: timeout acquiring connection (waited 5000ms) attempt=3321
ConnectionPool: timeout acquiring connection (waited 5000ms) attempt=2155
```

   - Sau normalize thành cùng template:

```text
ConnectionPool: timeout acquiring connection (waited <duration>) attempt=<id>
```

   - Ý nghĩa: thay vì xem từng log riêng lẻ, hệ thống đánh giá pattern lặp lại.

4. Tính các feature của log group.
   - `count`: số log cùng template.
   - `first_seen`, `last_seen`: thời gian xuất hiện đầu/cuối.
   - `severity_score`: `ERROR = 1.0`, `WARN = 0.6`, `INFO = 0.2`.
   - `frequency_score`: tăng khi template xuất hiện nhiều.
   - `burst_score`: tăng khi log xuất hiện dồn dập trong thời gian ngắn.
   - `keyword_score`: tăng nếu template chứa keyword vận hành nghiêm trọng như timeout, pool, OOM, DNS, TLS.
   - `metric_link_score`: bằng `1.0` nếu service cũng có metric anomaly, ngược lại `0.0`.
   - Ý nghĩa: log đáng nghi hơn khi vừa nghiêm trọng, vừa lặp nhiều, vừa burst, vừa có keyword vận hành, vừa trùng service có metric abnormal.

5. Tính log suspicion score.
   - Công thức scoring:

```text
log_score =
  0.25 * severity_score +
  0.20 * frequency_score +
  0.20 * burst_score +
  0.25 * keyword_score +
  0.10 * metric_link_score
```

   - Nếu score dưới ngưỡng thì bỏ qua để giảm noise.
   - Ý nghĩa: score có thể giải thích theo thành phần, không phải heuristic mơ hồ.

6. Gán log signals.
   - Luôn có `log_template` và `log_level_<level>`.
   - Thêm signal theo keyword như `timeout_anomaly`, `pool_anomaly`, `dns_anomaly`, `tls_anomaly`, `oom_anomaly`.
   - Nếu có metric link thì thêm `metric_linked`.
   - Ý nghĩa: các signal này về sau thành `dominant_signals` trong cluster và guardrail hint trong decision.

7. Emit log evidence candidate nếu score đủ cao.
   - `evidence_type = log`.
   - `evidence_id = log:{incident_id}:{service}:{stable_id}`.
   - `details` chứa `template_id`, `template`, `count`, `first_seen`, `last_seen`, score thành phần, `raw_indices`, `raw_examples`.
   - Ý nghĩa: log evidence vừa có fingerprint ổn định cho retrieval, vừa có raw examples để người vận hành kiểm tra.

Ví dụ luồng log cho E01:

```text
payment-svc ERROR logs
raw msg: ConnectionPool timeout acquiring connection waited 5000ms attempt=3321
template: ConnectionPool: timeout acquiring connection (waited <duration>) attempt=<id>
count: 84
keyword_score: timeout/pool high
metric_link_score: 1.0 vì payment-svc cũng có metric anomaly
=> score ~= 0.8242
=> emit log:E01:payment-svc:0b879767bd
```

#### 3. Merge và chuẩn hóa output

Sau khi metric branch và log branch chạy xong:
1. Gộp metric candidates và log candidates vào cùng `evidence_candidates[]`.
2. Sort/rank theo `score` giảm dần để evidence nghiêm trọng nằm trên.
3. Đảm bảo mọi candidate có cùng envelope:
   - `schema_version`
   - `evidence_id`
   - `evidence_type`
   - `incident_id`
   - `service`
   - `detected_at`
   - `timestamp_start`, `timestamp_end`
   - `score`
   - `summary`
   - `signals`
   - `source_ref`
   - `details`
4. Trả output cho Feature 002 Correlation.

Ý nghĩa của bước merge:
- Correlation không cần biết raw evidence đến từ metric hay log.
- RCA có thể dùng cùng `service`, `timestamp`, `score`, `evidence_id`.
- Decision/LLM có thể dùng `summary`, `signals`, `source_ref`, `details` để giải thích và audit.

### Ý Nghĩa Thiết Kế

Detection biến raw data nhiều định dạng thành một schema chung để các module sau xử lý thống nhất. Score được normalize về `[0, 1]` giúp correlation và RCA so sánh evidence công bằng. Log templating giúp so sánh theo pattern vận hành thay vì raw message, tránh nhiễu từ ID, duration hoặc version thay đổi liên tục.

---

## Feature 002 - Alert Correlation

### Vai Trò

Gom nhiều evidence candidates thành ít correlated alert clusters hơn, dựa trên độ gần về thời gian và quan hệ topology/trace. Đây là lớp giảm nhiễu từ nhiều alert rời rạc thành incident context.

### Input

Input gồm live incident JSON và detection output từ Feature 001.

Incident fields:
- `incident_id`: dùng để đảm bảo cluster output thuộc đúng incident. Về sau `cluster_id` sẽ embed `incident_id`, giúp RCA và audit trace ngược về sự cố gốc.
- `topology.nodes`: danh sách service trong static topology, ví dụ `edge-lb`, `checkout-svc`, `payment-svc`. Hiện tại dùng để tạo graph nền; về sau giúp phân biệt service liên quan thật với service chỉ xuất hiện do noise.
- `topology.edges`: quan hệ dependency giữa services, ví dụ `edge-lb -> checkout-svc -> payment-svc`. Hiện tại dùng để tính khoảng cách topology; về sau RCA dùng hướng caller/callee để suy luận downstream dependency.
- `traces`: runtime call edges gồm `from`, `to`, `count`, `error_count`, `p50_ms`, `p99_ms`. Hiện tại bổ sung quan hệ thực tế thiếu trong static topology; về sau hỗ trợ retrieval theo trace-edge overlap và RCA causal reasoning.

Detection fields:
- `schema_version`: version của detection schema. Về sau giúp các module đọc output cũ/mới an toàn hơn khi schema tiến hóa.
- `incident_id`: check consistency giữa incident và detection artifact. Về sau tránh lỗi dùng nhầm evidence của incident khác.
- `evidence_candidates`: danh sách alert-like records đã chuẩn hóa. Đây là input chính để correlation gom nhóm, không cần đọc lại raw metrics/logs.

Field dùng trong từng evidence:
- `evidence_id`: giữ assignment exactly-once, tức một evidence chỉ nằm trong một final cluster. Về sau RCA dùng lại ID này để giải thích candidate nào được evidence nào ủng hộ.
- `evidence_type`: giúp cluster summary cân bằng metric/log evidence, tránh chỉ nhìn một loại tín hiệu.
- `service`: node để group theo topology. Về sau `services[]` trong cluster trở thành candidate set ban đầu cho RCA.
- `detected_at`: time anchor để tạo session. Về sau giúp xây timeline incident và phân biệt các burst khác nhau.
- `timestamp_start`, `timestamp_end`: range thật của evidence. Hiện tại dùng tạo `time_range`; về sau hữu ích cho incident narrative, ví dụ “pool errors xuất hiện từ 14:08 đến 14:42”.
- `score`: dùng để lọc evidence dưới `min_score` và chọn `top_evidence`. Về sau giúp LLM chỉ nhận evidence mạnh, giảm prompt noise.
- `signals`: dùng để tổng hợp `dominant_signals`. Về sau decision guardrails có thể nhìn vào signal như `pool_anomaly`, `dns_anomaly`, `tls_anomaly`.
- `summary`: text ngắn để người đọc hiểu evidence trong cluster. Về sau có thể đưa trực tiếp vào prompt hoặc report.
- `details.metric`: tạo fingerprint ổn định cho metric, ví dụ `metric:payment-svc:latency_p99_ms`. Về sau giúp so sánh cluster hiện tại với historical metric signatures.
- `details.template_id`: tạo fingerprint ổn định cho log template, ví dụ `log:payment-svc:b0454ec747`. Về sau giúp deduplicate log pattern và retrieval incident tương tự.

Tham số correlation:
- `gap_sec = 300`: khoảng cách tối đa giữa 2 alert liên tiếp trong cùng time session. Giá trị này giúp gom các tín hiệu lệch pha vài phút giữa logs/metrics/traces; về sau có thể tune cho dữ liệu realtime dày hơn.
- `max_hop = 2`: khoảng cách topology tối đa để merge service. Giá trị này bắt được cascade gần như `edge-lb -> checkout-svc -> payment-svc` nhưng tránh kéo cả hệ thống vào một cluster.
- `min_score = 0.28`: ngưỡng giữ evidence. Hiện tại bảo toàn các evidence detection đã coi là hữu ích; về sau có thể tăng để giảm noise khi scale lên nhiều alert hơn.
- `time_anchor_field = detected_at`: field dùng làm mốc grouping theo thời gian. Giữ field này trong `params` giúp audit biết cluster được tạo bằng timeline nào.

### Output

Output object:

```json
{
  "schema_version": "1.0",
  "incident_id": "E01",
  "input_alerts": 9,
  "output_clusters": 1,
  "reduction_ratio": 0.8889,
  "params": {
    "gap_sec": 300,
    "max_hop": 2,
    "min_score": 0.28,
    "time_anchor_field": "detected_at"
  },
  "clusters": []
}
```

Mỗi `clusters[]` có:
- `cluster_id`: deterministic ID, ví dụ `corr:E01:s001:g001`. Về sau RCA dùng `cluster_id` để tạo ranking culprit theo từng cluster và audit không bị lệch thứ tự.
- `alert_count`: số evidence trong cluster. Hiện tại cho biết mức độ gom nhóm; về sau dùng để đánh giá reduction ratio và độ nhiễu của incident.
- `services`: danh sách service liên quan. Đây là candidate pool trực tiếp cho RCA.
- `time_range`: range từ evidence sớm nhất đến muộn nhất. Về sau giúp tạo timeline và giải thích incident kéo dài bao lâu.
- `max_score`, `mean_score`: độ nghi vấn tổng hợp của cluster. Hiện tại hỗ trợ triage cluster; về sau có thể dùng để ưu tiên cluster nào xử lý trước nếu một incident có nhiều cluster.
- `dominant_signals`: signals nổi bật trong cluster. Về sau decision layer dùng để chọn guardrail phù hợp, ví dụ `pool_anomaly` không nên auto-apply nếu RCA service không khớp.
- `fingerprints`: fingerprint ổn định như `metric:payment-svc:cpu`, `log:payment-svc:<template_id>`. Về sau rất hữu ích cho historical retrieval và dedup.
- `evidence_ids`: danh sách evidence gốc. Về sau RCA candidate và final decision có thể trỏ lại chính xác evidence gốc.
- `top_evidence`: top 5 evidence có score cao nhất. Về sau đưa vào LLM prompt để giảm noise mà vẫn giữ tín hiệu mạnh nhất.
- `topology_details`: `max_hop`, service-pair distance và trace edges được thêm. Về sau giúp audit vì sao hai service được gom cùng cluster.

Ví dụ cluster:

```json
{
  "cluster_id": "corr:E01:s001:g001",
  "alert_count": 9,
  "services": ["checkout-svc", "edge-lb", "payment-svc"],
  "time_range": ["2026-06-10T14:08:00Z", "2026-06-10T15:22:15Z"],
  "dominant_signals": ["metric_spike", "pool_anomaly", "timeout_anomaly"],
  "fingerprints": [
    "metric:payment-svc:latency_p99_ms",
    "log:payment-svc:b0454ec747"
  ],
  "evidence_ids": [
    "metric:E01:payment-svc.latency_p99_ms",
    "log:E01:payment-svc:0b879767bd"
  ],
  "topology_details": {
    "max_hop": 2,
    "service_distances": [{"from": "checkout-svc", "to": "payment-svc", "distance": 1}]
  }
}
```

Cách tạo các biến cluster và ý nghĩa:

- `cluster_id`: tạo theo format deterministic `corr:{incident_id}:s{session_idx}:g{group_idx}`. Field này giúp RCA, audit và diff output tham chiếu đúng cluster ngay cả khi chạy lại nhiều lần.
- `alert_count`: đếm số evidence candidates trong cluster. Field này cho biết cluster lớn hay nhỏ, và giúp đo mức giảm nhiễu từ nhiều evidence rời rạc.
- `services`: lấy unique service từ các evidence đã được merge theo time session và topology group. Field này trở thành candidate pool trực tiếp cho RCA, tức RCA chỉ tìm culprit trong scope này.
- `time_range`: lấy min `timestamp_start` và max `timestamp_end` của các evidence trong cluster. Field này giúp dựng timeline incident và giải thích burst kéo dài bao lâu.
- `max_score`, `mean_score`: tính từ score của các evidence trong cluster. Đây là suspiciousness summary của cluster, không phải action confidence.
- `dominant_signals`: đếm frequency của `signals` trong cluster rồi lấy signals nổi bật. Field này giúp decision/LLM hiểu pattern chính như `pool_anomaly`, `timeout_anomaly`, `dns_anomaly`, `tls_anomaly`.
- `fingerprints`: tạo từ stable detail của evidence:
  - Metric: `metric:{service}:{details.metric}`
  - Log: `log:{service}:{details.template_id}`
  - Ý nghĩa: dùng cho retrieval/dedup vì ổn định hơn raw timestamp, raw value hoặc raw log message.
- `evidence_ids`: danh sách `evidence_id` thuộc cluster. Đây là bridge từ cluster sang evidence gốc, giúp RCA và final decision audit được.
- `top_evidence`: lấy top evidence có score cao nhất trong cluster. Field này giúp LLM prompt gọn hơn vì không phải đưa toàn bộ evidence.
- `topology_details`: ghi `max_hop`, service-pair distances và trace edges được thêm vào graph. Field này giải thích vì sao các service được gom chung, tránh correlation trở thành black box.

### Logic Xử Lý

1. Lọc evidence có `score >= min_score`.
2. Parse `detected_at` làm time anchor, fallback sang `timestamp_start` nếu cần.
3. Sort evidence theo time anchor và `evidence_id`.
4. Tạo time session: alert liên tiếp cách nhau không quá `gap_sec` thì cùng session.
5. Trong mỗi session, build service graph từ `topology.edges`.
6. Thêm node từ topology, service trong evidence và trace endpoints.
7. Augment graph bằng live `traces` vì một số runtime services không có trong static topology.
8. Merge service nếu shortest-path distance `<= max_hop`.
9. Tạo cluster summary, fingerprints, `top_evidence` và `topology_details`.

### Ý Nghĩa Thiết Kế

Một incident thường tạo ra nhiều metric/log alert trên nhiều service. Nếu đưa từng alert riêng lẻ vào RCA hoặc LLM thì nhiều nhiễu và khó audit. Correlation dùng hai điều kiện có ý nghĩa vận hành: cùng burst thời gian và có liên hệ topology/trace. `max_hop = 2` đủ để bắt cascade như `edge -> checkout -> payment`, nhưng không gom cả hệ thống thành một cluster. Trace augmentation giúp không bỏ sót service chỉ xuất hiện ở runtime.

---

## Feature 003 - RCA RRF Ranking

### Vai Trò

Xếp hạng service có khả năng là culprit trong mỗi correlated cluster. Trong schema output, culprit này được lưu bằng các field RCA như `root_cause_rankings` hoặc `root_cause_service`; trên slide có thể diễn giải ngắn gọn là tìm culprit, chưa chọn remediation action.

### Input

Input gồm incident JSON, detection output và correlation output.

Incident fields:
- `incident_id`: giữ liên kết giữa RCA output và incident gốc. Về sau final decision dùng field này để ghi đúng `<ID>_decision.json` và `audit.jsonl`.
- `detected_at`: mốc tách baseline/post-alert. Hiện tại timestamp ranker dùng để tìm degradation sau alert; về sau giúp giải thích culprit/victim theo timeline.
- `topology.nodes`: danh sách service hợp lệ trong graph. Hiện tại dùng để build PageRank graph; về sau giúp tránh rank nhầm service không tồn tại trong hệ thống.
- `topology.edges`: hướng gọi service `caller -> callee`. Hiện tại dùng cho PageRank; về sau giúp giải thích downstream dependency, ví dụ payment lỗi làm checkout bị ảnh hưởng.
- `traces`: runtime edges có count/error/latency. Hiện tại augment graph và hỗ trợ causal signal; về sau decision/retrieval dùng trace-edge overlap để tìm incident lịch sử tương tự.
- `metrics_window.samples`: time series gốc. Hiện tại dùng cho timestamp và causal-lag ranker; về sau có thể mở rộng sang mô hình causal mạnh hơn mà không đổi contract upstream.

Detection fields:
- `schema_version`: đảm bảo RCA đọc đúng detection schema.
- `incident_id`: check consistency với incident và correlation.
- `evidence_candidates`: cung cấp score, timestamp, service, signals và evidence IDs. Về sau RCA candidate có thể trỏ lại evidence gốc thay vì chỉ trả service name.

Correlation fields:
- `schema_version`: đảm bảo RCA đọc đúng correlation schema.
- `incident_id`: check consistency giữa các stage.
- `clusters`: định nghĩa phạm vi RCA. RCA chỉ rank service trong từng cluster, tránh lấy service ngoài context làm culprit.

Tham số RCA:
- `rrf_k = 60`: hằng số làm mượt Reciprocal Rank Fusion. Hiện tại giảm chênh lệch quá mạnh giữa rank 1 và rank 2; về sau giúp ranking ổn định khi thêm ranker mới.
- `ranker_weights`: `pagerank = 0.40`, `timestamp = 0.35`, `causal_lag = 0.25`. Hiện tại phản ánh mức tin cậy tương đối của từng signal; về sau có thể tune theo domain mà không đổi output schema.
- `max_lag_samples = 8`: số sample lag tối đa khi so cross-correlation. Hiện tại giới hạn causal search window; về sau tránh overfit nếu time series dài hơn.
- `min_corr = 0.55`: ngưỡng correlation tối thiểu để chấp nhận causal-lag signal. Hiện tại lọc quan hệ yếu; về sau giúp warning rõ khi causal evidence không đủ mạnh.
- `degradation_z = 3.0`: ngưỡng z-score để coi metric đã degrade. Hiện tại dùng cho timestamp ranker; về sau có thể tune theo sensitivity của từng hệ thống.

### Output

Output object:

```json
{
  "schema_version": "1.0",
  "incident_id": "E01",
  "params": {},
  "root_cause_rankings": []
}
```

Mỗi cluster ranking có:
- `cluster_id`: cluster từ correlation. Về sau decision biết RCA ranking này thuộc đúng incident cluster nào.
- `services`: candidate services trong cluster. Đây là giới hạn an toàn để RCA không rank ngoài phạm vi evidence.
- `active_rankers`: ranker có đủ data để chạy. Về sau decision/LLM biết kết quả đang dựa trên bao nhiêu loại signal, ví dụ thiếu causal-lag thì nên thận trọng hơn.
- `confidence`: gồm `gap_ratio` và `level`. Về sau final decision dùng để giảm confidence hoặc escalate nếu top candidates quá sát nhau.
- `candidates`: danh sách service đã xếp hạng. Về sau action target thường lấy từ top candidate, nhưng vẫn giữ top-k để LLM/guardrail kiểm tra.
- `warnings`: lý do ranker bị skip hoặc input yếu. Về sau guardrails dùng warning để tránh auto-remediate khi RCA thiếu dữ liệu.

Mỗi candidate có:
- `rank`: thứ hạng sau RRF. Hiện tại xác định culprit candidate chính; về sau decision ưu tiên action target theo `rank = 1`.
- `service`: service candidate, ví dụ `payment-svc`. Đây là biến quan trọng để map sang action params như `rollback_service.service`.
- `rrf_score`: fused score từ các ranker. Hiện tại dùng để sort candidate; về sau có thể kết hợp với history/action vote để tính final confidence.
- `normalized_score`: score normalize theo top candidate. Về sau giúp LLM và slide dễ hiểu khoảng cách giữa các candidate mà không cần hiểu thang RRF.
- `ranker_ranks`: rank của service trong từng ranker. Về sau giúp giải thích sự đồng thuận, ví dụ service đứng #1 PageRank nhưng #2 timestamp.
- `ranker_scores`: raw score riêng của từng ranker để audit. Về sau hữu ích khi cần debug tại sao ranker cho kết quả lạ.
- `evidence_ids`: evidence ủng hộ service đó. Đây là bridge từ culprit candidate về raw evidence, dùng trực tiếp trong final decision `llm_evidence`.
- `explanation_signals`: tín hiệu giải thích như `high_pagerank_downstream_dependency`, `earliest_metric_degradation`, `metric_leads_related_service`. Về sau dùng làm natural-language rationale cho LLM/SRE.

Ví dụ RCA candidate:

```json
{
  "rank": 1,
  "service": "payment-svc",
  "rrf_score": 0.016235,
  "normalized_score": 1.0,
  "ranker_ranks": {
    "pagerank": 1,
    "timestamp": 2,
    "causal_lag": 2
  },
  "evidence_ids": [
    "metric:E01:payment-svc.latency_p99_ms",
    "log:E01:payment-svc:0b879767bd"
  ],
  "explanation_signals": [
    "high_pagerank_downstream_dependency",
    "earliest_metric_degradation"
  ]
}
```

### Logic Xử Lý

1. Lấy candidate set là `services` trong mỗi cluster.
2. Chạy PageRank trên directed graph `caller -> callee` từ topology và traces.
3. Chạy timestamp ranker để tìm service có degradation sớm nhất bằng metric z-score, fallback về earliest evidence timestamp.
4. Chạy causal-lag ranker bằng cross-correlation giữa anomaly series của các service.
5. Nếu causal-lag không đủ metric series thì skip và ghi warning.
6. Hợp nhất các ranker bằng Reciprocal Rank Fusion:

```text
rrf_score(service) = sum(weight_m * 1 / (rrf_k + rank_m(service)))
```

7. Sort candidate theo `rrf_score` giảm dần.
8. Tính confidence gap:

```text
gap_ratio = (score_top1 - score_top2) / score_top1
```

Confidence level:
- `high`: `gap_ratio > 0.30`
- `medium`: `0.10 <= gap_ratio <= 0.30`
- `low`: `gap_ratio < 0.10`

### Ý Nghĩa Thiết Kế

Culprit service không nên được xác định bằng một heuristic duy nhất. PageRank bắt dependency downstream, timestamp bắt service degrade sớm, causal-lag bắt khả năng một service lead service khác. Vì raw score của các ranker khác scale, hệ thống dùng Reciprocal Rank Fusion để kết hợp theo thứ hạng thay vì cộng raw score. Confidence gap giúp decision layer xử lý bảo thủ khi top candidates quá sát nhau.

---

## Feature 004 - LLM Remediation Decision

### Vai Trò

Chọn remediation action cuối cùng từ RCA, historical incidents, action catalog và optional LLM. Đây là lớp ra quyết định có guardrails và audit, không thực thi action thật.

### Input

CLI input:
- `--incident`: một incident JSON từ `data-pack/eval/E*.json`. Đây là input chính để chạy toàn bộ pipeline; về sau cùng CLI có thể replay incident cũ để so sánh decision trước/sau khi đổi model hoặc guardrail.
- `--history`: `data-pack/incidents_history.json`. Hiện tại dùng retrieval và action voting; về sau có thể mở rộng thành knowledge base từ incident thật.
- `--actions`: `data-pack/actions.yaml`. Hiện tại là catalog action hợp lệ; về sau giúp validation không cho LLM/action voting chọn action ngoài policy.
- `--artifacts-dir`: default `artifacts`. Hiện tại là nơi ghi evidence/decision; về sau hỗ trợ tách experiment output theo run.
- `--model`: default `openai/gpt-oss-20b`. Hiện tại chọn Groq model cho LLM reasoning; về sau có thể benchmark nhiều model mà không đổi pipeline.
- `--llm-mode`: `auto`, `required` hoặc `off`. Hiện tại kiểm soát fallback; về sau rất hữu ích cho reproducibility vì `off` cho deterministic baseline.
- Optional `.env` có `GROQ_API_KEY`. Hiện tại dùng để gọi LLM nếu có key; không ghi secret vào artifact để giữ an toàn.

Input nội bộ từ các stage trước:
- Detection: `evidence_candidates`. Cung cấp raw evidence đã chuẩn hóa để final decision có thể trỏ ngược về nguồn.
- Correlation: `clusters`, `dominant_signals`, `top_evidence`. Cung cấp incident context đã giảm nhiễu; về sau LLM prompt chỉ cần top evidence thay vì toàn bộ log/metric.
- RCA: `root_cause_rankings`, `candidates`, `confidence`. Cung cấp culprit candidate và độ chắc chắn; về sau guardrails dùng confidence để quyết định auto-remediate hay escalate.

Historical incident fields:
- `root_cause_class`: chỉ dùng để phân tích và giải thích, không map trực tiếp sang action. Về sau giúp SRE hiểu nhóm lỗi, nhưng guardrail ngăn rule cứng kiểu “class này thì action kia”.
- `affected_services`: service bị ảnh hưởng trong incident lịch sử. Hiện tại dùng tính service overlap; về sau giúp map action lịch sử sang service hiện tại tương đương.
- `log_signatures`: log patterns đã làm sạch. Hiện tại dùng log keyword/template overlap; về sau giúp retrieval mạnh hơn khi raw message khác ID nhưng cùng lỗi vận hành.
- `trace_signatures`: edge-level trace deviations. Hiện tại dùng trace-edge overlap; về sau giúp nhận ra cùng kiểu cascade dù alert service khác.
- `metric_signatures`: metric delta như `"30 -> 99"`. Hiện tại hỗ trợ similarity; về sau có thể dùng để giải thích “pattern tăng latency/CPU giống incident cũ”.
- `actions_taken`: action từng thực hiện, ví dụ `rollback_service:payment-svc:previous`. Hiện tại parse thành candidate action; về sau là nguồn học policy từ outcome thật.
- `outcome`: `success`, `partial`, `failed`. Hiện tại biến thành outcome weight; về sau giúp giảm chọn action từng thất bại.
- `mttr_minutes`: thời gian khắc phục. Hiện tại là supporting signal; về sau có thể dùng để ưu tiên action giảm MTTR.

Action catalog fields:
- `name`: tên action hợp lệ, ví dụ `rollback_service`. Hiện tại dùng validate decision; về sau đảm bảo LLM không hallucinate action ngoài catalog.
- `params`: tham số bắt buộc của action, ví dụ `service`, `target_version`. Hiện tại dùng normalize action output; về sau giúp action executor gọi đúng contract nếu có triển khai thực thi.
- `cost_min`: chi phí vận hành ước lượng. Hiện tại hỗ trợ decision risk; về sau có thể đưa vào utility function để cân bằng confidence và cost.
- `downtime_min`: downtime ước lượng. Hiện tại giúp guardrail tránh action có impact cao khi evidence yếu.
- `blast_radius_services`: số service có thể bị ảnh hưởng. Hiện tại dùng `blast_radius_check`; về sau giúp policy chỉ cho auto-action nếu blast radius nhỏ.
- `rollback_window_sec`: thời gian rollback dự kiến. Hiện tại hỗ trợ chọn rollback an toàn; về sau có thể dùng trong SLO/risk calculation.

LLM prompt gồm:
- Incident id, alert service và severity: giúp LLM có ngữ cảnh ban đầu nhưng không tự xem alert service là culprit.
- Top RCA candidates và per-ranker evidence: buộc LLM reasoning dựa trên RCA có cấu trúc, không đoán tự do.
- Correlated cluster top evidence và dominant signals: cung cấp evidence mạnh nhất, giảm prompt noise.
- Top 3 historical neighbors: giúp LLM so sánh với precedent gần nhất.
- Outcome-weighted action votes: đưa tín hiệu action đã thành công/thất bại trong quá khứ.
- Valid actions trong action catalog: giới hạn LLM trong action hợp lệ.

### Output

Final decision JSON:

```json
{
  "schema_version": "1.0",
  "incident_id": "E01",
  "selected_action": "rollback_service",
  "params": {
    "service": "payment-svc",
    "target_version": "previous"
  },
  "confidence": 0.8316,
  "evidence": {}
}
```

Field quan trọng:
- `selected_action`: action được recommend, ví dụ `rollback_service`. Hiện tại là output chính cho grader; về sau có thể nối với executor nếu muốn auto-remediation thật.
- `params`: tham số action đã normalize theo `actions.yaml`, ví dụ `{ "service": "payment-svc", "target_version": "previous" }`. Hiện tại giúp decision cụ thể và executable; về sau tránh action mơ hồ như “rollback something”.
- `confidence`: độ tin cậy cuối cùng trong `[0, 1]`. Hiện tại dùng để audit độ chắc chắn; về sau có thể đặt threshold auto-run, ví dụ chỉ auto action nếu confidence `>= 0.8`.
- `selected_action_meta`: metadata về cost, downtime, blast radius. Hiện tại giúp giải thích risk; về sau dùng cho policy như “blast radius > 1 thì cần human approval”.
- `evidence.method`: `llm-augmented`, `llm-guarded-fallback`, `llm-error-fallback`, `llm-missing-key-fallback` hoặc `llm-off-fallback`. Field này cho biết decision đến từ LLM hay fallback; về sau rất quan trọng để đánh giá chất lượng LLM so với deterministic baseline.
- `evidence.reasoning`: lý do chọn decision path. Hiện tại giúp người đọc hiểu tại sao action được chọn; về sau dùng làm audit note.
- `evidence.root_cause_service`: culprit service RCA top/final. Đây là bridge từ RCA sang action target.
- `evidence.root_cause_class`: class suy luận hỗ trợ, không phải rule trực tiếp. Về sau dùng cho reporting/category analytics, không dùng làm mapping action cứng.
- `evidence.rca_top_candidates`: giữ top candidates từ RCA. Về sau giúp review nếu action sai: có thể xem service #2/#3 có hợp lý hơn không.
- `evidence.top_3_neighbors`: incident lịch sử gần nhất. Về sau giúp giải thích decision dựa trên precedent nào.
- `evidence.action_votes`: danh sách action candidate và score. Về sau giúp compare action được chọn với các lựa chọn thay thế.
- `evidence.dominant_signals`: signal nổi bật của incident. Về sau giúp guardrails và report theo pattern lỗi.
- `evidence.blast_radius_check`: kết quả kiểm tra blast radius. Về sau là hook cho approval policy.
- `evidence.llm_evidence`: evidence IDs được LLM/decision dùng. Về sau giúp audit từ final action về detection evidence.

Ví dụ action vote và final decision:

```json
{
  "action_votes": [
    {
      "action": "rollback_service",
      "params": {
        "service": "payment-svc",
        "target_version": "previous"
      },
      "score": 0.3316
    },
    {
      "action": "page_oncall",
      "params": {
        "team": "platform-team"
      },
      "score": 0.7222
    }
  ],
  "final_decision": {
    "selected_action": "rollback_service",
    "confidence": 0.8316,
    "evidence": {
      "method": "llm-guarded-fallback",
      "root_cause_service": "payment-svc"
    }
  }
}
```

Artifact ghi ra:
- `artifacts/remediation/<ID>_decision.json`
- `artifacts/remediation/<ID>_llm_prompt.json`
- `artifacts/remediation/<ID>_llm_response.json`
- `artifacts/remediation/audit.jsonl`

### Logic Xử Lý

1. Chạy detection, correlation và RCA cho incident.
2. Retrieve historical incidents bằng hybrid similarity:
   - service overlap,
   - log keyword overlap,
   - trace-edge overlap,
   - bonus nếu RCA top culprit service nằm trong historical affected services.
3. Lấy top 3 historical neighbors.
4. Parse `actions_taken` từ history sang schema trong `actions.yaml`.
5. Tính action vote:

```text
vote = similarity * outcome_weight
```

Outcome weight:
- `success = 1.0`
- `partial = 0.55`
- `failed = 0.1`

6. Map service-targeted action từ historical service sang current RCA top culprit service.
7. Tạo prompt cho LLM với RCA, history, votes và valid actions.
8. Validate LLM response:
   - `root_cause_service` là culprit service và phải nằm trong RCA candidates.
   - `selected_action` phải tồn tại trong `actions.yaml`.
   - Required params phải đủ sau normalization.
   - `rollback_service` default `target_version = previous`.
   - `confidence` phải trong `[0, 1]`.
9. Áp dụng guardrails:
   - LLM off/unavailable/invalid thì dùng deterministic fallback.
   - LLM conflict với safety thì giữ response artifact nhưng chọn guarded fallback.
   - Evidence mới hoặc yếu thì `page_oncall`.
   - Pool evidence conflict thì escalate, không auto-apply sai service.
10. Ghi decision artifact và append một dòng vào `audit.jsonl`.

### Ý Nghĩa Thiết Kế

LLM được dùng như lớp reasoning/summarization có guardrails, không thay thế RCA. Decision vẫn dựa trên evidence có cấu trúc, historical outcome và action metadata. Hybrid retrieval giúp action được chọn theo tiền lệ gần nhất thay vì rule cứng. Outcome-weighted voting ưu tiên action từng thành công và giảm trọng số action partial/failed. Guardrails giữ hệ thống an toàn khi LLM trả JSON sai, chọn action không hợp lệ hoặc evidence không đủ mạnh để auto-remediate.

---

## Nội Dung Tóm Tắt Cho 1 Slide Mỗi Feature

### 001 Detection & Triage

Input: `metrics_window.samples`, `logs`, `detected_at`, `trigger_alert`.

Output: `evidence_candidates[]` với `evidence_id`, `evidence_type`, `service`, `score`, `signals`, `source_ref`, `details`.

Logic: tách metric/log, tính anomaly score, normalize log template, gán signals, chuẩn hóa score `[0, 1]`.

Ý nghĩa: biến raw evidence thành schema chung, giúp các stage sau có đủ tín hiệu và traceability.

### 002 Alert Correlation

Input: incident topology/traces và `evidence_candidates[]`.

Output: `clusters[]` với `cluster_id`, `services`, `time_range`, `dominant_signals`, `evidence_ids`, `topology_details`.

Logic: group theo time session `gap_sec`, merge theo service graph `max_hop`, augment graph bằng live traces.

Ý nghĩa: giảm nhiều alert rời rạc thành incident cluster có ngữ cảnh topology.

### 003 RCA RRF Ranking

Input: incident metrics/topology/traces, detection evidence, correlation clusters.

Output: `root_cause_rankings[]` với `candidates[]`, `rrf_score`, `normalized_score`, `ranker_ranks`, `confidence`, `warnings`.

Logic: chạy PageRank, timestamp degradation, causal-lag; hợp nhất bằng Reciprocal Rank Fusion.

Ý nghĩa: xếp hạng culprit service bằng nhiều tín hiệu độc lập, tránh phụ thuộc một heuristic; field schema vẫn giữ tên `root_cause_rankings`.

### 004 LLM Remediation Decision

Input: incident, RCA output, historical incidents, action catalog, optional Groq LLM.

Output: final decision với `selected_action`, `params`, `confidence`, `evidence` và `audit.jsonl`.

Logic: retrieve history, outcome-weighted action voting, optional LLM, validate response, apply safety guardrails/fallback.

Ý nghĩa: chọn remediation action có cơ sở evidence, có audit và vẫn an toàn khi LLM không đáng tin.
