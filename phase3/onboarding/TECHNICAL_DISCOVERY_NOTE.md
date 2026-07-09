# Technical Discovery Note - AI Shopping Experience

Phạm vi: A1.1, A1.2, A1.3, A2.1, A2.2, A2.3, A2.4.

Tài liệu này gộp technical discovery của hai workstream:

- Person 1: A1 Trustworthy AI foundation.
- Person 2: A2 Shopping Copilot capability.

Nội dung chỉ phục vụ discovery trước execution. Tài liệu không bao gồm implementation backlog chi tiết, không chốt code-level task cuối cùng, và không thay thế phần dependency/question đã có trong backlog tổng.

## 1. Current State

### A1 - Trustworthy AI Foundation

Các file và module chính:

- `phase3/techx-corp-platform/src/product-reviews/product_reviews_server.py`
  - Implement `ProductReviewService`.
  - Xử lý `GetProductReviews`, `GetAverageProductReviewScore`, `AskProductAIAssistant`.
  - Gọi OpenAI-compatible chat completion, cho model chọn tool, backend execute tool, rồi gọi model lần hai để tạo final response.
- `phase3/techx-corp-platform/src/product-reviews/database.py`
  - Fetch product reviews và average review score từ Postgres.
  - Query review đang dùng parameterized SQL theo `product_id`.
- `phase3/techx-corp-platform/src/product-reviews/metrics.py`
  - Hiện chỉ có counter cho số review trả về và số request AI assistant.
- `phase3/techx-corp-platform/src/product-reviews/requirements.txt`
  - Đang có `openai`, OpenTelemetry, OpenFeature/flagd, `psycopg2-binary`, `simplejson`, `grpcio-health-checking`.
- `phase3/techx-corp-platform/src/llm/app.py`
  - Mock LLM service tương thích OpenAI API.
  - Có tool-call response, static review summaries, inaccurate-response simulation, và rate-limit simulation.
- `phase3/techx-corp-platform/pb/demo.proto`
  - Contract hiện tại của `AskProductAIAssistant` chỉ gồm `product_id`, `question`, và response text.
- Frontend liên quan:
  - `src/frontend/gateways/rpc/ProductReview.gateway.ts`
  - `src/frontend/gateways/Api.gateway.ts`
  - `src/frontend/providers/ProductAIAssistant.provider.tsx`
  - `src/frontend/components/ProductReviews/ProductReviews.tsx`

Công nghệ đang dùng:

- Python gRPC service cho product reviews.
- OpenAI Python SDK trỏ tới mock LLM hoặc OpenAI-compatible endpoint.
- Postgres cho review data.
- gRPC/protobuf cho service contract.
- OpenTelemetry cho trace/log/metric.
- OpenFeature với flagd cho feature flag.
- Next.js/React frontend với React Query.
- Observability stack: OpenTelemetry Collector, Prometheus, Jaeger, Grafana, OpenSearch.

Luồng dữ liệu hiện tại:

1. Frontend gọi `ApiGateway.askProductAIAssistant(productId, question)`.
2. Gateway gọi gRPC `ProductReviewService.AskProductAIAssistant`.
3. `product_reviews_server.py` nhận `product_id` và raw `question`.
4. Service ghi trace attribute, hiện có cả raw `app.product.question`.
5. Service tạo prompt và gọi LLM kèm tool definitions.
6. Model có thể gọi `fetch_product_reviews` hoặc `fetch_product_info`.
7. Backend execute tool, append result vào messages.
8. Service gọi LLM lần hai để tạo final answer.
9. Final answer text được trả về qua `AskProductAIAssistantResponse.response`.
10. Frontend hiển thị plain text.

Thành phần có thể tái sử dụng:

- `ProductReviewService.AskProductAIAssistant` làm entry point cho A1/A2.
- `database.fetch_product_reviews_from_db` để lấy review evidence.
- `product_catalog_stub.GetProduct` cho product info.
- OpenAI-compatible SDK flow hiện có.
- Mock LLM để test deterministic và simulate failure.
- Feature flags `llmInaccurateResponse`, `llmRateLimitError`.
- OpenTelemetry setup hiện có.
- Frontend Ask AI UI hiện có cho MVP single response.
- Valkey đã tồn tại trong stack, nhưng việc dùng cho AI cache/conversation/pending action cần xác nhận namespace/ownership.

