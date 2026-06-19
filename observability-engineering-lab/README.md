# Observability Engineering Lab

This lab has 2 separately managed parts:

- `infra/`: Prometheus, Node Exporter, Grafana
- `app/`: demo FastAPI app that exposes metrics for Prometheus scraping

## Run Infra

Start Prometheus, Node Exporter, and Grafana:

```powershell
cd observability-engineering-lab\infra
docker compose up -d
```

## Run Demo App

Start the demo app separately. It is not started together with infra:

```powershell
cd observability-engineering-lab
docker compose up -d --build
```

The demo app uses the `observability_lab` Docker network so Prometheus in infra can scrape `demo-app:8000`.

## Ports

| Service | URL | Note |
| --- | --- | --- |
| Demo App | http://localhost:8001 | FastAPI demo app |
| Demo App Metrics | http://localhost:8001/metrics | Metrics endpoint |
| Prometheus | http://localhost:9090 | Query metrics, check targets |
| Node Exporter | http://localhost:9100/metrics | Host/container node metrics |
| Grafana | http://localhost:3000 | Login `admin` / `grafana` |

## Grafana Datasource

Grafana auto-add Prometheus datasource from:

```text
infra/grafana/provisioning/datasources/datasource.yml
```

Datasource URL inside Docker network:

```text
http://prometheus:9090
```

Without this provisioning file, Grafana still runs, but Prometheus must be added manually in the Grafana UI.

## Reset Clean

Reset infra, including Prometheus/Grafana volumes:

```powershell
cd observability-engineering-lab\infra
docker compose down -v --remove-orphans
docker compose up -d
```

Reset demo app:

```powershell
cd observability-engineering-lab
docker compose down -v --remove-orphans
docker compose up -d --build
```

## Check Status

```powershell
docker ps
```

Prometheus targets should include:

- `prometheus:9090`
- `node-exporter:9100`
- `demo-app:8000`
