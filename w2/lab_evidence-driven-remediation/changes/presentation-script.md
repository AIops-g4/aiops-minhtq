# Presentation Script - AIOps Evidence-Driven Remediation

Tổng thời lượng gợi ý: khoảng 18-22 phút. Nếu cần trình bày ngắn hơn, ưu tiên giữ các slide 1, 2, 3, 5, 9, 12, 14, 16, 18 và 19.

## Slide 1: Evidence-Driven Remediation

**Thời lượng ước tính:** 45 giây

**Kịch bản thuyết trình:**
Chào mọi người, hôm nay em sẽ trình bày project AIOps Evidence-Driven Remediation. Mục tiêu của project là từ một incident JSON gồm metrics, logs, traces và topology, hệ thống có thể đi qua nhiều lớp phân tích để đề xuất một remediation action cuối cùng.

Điểm quan trọng ở đây là hệ thống không chọn action bằng cách đoán trực tiếp. Mỗi quyết định đều phải có evidence chain: phát hiện tín hiệu bất thường, gom chúng thành incident context, xếp hạng culprit service, rồi mới dùng history, action catalog và guardrails để chọn action.

**Chuyển ý sang slide tiếp theo:**
Trước khi đi vào từng feature, em sẽ đi qua pipeline tổng thể để thấy các module nối với nhau như thế nào.

**Cụm từ cần nhấn mạnh:**
Evidence chain trước, action sau.

## Slide 2: Từ Incident JSON Tới Action Có Thể Audit

**Thời lượng ước tính:** 1 phút

**Kịch bản thuyết trình:**
Pipeline bắt đầu từ incident JSON. Đây là input raw gồm metric time series, logs, traces và topology. Stage đầu tiên là Detection, tạo ra `evidence_candidates`. Sau đó Correlation gom các evidence này thành `alert_clusters`, để giảm nhiễu từ nhiều alert rời rạc.

Tiếp theo, RCA Ranking xếp hạng các service có khả năng là culprit. Cuối cùng Decision layer dùng RCA, historical incidents, action catalog và optional LLM để chọn `selected_action`, đồng thời ghi audit.

Điểm em muốn nhấn mạnh là mỗi stage có contract rõ ràng. Các field như `incident_id`, `evidence_id`, `source_ref` giúp mình truy ngược quyết định về dữ liệu gốc. Vì vậy output không phải black box.

**Chuyển ý sang slide tiếp theo:**
Một khái niệm xuyên suốt trong pipeline là phân biệt service gây lỗi và service bị ảnh hưởng, nên slide tiếp theo em sẽ giải thích Culprit vs Victim.

**Cụm từ cần nhấn mạnh:**
Không shortcut từ alert sang action.

## Slide 3: Culprit vs Victim

**Thời lượng ước tính:** 1 phút

**Kịch bản thuyết trình:**
Trong AIOps, service phát alert chưa chắc là service gây lỗi. Vì vậy em dùng hai khái niệm: Culprit và Victim.

Culprit là service gây lỗi gốc, tức là target chính của RCA và remediation. Victim là service bị ảnh hưởng, có thể latency tăng, log lỗi, hoặc phát alert, nhưng không nhất thiết là nguyên nhân.

Ví dụ ở đây, `payment-svc` bị pool exhausted. Lỗi này làm `checkout-svc` latency tăng, rồi có thể làm `edge-lb` request timeout. Nếu mình chỉ nhìn alert từ `checkout-svc` và rollback checkout ngay, có thể xử lý sai chỗ. Pipeline này được thiết kế để tránh lỗi đó.

**Chuyển ý sang slide tiếp theo:**
Bây giờ em đi vào feature đầu tiên, nơi raw metrics và logs được chuẩn hóa thành evidence.

**Cụm từ cần nhấn mạnh:**
Alert service có thể chỉ là victim.

## Slide 4: Detection & Triage

**Thời lượng ước tính:** 35 giây

**Kịch bản thuyết trình:**
Feature 001 là Detection & Triage. Vai trò của module này là chuyển raw evidence thành một danh sách signals có thể so sánh được.

