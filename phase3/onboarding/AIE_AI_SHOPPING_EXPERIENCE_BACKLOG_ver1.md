# AI Shopping Experience Backlog

## Tổng quan

Backlog này gộp hai luồng công việc: Trustworthy AI cho phần product reviews và Shopping Copilot cho trải nghiệm mua sắm có AI hỗ trợ. Mục tiêu chung là xây dựng một luồng AI có thể tin cậy được: câu trả lời phải có bằng chứng, dữ liệu đầu vào phải được xem là không đáng tin mặc định, hành động có tác động tới giỏ hàng phải được backend kiểm soát, và toàn bộ pipeline phải có timeout, fallback, cache, metric để vận hành ổn định.

Ở hiện trạng, phần lớn logic AI đang xoay quanh hàm `get_ai_assistant_response` trong `src/product-reviews/product_reviews_server.py`. Service gọi LLM để chọn tool, dùng dữ liệu review hoặc catalog, rồi trả câu trả lời cuối cùng về frontend. Backlog tổng hợp này ưu tiên làm chắc phần tin cậy và an toàn của luồng hiện có trước, sau đó mở rộng thành Shopping Copilot có thể tìm sản phẩm, trả lời câu hỏi dựa trên review, chuẩn bị thao tác thêm vào giỏ, và hỗ trợ hội thoại nhiều lượt.

## Mục tiêu sản phẩm

- Làm cho câu trả lời AI về review sản phẩm có thể kiểm chứng bằng review gốc.
- Xem review, câu hỏi người dùng, và tool arguments là dữ liệu không đáng tin mặc định.
- Ngăn prompt injection, rò rỉ PII, và tool execution ngoài phạm vi cho phép.
- Cải thiện độ ổn định, chi phí, và khả năng quan sát của các luồng dùng LLM.
- Mở rộng Shopping Copilot mà không cho phép hallucinate sản phẩm hoặc tự ý ghi vào giỏ hàng.
- Thêm orchestration nhiều lượt có giới hạn rõ về state, số bước, tool call, và deadline.

## Backlog Summary

Trước khi đi vào kế hoạch tám ngày, phần này tóm tắt toàn bộ backlog trong hai tài liệu. Mỗi backlog gồm mục tiêu, phạm vi xử lý và kết quả dự kiến.

| Backlog | Title | Description | Outcome |
| --- | --- | --- | --- |
| A1.1 | Verified Summarization, Grounding, and Citations | Kiểm chứng các nhận định do mô hình tạo ra bằng nội dung đánh giá thực tế. Mỗi nhận định được liên kết với nguồn cụ thể. Hệ thống sử dụng câu trả lời thay thế khi không có đủ bằng chứng. | Câu trả lời chỉ chứa nhận định có nguồn hợp lệ. Người dùng có thể xác định nội dung đánh giá được sử dụng làm bằng chứng. |
| A1.2 | Prompt Injection, PII, and System Prompt Protection | Xem câu hỏi và nội dung đánh giá là dữ liệu không đáng tin cậy. Giới hạn công cụ được phép gọi, kiểm tra tham số công cụ, che dữ liệu cá nhân và ngăn yêu cầu tiết lộ chỉ dẫn hệ thống. | Nội dung độc hại không thể thay đổi công cụ hoặc sản phẩm được truy vấn. Dữ liệu cá nhân không được ghi nguyên văn vào nhật ký và dữ liệu theo dõi. |
| A1.3 | Resilience and Cost Optimization | Bổ sung giới hạn thời gian, thử lại có kiểm soát, câu trả lời thay thế, lưu tạm kết quả đã kiểm chứng và số liệu theo dõi hoạt động của mô hình. | Lỗi hoặc phản hồi chậm từ mô hình không làm gián đoạn luồng chính. Các yêu cầu lặp lại có thể sử dụng kết quả đã lưu và giảm số lần gọi mô hình. |
| A2.1 | Natural Language Product Discovery | Chuyển yêu cầu tìm kiếm tự nhiên thành từ khóa, mức giá và đặc tính sản phẩm. Kết quả được lấy từ danh mục, sau đó được lọc và xếp hạng bằng mã chương trình. | Người dùng tìm được sản phẩm phù hợp với điều kiện mô tả. Hệ thống không tạo ra sản phẩm không tồn tại trong danh mục. |
| A2.2 | Review Grounded Product Question Answering | Trả lời câu hỏi về sản phẩm dựa trên nội dung đánh giá. Tính năng tái sử dụng cơ chế kiểm chứng của A1.1 và sử dụng sản phẩm đã xuất hiện trong hội thoại. | Câu trả lời về sản phẩm có nguồn dẫn chứng. Hệ thống thông báo thiếu thông tin khi đánh giá không hỗ trợ nội dung được hỏi. |
| A2.3 | Confirmation Controlled Cart Actions | Tạo hành động chờ khi người dùng yêu cầu thêm sản phẩm vào giỏ hàng. Hệ thống chỉ thực hiện thay đổi sau khi kiểm tra xác nhận, người dùng, thời hạn và tính toàn vẹn của tham số. | Không có thay đổi giỏ hàng trước khi nhận xác nhận hợp lệ. Mã hết hạn, bị thay đổi hoặc đã được sử dụng không thể tạo thêm thao tác ghi. |
| A2.4 | Multi Turn Conversations and Bounded Orchestration | Lưu trạng thái hội thoại, danh sách sản phẩm đã xuất hiện và hành động đang chờ. Hệ thống xử lý tham chiếu giữa các lượt và giới hạn số bước, số lần gọi công cụ cùng thời gian thực hiện. | Người dùng có thể tiếp tục hội thoại bằng các tham chiếu như sản phẩm đầu tiên. Các yêu cầu được xử lý trong giới hạn tài nguyên xác định. |

