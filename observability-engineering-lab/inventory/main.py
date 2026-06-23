import asyncio
import json
import logging
import random
import time
from datetime import datetime, UTC

from fastapi import FastAPI, Response
from opentelemetry import trace
from prometheus_client import Counter, Histogram, make_asgi_app


tracer = trace.get_tracer(__name__)
logger = logging.getLogger("inventory-service")
logging.basicConfig(level=logging.INFO, format="%(message)s")


def current_trace_fields():
    span_context = trace.get_current_span().get_span_context()
    if not span_context.is_valid:
        return {}

    return {
        "trace_id": format(span_context.trace_id, "032x"),
        "span_id": format(span_context.span_id, "016x"),
    }


def log_event(level, event, **fields):
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "level": level,
        "service": "inventory-service",
        "environment": "local",
        "service_version": "1.0.0",
        "event": event,
        **current_trace_fields(),
        **fields,
    }
    logger.log(getattr(logging, level.upper()), json.dumps(payload, separators=(",", ":")))

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
    log_event(
        "info" if response.status_code < 400 else "warn",
        "http_request",
        method=request.method,
        path=request.url.path,
        endpoint=endpoint,
        status_code=response.status_code,
        duration_ms=round((time.time() - start) * 1000, 2),
    )

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
        log_event(
            "warn",
            "inventory_stock_conflict",
            sku=sku,
            requested_quantity=quantity,
            available_stock=stock,
            status_code=409,
        )
        return Response("Not enough stock", status_code=409)

    return {
        "sku": sku,
        "requested_quantity": quantity,
        "available_stock": stock,
        "reserved": True,
    }


app.mount("/metrics", make_asgi_app())