Thay vì để metrics và logs ở dạng raw, module này chuẩn hóa chúng thành cùng một envelope gọi là `evidence_candidates`. Nhờ đó các stage sau không cần quan tâm evidence đến từ metric hay log, mà chỉ cần đọc các field chung như service, score, signals và source reference.

**Chuyển ý sang slide tiếp theo:**
Để thấy rõ hơn contract của stage này, em sẽ nói về input và output chính.

**Cụm từ cần nhấn mạnh:**
Chuẩn hóa raw evidence thành schema chung.

## Slide 5: Input Là Raw Incident, Output Là `evidence_candidates[]`

**Thời lượng ước tính:** 1 phút 20 giây

**Kịch bản thuyết trình:**
Input của Detection là incident JSON. Trong đó có một số field quan trọng.

`incident_id` giúp join toàn bộ artifact của cùng một sự cố. `detected_at` là mốc chia baseline và post-alert, rất quan trọng để biết tín hiệu nào xảy ra trước hay sau alert. `trigger_alert.service` chỉ là điểm bắt đầu điều tra, không được xem là culprit mặc định.

Hai nguồn dữ liệu chính là `metrics_window.samples` và `logs`. Metrics dùng để tính anomaly score. Logs được normalize thành template để so sánh pattern thay vì so raw message.

Output là `evidence_candidates[]`. Mỗi evidence có `evidence_id`, `service`, `score`, `signals`, `source_ref`, và `details`. Những field này không chỉ dùng hiện tại, mà còn giúp stage sau: correlation dùng `service` và `score`, RCA dùng `evidence_id`, decision dùng `signals` và `source_ref` để audit.

**Chuyển ý sang slide tiếp theo:**
Trong Detection, phần metric có nhiều biến tính toán quan trọng, nên em sẽ giải thích kỹ hơn ở slide tiếp theo.

**Cụm từ cần nhấn mạnh:**
Mỗi field được thiết kế để dùng lại ở stage sau.

## Slide 6: Detection Chạy 2 Nhánh Rồi Merge Về Cùng Schema

**Thời lượng ước tính:** 1 phút

**Kịch bản thuyết trình:**
Ở slide này, em muốn nhấn mạnh rằng metric và log không chạy tuần tự, mà là hai nhánh song song.

Từ incident JSON, hệ thống tách ra hai luồng xử lý. Metric branch đọc `metrics_window.samples`, chia baseline và post-alert, rồi tính delta, ratio, slope và z-score. Log branch đọc raw logs, normalize message thành template, group theo service, level và template, rồi tính severity, burst, keyword và metric-link score.

Mời mọi người nhìn hình metric ở slide này: phần baseline ổn định trước alert là cơ sở để detector biết sau alert metric đã lệch đi bao nhiêu. Hình này thuộc metric branch, còn log branch chạy song song với logic riêng.

Hai nhánh này độc lập về logic, nhưng cuối cùng đều emit cùng một schema là `EvidenceCandidate`. Sau đó hệ thống mới merge lại thành `evidence_candidates[]`. Nhờ vậy correlation và RCA không cần biết evidence đến từ metric hay log; chúng chỉ cần đọc chung các field như `service`, `timestamp`, `score`, `signals` và `evidence_id`.

**Chuyển ý sang slide tiếp theo:**
Sau khi hiểu hai nhánh chạy song song, em sẽ đi sâu hơn vào nhánh metric để giải thích các biến tính toán quan trọng.

**Cụm từ cần nhấn mạnh:**
Metric và log chạy song song, merge ở cuối.

## Slide 7: Score Được Tạo Từ Biến Metric Và Biến Log

**Thời lượng ước tính:** 1 phút 30 giây

**Kịch bản thuyết trình:**
Slide này là phần chuẩn bị nguyên liệu để slide sau tính score. Vì Detection có hai nhánh song song, nên score cũng lấy input từ hai nhóm biến: metric variables và log variables.

