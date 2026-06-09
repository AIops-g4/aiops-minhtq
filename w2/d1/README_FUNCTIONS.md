# Giải Thích Cơ Chế Clustering Trong `assignment.ipynb`

Notebook này làm nhiệm vụ **alert correlation**: từ nhiều alert rời rạc, gom chúng thành một số cluster có ý nghĩa hơn để người on-call xử lý ít việc hơn.

Ý tưởng chính:

```text
20 alert riêng lẻ
-> gom theo thời gian
-> trong từng nhóm thời gian, gom tiếp theo service topology
-> tách alert được ghi rõ là noise
-> ghi ra cluster_summary.json
```

Quy tắc cốt lõi:

```text
Cùng cluster = gần nhau về thời gian + gần nhau trên service graph + không bị đánh dấu là noise
```

## 1. Hai Lớp Clustering Chính

Code dùng 2 lớp clustering quan trọng:

```text
Layer 2: session_groups()
  -> gom alert xảy ra gần nhau về thời gian

Layer 3: topology_group()
  -> trong mỗi nhóm thời gian, gom alert theo quan hệ service
```

Hàm tổng hợp là `correlate()`:

```python
for session_alerts in session_groups(alerts, gap_sec=120):
    for group in topology_group(session_alerts, graph, max_hop=2):
        clusters.append(summarize_cluster(...))
```

Nghĩa là code không gom bừa tất cả alert cùng lúc. Nó làm theo thứ tự:

```text
Bước 1: Alert nào xảy ra gần nhau?
Bước 2: Trong số đó, service nào có liên quan topology?
```

## 2. `session_groups()`: Gom Theo Thời Gian

Hàm này trả lời câu hỏi:

```text
Alert nào xảy ra gần nhau trong cùng một đợt?
```

Code dùng `gap_sec = 120`, tức là 2 phút. Nếu alert mới cách alert trước đó không quá 120 giây, nó được đưa vào cùng session.

Ví dụ đơn giản:

```text
a1 09:00:00 payment-svc
a2 09:00:30 checkout-svc
a3 09:01:20 edge-lb
a4 09:10:00 search-svc
```

So khoảng cách thời gian:

```text
a2 - a1 = 30 giây  -> cùng session
a3 - a2 = 50 giây  -> cùng session
a4 - a3 = 520 giây -> quá 120 giây, tạo session mới
```

Kết quả:

```python
[
    [a1, a2, a3],
    [a4],
]
```

Điểm cần chú ý: hàm so alert mới với **alert cuối cùng trong session**, không so với alert đầu tiên.

Ví dụ:

```text
09:00:00
09:01:30
09:03:00
09:04:30
```

Mỗi cặp liên tiếp cách nhau 90 giây. Vì 90 nhỏ hơn 120, cả 4 alert vẫn nằm trong cùng một session, dù từ đầu đến cuối dài hơn 2 phút.

Với dataset hiện tại, 20 alert nằm trong khoảng:

```text
09:42:01 -> 09:48:30
```

Các alert nối tiếp nhau không cách quá 120 giây, nên `session_groups()` tạo ra **1 session lớn chứa cả 20 alert**.

## 3. Vì Sao Chỉ Gom Theo Thời Gian Là Chưa Đủ?

Nếu chỉ dùng `session_groups()`, kết quả sẽ gần như là:

```text
1 cluster chứa cả 20 alert
```

Điều này không tốt, vì trong dataset có alert xảy ra cùng thời điểm nhưng không liên quan đến sự cố chính:

```text
a-0013 recommender-svc: unrelated concurrent batch retrain
a-0016 search-svc: noise independent slow query
```

Chúng xảy ra gần thời gian với incident payment, nhưng không nên bị gom vào incident payment.

Vì vậy cần bước thứ hai: `topology_group()`.

## 4. `topology_group()`: Gom Theo Quan Hệ Service

Hàm này trả lời câu hỏi:

```text
Trong cùng một session thời gian, service nào gần nhau trên service graph?
```

Service graph trong `services.json` mô tả quan hệ gọi nhau giữa service.

Ví dụ:

```text
edge-lb -> checkout-svc -> payment-svc -> payments-db
checkout-svc -> cart-svc
checkout-svc -> notification-svc
```

Edge `A -> B` nghĩa là:

```text
A gọi B
A phụ thuộc vào B
```

Nếu `payment-svc` bị lỗi, alert có thể xuất hiện ở:

```text
payment-svc
checkout-svc
edge-lb
```

Vì `checkout-svc` gọi `payment-svc`, còn `edge-lb` gọi `checkout-svc`. Lỗi ở phía dưới có thể làm service phía trên cũng chậm hoặc lỗi.

## 5. Vì Sao Chuyển Graph Có Hướng Thành Vô Hướng?

Graph gốc có hướng:

```text
edge-lb -> checkout-svc -> payment-svc
```

Nhưng khi `payment-svc` lỗi, ảnh hưởng thường lan ngược lên caller:

```text
payment-svc ảnh hưởng checkout-svc
checkout-svc ảnh hưởng edge-lb
```

Nếu giữ graph có hướng và hỏi:

