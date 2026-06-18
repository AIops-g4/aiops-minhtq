# MLOps Lifecycle Lab

Run the local stack from `data-pack`, train the first model, start the API, then run drift detection and retraining from this directory:

```powershell
cd data-pack
bash scripts/start_stack.sh
cd ..
uv run python pipeline.py --data data-pack/data/baseline.csv
uv run python serve.py
uv run python drift_detector.py --reference data-pack/data/baseline.csv --current data-pack/data/drifted.csv --check-mode combined --model-uri models:/anomaly-detector@production --labeled-current data-pack/data/drifted.csv
uv run python retrain.py --reference data-pack/data/baseline.csv --current data-pack/data/drifted.csv --holdout data-pack/data/holdout.csv --post-deploy-eval data-pack/data/post_deploy_eval.csv
```

MLflow is available at `http://localhost:5000`, the serving API at `http://localhost:8000`, Prometheus at `http://localhost:9090`, Pushgateway at `http://localhost:9091`, and Grafana at `http://localhost:3000`.