Ở nhánh metric, các biến chính gồm `directional_z`, `robust_z`, `drift`, `ratio`, và `slope_signal`. `directional_z` đo độ lệch theo hướng metric xấu đi, ví dụ latency tăng hoặc availability giảm. `robust_z` dùng median và MAD nên ít bị outlier làm lệch. `drift` cho biết sau alert trung bình metric đã lệch khỏi baseline bao nhiêu. `ratio` cho biết tăng gấp mấy lần, còn `slope_signal` cho biết tốc độ xấu đi có kéo dài hay không.

Ở nhánh log, các biến chính gồm `severity_score`, `frequency_score`, `burst_score`, `keyword_score`, và `metric_link_score`. Một log sẽ đáng nghi hơn nếu nó là ERROR, xuất hiện nhiều lần, burst trong thời gian ngắn, chứa keyword vận hành như timeout hoặc pool exhausted, và service đó cũng có metric anomaly.

Nói ngắn gọn, slide này cho thấy score không phải một con số tự nhiên xuất hiện. Nó được xây từ các tín hiệu đã có ý nghĩa vận hành.

**Chuyển ý sang slide tiếp theo:**
Sau khi có các biến đầu vào này, slide tiếp theo sẽ chỉ rõ công thức biến chúng thành `score`.

**Cụm từ cần nhấn mạnh:**
Score có nguyên liệu từ cả metric và log.

## Slide 8: `score` Là Suspiciousness Của Evidence

**Thời lượng ước tính:** 1 phút 10 giây

**Kịch bản thuyết trình:**
Slide này trả lời câu hỏi quan trọng: score trong Feature 001 được tính như thế nào, vì sang Feature 002 mình sẽ dùng `min_score` để filter evidence.

Với metric, hệ thống không cộng tất cả tín hiệu lại, mà lấy tín hiệu anomaly mạnh nhất bằng hàm `max`. Các tín hiệu gồm directional z-score, robust z-score, drift, ratio signal và slope signal. Lý do dùng `max` là vì một metric có thể chỉ bất thường rõ ở một kiểu, ví dụ spike rất mạnh nhưng slope không quá lớn.

Với log, score được tính bằng weighted sum. Nó kết hợp severity, frequency, burst, keyword và metric-link. Nghĩa là một log đáng nghi hơn nếu nó là ERROR, lặp nhiều, xuất hiện dồn dập, chứa keyword vận hành như timeout hoặc pool exhausted, và service đó cũng có metric anomaly.

Ngoài score, Feature 001 còn gán `signals`. Signals là các nhãn giải thích, không phải số. Với metric, signal được tạo từ hướng tăng hoặc giảm, token trong tên metric như latency, error, memory, pool, dns, rồi thêm `metric_spike` và `post_alert`. Với log, signal luôn có `log_template` và `log_level_*`; sau đó keyword trong template tạo ra các nhãn như `pool_anomaly`, `timeout_anomaly`, `dns_anomaly`, và nếu service đó cũng có metric anomaly thì thêm `metric_linked`.

Điểm cần nhớ là score này không phải confidence của action. Nó chỉ cho biết evidence này đáng nghi đến mức nào để giữ lại cho correlation và RCA.

**Chuyển ý sang slide tiếp theo:**
Sau khi score được tính, hệ thống đóng gói từng tín hiệu thành evidence candidate để audit và truyền sang stage sau.

**Cụm từ cần nhấn mạnh:**
Score là suspiciousness của evidence, không phải confidence của action.

## Slide 9: `evidence_candidates[]` Là Output Chuẩn Hóa Của Detection

**Thời lượng ước tính:** 1 phút

**Kịch bản thuyết trình:**
Slide này tổng kết output của Feature 001. Output không phải là một action, cũng chưa phải root cause. Nó là một object gồm `schema_version`, `incident_id` và danh sách `evidence_candidates`.

Mỗi candidate đại diện cho một signal đáng nghi đã được chuẩn hóa. Nó có thể là metric evidence, ví dụ latency của `payment-svc` tăng bất thường, hoặc log evidence, ví dụ connection pool timeout xuất hiện nhiều lần.