## Thứ tự triển khai đề xuất

Thứ tự này được suy ra từ ba tiêu chí chính: dependency-first, risk-first, và backend-enforcement-first. Nếu formal hóa theo bộ `pm-product-discovery/prioritize-features`, đây là cách xếp hạng dựa trên impact, risk, strategic alignment, và effort. Những hạng mục chặn rủi ro sai thông tin, prompt injection, rò rỉ PII, hoặc write action không kiểm soát được đưa lên trước; những hạng mục tối ưu vận hành hoặc mở rộng UX nhiều lượt được đặt sau khi foundation đã ổn định.

1. Xây grounding, citation, và abstention cho câu trả lời về product reviews.
2. Thêm guardrails cho prompt injection, PII redaction, và tool argument validation.
3. Thêm timeout, retry, fallback, cache, và metric về chi phí/độ trễ.
4. Thêm natural-language product discovery trên nền catalog search.
5. Tái sử dụng grounding pipeline cho product question answering.
6. Thêm confirmation-controlled cart actions.
7. Thêm bounded multi-turn conversation state và reference resolution.

---

## A1.1 - Verified Summarization, Grounding, and Citations

### Tóm tắt

Câu tóm tắt review sản phẩm phải được kiểm chứng với review thật trước khi trả cho người dùng. Backend cần yêu cầu model trả output có cấu trúc, gồm claim và source ID, sau đó validate claim đó có trỏ tới review hợp lệ hay không. Khi không đủ bằng chứng, hệ thống phải biết từ chối trả lời chi tiết thay vì đoán.

### Vấn đề

Luồng hiện tại fetch product reviews rồi yêu cầu LLM trả lời dựa trên tool result, nhưng sau đó trả thẳng `final_response.choices[0].message.content` mà không kiểm tra từng nhận định có được review hỗ trợ hay không. Feature flag `llmInaccurateResponse` còn cho thấy hệ thống có thể cố tình sinh câu trả lời sai mà không có bước backend nào chặn lại trước khi trả ra frontend.

Payload `ProductReview` hiện chỉ có `username`, `description`, và `score`, chưa có source ID ổn định cho từng review. Response gRPC cũng chỉ trả text, nên frontend chưa có citation có cấu trúc để hiển thị hoặc kiểm tra.

### Cách tiếp cận