### A2 - Shopping Copilot Capability

Các file và module chính:

- `src/product-catalog/main.go`
  - Go service implement `ProductCatalogService`.
  - `searchProductsFromDB` đang search bằng `LIKE` trên `LOWER(p.name)` và `LOWER(p.description)`.
- `src/frontend/gateways/rpc/ProductCatalog.gateway.ts`
  - Hiện expose `listProducts` và `getProduct`.
  - Chưa expose `searchProducts`.
- `src/product-reviews/product_reviews_server.py`
  - AI assistant entry point.
  - Tool registry hiện có `fetch_product_reviews` và `fetch_product_info`.
  - Chưa có `search_catalog`, cart tools, conversation state, hoặc bounded orchestrator.
- `src/cart/src/Program.cs`
  - .NET cart service implement `CartService`.
  - `AddItem` là write action vào Valkey cart store.
- `src/frontend/gateways/rpc/Cart.gateway.ts`
  - Frontend hiện gọi cart trực tiếp qua API/gRPC.
- `src/frontend/providers/ProductAIAssistant.provider.tsx`
  - Hiện chỉ giữ một `aiResponse`.
  - Không có `conversation_id`, message history, product references, hoặc pending action.

Luồng dữ liệu hiện tại:

- Product search:

```text
Frontend -> Api.gateway.ts -> ProductCatalog gRPC SearchProducts
-> searchProductsFromDB LIKE query -> trả danh sách thô
```

- Review Q&A:

```text
Frontend -> POST /api/product-ask-ai-assistant/{productId}
-> AskProductAIAssistant gRPC -> get_ai_assistant_response
-> LLM tool call fetch_product_reviews -> final LLM call -> trả text thuần
```

- Cart:

```text
Frontend add-to-cart button -> POST /api/cart
-> CartService.AddItem gRPC -> Valkey
```

Hiện AI agent chưa có đường vào cart, chưa có pending action, chưa có confirmation token, và chưa có conversation state để resolve các tham chiếu như "cái đầu tiên".

Thành phần có thể tái sử dụng:

- `SearchProducts` RPC và `SearchProductsRequest` đã tồn tại trong proto.
- `product_catalog_stub` đã được khởi tạo trong `product_reviews_server.py`.
- Tool calling loop hiện có có thể mở rộng thêm tools.
- `fetch_product_reviews` và `fetch_product_info` đã hoạt động.
- Valkey có thể lưu conversation state và pending action nếu namespace được thống nhất.
- `SessionGateway.getSession()` giúp lấy `userId` từ session thay vì từ model-generated arguments.

## 2. Technical Gaps

### A1 Technical Gaps

