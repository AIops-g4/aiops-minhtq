import os
import csv
import queue
import urllib.request
import threading
import logging
from collections import deque
import pandas as pd
import numpy as np

# Cấu hình logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- CONFIGURATIONS ---
DATA_URL = "https://raw.githubusercontent.com/numenta/NAB/master/data/realKnownCause/machine_temperature_system_failure.csv"
DATA_FILE = "./data/machine_temperature_system_failure.csv"
OUTPUT_FILE = "./data/features.parquet"

# Kích thước của Sliding Window để tính rolling features. 
# Dữ liệu có granularity 5 phút -> Window 12 = 1 giờ (60 phút / 5)
WINDOW_SIZE = 12 
POISON_PILL = "EOF"  # Tín hiệu giả lập báo kết thúc stream

def download_data():
    """Tải file dữ liệu CSV nếu chưa tồn tại ở local."""
    if not os.path.exists(DATA_FILE):
        logging.info(f"Đang tải dataset từ {DATA_URL}...")
        urllib.request.urlretrieve(DATA_URL, DATA_FILE)
        logging.info("Tải dataset thành công.")

def producer(q: queue.Queue):
    """
    Giả lập Data Producer (như Kafka Producer hoặc Fluent Bit).
    Đọc dữ liệu từ source và đẩy từng event vào Queue.
    """
    logging.info("Producer bắt đầu chạy...")
    try:
        with open(DATA_FILE, 'r') as f:
            # Lọc bỏ khoảng trắng thừa trong header nếu có
            reader = csv.DictReader(f, skipinitialspace=True)
            for row in reader:
                # push vào queue, giả lập việc emit event.
                # Do Queue có maxsize, hàm put() sẽ tự động block nếu Queue bị đầy (Backpressure)
                q.put(row)
                
        # Báo cho Consumer biết stream đã kết thúc
        q.put(POISON_PILL)
        logging.info("Producer đã đẩy toàn bộ dữ liệu vào Queue.")
    except Exception as e:
        logging.error(f"Producer gặp lỗi: {e}")

def consumer(q: queue.Queue):
    """
    Giả lập Stream Processing Engine (như Apache Flink / Spark Streaming).
    Consume event từ Queue, tính toán real-time feature và sink ra storage.
    """
    logging.info("Consumer bắt đầu chạy và lắng nghe Queue...")
    
    # State management cho Sliding Window
    window = deque(maxlen=WINDOW_SIZE)
    prev_val = None
    results = []

    while True:
        # Lấy event từ message queue
        msg = q.get()
        
        # Nếu nhận được tín hiệu kết thúc -> dừng xử lý
        if msg == POISON_PILL:
            break

        ts = msg['timestamp']
        val = float(msg['value'])
        
        # 1. Cập nhật State (Đẩy data point mới vào Window)
        window.append(val)
        
        # 2. Feature Extraction (Tính toán on-the-fly)
        rolling_mean = np.mean(window) if len(window) > 0 else val
        rolling_std = np.std(window) if len(window) > 1 else 0.0
        rate_of_change = (val - prev_val) if prev_val is not None else 0.0
        
        prev_val = val # Cập nhật giá trị previous cho vòng lặp tiếp theo

        # 3. Sink output
        results.append({
            'timestamp': ts,
            'value': val,
            'rolling_mean': rolling_mean,
            'rolling_std': rolling_std,
            'rate_of_change': rate_of_change
        })
        
        # Đánh dấu task trong queue đã xử lý xong
        q.task_done()
        
    logging.info("Stream đã kết thúc. Đang lưu features ra storage (Parquet)...")
    
    # Xuất ra file định dạng Columnar Parquet
    df = pd.DataFrame(results)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df.to_parquet(OUTPUT_FILE, index=False)
    logging.info(f"Consumer đã xử lý và lưu thành công {len(df)} events ra file {OUTPUT_FILE}.")

def main():
    download_data()
    
    # Giả lập Kafka Topics / Message Queue với maxsize giới hạn
    # maxsize=1000 giúp mô phỏng cơ chế Backpressure: 
    # Nếu Consumer xử lý không kịp, Producer sẽ bị block không cho đẩy thêm dữ liệu.
    stream_queue = queue.Queue(maxsize=1000)
    
    # Khởi tạo 2 luồng độc lập
    prod_thread = threading.Thread(target=producer, args=(stream_queue,))
    cons_thread = threading.Thread(target=consumer, args=(stream_queue,))
    
    prod_thread.start()
    cons_thread.start()
    
    # Đợi cả 2 process kết thúc
    prod_thread.join()
    cons_thread.join()
    
    logging.info("Pipeline mô phỏng hoàn tất.")

if __name__ == "__main__":
    main()