- Gắn source ID ổn định cho mỗi review trước khi đưa vào model.
- Yêu cầu model trả structured output gồm `summary`, `claims`, và `sources`.
- Thêm `grounding.py` trong `src/product-reviews/` để validate claim-to-source.
- Bản đầu tiên có thể structural check: mọi source ID được cite phải tồn tại trong tập review đã fetch.
- Nếu eval cho thấy structural check chưa đủ, bổ sung semantic validation ở bước sau.
- Chỉ đưa claim đã validate vào response cuối.
- Dùng câu abstention cố định khi review không cung cấp đủ bằng chứng.
- Cân nhắc mở rộng `pb/demo.proto` nếu citation cần trở thành field chính thức trong response.

### Độ ưu tiên

P1. Đây là nền tảng cho toàn bộ các capability AI phía sau. Cache, review Q&A, và Shopping Copilot đều rủi ro hơn nếu hệ thống có thể lặp lại một claim không có bằng chứng.

### Phụ thuộc và câu hỏi mở

- Cần xác nhận review ID nên được sinh từ `product_id` + hash nội dung review hay thêm trực tiếp vào protobuf schema.
- Cần xác nhận contract citation với frontend và team product-catalog.
- Cần chạy baseline eval nhỏ khoảng 20-30 câu hỏi review cố định trước và sau khi triển khai.

---

## A1.2 - Prompt Injection, PII, and System Prompt Protection

### Tóm tắt

Review và câu hỏi người dùng phải được xử lý như untrusted input. Service cần bảo vệ system prompt, validate tool call và arguments, đồng thời redact dữ liệu nhạy cảm trước khi gửi cho LLM hoặc ghi vào log/trace.

### Vấn đề

Nội dung review là user-generated content nhưng hiện được đưa vào message cho model như dữ liệu đáng tin. Một review độc hại có thể chứa instruction kiểu "ignore previous instructions" hoặc yêu cầu lộ system prompt. Code hiện có reject tool name lạ, đây là điểm tốt, nhưng vẫn chưa validate argument do model sinh ra có nằm trong phạm vi request gốc hay không.

Service cũng đang ghi raw user question và full LLM messages vào telemetry. Nếu người dùng nhập email, số điện thoại, hoặc thông tin nhạy cảm khác, dữ liệu đó có thể bị nhân bản sang LLM request, OpenSearch, và Jaeger.

### Cách tiếp cận

- Bỏ `username` khỏi payload gửi cho model nếu không thật sự cần.
- Bọc review content trong boundary rõ ràng như `REVIEW_DATA` để phân biệt dữ liệu và instruction.
- Cập nhật system prompt để nói rõ review content chỉ là bằng chứng, không phải chỉ dẫn.
- Thêm backend enforcement cho tool arguments, đặc biệt là `product_id`.
- Reject tool call nếu `product_id` model trả về khác với `product_id` của request gốc.
- Thêm `guardrails.py` cho prompt-injection detection, PII redaction, và argument validation.
- Redact PII trước khi gọi LLM, ghi log, hoặc set trace attributes.
- Thay trace raw `app.product.question` bằng metadata an toàn như product ID, prompt length, intent, và redaction status.
- Chặn các request cố tình yêu cầu lộ system prompt hoặc override tool policy.

### Độ ưu tiên

P1. Đây là kiểm soát về bảo mật và riêng tư dữ liệu, không chỉ là cải thiện chất lượng câu trả lời. Nên triển khai song song hoặc ngay sau A1.1 vì cả hai đều thay đổi cách build message và execute tool trong cùng luồng.

### Phụ thuộc và câu hỏi mở

- Cần xác nhận yêu cầu detect PII cho tiếng Việt và định dạng số điện thoại Việt Nam.
- Cần xác nhận nên dùng thư viện PII bên ngoài hay bản đầu tiên chỉ dùng regex nhẹ.
- Cần xác nhận policy retention/redaction với DevOps/CloudOps.

---

## A1.3 - Resilience and Cost Optimization

### Tóm tắt

AI review response nên là best-effort và không được kéo sập trải nghiệm trang sản phẩm khi LLM chậm, lỗi, hoặc quá tốn kém. Service cần timeout, retry có giới hạn, fallback, cache, và metric cho latency, token usage, cache hit rate, và fallback rate.

### Vấn đề

Luồng assistant hiện gọi LLM tối thiểu hai lần cho mỗi request: một lần để chọn tool và một lần để tổng hợp câu trả lời cuối. Các call này chưa có timeout riêng, chưa có deadline tổng, và chưa có fallback nhất quán khi LLM thật bị lỗi. Hệ thống cũng chưa có cache, nên cùng một câu hỏi trên cùng một tập review chưa đổi vẫn bị regenerate và tốn thêm latency/token.

