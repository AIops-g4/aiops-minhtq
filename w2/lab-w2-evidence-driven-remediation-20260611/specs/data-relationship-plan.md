# Kế Hoạch Phân Tích Dữ Liệu Và Quan Hệ Biến Trong Lab Remediation Engine

## Tóm Tắt

Mục tiêu là phân tích rõ các biến trong data pack và cách chúng liên hệ với nhau để xây engine theo pipeline:

`bằng chứng thô của incident -> feature/signature -> truy xuất lịch sử -> voting action -> quyết định cuối cùng -> audit.jsonl`

Điểm quan trọng: không được ánh xạ trực tiếp `root_cause_class -> action`. Engine phải suy luận từ logs, traces, metrics, topology, outcome trong lịch sử và metadata của action.

## Các Biến Dữ Liệu Và Ý Nghĩa

- Incident hiện tại trong `eval/E01.json` ... `E08.json`:
  - `incident_id`: ID đầy đủ trong file, ví dụ `E01-2026-06-10-001`; nhưng `audit.jsonl.incident_id` phải dùng basename của file như `E01`.
  - `detected_at`: thời điểm incident được phát hiện, dùng để phân biệt giai đoạn baseline trước alert và giai đoạn sau alert.
  - `trigger_alert.service`: service phát alert; đây là điểm bắt đầu điều tra, không chắc là root cause.
  - `trigger_alert.rule_id`: loại alert, ví dụ latency, error rate, DNS hoặc memory leak.
  - `trigger_alert.severity`: mức độ ảnh hưởng, dùng phụ trợ khi tính confidence/risk.
  - `topology.nodes`: danh sách service/node và tier.
  - `topology.edges`: quan hệ gọi giữa các service, ví dụ `checkout-svc -> payment-svc`.
  - `metrics_window.samples`: time series dạng `service.metric -> [[timestamp, value], ...]`.
  - `traces`: bằng chứng runtime ở cấp edge, gồm `from`, `to`, `count`, `error_count`, `p50_ms`, `p99_ms`.
  - `logs`: bằng chứng ở cấp service, gồm `ts`, `svc`, `level`, `msg`.

- Tập incident lịch sử `incidents_history.json`:
  - `root_cause_class`: nhãn nguyên nhân lịch sử, chỉ dùng để hiểu hoặc gom nhóm; không dùng làm rule trực tiếp.
  - `affected_services`: các service từng bị ảnh hưởng, dùng để so với affected services suy luận từ incident mới.
  - `log_signatures`: template log đã được làm sạch; live logs phải được normalize/template hóa trước khi so sánh.
  - `trace_signatures`: signature theo edge, gồm độ lệch và error rate.
  - `metric_signatures`: metric delta dạng chuỗi như `"30 -> 99"`, cần parse thành số.
  - `actions_taken`: action dạng chuỗi như `rollback_service:payment-svc:previous`, phải parse theo schema trong `actions.yaml`.
  - `outcome`: `success`, `partial`, `failed`; dùng làm trọng số khi voting action.
  - `mttr_minutes`: thời gian xử lý incident, dùng phụ trợ nếu cần ưu tiên action hiệu quả hơn.

- Catalog action `actions.yaml`:
  - `name`: tên action hợp lệ để recommend.
  - `params`: các tham số bắt buộc của action.
  - `cost_min`, `downtime_min`, `blast_radius_services`, `rollback_window_sec`: metadata để tính utility/risk.
  - `page_oncall`: action escalate; không được để action này thắng chỉ vì cost bằng 0 hoặc xuất hiện nhiều trong lịch sử.

## Quan Hệ Giữa Các Biến

- `service` là khóa liên kết chính:
  - `logs.svc` cho biết service nào phát log bất thường.
  - `metrics_window.samples` có key dạng `service.metric`.
  - `traces.from/to` cho biết service nào nằm trên edge lỗi hoặc chậm.
  - `topology.nodes.id` định nghĩa service trong graph.
  - `actions_taken` và action params thường nhắm vào một `service`.

- `trigger_alert.service` không đồng nghĩa với root cause:
  - E01 alert ở `checkout-svc`, nhưng accepted action nhắm vào `payment-svc`.
  - E08 alert ở `bb-edge`, nhưng accepted auto-action là `rollback_service` cho `t24-service`.
  - Vì vậy cần dùng trace/topology để đi từ nơi phát alert tới downstream/root candidate.

- `traces` là bằng chứng thể hiện quan hệ giữa các service:
  - `from -> to` mô tả dependency runtime.
  - `error_count / count` tạo error rate.
  - `p99_ms` và `p50_ms` cho biết latency anomaly.
  - Edge có error/latency cao giúp xác định downstream service hoặc leaf service gây cascade.

- `logs` là bằng chứng cục bộ của từng service:
  - Raw log phải được chuyển thành template/signature.
  - Số lượng log theo `svc`, `level`, và mức độ match với historical `log_signatures` giúp xác định service nghi vấn.
  - Khi logs và traces mâu thuẫn, traces nên có trọng số cao hơn cho cascade/downstream reasoning.

- `metrics` là bằng chứng phụ:
  - Metric key được tách thành `service` và `metric`.
  - So sánh đầu/cuối hoặc trước/sau `detected_at` để lấy delta/ratio.
  - Không dùng metrics một mình vì rubric yêu cầu engine phải dùng cả logs và traces.

- `history` liên hệ với live incident qua similarity của signature:
  - Live logs được normalize để so với `log_signatures`.
  - Live traces được aggregate để so với `trace_signatures`.
  - Live metrics delta được so với `metric_signatures`.
  - Live affected services được suy luận từ alert service, log bursts, trace anomalies và metric anomalies.

- `actions_taken` liên hệ với decision qua outcome-weighted voting:
  - Historical incident tương tự có `outcome=success` sẽ tăng vote.
  - `partial` làm vote yếu hơn.
  - `failed` phải bị phạt hoặc loại khỏi top.
  - Nếu không có neighbor đủ gần, chọn `page_oncall`.