Các field quan trọng ở đây là `service`, time range, `score`, `signals`, `source_ref`, `evidence_id` và `details`. `service` và time range giúp correlation group evidence. `score` giúp filter và rank.

Riêng `signals`, mình có thể đọc trực tiếp từ ví dụ. `log_template` xuất hiện vì log đã được normalize thành template. `log_level_error` đến từ level ERROR. `pool_anomaly` đến từ keyword như ConnectionPool hoặc pool exhausted. `timeout_anomaly` đến từ keyword timeout. Nếu cùng service đó cũng có metric anomaly, hệ thống thêm `metric_linked`. Vì vậy signals không phải label thủ công, mà được sinh bằng rule từ level, keyword, metric name và metric-link.

`source_ref` và `evidence_id` giữ trace về raw incident. Còn `details` chứa phần debug: metric thì có baseline, delta, z-score; log thì có template ID, count và raw examples.

Nói ngắn gọn, Feature 001 biến raw data thành một danh sách evidence có thể truyền tiếp, so sánh được và audit được.

**Chuyển ý sang slide tiếp theo:**
Khi đã có nhiều evidence candidates, vấn đề tiếp theo là gom chúng lại thành incident context.

**Cụm từ cần nhấn mạnh:**
Detection output là contract cho Correlation.

## Slide 10: Alert Correlation

**Thời lượng ước tính:** 35 giây

**Kịch bản thuyết trình:**
Feature 002 là Alert Correlation. Một incident thật thường tạo ra rất nhiều evidence: metric tăng, log lỗi, trace chậm, ở nhiều service khác nhau.

Nếu đưa toàn bộ evidence rời rạc vào RCA hoặc LLM thì sẽ rất nhiễu. Vì vậy module này gom các evidence có liên quan thành incident cluster, dựa trên hai yếu tố: gần nhau theo thời gian và gần nhau trong topology hoặc trace.

**Chuyển ý sang slide tiếp theo:**
Em sẽ giải thích logic grouping gồm ba bước: filter, session, và topology.

**Cụm từ cần nhấn mạnh:**
Nhiều alert rời rạc thành một incident context.

## Slide 11: Time Session Trước, Topology Grouping Sau

**Thời lượng ước tính:** 1 phút

**Kịch bản thuyết trình:**
Correlation bắt đầu bằng việc lọc evidence theo `min_score`. Mặc định là 0.28 để không bỏ mất evidence mà Detection đã xem là có ích.

Sau đó module tạo time session. Các evidence có `detected_at` gần nhau, cụ thể là cách nhau không quá `gap_sec = 300`, sẽ được xem là cùng một burst thời gian.

Cuối cùng, trong mỗi session, hệ thống build service graph từ topology và augment thêm live traces. Hai service được merge nếu shortest path nhỏ hơn hoặc bằng `max_hop = 2`. Giá trị 2 hop đủ để bắt cascade kiểu `edge-lb -> checkout-svc -> payment-svc`, nhưng không kéo toàn bộ hệ thống vào một cluster.

**Chuyển ý sang slide tiếp theo:**
Sau khi group xong, output cluster phải vừa tóm tắt được sự cố, vừa giữ đường truy vết.

**Cụm từ cần nhấn mạnh:**
Time proximity plus topology proximity.

## Slide 12: Cluster Giữ Cả Summary Lẫn Đường Truy Vết

**Thời lượng ước tính:** 1 phút

**Kịch bản thuyết trình:**
Đây là ví dụ một cluster của E01. Ta thấy cluster có các service như `checkout-svc`, `edge-lb`, và `payment-svc`. Đây chính là phạm vi mà RCA sẽ xét culprit candidate.

`dominant_signals` tóm tắt pattern chính của cluster, ví dụ `pool_anomaly` và `timeout_anomaly`. `fingerprints` giữ các signature ổn định của metric và log, rất hữu ích cho retrieval lịch sử.

