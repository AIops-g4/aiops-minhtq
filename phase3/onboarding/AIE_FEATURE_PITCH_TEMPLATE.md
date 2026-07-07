# AIE Feature Pitch Template

## Purpose

Template này giúp team chuyển một feature trong `AIE_IMPLEMENTATION_GUIDE.md` thành một backlog item có thể trình bày và bảo vệ trước mentor. Mỗi feature nên trả lời được ba câu hỏi:

1. Khách hàng đang gặp vấn đề gì?
2. Team đề xuất giải quyết vấn đề đó như thế nào?
3. Vì sao feature này cần được ưu tiên ở thời điểm hiện tại?

Mỗi feature nên được viết gọn trong bốn đoạn và trình bày trong khoảng một đến hai phút.

---

## Feature Template

### [Feature ID] - [Feature Name]

> Hiện tại, [đối tượng sử dụng] có thể gặp [vấn đề] vì [nguyên nhân]. Team đề xuất [thay đổi chính] để [giá trị khách hàng]. Khi [điều kiện không đáp ứng hoặc xảy ra lỗi], hệ thống sẽ [hành vi an toàn].

#### Problem & Evidence

[Mô tả luồng hiện tại và chỉ ra vấn đề bằng bằng chứng cụ thể từ code, metric, log, incident, SLO hoặc baseline. Giải thích ai bị ảnh hưởng và hậu quả đối với trải nghiệm, doanh thu, chi phí hoặc uy tín. Không chỉ viết rằng hệ thống “chưa có feature”; hãy nói rõ việc thiếu nó đang gây ra rủi ro gì.]

#### Approach

[Giải thích giải pháp theo đúng thứ tự hệ thống xử lý request. Nêu service, module hoặc contract cần thay đổi, primitive có thể tái sử dụng và cách hệ thống fallback khi không thể hoàn thành an toàn. Nếu cần thêm dependency hoặc thông tin từ DevOps, CloudOps, hãy nói rõ thay vì coi đó là điều đã có sẵn.]

#### Priority

[Nêu mức ưu tiên đề xuất và bảo vệ lựa chọn đó bằng khả năng xảy ra, mức nghiêm trọng và tác động business. Giải thích vì sao feature này nên được làm trước các feature khác, feature nào phụ thuộc vào nó và giả định nào vẫn cần xác nhận với các team liên quan.]

---

## Example

### A1.1 - Verified Summarization, Grounding, and Citations

Team đề xuất bổ sung grounding và citation cho phần tóm tắt review. Mục tiêu là để khách hàng không chỉ nhận được một câu trả lời dễ đọc mà còn biết câu trả lời đó dựa trên những review nào. Khi dữ liệu chưa đủ để kết luận, hệ thống sẽ nói rõ thay vì tự suy đoán.

#### Problem & Evidence

Luồng hiện tại lấy review, gửi cho model rồi trả thẳng phần nội dung model sinh ra. Response chỉ có text, chưa kèm nguồn và backend cũng chưa kiểm tra từng nhận định có thật sự được review hỗ trợ hay không. Vì vậy, một câu như “pin dùng được 20 giờ” vẫn có thể xuất hiện dù review chỉ nói chung rằng pin tốt. Với khách hàng đang cân nhắc mua sản phẩm, đây không còn là lỗi diễn đạt mà là nguy cơ ra quyết định dựa trên thông tin sai. Trước khi triển khai, team sẽ chạy baseline eval để biết tỷ lệ nhận định thiếu bằng chứng đang ở mức nào.

#### Approach

Mỗi review sẽ được gắn một source ID ổn định trước khi đưa vào model. Model được yêu cầu trả về các nhận định cùng danh sách source hỗ trợ, sau đó backend kiểm tra cấu trúc và đối chiếu lại bằng chứng. Chỉ kết quả đạt yêu cầu mới được hiển thị; nếu không đủ dữ liệu, hệ thống chuyển sang câu trả lời an toàn như “Các review hiện tại chưa cung cấp thông tin này”. Phần lớn thay đổi nằm trong `src/product-reviews` và tận dụng OpenAI SDK cùng gRPC/protobuf đang có. Team chỉ thêm thư viện mới nếu kết quả eval cho thấy cách kiểm tra hiện tại chưa đáp ứng được yêu cầu.

#### Priority

Team xếp feature này ở mức P1 vì rủi ro đã tồn tại ngay trong luồng hiện tại và ảnh hưởng trực tiếp đến niềm tin của khách hàng tại thời điểm mua hàng. Grounding cũng là nền móng cho các bước tiếp theo: khi Shopping Copilot được cấp thêm dữ liệu và quyền gọi tool, một câu trả lời thiếu kiểm soát sẽ gây hậu quả lớn hơn nhiều. Vì vậy, team muốn chứng minh rằng hệ thống biết trả lời đúng và biết dừng khi thiếu bằng chứng trước khi mở rộng những khả năng phức tạp hơn.