| Gap | Related Backlog | Impact | Blocking | Open-source research |
| --- | --- | --- | --- | --- |
| Review records chưa có stable source ID trong response hoặc DB query output. | A1.1 | Chưa thể cite từng review một cách ổn định. | Chặn citation output và A2.2 reuse. | Không cần ngay. Có thể tự sinh ID/hash trong backend. |
| `AskProductAIAssistantResponse` chỉ trả plain text. | A1.1 | Frontend chưa nhận được structured claims, citations, status, fallback reason. | Chặn citation UI first-class nếu không encode vào text. | Không cần. Đây là contract/protobuf design. |
| Final LLM response được trả thẳng, chưa có backend validation cho claim và citation. | A1.1 | Claim sai hoặc thiếu evidence vẫn có thể tới user. | Chặn trustworthy summarization. | **DeepEval hoặc Ragas** cho offline eval semantic grounding/hallucination. Không đưa vào runtime path trong MVP. |
| Model output chưa có schema/structured format bắt buộc. | A1.1 | Khó parse và validate deterministic. | Chặn automated validation ổn định. | **Instructor + Pydantic** để ép LLM trả structured output, parse, retry khi sai format, và validate schema. |
| Backend chưa có abstention policy khi evidence không đủ. | A1.1 | Model có thể đoán thay vì từ chối. | Chặn safe unsupported-question behavior. | Không cần ngay. Có thể implement bằng rule/policy nội bộ. |
| Review content và user question chưa được xử lý rõ như untrusted data. | A1.2 | Prompt injection trong review/question có thể ảnh hưởng tool use hoặc final answer. | Chặn mở rộng tool surface an toàn. | **LLM Guard** để scan input/output cho prompt injection, system prompt extraction, policy override, secrets/data leakage. |
| Tool argument validation còn thiếu, đặc biệt `product_id` do model sinh ra. | A1.2 | Model có thể yêu cầu truy vấn product khác request gốc. | Chặn safe tool execution. | Không cần. Nên enforce bằng backend allow-list/rule. |
| Raw question và full messages đang được log/trace. | A1.2 | PII/prompt content có thể rò vào logs, traces, OpenSearch, hoặc external LLM request. | Chặn privacy-safe operation. | Dùng **Presidio** trước khi ghi log/trace/gửi LLM. |
| Chưa có PII redaction layer. | A1.2 | Email, phone, address, credit-card-like text có thể đi vào LLM/logs nguyên văn. | Chặn privacy requirement. | **Presidio** để detect/mask/redact/anonymize PII; bổ sung custom recognizer/regex cho phone Việt Nam và pattern domain riêng nếu cần. |
| `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true` đang bật. | A1.2 | GenAI instrumentation có thể capture prompt/message content. | Chặn bảo vệ prompt/PII nghiêm ngặt. | Không cần thư viện. Cần review config vận hành và chỉ capture safe metadata. |
| Chưa có telemetry sanitization ở pipeline sau app. | A1.2 | Nếu raw prompt lọt qua app logger/instrumentation, OpenSearch/Jaeger vẫn có thể lưu dữ liệu nhạy cảm. | Chặn privacy-safe observability. | Không cần thư viện app mới; cần cấu hình OpenTelemetry Collector để drop/hash/redact attributes nhạy cảm. |
| Chưa có per-call timeout và total deadline cho LLM flow. | A1.3 | LLM chậm có thể kéo dài product page request. | Chặn resilience target. | Không cần ngay nếu SDK timeout đủ dùng. Có thể đặt timeout trong `llm_client.py`. |
| Chưa có retry policy có kiểm soát cho lỗi tạm thời như 429/5xx. | A1.3 | Transient failure có thể fail luôn hoặc retry không theo budget. | Chặn resilience acceptance. | **Tenacity** cho retry/backoff, jitter, stop policy, callback/logging; chỉ retry lỗi transient trong total deadline. |
| Chưa có cache cho AI response đã validate. | A1.3 | Cùng question/review set vẫn gọi LLM lại, tăng latency và cost. | Chặn cost optimization. | Dùng lại **Valkey hiện có** với namespace riêng cho AI cache. |
| Chưa có Python client để `product-reviews` kết nối Valkey. | A1.3, A2.3, A2.4 | Valkey đã có trong stack, nhưng Python service vẫn cần client library và connection lifecycle rõ ràng. | Chặn AI cache, pending action, conversation state. | Chốt dùng **valkey-py** cho MVP vì đơn giản và đúng nhu cầu key/value + TTL. |
| Metrics mới chỉ đếm AI assistant requests. | A1.3 | Chưa thấy LLM latency, token usage, estimated cost, cache hit/miss, fallback rate, guardrail blocks, grounding failures. | Chặn operational readiness. | Không cần. Có thể mở rộng bằng OpenTelemetry hiện có. |
| Chưa có AI-specific unit/eval fixtures cho grounding, injection, PII, timeout, retry, cache. | A1.1, A1.2, A1.3 | Khó verify thay đổi và dễ lọt regression. | Chặn execution an toàn. | **DeepEval** phù hợp hơn nếu scope mở sang agent/tool workflow; **Ragas** phù hợp nếu chỉ eval review-grounded/RAG-style QA. |

### A2 Technical Gaps

