# Detection Approach

## Approach tôi dùng

Pipeline sử dụng **hybrid streaming detection**:

- EWMA làm baseline động cho request rate.
- Rolling linear slope phát hiện memory tăng dần.
- Rule đa metric để phân loại ba fault.
- Log message làm evidence bổ sung.
- Persistence ba mẫu liên tiếp để chống nhiễu và false alert.

Giải pháp dùng Python standard library, không cần model train trước hoặc dependency ngoài.

## Tại sao chọn approach này

Generator có ba fault với nguyên nhân và tín hiệu khác nhau. Rule đa metric giúp xác định
đúng `type`, trong khi EWMA và rolling slope phát hiện thay đổi so với trạng thái bình
thường. Yêu cầu ba mẫu liên tiếp giúp tránh alert từ một datapoint nhiễu.

Isolation Forest không được chọn làm detector chính vì cần dữ liệu train, khó giải thích
loại fault, và có thể đánh dấu các điểm baseline hiếm là anomaly.

## Cách hoạt động

1. Server nhận payload tại `POST /ingest` và validate timestamp, logs, cùng toàn bộ metrics.
2. Hai mươi mẫu đầu được dùng làm warm-up cho EWMA baseline.
3. Với mỗi mẫu tiếp theo, detector tính:
   - Memory utilization và rolling memory slope.
   - Request-rate ratio so với EWMA baseline.
   - Evidence từ các log WARN/ERROR đặc trưng.
4. Detector đánh giá rule của từng fault và yêu cầu rule đúng ba mẫu liên tiếp.
5. Khi xác nhận fault, pipeline append một JSON alert vào `alerts.jsonl`.
6. Mỗi loại fault chỉ alert một lần trong vòng đời process để tránh duplicate alert.

Thứ tự ưu tiên phân loại là `dependency_timeout`, `memory_leak`, rồi `traffic_spike`.
Điều này tránh retry traffic của dependency timeout bị phân loại nhầm thành traffic spike.

## Parameters tôi chọn

| Parameter | Giá trị | Lý do |
|---|---:|---|
| Warm-up | 20 samples | Đủ tạo baseline ban đầu, vẫn khởi động nhanh |
| Persistence | 3 samples | Chống noise nhưng giữ TTD thấp |
| EWMA alpha | 0.08 | Baseline thích nghi chậm, không hấp thụ spike ngay |
| Memory history | 20 samples | Đủ thấy xu hướng leak qua noise |
| Memory slope | > 1.5 MB/sample | Bắt growth liên tục thay vì chỉ dùng absolute threshold |
| Timeout rate | > 8% | Cao hơn rõ rệt baseline khoảng 0-0.4% |
| Traffic ratio | > 2x baseline | Phân biệt spike với chu kỳ traffic bình thường |

### Fault rules

`memory_leak`:

- Memory utilization > 48%.
- Memory slope > 1.5 MB/sample.
- GC pause > 30 ms.

`traffic_spike`:

- Request rate > 2 lần EWMA baseline và > 250 req/s.
- Queue depth > 40 và P99 latency > 250 ms.
- Upstream timeout rate < 8%.

`dependency_timeout`:

- Upstream timeout rate > 8%.
- HTTP 5xx rate > 4%.
- P99 latency > 200 ms.

## Chạy bài

Mở terminal thứ nhất:

```bash
cd w1/individual-lab
python pipeline.py --reset-alerts
```

Mở terminal thứ hai:

```bash
cd w1/individual-lab
python stream_generator.py --birthday YYYY-MM-DD --target http://localhost:8000/ingest
```

Chạy kiểm thử:

```bash
cd w1/individual-lab
python -m unittest -v test_pipeline.py
```

## Cải thiện nếu có thêm thời gian

- Cho phép reset/cooldown incident để phát hiện nhiều lần cùng một fault trong process dài.
- Persist EWMA state để pipeline restart không cần warm-up lại.
- Thêm Prometheus metrics về số request, anomaly candidate và alert.
- Dùng Drain3 khi log message thực tế đa dạng hơn các mẫu cố định của generator.