Metrics hiện tại chủ yếu đếm request tổng, chưa cho thấy LLM latency, token usage, estimated cost, cache hit/miss, hay fallback frequency.

### Cách tiếp cận

- Thêm timeout rõ ràng cho từng OpenAI SDK call.
- Thêm total deadline cho toàn bộ assistant request.
- Chỉ retry lỗi tạm thời như 429 và 5xx trong phần deadline còn lại.
- Trả fallback thân thiện thay vì để exception từ LLM làm fail luồng trang sản phẩm.
- Chỉ cache summary đã qua grounding và validation.
- Không cache raw response chưa validate, response bị guardrail chặn, hoặc fallback response.
- Tạo cache key từ `product_id`, review content hash, model name, prompt version, và guardrail version.
- Thêm `cache.py` để quản lý cache key và read/write.
- Mở rộng `metrics.py` với LLM latency, token usage, estimated cost, cache hit/miss, và fallback counters.

### Độ ưu tiên

P2. Thấp hơn A1.1 và A1.2 một bậc vì chủ yếu xử lý reliability và operating cost. Tuy vậy vẫn nên làm sớm vì Shopping Copilot sẽ làm số LLM/tool call trên mỗi interaction tăng lên.

### Phụ thuộc và câu hỏi mở

- Cần xác nhận AI cache dùng chung `valkey-cart` với namespace riêng hay dùng Valkey instance riêng.
- Cần xác nhận timeout/retry budget với SLO của product page.
- Cần xác nhận có cần dependency retry/backoff riêng hay local implementation là đủ.

---

## A2.1 - Natural Language Product Discovery

### Tóm tắt

Người dùng nên tìm được sản phẩm bằng điều kiện tự nhiên như giá, danh mục, và tính năng. Agent cần chuyển câu hỏi thành intent có cấu trúc, gọi catalog search, filter/rank bằng code, và không được tự tạo sản phẩm ngoài catalog result.

### Vấn đề

`ProductCatalogService.SearchProducts` đã có trong `pb/demo.proto`, nhưng implementation Go hiện chủ yếu dùng `LIKE` trên name và description. Query như "Tìm tai nghe chống ồn dưới $50" khó hoạt động tốt vì chứa cả feature và price constraint. Frontend gateway cũng chưa expose `SearchProducts`, nên luồng UI tới catalog search chưa hoàn chỉnh.

Nếu không có intent parsing và code-side filtering, người dùng có thể nhận kết quả rỗng hoặc phải tự lọc thủ công. Nếu model tự điền kết quả khi catalog không trả về gì, hệ thống sẽ có nguy cơ hallucinate sản phẩm không tồn tại.

### Cách tiếp cận

- Parse natural language thành intent có cấu trúc như `search_term`, `features`, `category`, và `max_price_usd`.
- Gọi `SearchProducts` với query ngắn và phù hợp cho catalog retrieval.
- Filter và rank sản phẩm bằng backend code dựa trên name, description, category, và price.
- Trả no-results response rõ ràng khi không có catalog item nào thỏa điều kiện.
- Thêm `product_search.py` dưới `src/product-reviews/` cho intent parsing, catalog calls, filtering, và ranking.
- Bổ sung frontend gateway support cho catalog search nếu cần.
- Chỉ mở rộng `pb/demo.proto` hoặc `src/product-catalog/main.go` nếu eval chứng minh search contract hiện tại không đủ.

### Độ ưu tiên

P1. Đây là entry point của Shopping Copilot. Review Q&A, cart actions, và reference resolution đều phụ thuộc vào product ID đáng tin từ search.

### Phụ thuộc và câu hỏi mở

- Cần xác nhận `SearchProductsRequest` hiện tại có đủ dùng hay cần thêm structured filters.
- Cần xác nhận đường tích hợp frontend để expose `SearchProducts`.
- Cần định nghĩa no-results UX copy và ranking expectation.

---

## A2.2 - Review Grounded Product Question Answering

### Tóm tắt