| Gap | Related Backlog | Impact | Blocking | Open-source research |
| --- | --- | --- | --- | --- |
| Thiếu intent parser cho natural language search. | A2.1 | Không chuyển được câu tự nhiên thành `search_term`, `features`, `category`, `max_price_usd`. | Chặn product discovery tốt. | Không cần ngay nếu dùng rule/structured output hiện có. Có thể kế thừa **Instructor + Pydantic** nếu model parse intent. |
| `SearchProducts` chỉ search `LIKE`, chưa filter/rank theo price/features. | A2.1 | Kết quả search thô, khó xử lý query như "dưới $50" hoặc feature cụ thể. | Chặn ranking đáng tin. | Không cần ngay. Nếu LIKE không đủ, cân nhắc `sentence-transformers` sau eval. |
| `search_catalog` chưa có trong tool registry. | A2.1 | Agent chưa thể gọi catalog search. | Chặn Shopping Copilot entry point. | Không cần thư viện mới. |
| `SearchProducts` chưa expose ở frontend gateway. | A2.1 | UI không gọi search trực tiếp được nếu cần Copilot UI riêng. | Không chặn backend-first MVP. | Không cần thư viện mới. |
| Chưa có hallucination guard khi catalog no-results. | A2.1 | Agent có thể tự bịa product khi catalog không có kết quả. | Chặn product-grounded behavior. | Kế thừa guardrails và grounding policy từ A1; không cần thư viện riêng. |
| Review Q&A chưa có citation validation. | A2.2 | Answer có thể thiếu evidence. | Chặn review-grounded QA. | Kế thừa `grounding.py`, **Instructor + Pydantic**, và eval từ A1. |
| Review Q&A chưa có abstention khi evidence không đủ. | A2.2 | Model có thể đoán. | Chặn safe answer. | Không cần thư viện riêng. |
| Không có reference resolution cho "cái đầu tiên", "cái đó". | A2.2, A2.4 | Multi-turn không resolve được product ID. | Chặn Shopping Copilot nhiều lượt. | Không cần thư viện mới. |
| Response thiếu `sources` field. | A2.2 | Frontend không hiển thị citation được. | Chặn citation UX. | Không cần thư viện mới; cần protobuf/API change. |
| Chưa có pending action mechanism cho cart. | A2.3 | AI không thể chuẩn bị action chờ xác nhận. | Chặn cart confirmation flow. | Dùng lại **Valkey hiện có** với namespace `pending_action:*`. |
| Chưa có confirmation token và one-time validation. | A2.3 | Write action có thể bị replay hoặc sửa tham số. | Chặn safe cart action. | Không cần thư viện ngoài cho token/HMAC; dùng Python standard library và lưu state trên Valkey. |
| Chưa có stack/owner cho secret dùng ký confirmation token. | A2.3 | HMAC token cần secret ổn định, không hard-code, có thể rotate. | Chặn safe token signing. | Dùng cơ chế secret/env hiện có của deployment; cần thêm env như `PENDING_ACTION_SIGNING_SECRET`. |
| `CartService` stub chưa có trong `product-reviews`. | A2.3 | Backend AI chưa gọi cart được sau confirmation. | Chặn execute add-to-cart. | Không cần thư viện mới. |
| `EmptyCart` và checkout chưa bị loại khỏi agent surface bằng policy rõ. | A2.3 | Có nguy cơ expose nhầm destructive/write tools. | Chặn safe tool registry. | Không cần thư viện mới. |
| User ID có thể bị spoof nếu lấy từ model argument. | A2.3 | Agent injection có thể thao túng user/cart. | Chặn backend authorization. | Không cần thư viện mới; enforce session-bound identity. |
| Không có `conversation_id` và persisted state. | A2.4 | Mỗi request độc lập, không có multi-turn continuity. | Chặn conversation flow. | Dùng lại **Valkey hiện có** với namespace `conv:*`. |
| Không lưu `product_references`. | A2.4 | Không resolve được kết quả search trước đó. | Chặn reference resolution. | Không cần thư viện mới. |
| Agent loop không có giới hạn rounds/tool calls/deadline. | A2.4 | Có thể vượt cost/latency budget. | Chặn bounded orchestration. | Không cần LangGraph/Temporal cho MVP; dùng Python state machine + `llm_client.py`. |
| Frontend không hiển thị message history. | A2.4 | UI không hỗ trợ conversation thread. | Chặn multi-turn UX. | Không cần thư viện mới. |
| State chưa cách ly theo user/session. | A2.4 | Có risk đọc nhầm state giữa users. | Chặn safe state management. | Không cần thư viện mới; key design trên Valkey. |

## 3. Proposed Approach

### A1.1 - Verified Summarization, Grounding, and Citations