Quan trọng nhất là `evidence_ids`. Field này giúp RCA và final decision trỏ ngược lại các evidence gốc. Vì vậy cluster không chỉ là summary, mà còn là cầu nối audit.

**Chuyển ý sang slide tiếp theo:**
Khi đã có cluster, bước tiếp theo là xác định trong cluster đó service nào là culprit.

**Cụm từ cần nhấn mạnh:**
Cluster vừa giảm nhiễu, vừa giữ traceability.

## Slide 13: Các Biến Cluster Được Tạo Từ Evidence, Time Và Topology

**Thời lượng ước tính:** 1 phút 15 giây

**Kịch bản thuyết trình:**
Slide này giải thích rõ hơn các field trong cluster được tạo ra như thế nào.

`cluster_id` là deterministic ID, sinh từ incident, session index và group index. Nó giúp output ổn định khi chạy lại. `alert_count` là số evidence nằm trong cluster, cho biết cluster này gom được bao nhiêu alert-like signals.

`services` được lấy từ unique service trong evidence sau khi đã group theo topology. Đây là field rất quan trọng vì nó trở thành candidate pool cho RCA. `time_range` lấy timestamp sớm nhất và muộn nhất, giúp dựng timeline incident.

`dominant_signals` được tạo bằng cách đếm các signals xuất hiện trong cluster, ví dụ pool hoặc timeout. `fingerprints` được tạo từ metric name hoặc log template ID, nên ổn định hơn raw timestamp và raw value. `evidence_ids` giữ đường link về evidence gốc. Cuối cùng, `topology_details` ghi lại service distance và trace edges dùng để merge, giúp audit vì sao các service được gom chung.

**Chuyển ý sang slide tiếp theo:**
Khi cluster đã có services và evidence IDs, RCA có thể bắt đầu xếp hạng culprit service trong phạm vi cluster đó.

**Cụm từ cần nhấn mạnh:**
Cluster fields là cầu nối từ evidence sang RCA.

## Slide 14: RCA RRF Ranking

**Thời lượng ước tính:** 40 giây

**Kịch bản thuyết trình:**
Feature 003 là RCA RRF Ranking. Module này không chọn remediation action. Nhiệm vụ của nó chỉ là xếp hạng service có khả năng là culprit trong mỗi correlated cluster.

Output của RCA gồm danh sách candidates, score, các ranker đã chạy, warnings, và confidence gap. Những thông tin này sẽ được Decision layer dùng để chọn action hoặc quyết định có nên escalate hay không.

**Chuyển ý sang slide tiếp theo:**
Điểm quan trọng của RCA là không dựa vào một heuristic duy nhất.

**Cụm từ cần nhấn mạnh:**
RCA chỉ tìm culprit, chưa chọn action.

## Slide 15: Không Tin Một Heuristic Duy Nhất

**Thời lượng ước tính:** 1 phút 10 giây

**Kịch bản thuyết trình:**
RCA dùng ba ranker chính.

Ranker đầu tiên là PageRank, chạy trên graph `caller -> callee`. Ý tưởng là lỗi ở downstream service có thể lan ngược lên caller, nên topology giúp tìm service có vai trò dependency quan trọng.

Ranker thứ hai là timestamp. Nó tìm service có metric degrade sớm nhất. Nếu một service xấu đi trước, khả năng nó là culprit cao hơn service chỉ bị ảnh hưởng sau đó.

Ranker thứ ba là causal-lag, dùng cross-correlation giữa anomaly series để xem service nào có tín hiệu lead service khác. Nếu không đủ dữ liệu metric thì ranker này được skip và ghi warning, thay vì tạo confidence giả.

**Chuyển ý sang slide tiếp theo:**
Vì ba ranker có score khác scale, hệ thống cần một cách hợp nhất ổn định hơn là cộng raw score.

**Cụm từ cần nhấn mạnh:**
Graph, time, và lag bổ sung cho nhau.

## Slide 16: RRF Hợp Nhất Bằng Thứ Hạng, Không Cộng Raw Score

**Thời lượng ước tính:** 1 phút 20 giây

