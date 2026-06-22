# Observability Engineering Lab

This lab has 2 separately managed parts:

- `infra/`: Prometheus, Alertmanager, Node Exporter, Loki, Alloy, Jaeger, OpenTelemetry Collector, Grafana
- `app/`: order-style FastAPI app that exposes metrics and exports traces with OTLP
- `inventory/`: inventory FastAPI service used to demonstrate trace context propagation across services

## Run Infra

Start Prometheus, Alertmanager, Node Exporter, Loki, Alloy, Jaeger, OpenTelemetry Collector, and Grafana:

```powershell
cd observability-engineering-lab\infra
docker compose up -d
```

## Run Demo App

Start the demo app separately. It is not started together with infra:

```powershell
cd observability-engineering-lab
docker compose up -d
```

The demo app and inventory service use the `observability_lab` Docker network so Prometheus in infra can scrape them and both services can export OTLP traces to `otel-collector:4317`.

## Ports

| Service | URL | Note |
| --- | --- | --- |
| Demo App | http://localhost:8001 | FastAPI demo app |
| Demo App Metrics | http://localhost:8001/metrics | Metrics endpoint |
| Inventory Service | http://localhost:8002 | Internal service exposed for local testing |
| Inventory Metrics | http://localhost:8002/metrics | Inventory metrics endpoint |
| Prometheus | http://localhost:9090 | Query metrics, check targets |
| Node Exporter | http://localhost:9100/metrics | Host/container node metrics |
| Loki | http://localhost:3100/ready | Log store readiness endpoint |
| Loki Metrics | http://localhost:3100/metrics | Loki internal metrics |
| Alloy | http://localhost:12345 | Alloy UI/debug endpoint |
| OpenTelemetry Collector gRPC | localhost:4317 | OTLP gRPC receiver |
| OpenTelemetry Collector HTTP | http://localhost:4318 | OTLP HTTP receiver |
| Jaeger | http://localhost:16686 | Trace search UI |
| Grafana | http://localhost:3000 | Login `admin` / `grafana` |

## Grafana Datasources

Grafana auto-adds Prometheus and Loki datasources from:

```text
infra/grafana/provisioning/datasources/datasource.yml
```

Datasource URL inside Docker network:

```text
http://prometheus:9090
http://loki:3100
```

Without this provisioning file, Grafana still runs, but datasources must be added manually in the Grafana UI.

## Check Status

```powershell
docker ps
```

Prometheus targets should include:

- `prometheus:9090`
- `node-exporter:9100`
- `demo-app:8000`

Loki readiness should return `ready`:

```powershell
Invoke-WebRequest http://localhost:3100/ready
```

Alloy should discover running Docker containers and forward their logs to Loki. In Grafana Explore, use the Loki datasource and query labels such as:

```logql
{compose_project="infra"}
```

The FastAPI app should export traces through OpenTelemetry Collector to Jaeger. The `/checkout` route calls `inventory-service`, so one trace should include spans from both services. Generate a few requests:

```powershell
1..10 | ForEach-Object { curl.exe http://localhost:8001/checkout }
```

Then open Jaeger at http://localhost:16686 and search for service `demo-fastapi-app`, operation `GET /checkout`.

You should see a trace shaped like:

```text
demo-fastapi-app  GET /checkout
├─ checkout.calculate_cart
├─ GET http://inventory-service:8000/inventory/sku-123
└─ inventory-service  GET /inventory/{sku}
   └─ inventory.check_stock
```

This confirms that trace context was propagated from the order API container to the inventory service container through HTTP headers.

To check whether traces reached the Collector:

```powershell
docker compose -f infra\docker-compose.yml logs -f otel-collector
```