```text
Từ payment-svc có đường đi tới edge-lb không?
```

câu trả lời là không, vì chiều edge là ngược lại.

Do đó code chuyển sang vô hướng:

```python
undirected = graph.to_undirected()
```

Khi đó graph được hiểu như:

```text
edge-lb -- checkout-svc -- payment-svc
```

Bây giờ ta chỉ hỏi:

```text
Hai service có gần nhau không?
```

chứ không bắt buộc đúng chiều gọi service.

## 6. `max_hop = 2` Nghĩa Là Gì?

`max_hop = 2` nghĩa là 2 service được xem là liên quan nếu chúng cách nhau không quá 2 cạnh trên graph.

Ví dụ:

```text
edge-lb -- checkout-svc -- payment-svc
```

Khoảng cách:

```text
payment-svc <-> checkout-svc = 1 hop
payment-svc <-> edge-lb      = 2 hop
```

Vì cả hai đều `<= 2`, alert của 3 service này có thể vào cùng cluster.

Ví dụ thêm:

```text
payment-svc -- checkout-svc -- cart-svc
```

Khoảng cách từ `payment-svc` đến `cart-svc` cũng là 2 hop, nên `cart-svc` cũng có thể được gom vào cluster chính nếu xảy ra cùng session.

## 7. Ví Dụ Clustering Mini

Giả sử sau bước time-window, ta có 6 alert trong cùng session:

```text
a1 payment-svc
a2 checkout-svc
a3 edge-lb
a4 cart-svc
a5 recommender-svc
a6 search-svc
```

Topology liên quan:

```text
edge-lb -- checkout-svc -- payment-svc
checkout-svc -- cart-svc
catalog-svc -- recommender-svc
search-svc -- catalog-db
```

Với `max_hop = 2`:

```text
payment-svc đến checkout-svc = 1
payment-svc đến edge-lb      = 2
payment-svc đến cart-svc     = 2
```

Nên các alert này được gom:

```text
Cluster chính:
[payment-svc, checkout-svc, edge-lb, cart-svc]
```

Nếu `recommender-svc` có note `unrelated` và `search-svc` có note `noise`, chúng bị tách riêng:

```text
Cluster riêng:
[recommender-svc]

Cluster riêng:
[search-svc]
```

Kết quả cuối:

```python
[
    [payment_alerts, checkout_alerts, edge_alerts, cart_alerts],
    [recommender_alert],
    [search_alert],
]
```

## 8. Áp Dụng Vào Dataset Hiện Tại

Dataset có 20 alert.

`session_groups()` tạo 1 session lớn vì các alert xảy ra gần nhau.

Sau đó `topology_group()` chia session này thành 3 cluster:

```text
Cluster 1: payment cascade
services = payment-svc, checkout-svc, edge-lb, cart-svc, notification-svc
alert_count = 18

Cluster 2: explicit noise
services = recommender-svc
alert_ids = a-0013

Cluster 3: explicit noise
services = search-svc
alert_ids = a-0016
```

Output:

```text
input_alerts = 20
output_clusters = 3
reduction_ratio = 0.85
```

Công thức:

```text
reduction_ratio = 1 - output_clusters / input_alerts
                = 1 - 3 / 20
                = 0.85
```

Nghĩa là thay vì xem 20 alert riêng lẻ, người on-call chỉ cần xem 3 cluster.

## 9. Các Hàm Phụ, Giải Thích Ngắn Gọn

Các hàm dưới đây không phải trọng tâm clustering, nhưng hỗ trợ pipeline chạy đúng.

`parse_ts(value)`:

```text
Đổi timestamp string thành datetime để sort và tính khoảng cách thời gian.
```

`fingerprint(alert)`:

```text
Tạo định danh alert theo service, metric, severity.
Ví dụ: payment-svc|latency_p99_ms|crit
```

`is_explicit_noise(alert)`:

```text
Kiểm tra labels.note có chứa unrelated, noise hoặc independent không.
Nếu có, alert được tách thành cluster riêng.
```

`max_severity(alerts)`:

```text
Lấy severity cao nhất trong cluster theo thứ tự info < warn < crit.
```

`build_service_graph(services_doc)`:

```text
Đọc services.json và tạo graph service bằng networkx.
```

`summarize_cluster(cluster_id, group)`:

```text
Biến một group alert thành JSON metadata gồm cluster_id, alert_count, services, time_range, max_severity, fingerprints, alert_ids.
```

`correlate(alerts, graph, gap_sec=120, max_hop=2)`:

```text
Hàm chính: gọi session_groups(), topology_group(), rồi summarize_cluster().
```

## 10. Tóm Tắt Dễ Nhớ

```text
session_groups()
  -> "Có xảy ra gần nhau không?"

topology_group()
  -> "Có gần nhau trên service graph không?"

is_explicit_noise()
  -> "Dataset có nói rõ alert này là noise không?"

correlate()
  -> "Kết hợp tất cả để tạo cluster cuối cùng."
```

Một cluster tốt trong bài này cần thỏa:

```text
gần thời gian
+ gần topology
+ không phải explicit noise
```