**Kịch bản thuyết trình:**
RRF, tức Reciprocal Rank Fusion, hợp nhất các ranker dựa trên thứ hạng. Công thức là tổng của `weight * 1 / (rrf_k + rank)`.

Điểm hay là RRF không phụ thuộc raw score của từng ranker. PageRank, timestamp và causal-lag có bản chất score khác nhau, nên cộng trực tiếp sẽ không ổn định. Dùng rank giúp phản ánh sự đồng thuận tốt hơn.

Trong ví dụ, `payment-svc` rank 1 sau fusion. Output vẫn giữ `ranker_ranks`, tức là mình biết từng ranker đánh giá service này như thế nào. Ngoài ra còn có `evidence_ids` để trỏ về metric và log ủng hộ candidate này.

Confidence gap cũng rất quan trọng. Nếu top 1 và top 2 quá sát nhau, decision layer sẽ không nên quá tự tin.

**Chuyển ý sang slide tiếp theo:**
Sau RCA, ta đã có culprit candidate. Bước cuối cùng là chọn remediation action.

**Cụm từ cần nhấn mạnh:**
RRF đo sự đồng thuận bằng thứ hạng.

## Slide 17: LLM Remediation Decision

**Thời lượng ước tính:** 40 giây

**Kịch bản thuyết trình:**
Feature 004 là lớp ra quyết định cuối cùng. Module này kết hợp RCA output, historical incidents, action catalog và optional LLM.

Điểm cần nhấn mạnh là LLM không thay thế RCA. LLM chỉ hỗ trợ reasoning hoặc summarization. Final decision vẫn phải đi qua validation, action catalog và guardrails.

**Chuyển ý sang slide tiếp theo:**
Trước hết, em sẽ nói về phần retrieval lịch sử, vì đây là nguồn chính để action voting có cơ sở.

**Cụm từ cần nhấn mạnh:**
LLM là helper, không phải người quyết định tự do.

## Slide 18: History Corpus Hiện Tại Là `incidents_history.json`

**Thời lượng ước tính:** 1 phút 20 giây

**Kịch bản thuyết trình:**
Phần retrieval hiện tại có thể gọi là RAG-style retrieval trên structured history. Corpus chính là file `data-pack/incidents_history.json`. Đây chưa phải vector database đầy đủ, nhưng có cùng ý tưởng: lấy incident hiện tại, tìm các incident lịch sử giống nhất, rồi dùng chúng làm context cho decision.

Similarity được tính từ service overlap, log signatures, trace signatures, metric signatures, và có bonus nếu RCA top culprit xuất hiện trong affected services của incident lịch sử.

Sau khi retrieve top neighbors, hệ thống parse `actions_taken` và tính action vote theo công thức `similarity * outcome_weight`. Action từng success có trọng số cao hơn, partial thấp hơn, failed rất thấp.

Song song đó, `actions.yaml` đóng vai trò action catalog: action nào hợp lệ, cần params gì, cost/downtime/blast radius ra sao.

**Chuyển ý sang slide tiếp theo:**
Kết quả cuối cùng của decision layer là một JSON chứa action, params, confidence và evidence.

**Cụm từ cần nhấn mạnh:**
RAG-style retrieval từ structured history.

## Slide 19: Final Decision Giữ Cả Action, Confidence Và Evidence

**Thời lượng ước tính:** 1 phút

**Kịch bản thuyết trình:**
Đây là ví dụ final decision. `selected_action` là `rollback_service`, params chỉ rõ service là `payment-svc` và target version là `previous`.

`confidence` thể hiện độ tin cậy cuối cùng. Trong tương lai, field này có thể dùng để đặt threshold auto-run, ví dụ chỉ tự động chạy action nếu confidence đủ cao.

Trong `evidence`, field `method` cho biết quyết định đến từ LLM augmented hay fallback. Ở ví dụ này là `llm-guarded-fallback`, nghĩa là có LLM nhưng guardrail đã can thiệp.

