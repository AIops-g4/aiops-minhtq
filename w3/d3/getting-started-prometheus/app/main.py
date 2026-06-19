import random
import time

from fastapi import FastAPI, Response
from prometheus_client import Counter, Histogram, make_asgi_app


REQUEST_COUNT = Counter(
    "app_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status"],
)

REQUEST_LATENCY = Histogram(
    "app_request_latency_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
)

app = FastAPI()

# Middleware đo metric cho mọi request đi qua FastAPI
@app.middleware("http") # Đăng ký một HTTP middleware. Nghĩa là mỗi request vào app sẽ đi qua hàm collect_metrics trước khi tới route thật, ví dụ /, /users, /predict.
async def collect_metrics(request, call_next):
#   request là thông tin request đi vào.
#   call_next là hàm để chuyển request tiếp vào route thật và lấy response trả ra.
    if request.url.path == "/metrics": # Nếu request đang gọi /metrics thì bỏ qua đo metric -> Lý do: /metrics là endpoint Prometheus scrape định kỳ.
        return await call_next(request)

    start = time.time()
    response = await call_next(request) # Cho request đi tiếp vào route thật và trả ra response.
    route = request.scope.get("route")
    endpoint = route.path if route else request.url.path # Dùng route.path để lấy endpoint nhưng không lấy variables, ví dụ /users/{id} thay vì /users/123.

    REQUEST_LATENCY.labels(request.method, endpoint).observe(time.time() - start)
    REQUEST_COUNT.labels(request.method, endpoint, str(response.status_code)).inc()

    return response


@app.get("/")
async def root():
    time.sleep(random.uniform(0.01, 0.2))

    if random.random() < 0.2:
        return Response("Internal Server Error", status_code=500)

    return {"message": "Hello from Demo 3 FastAPI App"}


app.mount("/metrics", make_asgi_app())
