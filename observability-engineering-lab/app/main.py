import asyncio
import random
import time

import httpx
from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse
from opentelemetry import trace
from prometheus_client import Counter, Histogram, make_asgi_app


tracer = trace.get_tracer(__name__)

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


@app.get("/checkout")
async def checkout():
    with tracer.start_as_current_span("checkout.calculate_cart") as span:
        cart_size = random.randint(1, 5)
        await asyncio.sleep(random.uniform(0.05, 0.2))
        span.set_attribute("cart.size", cart_size)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "http://inventory-service:8000/inventory/sku-123",
                params={"quantity": cart_size},
            )
            response.raise_for_status()
    except httpx.RequestError as exc:
        trace.get_current_span().record_exception(exc)
        return JSONResponse(
            status_code=502,
            content={
                "message": "checkout failed",
                "reason": "inventory service request failed",
            },
        )
    except httpx.HTTPStatusError as exc:
        trace.get_current_span().record_exception(exc)
        return JSONResponse(
            status_code=502,
            content={
                "message": "checkout failed",
                "reason": "inventory service returned an error",
                "inventory_status": exc.response.status_code,
            },
        )

    return {
        "message": "checkout completed",
        "inventory": response.json(),
    }


app.mount("/metrics", make_asgi_app())