Các field như `top_3_neighbors`, `dominant_signals`, và `blast_radius_check` giúp người vận hành hiểu tại sao action được chọn và mức rủi ro của action.

**Chuyển ý sang slide tiếp theo:**
Để quyết định này an toàn, hệ thống cần guardrails rõ ràng.

**Cụm từ cần nhấn mạnh:**
Decision phải executable và audit được.

## Slide 20: LLM Được Dùng Có Kiểm Soát

**Thời lượng ước tính:** 1 phút

**Kịch bản thuyết trình:**
Slide này tóm tắt các guardrails chính.

Thứ nhất, `root_cause_service` mà LLM đề xuất phải nằm trong RCA candidates. Điều này ngăn LLM tự bịa ra service ngoài evidence.

Thứ hai, `selected_action` phải tồn tại trong `actions.yaml`, và phải đủ required params. Ví dụ rollback thì cần service và target version.

Thứ ba, nếu LLM off, thiếu key, trả invalid JSON, hoặc conflict với safety check, hệ thống dùng deterministic fallback.

Cuối cùng, nếu evidence mới, yếu, hoặc có conflict, hệ thống escalate bằng `page_oncall`. Đây là guardrail để không auto-remediate khi chưa đủ cơ sở.

**Chuyển ý sang slide tiếp theo:**
Tất cả các quyết định và guardrails này chỉ có giá trị nếu mình truy ngược được về evidence gốc.

**Cụm từ cần nhấn mạnh:**
Guardrails biến LLM thành helper an toàn.

## Slide 21: Mỗi Quyết Định Đều Truy Ngược Được Về Evidence

**Thời lượng ước tính:** 1 phút

**Kịch bản thuyết trình:**
Slide này nói về traceability end-to-end.

Ở Detection, ta có `source_ref` và `evidence_candidates`. Ở RCA, ta có `root_causes` với candidate, ranker ranks, warnings và confidence. Ở Remediation, ta có final decision, prompt, response và audit line.

Chuỗi truy vết là: `source_ref` chỉ về path trong incident JSON, `evidence_id` định danh signal, `cluster_id` cho biết signal thuộc incident context nào, `root_cause_service` cho biết culprit, và `selected_action` là quyết định cuối.

Nhờ chuỗi này, khi người vận hành hỏi “vì sao rollback payment-svc?”, mình không trả lời chung chung. Mình có thể chỉ ra metric nào, log nào, cluster nào, RCA ranking nào, và incident lịch sử nào đã được dùng.

**Chuyển ý sang slide tiếp theo:**
Em sẽ kết thúc bằng một recap ngắn về các thông điệp chính của deck.

**Cụm từ cần nhấn mạnh:**
Không có quyết định nào mất dấu evidence.

## Slide 22: Thông Điệp Chính Cho Slide Deck

**Thời lượng ước tính:** 1 phút

**Kịch bản thuyết trình:**
Để tổng kết, project này có bốn điểm chính.

Thứ nhất, mỗi feature có input/output contract rõ ràng. Các field như `incident_id`, `service`, `evidence_id`, `cluster_id` nối các stage lại với nhau.

Thứ hai, mỗi field đều có “đời sau”. Score dùng cho ranking, fingerprints dùng cho retrieval, warnings và confidence dùng cho guardrails, `source_ref` dùng cho audit.

Thứ ba, mình luôn phân biệt culprit và victim. Alert service chỉ là điểm bắt đầu điều tra, không phải action target mặc định.

Cuối cùng, LLM không thay thế evidence. Final decision vẫn dựa trên RCA, history, action catalog và safety checks.

Nếu cần nói một câu ngắn gọn về project, em sẽ nói: đây là một remediation engine đi từ evidence có cấu trúc tới action có kiểm soát và audit được.

**Chuyển ý sang slide tiếp theo:**
Kết thúc phần trình bày. Nếu có câu hỏi, em có thể đi sâu vào từng stage hoặc mở artifact JSON để demo evidence chain.

**Cụm từ cần nhấn mạnh:**
Evidence có cấu trúc, action có kiểm soát.