- Tái sử dụng `AskProductAIAssistant`, `fetch_product_reviews_from_db`, OpenAI-compatible flow và mock LLM.
- Tạo `grounding.py` trong `src/product-reviews/`.
- `grounding.py` chịu trách nhiệm:
  - Gán `source_id` cho từng review evidence.
  - Parse structured model output.
  - Validate citation trỏ tới source hợp lệ.
  - Loại unsupported claim hoặc trả abstention khi evidence không đủ.
- Dùng **Instructor + Pydantic** trong `grounding.py` để định nghĩa schema như `GroundedAnswer`, `Claim`, `Citation`, `Abstention`, ép model trả structured output, parse, retry khi sai format, và validate object sau parse.
- Dùng **DeepEval hoặc Ragas** trong `evals/` hoặc CI cho regression test grounding/hallucination, không đặt trong runtime path MVP.
- Contract/data cần cân nhắc:
  - MVP có thể giữ `response` text nếu chưa làm UI citation.
  - Nếu citation là first-class UI, cần mở rộng `AskProductAIAssistantResponse` với `answer`, `claims`, `citations`, `status`, `fallback_reason`.
- Cần thống nhất với A2:
  - Citation shape dùng chung cho A2.2.
  - Fallback/status shape dùng chung cho Shopping Copilot.

### A1.2 - Prompt Injection, PII, and System Prompt Protection

- Tạo `guardrails.py` trong `src/product-reviews/`.
- Dùng **Presidio** cho PII detection/redaction trước khi:
  - Ghi log.
  - Set trace attributes.
  - Gửi user question hoặc review-derived content vào LLM.
- Bổ sung telemetry sanitization ở OpenTelemetry Collector hoặc config tương đương để drop/hash/redact các attribute nhạy cảm nếu app instrumentation vẫn emit raw content.
- Dùng **LLM Guard** cho runtime scanning:
  - Scan input trước khi gọi LLM để phát hiện prompt injection, system prompt extraction, policy override.
  - Scan output trước khi trả frontend để giảm risk leak system prompt, secrets, hoặc nội dung không nên hiển thị.
- Backend vẫn phải tự enforce các rule quan trọng:
  - Validate tool name và tool arguments.
  - Reject tool call nếu `product_id` khác request gốc.
  - Tách read tools và write tools.
  - Không lấy user/session identity từ model-generated arguments.
- MVP không bắt buộc đổi protobuf, nhưng có thể thêm `status` hoặc `safety_reason` nếu UI cần phân biệt blocked/fallback/normal.

### A1.3 - Resilience and Cost Optimization

- Tạo `llm_client.py` hoặc `llm_gateway.py`.
- Dùng **Tenacity** trong `llm_client.py` cho retry/backoff.
- Retry chỉ áp dụng cho lỗi transient như 429, 500, 502, 503, timeout tạm thời.
- Không retry lỗi deterministic như guardrail block, product ID mismatch, invalid tool name, unsupported question, schema invalid sau max parse attempt.
- Retry phải nằm trong total deadline budget của request.
- Tạo `ai_cache.py` nếu cache được đưa vào scope.
- Cache dùng lại Valkey hiện có với namespace riêng, ví dụ `ai_cache:*`.
- Chốt Python Valkey client cho `product-reviews`: dùng **valkey-py** để thao tác key/value + TTL trên Valkey hiện có.
- Mở rộng `metrics.py` với LLM latency, token usage, estimated cost, retry count, timeout count, cache hit/miss, fallback count, grounding pass/fail, guardrail block count.

### A2.1 - Natural Language Product Discovery

- Tạo `src/product-reviews/product_search.py`.
- Module này chịu trách nhiệm:
  - Parse natural language query thành `search_term`, `features`, `category`, `max_price_usd`.
  - Gọi `SearchProducts` với query rút gọn.
  - Filter bằng code theo `price_usd <= max_price_usd`.
  - Rank bằng code theo feature match trong `name + description + categories`.
  - Format kết quả thành JSON tool result.
- Đăng ký tool mới `search_catalog` trong `product_reviews_server.py`.
- Nếu `search_catalog` trả empty list, agent phải trả no-results response và không tự sinh product.
- `SearchProductsRequest` hiện chỉ có `query`; chỉ mở rộng proto nếu eval cho thấy LIKE search không đủ.
- Frontend chỉ cần thêm `searchProducts(query)` nếu Copilot UI cần gọi search trực tiếp; backend-first MVP chưa bắt buộc.

