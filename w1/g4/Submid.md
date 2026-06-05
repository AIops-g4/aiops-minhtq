## Methodology

To early detect anomalies leading to system failures, we propose a combined approach utilizing three models: **STL** (for Change Point Detection), and **EWMA, Isolation Forest** (for validation and reliability enhancement). The core objective is to identify potential degradation before a complete system crash occurs.

### 1. Change Point Detection using STL Algorithm
Real-world monitoring data often contains significant noise and natural cyclical fluctuations. To accurately capture deteriorating trends, we utilize the **STL (Seasonal and Trend decomposition using Loess)** algorithm.

*   **Trend Extraction:** STL decomposes the original time series into three components: Seasonality, Residual (noise), and the core Trend. By utilizing only the Trend component (`.fit().trend`), we eliminate random noise spikes, revealing the gradual changes in metrics (e.g., memory leaks).
*   **Change Point Identification:** To precisely pinpoint the moment the trend begins to accelerate (Change Point), we apply a kinematic measurement approach based on the following specific parameters:
    1.  **Slope Measurement (Current Velocity):** At each timestamp, we calculate the slope (rate of change) of the Trend line using linear regression over a rolling **2-hour lookback window** (e.g., 120 data points if sampling per minute). This slope value represents the current "velocity" of the metric—indicating how fast it is growing or shrinking at that specific moment.
    2.  **Baseline Establishment (Normal Reference):** To evaluate if the current velocity is abnormal, we establish a baseline. We extract the slope values during the early morning hours (e.g., `01:00` to `08:00`), representing the system's most stable state with minimal load. The dynamic threshold is defined using the statistical distribution of this stable period (typically: `Baseline Threshold = Mean + 2 * Standard Deviation`).
    3.  **Alert Trigger (Anomaly Confirmation):** A point is marked as a Change Point when the current slope strictly exceeds the established Baseline threshold. To eliminate false positives caused by brief, random spikes, this violation must be maintained **continuously for 5 minutes** (e.g., 10 consecutive data points). The first timestamp of this continuous sequence is officially flagged as the root-cause onset.

### 2. Trend Validation with EWMA (Exponentially Weighted Moving Average)
To reinforce the findings from STL, the **EWMA** algorithm is used supplementarily. Theoretically, EWMA is highly sensitive to detecting gradual drifts.

*   **Configuration:** The model is configured with `span = 120` (equivalent to a 1-hour observation window) and an error threshold of `sigma = 2.5`.
*   **Results:** EWMA successfully indicates early signs of abnormal metric growth, perfectly aligning with the error onset point discovered by the STL algorithm.

### 3. Cross-verification with Isolation Forest (IF)
To complete the analytical foundation, an unsupervised machine learning model, **Isolation Forest**, is applied.

*   **Problem Setup:** To align with the "early detection" objective, we discarded data after 15:00 (the phase where the system error has clearly manifested) and only provided the IF algorithm with the timeframe from `00:00` to `15:00` to autonomously isolate anomalies.
*   **Results:** Isolation Forest independently detected a cluster of anomalies emerging right around 08:00. The consensus between traditional statistical methods (STL, EWMA) and the Machine Learning algorithm (IF) provides robust evidence for the accuracy of the root-cause onset time.