import pandas as pd

class CostEstimator:
    """
    Cost Estimator for Observability Platform comparing Build (Self-hosted on AWS EKS)
    vs Buy (Datadog SaaS) across different scale tiers.
    """
    # --- AWS Regional Pricing Constants (Monthly) ---
    EKS_CONTROL_PLANE_COST = 73.00       # AWS EKS cluster fee ($0.10/hour)
    VCPU_MONTHLY_COST = 30.00            # ~$0.041/vCPU-hour (e.g., m6g EC2 instance class)
    RAM_GB_MONTHLY_COST = 4.00           # ~$0.0055/GB-hour
    EBS_GP3_GB_COST = 0.08               # $0.08/GB-month (Hot tier block storage)
    S3_STANDARD_GB_COST = 0.023          # $0.023/GB-month (Cold tier object storage)
    NETWORK_TRANSFER_GB_COST = 0.01      # $0.01/GB cross-AZ data transfer

    # --- Datadog SaaS Pricing Constants (Monthly) ---
    DD_LOG_INGESTION_GB_COST = 0.10      # $0.10/GB ingested
    DD_LOG_RETENTION_GB_COST = 1.70      # $1.70/GB retained (30 days plan)
    DD_HOST_APM_COST = 35.00             # $35/host (Infrastructure + APM bundle)
    DD_CUSTOM_METRICS_EPS_COST = 0.014   # Proportional cost for high-cardinality custom metrics per events/sec

    # --- Technical & Retention Assumptions ---
    DAYS_IN_MONTH = 30
    LOG_RETENTION_HOT_DAYS = 7           # Hot tier GP3 retention
    LOG_RETENTION_COLD_DAYS = 365        # Cold tier S3 retention for ML training
    METRIC_RETENTION_HOT_DAYS = 7        # Hot tier retention for metrics in VictoriaMetrics
    
    METRIC_EVENT_SIZE_BYTES = 100        # Average raw size of a metric event
    COMPRESSION_RATIO_HOT = 0.5          # Log/Metric compression in hot databases (Loki/VM)
    COMPRESSION_RATIO_COLD = 0.15        # Parquet compression on AWS S3
    NETWORK_COMPRESSION_RATIO = 0.2      # Compression achieved at source before network transfer

    def __init__(self, services: int, log_gb_per_day: float, metric_events_per_sec: float, sre_count: int, sre_salary: float):
        self.services = services
        self.log_gb_per_day = log_gb_per_day
        self.metric_events_per_sec = metric_events_per_sec
        self.sre_count = sre_count
        self.sre_salary = sre_salary

    def calculate_build_compute_cost(self) -> float:
        """
        Estimates compute resources (vCPU/RAM) required for self-hosted EKS cluster:
        - Base overhead (Grafana, OTel collectors, K8s system services).
        - Processing pipelines (Kafka + Flink stream nodes).
        - Database query & ingestion nodes (Loki + VictoriaMetrics).
        """
        # Base cluster resources (scales slightly with the number of services)
        base_vcpu = 2 + (self.services // 50)
        base_ram = 8 + (self.services // 10)
        
        # Ingestion & Processing (Flink / Kafka)
        log_proc_vcpu = self.log_gb_per_day / 50.0  # 1 vCPU per 50 GB/day logs
        log_proc_ram = log_proc_vcpu * 4.0          # 4 GB RAM per vCPU
        
        metric_proc_vcpu = self.metric_events_per_sec / 100000.0  # 1 vCPU per 100K events/sec
        metric_proc_ram = metric_proc_vcpu * 4.0
        
        # Storage & Queries (Loki + VictoriaMetrics query/ingestion paths)
        log_store_vcpu = self.log_gb_per_day / 100.0
        log_store_ram = log_store_vcpu * 4.0
        
        metric_store_vcpu = self.metric_events_per_sec / 200000.0
        metric_store_ram = metric_store_vcpu * 4.0
        
        # Aggregations
        total_vcpu = base_vcpu + log_proc_vcpu + metric_proc_vcpu + log_store_vcpu + metric_store_vcpu
        total_ram = base_ram + log_proc_ram + metric_proc_ram + log_store_ram + metric_store_ram
        
        compute_cost = (total_vcpu * self.VCPU_MONTHLY_COST) + (total_ram * self.RAM_GB_MONTHLY_COST) + self.EKS_CONTROL_PLANE_COST
        return round(compute_cost, 2)

    def calculate_build_storage_cost(self) -> float:
        """
        Estimates storage costs for Hot Tier (EBS GP3) and Cold Tier (S3 Standard).
        """
        # --- Hot Log Storage (GP3) ---
        hot_log_gb = self.log_gb_per_day * self.LOG_RETENTION_HOT_DAYS * self.COMPRESSION_RATIO_HOT
        hot_log_cost = hot_log_gb * self.EBS_GP3_GB_COST
        
        # --- Hot Metric Storage (GP3) ---
        metric_volume_gb_per_day = (self.metric_events_per_sec * 86400 * self.METRIC_EVENT_SIZE_BYTES) / (1024**3)
        hot_metric_gb = metric_volume_gb_per_day * self.METRIC_RETENTION_HOT_DAYS * self.COMPRESSION_RATIO_HOT
        hot_metric_cost = hot_metric_gb * self.EBS_GP3_GB_COST
        
        # --- Cold Log Storage (S3 Parquet) ---
        cold_log_gb = self.log_gb_per_day * self.LOG_RETENTION_COLD_DAYS * self.COMPRESSION_RATIO_COLD
        cold_log_cost = cold_log_gb * self.S3_STANDARD_GB_COST
        
        return round(hot_log_cost + hot_metric_cost + cold_log_cost, 2)

    def calculate_build_network_cost(self) -> float:
        """
        Estimates cross-AZ data transfer costs (3 hops average: OTel -> Kafka -> Flink -> Storage).
        """
        monthly_log_gb = self.log_gb_per_day * self.DAYS_IN_MONTH
        
        metric_gb_per_day = (self.metric_events_per_sec * 86400 * self.METRIC_EVENT_SIZE_BYTES) / (1024**3)
        monthly_metric_gb = metric_gb_per_day * self.DAYS_IN_MONTH
        
        network_volume_gb = (monthly_log_gb + monthly_metric_gb) * self.NETWORK_COMPRESSION_RATIO
        network_cost = network_volume_gb * 3 * self.NETWORK_TRANSFER_GB_COST
        return round(network_cost, 2)

    def calculate_datadog_cost(self) -> float:
        """
        Estimates Datadog SaaS costs based on active hosts, custom metrics, and log ingestion/retention.
        """
        # Assume 2 hosts per service running in active deployment
        hosts = self.services * 2
        host_cost = hosts * self.DD_HOST_APM_COST
        
        # Logs Ingestion & 30-day Retention
        log_ingest_cost = self.log_gb_per_day * self.DAYS_IN_MONTH * self.DD_LOG_INGESTION_GB_COST
        log_retention_cost = self.log_gb_per_day * self.DAYS_IN_MONTH * self.DD_LOG_RETENTION_GB_COST
        
        # Custom Metrics (penalized heavily due to cardinality)
        metric_cost = self.metric_events_per_sec * self.DD_CUSTOM_METRICS_EPS_COST
        
        return round(host_cost + log_ingest_cost + log_retention_cost + metric_cost, 2)

    def get_build_breakdown(self) -> dict:
        """Returns the cost breakdown of the Build option."""
        compute = self.calculate_build_compute_cost()
        storage = self.calculate_build_storage_cost()
        network = self.calculate_build_network_cost()
        infra_total = round(compute + storage + network, 2)
        sre_cost = self.sre_count * self.sre_salary
        tco_total = round(infra_total + sre_cost, 2)
        
        return {
            "Compute ($)": compute,
            "Storage ($)": storage,
            "Network ($)": network,
            "Infra Total ($)": infra_total,
            "SRE Operational ($)": sre_cost,
            "Total TCO ($)": tco_total
        }

def run_estimation_model():
    # Scale Tiers configuration
    tiers = {
        "Small": {
            "services": 10,
            "log_gb": 50,
            "metric_eps": 100000,
            "sre_count": 0,       # Shared effort (no dedicated SRE)
            "sre_salary": 0
        },
        "Medium": {
            "services": 100,
            "log_gb": 500,
            "metric_eps": 1000000,
            "sre_count": 1,       # 1 Dedicated SRE
            "sre_salary": 5000.00
        },
        "Large": {
            "services": 1000,
            "log_gb": 5000,
            "metric_eps": 10000000,
            "sre_count": 3,       # 3 Dedicated SREs
            "sre_salary": 5000.00
        }
    }
    
    build_details = {}
    comparison = {}

    for name, cfg in tiers.items():
        estimator = CostEstimator(
            services=cfg["services"],
            log_gb_per_day=cfg["log_gb"],
            metric_events_per_sec=cfg["metric_eps"],
            sre_count=cfg["sre_count"],
            sre_salary=cfg["sre_salary"]
        )
        
        # Build breakdown
        build_details[name] = estimator.get_build_breakdown()
        
        # Build vs Buy comparison
        build_tco = build_details[name]["Total TCO ($)"]
        buy_total = estimator.calculate_datadog_cost()
        savings = round(buy_total - build_tco, 2)
        savings_pct = round((savings / buy_total) * 100, 2) if buy_total > 0 else 0
        
        comparison[name] = {
            "Build (Self-host TCO) ($)": build_tco,
            "Buy (Datadog SaaS) ($)": buy_total,
            "Monthly Savings ($)": savings,
            "Savings (%)": savings_pct
        }

    # Format output tables
    df_build = pd.DataFrame(build_details).T
    df_compare = pd.DataFrame(comparison).T
    
    print("\n" + "="*70)
    print("1. BUILD (SELF-HOSTED OPEN-SOURCE) COST BREAKDOWN PER COMPONENT")
    print("="*70)
    print(df_build[["Compute ($)", "Storage ($)", "Network ($)", "Infra Total ($)", "SRE Operational ($)", "Total TCO ($)"]].to_string())
    
    print("\n" + "="*70)
    print("2. BUILD (SELF-HOSTED) VS BUY (DATADOG SAAS) COMPARISON")
    print("="*70)
    print(df_compare.to_string())
    print("="*70 + "\n")

if __name__ == "__main__":
    run_estimation_model()