### A2.2 - Review Grounded Product Question Answering

- Kế thừa `grounding.py` từ A1.1; A2.2 không tự viết validator riêng.
- Sau khi fetch reviews:
  - Chọn review liên quan tới câu hỏi.
  - Gọi grounding validator để xác nhận claim/citation.
  - Nếu không có evidence, trả abstention như "Các review hiện tại không cung cấp thông tin này."
  - Nếu có evidence, trả answer kèm `sources`.
- Cần mở rộng response contract nếu citation là first-class:

```protobuf
message AskProductAIAssistantResponse {
  string response = 1;
  repeated ReviewSource sources = 2;
  bool abstained = 3;
  string fallback_reason = 4;
}

message ReviewSource {
  string username = 1;
  string excerpt = 2;
}
```

- Nếu request dùng placeholder như `"first"` hoặc product_id rỗng, server cần resolve từ conversation state của A2.4.

### A2.3 - Confirmation Controlled Cart Actions

- Tạo `src/product-reviews/cart_actions.py`.
- Module này chịu trách nhiệm:
  - `create_pending_action(product_id, quantity, user_id)`.
  - Sinh token bằng `secrets.token_hex`.
  - Ký payload bằng HMAC-SHA256 với server secret.
  - Lưu pending action vào Valkey với TTL.
  - `execute_pending_action(token, user_id, cart_stub)` để validate token/user/TTL/integrity rồi gọi `CartService.AddItem`.
  - `reject_pending_action(token)` để xóa pending action khi user hủy.
- Chỉ đăng ký tool write dạng gated, ví dụ `cart.add` tạo pending action.
- Không đăng ký `cart.empty` hoặc `checkout.place_order`.
- `user_id` luôn lấy từ session/server context, không từ model argument.
- Secret ký token phải đến từ deployment secret/env, ví dụ `PENDING_ACTION_SIGNING_SECRET`; không hard-code trong repo.
- Thêm `CartServiceStub` vào `product_reviews_server.py` nếu execute add-to-cart nằm trong service này.
- Thêm env `CART_ADDR` và Valkey connection config cho `product-reviews` nếu cần.
- Metrics cần có: `action_created`, `action_confirmed`, `action_rejected`, `action_expired`, `action_replay_attempt`.

### A2.4 - Multi Turn Conversations and Bounded Orchestration

- Tạo `src/product-reviews/conversation.py`.
- `conversation.py` chịu trách nhiệm:
  - Load/save conversation state từ Valkey.
  - Lưu `conversation_id`, `user_id`, `messages`, `product_references`, `pending_action`.
  - Resolve reference như "đầu tiên", "first", "1", "thứ hai".
  - Update product references sau search.
- Tạo `src/product-reviews/orchestrator.py`.
- `orchestrator.py` chịu trách nhiệm:
  - Chạy bounded agent loop.
  - Giới hạn `max_rounds`, `max_tool_calls`, `deadline_seconds`.
  - Phối hợp với `llm_client.py` để timeout/retry không vượt budget.
  - Trả status như `completed`, `budget_exceeded`, `error`.
- Mở rộng request/response contract:

```protobuf
message AskProductAIAssistantRequest {
  string product_id = 1;
  string question = 2;
  string conversation_id = 3;
  string user_id = 4;
}

message AskProductAIAssistantResponse {
  string response = 1;
  string conversation_id = 2;
  repeated ReviewSource sources = 3;
  PendingAction pending_action = 4;
  string status = 5;
  repeated string product_references = 6;
  string fallback_reason = 7;
}
```

- Frontend `ProductAIAssistant.provider.tsx` cần chuyển từ `aiResponse` đơn sang `messages[]`, `conversationId`, `productReferences`.
- Valkey key nên có dạng `conv:{user_id}:{conversation_id}` để cách ly state theo user.
- TTL đề xuất: 1 giờ cho conversation state.
- Không cần LangGraph/Temporal/OpenAI Assistants API cho MVP; Python state machine đủ cho 4 rounds, 8 tool calls.

## 4. Open Source Research

