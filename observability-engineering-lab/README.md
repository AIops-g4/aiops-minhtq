# Observability Engineering Lab

This lab has 2 separately managed parts:

- `infra/`: Prometheus, Alertmanager, Node Exporter, Loki, Alloy, Grafana
- `app/`: demo FastAPI app that exposes metrics for Prometheus scraping

## Run Infra

Start Prometheus, Alertmanager, Node Exporter, Loki, Alloy, and Grafana:

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

The demo app uses the `observability_lab` Docker network so Prometheus in infra can scrape `demo-app:8000`.

## Ports

| Service | URL | Note |
| --- | --- | --- |
| Demo App | http://localhost:8001 | FastAPI demo app |
| Demo App Metrics | http://localhost:8001/metrics | Metrics endpoint |
| Prometheus | http://localhost:9090 | Query metrics, check targets |
| Node Exporter | http://localhost:9100/metrics | Host/container node metrics |
| Loki | http://localhost:3100/ready | Log store readiness endpoint |
| Loki Metrics | http://localhost:3100/metrics | Loki internal metrics |
| Alloy | http://localhost:12345 | Alloy UI/debug endpoint |
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