Shopping Copilot phải trả lời câu hỏi về sản phẩm bằng cùng grounding và citation pipeline của product review summaries. Khi review không hỗ trợ câu trả lời, agent phải abstain thay vì suy đoán.

### Vấn đề

Product AI assistant hiện có thể fetch reviews, nhưng response cuối chưa được validate với review đó. Người dùng có thể hỏi câu cụ thể và nhận câu trả lời nghe hợp lý nhưng không có bằng chứng. Request hiện cũng chỉ có `product_id` và `question`, nên chưa resolve được tham chiếu như "cái đầu tiên" sau một lượt search.

### Cách tiếp cận

- Tái sử dụng `grounding.py` từ A1.1 cho review-grounded Q&A.
- Resolve product references từ conversation state sau khi A2.4 có sẵn.
- Fetch product reviews cho product đã resolve.
- Yêu cầu structured output gồm claim và citation.
- Chỉ trả câu trả lời đã validate.
- Abstain khi không có evidence.
- Giữ một grounding policy dùng chung cho review summaries và Shopping Copilot answers.

### Độ ưu tiên

P1. Nên làm song song hoặc ngay sau A1.1 để tránh viết hai implementation grounding khác nhau cho các response đều dựa trên review.

### Phụ thuộc và câu hỏi mở

- Phụ thuộc A1.1 grounding.
- Phụ thuộc A2.4 cho tham chiếu nhiều lượt như "cái đầu tiên".
- Cần xác nhận cách hiển thị citation trong Shopping Copilot UI.

---

## A2.3 - Confirmation Controlled Cart Actions

### Tóm tắt

Shopping Copilot có thể chuẩn bị thao tác thêm vào giỏ, nhưng backend phải yêu cầu người dùng xác nhận rõ ràng trước khi gọi `CartService.AddItem`. Prompt instruction không đủ an toàn cho write action.

### Vấn đề

`CartService.AddItem` thay đổi trạng thái giỏ hàng. Nếu agent được phép gọi trực tiếp, prompt injection hoặc lỗi model có thể thêm sản phẩm mà người dùng chưa thật sự đồng ý. Scope capstone cũng không cho phép agent tự checkout hoặc empty cart, nên tool registry phải giới hạn chặt các action được expose.

### Cách tiếp cận

- Dùng cart action flow hai bước.
- Lượt đầu: tạo `pending_action` gồm product ID, quantity, và confirmation token.
- Hỏi người dùng xác nhận đúng thay đổi sẽ áp dụng vào giỏ.
- Lượt sau: backend validate token, user ownership, TTL, idempotency, và action parameters không bị đổi.
- Chỉ gọi `CartService.AddItem` sau khi backend validation thành công.
- Lưu one-time token trong Valkey với TTL.
- Thêm `cart_actions.py` cho pending action creation, confirmation validation, và write blocking.
- Không bao giờ đăng ký `EmptyCart` hoặc checkout tools trong agent tool registry.
- Luôn lấy user identity từ session context, không lấy từ argument do model sinh.

### Độ ưu tiên

P1. Đây là invariant an toàn bắt buộc cho mọi AI flow có thể ghi vào giỏ hàng.

### Phụ thuộc và câu hỏi mở

- Phụ thuộc A2.1 để có product ID đáng tin.
- Phụ thuộc A2.4 để giữ pending action qua nhiều lượt.
- Cần xác nhận confirmation token dùng chung `valkey-cart` với namespace riêng hay dùng store riêng.

---

## A2.4 - Multi Turn Conversations and Bounded Orchestration

### Tóm tắt

Shopping Copilot cần hỗ trợ hội thoại nhiều lượt, product references, và pending actions nhưng vẫn phải nằm trong execution budget rõ ràng. Conversation state nên ngắn hạn, cách ly theo user/session, và lưu trong backend store dùng chung để nhiều pod cùng truy cập được.

### Vấn đề

`ProductAIAssistant.provider.tsx` hiện chỉ giữ một AI response và reset trước mỗi request. RPC contract hiện có `product_id` và `question`, nhưng chưa có `conversation_id`, message history, product references, pending action, hoặc status. Vì vậy các tham chiếu như "cái đó", "sản phẩm đầu tiên", hoặc "thêm hai cái đó" không thể resolve đáng tin.

