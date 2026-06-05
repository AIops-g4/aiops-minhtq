## Phương pháp Tiếp cận (Methodology)

Để phát hiện sớm các dấu hiệu bất thường (anomalies) dẫn đến sự cố hệ thống, chúng tôi đề xuất một phương pháp tiếp cận kết hợp ba mô hình: **STL** (để phát hiện điểm thay đổi - Change Point Detection) và **EWMA, Isolation Forest** (để xác thực và củng cố độ tin cậy). Mục tiêu cốt lõi là nhận diện sự suy thoái tiềm ẩn trước khi hệ thống hoàn toàn sụp đổ.

### 1. Phát hiện Điểm thay đổi (Change Point Detection) bằng thuật toán STL
Dữ liệu giám sát (monitoring) thực tế thường chứa nhiều nhiễu và biến động chu kỳ tự nhiên. Để bắt được chính xác xu hướng chuyển biến xấu, chúng tôi sử dụng thuật toán **STL (Seasonal and Trend decomposition using Loess)**.

*   **Trích xuất Xu hướng (Trend Extraction):** STL phân tách chuỗi thời gian gốc thành ba thành phần: Tính mùa vụ (Seasonality), Nhiễu (Residual) và Xu hướng cốt lõi (Trend). Bằng cách thiết lập cấu hình `period = 120` (chu kỳ lặp) và `robust = True` (chống nhiễu mạnh), chúng tôi loại bỏ các "gai" nhiễu ngẫu nhiên, giúp làm lộ rõ sự thay đổi từ từ của các chỉ số (ví dụ: sự rò rỉ bộ nhớ).
*   **Xác định Điểm thay đổi (Change Point Identification):** Để đánh dấu chính xác thời điểm xu hướng bắt đầu tăng tốc, chúng tôi áp dụng phương pháp đo động học dựa trên các tham số cấu hình cụ thể sau:
    1.  **Đo lường độ dốc - Slope Measurement (Vận tốc hiện tại):** Tại mỗi thời điểm, chúng tôi tính toán độ dốc (tốc độ thay đổi) của đường Trend bằng hồi quy tuyến tính trên một **cửa sổ quan sát lùi (`rolling window`) = 120 mẫu** (tương đương 2 giờ). Giá trị độ dốc này đại diện cho "vận tốc" hiện tại của metric.
    2.  **Thiết lập Baseline - Baseline Establishment (Hệ quy chiếu bình thường):** Chúng tôi trích xuất các giá trị độ dốc trong khoảng thời gian rạng sáng từ `01:00` đến `08:00` làm hệ quy chiếu, đại diện cho trạng thái hệ thống êm nhất. Ngưỡng động được tính toán dựa trên phân phối thống kê: `Ngưỡng Baseline = Giá trị trung bình (mean) + 2.0 * Độ lệch chuẩn (std) + 1e-6` (hằng số nhỏ để tránh lỗi chia cho 0).
    3.  **Kích hoạt Cảnh báo - Alert Trigger (Xác nhận bất thường):** Điểm thay đổi (Change Point) được đánh dấu khi độ dốc hiện tại vượt qua ngưỡng Baseline. Để loại bỏ cảnh báo giả, sự vi phạm này phải được duy trì **liên tục trong 10 mẫu** (tương đương 5 phút). Mốc thời gian đầu tiên của chuỗi 10 mẫu liên tục này được xác nhận là thời điểm khởi phát sự cố.

### 2. Xác thực xu hướng bằng EWMA (Exponentially Weighted Moving Average)
Để củng cố kết quả từ STL, thuật toán **EWMA** được sử dụng bổ trợ. Về mặt lý thuyết, EWMA có độ nhạy rất cao trong việc bắt các độ lệch chậm (gradual drift).

*   **Cấu hình:** Mô hình được thiết lập với `span = 120` (tương đương 1 giờ quan sát lùi), `adjust = False` (sử dụng trọng số đệ quy tiêu chuẩn) và ngưỡng sai số `sigma = 2.5`.
*   **Kết quả:** EWMA thành công trong việc chỉ ra các dấu hiệu tăng trưởng khác thường của metric từ sớm, hoàn toàn khớp với điểm khởi phát lỗi do thuật toán STL tìm ra.

### 3. Đối soát chéo bằng Isolation Forest (IF)
Để hoàn thiện cơ sở lập luận, mô hình học máy không giám sát **Isolation Forest** được áp dụng.

*   **Thiết lập Bài toán:** Để đáp ứng mục tiêu "phát hiện sớm", chúng tôi chủ động loại bỏ phần dữ liệu sau 15:00 (giai đoạn hệ thống đã bùng phát lỗi rõ rệt) và chỉ cung cấp cho IF khoảng thời gian từ `00:00` đến `15:00` để thuật toán tự khoanh vùng bất thường. Mô hình được khởi tạo với cấu hình `n_estimators = 200` (sử dụng 200 cây quyết định), tỷ lệ nhiễu dự kiến `contamination = 0.05` (hoặc `0.01` tùy theo metric) và cố định `random_state = 42` để đảm bảo kết quả nhất quán.
*   **Kết quả:** Isolation Forest độc lập phát hiện được cụm điểm bất thường xuất hiện ngay từ khoảng 08:00. Sự đồng thuận (consensus) giữa phương pháp thống kê truyền thống (STL, EWMA) và thuật toán Machine Learning (IF) cung cấp một bằng chứng vững chắc về tính chính xác của thời điểm root-cause khởi phát.