| Purpose | Candidate | Used by | Reason | Integration Impact |
| --- | --- | --- | --- | --- |
| PII detection/redaction | **Presidio** | A1.2 | Regex tự viết chỉ bắt được case đơn giản như email/phone, dễ miss tên riêng, địa chỉ, credit-card-like text, format nhập không chuẩn. Presidio có analyzer/anonymizer pipeline, hỗ trợ pattern matching, NLP recognizer, và custom recognizer. | Thêm dependency Python, tạo redaction pipeline trong `guardrails.py`, cần custom recognizer/regex cho phone Việt Nam và pattern domain riêng nếu scope yêu cầu. |
| Prompt injection và runtime safety scanning | **LLM Guard** | A1.2, hỗ trợ A2 tool safety | Review/user question là untrusted input. LLM Guard có scanner cho prompt injection, system prompt extraction, secrets/data leakage, unsafe content, output sanitization. | Thêm scanner vào `guardrails.py` cho input trước LLM và output trước frontend. Không thay thế backend enforcement cho tool allow-list/product_id/read-write split. |
| Structured output/schema validation | **Instructor + Pydantic** | A1.1, A2.1, A2.2 | Cần output có cấu trúc như `status`, `answer`, `claims`, `citations`, `fallback_reason`, hoặc parsed search intent. Pydantic định nghĩa schema; Instructor ép response, parse, validate, retry khi output sai format. | Thêm schema models trong `grounding.py` và có thể `product_search.py`; wrap LLM call bằng Instructor. Bộ đôi này chỉ đảm bảo format/contract; evidence support vẫn cần grounding logic/eval. |
| Grounding/hallucination eval | **DeepEval hoặc Ragas** | A1.1, A2.2 | Structural citation chỉ chứng minh source tồn tại, chưa chứng minh claim được evidence support. Cần eval cho supported/unsupported question, misleading review, injected review, missing/wrong citation, vague answer, fallback. | Không đưa vào runtime MVP. Dùng trong `evals/` hoặc CI. DeepEval hợp hơn nếu mở rộng sang agent/tool workflow; Ragas hợp nếu chỉ review-grounded/RAG-style QA. |
| Retry/backoff | **Tenacity** | A1.3, A2.4 through `llm_client.py` | LLM có thể fail do rate limit, transient 5xx, timeout. Tenacity gọn, hỗ trợ retry condition, stop policy, exponential backoff, jitter, callback/logging. | Thêm vào `llm_client.py`; test bằng mock LLM rate-limit simulation; emit retry/fallback/timeout metrics. |
| Shared state/cache store | **Valkey hiện có** | A1.3, A2.3, A2.4 | Product-reviews cần nơi lưu AI cache, pending action token, và conversation state. Team đã chốt dùng lại Valkey hiện có. | Thiết kế namespace riêng cho `ai_cache:*`, `pending_action:*`, `conv:*`; thêm connection/env config tới Valkey hiện có; không deploy store mới. |
| Python Valkey client | **valkey-py** | A1.3, A2.3, A2.4 | Dùng Valkey server chưa đủ; Python service cần client để set/get TTL, delete one-time token, và quản lý connection. | Thêm dependency Python `valkey` vào `product-reviews`; dùng cho `ai_cache:*`, `pending_action:*`, `conv:*` trên Valkey hiện có. |
| Telemetry attribute sanitization | **OpenTelemetry Collector config** | A1.2 | App-level redaction vẫn có thể bị bypass bởi auto instrumentation hoặc log message thô. Cần lớp phòng thủ thứ hai ở telemetry pipeline. | Cấu hình drop/hash/redact các attribute như raw prompt, question, message content trước khi gửi Jaeger/OpenSearch. |
| Token signing secret management | **Deployment secret/env config** | A2.3 | Confirmation token cần HMAC secret ổn định và không hard-code. | Thêm env/secret `PENDING_ACTION_SIGNING_SECRET`; cần policy rotate và local dev fallback an toàn. |
| Semantic product search fallback | `sentence-transformers` optional | A2.1 | Nếu LIKE search không đủ chính xác cho synonym/ngôn ngữ tự nhiên, embedding similarity có thể cải thiện retrieval/ranking. | Không cần ngay. Chỉ cân nhắc sau eval vì tăng dependency, memory/CPU, và latency. |