Nếu mở agent loop mà không giới hạn, model có thể gọi tool liên tục, tăng chi phí, và vượt latency budget của product page.

### Cách tiếp cận

- Mở rộng request/response contract với `conversation_id`, `message`, `product_references`, `sources`, `pending_action`, và `status`.
- Cập nhật frontend provider để giữ danh sách message thay vì một response đơn.
- Lưu conversation state ngắn hạn trong Valkey với TTL.
- Track product references sau search, ví dụ danh sách product IDs theo thứ tự kết quả gần nhất.
- Resolve các tham chiếu như "cái đầu tiên" hoặc "sản phẩm đó".
- Thêm `conversation.py` cho state management và reference resolution.
- Thêm `orchestrator.py` cho bounded agent execution.
- Giới hạn số vòng, số tool call, và total deadline, ví dụ tối đa bốn vòng và tám tool calls cho mỗi request.
- Tách read tools và write tools trong tool registry.
- Loại `cart.empty` và checkout tools khỏi agent surface.

### Độ ưu tiên

P2. Nên làm sau khi single-turn search và grounded Q&A đã ổn định. A2.4 cần cho Shopping Copilot hoàn chỉnh và confirmation-controlled cart actions, nhưng sẽ dễ validate hơn khi các capability đơn lượt đã đáng tin.

### Phụ thuộc và câu hỏi mở

- Phụ thuộc A2.1 để có product references từ search.
- Phụ thuộc A2.2 để có grounded answers trong conversation history.
- Hỗ trợ A2.3 bằng cách giữ pending cart actions qua nhiều lượt.
- Cần xác nhận backward compatibility khi thêm conversation fields vào protobuf.
- Cần xác nhận Valkey TTL, namespace, và session isolation.

---

## Hạng mục kỹ thuật xuyên suốt

### Protobuf và contract

- Thêm source IDs và citations nếu citation cần là first-class field.
- Thêm conversation fields cho Shopping Copilot state.
- Giữ backward compatibility nếu có thể.
- Regenerate clients và servers sau khi đổi `pb/demo.proto`.

### Evaluation

- Tạo fixed eval set cho review QA và summarization.
- Đo unsupported claim rate trước và sau grounding.
- Thêm prompt-injection test cases với malicious reviews và user questions.
- Thêm cart-action tests chứng minh không thể write nếu chưa xác nhận.
- Thêm no-results search tests để đảm bảo agent không hallucinate sản phẩm.

### Observability

- Track LLM latency theo call type.
- Track token usage và estimated cost.
- Track grounding pass/fail và abstention rate.
- Track guardrail block rate và PII redaction status.
- Track cache hit/miss.
- Track fallback rate.
- Track pending-action creation, confirmation, rejection, expiry, và replay attempts.

### Security và privacy

- Xem mọi review text, user message, và model output là untrusted.
- Không dựa vào prompt instruction làm control duy nhất cho tool execution.
- Redact PII trước khi ghi log, trace, hoặc gọi LLM.
- Không lấy user identity hoặc authorization từ model-generated arguments.
- Dùng backend allow-list cho tools và tool arguments.

## Eight Day Implementation Plan

Kế hoạch tám ngày này giả định team có hai người. Mỗi người phụ trách trọn vẹn phần mình gồm lập trình, kiểm thử, và kiểm tra giao diện liên quan. Cách chia dựa trên sprint planning của `pm-execution`: gom việc theo dependency, giảm handoff, giữ một critical path rõ ràng, và dành khoảng 15-20% thời gian mỗi ngày cho bug, review, và integration issue.

### Workstream Ownership

| Owner | Primary Scope | Backlogs | Responsibility |
| --- | --- | --- | --- |
| Person A | Trustworthy AI foundation | A1.1, A1.2, A1.3, support A2.2 | Grounding, guardrails, PII redaction, resilience, cache, metrics, review QA validation. |
| Person B | Shopping Copilot capability | A2.1, A2.3, A2.4, support A2.2 | Product discovery, cart confirmation, conversation state, bounded orchestration, UI flow checks. |

### Day 1 - Align Contracts and Split Interfaces

