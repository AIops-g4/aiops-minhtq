import asyncio
import random
import time

from fastapi import FastAPI, Response
from opentelemetry import trace
from prometheus_client import Counter, Histogram, make_asgi_app


tracer = trace.get_tracer(__name__)

REQUEST_COUNT = Counter(
    "inventory_requests_total",
    "Total number of inventory HTTP requests",
    ["method", "endpoint", "status"],
)

REQUEST_LATENCY = Histogram(
    "inventory_request_latency_seconds",
    "Inventory HTTP request latency in seconds",
    ["method", "endpoint"],
)

app = FastAPI()


@app.middleware("http")
async def collect_metrics(request, call_next):
    if request.url.path in {"/metrics", "/metrics/"}:
        return await call_next(request)

    start = time.time()
    response = await call_next(request)
    route = request.scope.get("route")
    endpoint = route.path if route else request.url.path

    REQUEST_LATENCY.labels(request.method, endpoint).observe(time.time() - start)
    REQUEST_COUNT.labels(request.method, endpoint, str(response.status_code)).inc()

    return response


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/inventory/{sku}")
async def get_inventory(sku: str, quantity: int = 1):
    with tracer.start_as_current_span("inventory.check_stock") as span:
        stock = random.randint(0, 20)
        await asyncio.sleep(random.uniform(0.25, 0.75))
        span.set_attribute("inventory.sku", sku)
        span.set_attribute("inventory.requested_quantity", quantity)
        span.set_attribute("inventory.available_stock", stock)

    if stock < quantity:
        return Response("Not enough stock", status_code=409)

    return {
        "sku": sku,
        "requested_quantity": quantity,
        "available_stock": stock,
        "reserved": True,
    }


app.mount("/metrics", make_asgi_app())