- Person A xác định source ID format, structured output schema, citation format, và abstention copy cho A1.1.
- Person A tạo test fixture review và baseline eval nhỏ cho unsupported claims.
- Person B xác định Shopping Copilot request/response shape ở mức draft: search result, product references, pending action, và conversation status.
- Hai người chốt shared contracts: citation shape, product reference shape, error/fallback shape, và UI states cần kiểm tra.

### Day 2 - Build Grounding Foundation and Search Skeleton

- Person A cập nhật message construction để model trả claim/source có cấu trúc.
- Person A bắt đầu `grounding.py` với structural validation và abstention path.
- Person B tạo skeleton `product_search.py`, parse intent cơ bản, và nối tới catalog search hiện có.
- Person B kiểm tra no-results path để đảm bảo hệ thống không sinh sản phẩm ngoài catalog.

### Day 3 - Complete A1.1 and Product Discovery MVP

- Person A hoàn thiện A1.1: chỉ trả claim có source hợp lệ, chạy unit test, eval nhỏ, và kiểm tra UI review response.
- Person B hoàn thiện A2.1 MVP: filter/rank bằng code theo price, category, và features.
- Hai người sync để A2.1 output có product ID và product references dùng được cho A2.2/A2.4.
- Integration check: search result có thể dẫn tới câu hỏi review-grounded ở bước sau.

### Day 4 - Guardrails and Review-Grounded Q&A

- Person A triển khai A1.2: `guardrails.py`, prompt injection detection, PII redaction, và tool argument validation.
- Person A kiểm tra log/trace để dữ liệu cá nhân không còn được ghi nguyên văn.
- Person B triển khai A2.2 bằng cách tái sử dụng `grounding.py` từ A1.1 cho product question answering.
- Hai người kiểm tra flow: search sản phẩm, hỏi review, câu trả lời có source hoặc abstain khi thiếu evidence.

### Day 5 - Resilience and Conversation State

- Person A triển khai A1.3: timeout, retry có giới hạn, fallback, cache cho response đã validate, và metric cơ bản.
- Person B bắt đầu A2.4: conversation state, product references, và reference resolution cho các câu như "sản phẩm đầu tiên".
- Hai người thống nhất cache key và state key để không cache response chưa validate hoặc state sai user/session.
- UI check: AI tạm thời không khả dụng thì product page và search flow vẫn hoạt động.

### Day 6 - Cart Confirmation and Bounded Orchestration

- Person A bổ sung metrics/fallback coverage cho các luồng A2 dùng LLM hoặc grounding.
- Person B triển khai A2.3: `pending_action`, confirmation token, TTL, idempotency check, và backend-only `CartService.AddItem`.
- Person B tiếp tục A2.4: giới hạn số vòng, số tool call, và total deadline.
- Hai người kiểm tra guardrail cho write action: không expose checkout hoặc empty-cart trong agent tool registry.

### Day 7 - Integration, UI Validation, and Negative Tests

- Person A chạy test cho grounding, injection, PII redaction, fallback, cache hit/miss, và metric emission.
- Person B chạy test cho product discovery, reference resolution, pending action, confirm/reject, expired token, và replay token.
- Hai người chạy end-to-end flow: search -> review Q&A -> add-to-cart confirmation -> multi-turn reference.
- Sửa các lỗi integration, UI copy, và edge case ảnh hưởng tới demo.

### Day 8 - Hardening and Demo Readiness

- Person A harden A1.x: eval kết quả, log/trace review, fallback behavior, và dashboard/metric readiness.
- Person B harden A2.x: conversation state cleanup, bounded orchestration, cart confirmation UX, và no-results UX.
- Hai người cùng chạy final end-to-end test trên toàn bộ happy path và negative path.
- Chốt demo checklist, known limitations, và các assumption cần xác nhận sau sprint.

### Critical Path and Integration Notes

- A1.1 phải xong trước A2.2 vì product Q&A cần grounding pipeline.
- A1.2 phải có trước khi mở rộng tool surface cho search, review QA, cart action, và orchestration.
- A1.3 nên có trước khi multi-turn flow chạy nhiều LLM/tool calls.
- A2.1 phải có product ID đáng tin trước khi A2.3 tạo pending cart action.
- A2.4 có thể phát triển song song, nhưng reference resolution và pending action state chỉ demo được đầy đủ sau A2.1 và A2.3.
