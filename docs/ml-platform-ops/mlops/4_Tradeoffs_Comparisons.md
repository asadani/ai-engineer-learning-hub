# Tradeoffs & Comparisons

## Pipeline Orchestrator Comparison

| Dimension | SageMaker Pipelines | Apache Airflow | Metaflow | Kubeflow Pipelines |
|-----------|--------------------|--------------|---------|--------------------|
| **Learning curve** | Low (AWS console) | Medium | Low (Python decorators) | High (Kubernetes) |
| **AWS integration** | Native | Plugin-based | Native (via S3/EC2) | Manual |
| **Compute flexibility** | SageMaker only | Any | Any (local + cloud) | Kubernetes only |
| **Parallelism** | Built-in branching | TaskGroup | Native fan-out | Native |
| **Artifact versioning** | S3 + pipeline steps | Manual | Built-in per step | Built-in |
| **Local dev experience** | Poor (AWS-only) | Medium | Excellent | Poor |
| **Dependency on infra** | AWS account | Airflow cluster | Minimal | K8s cluster |
| **Production maturity** | High | Very High | High | Medium |
| **Best for** | AWS-native teams | Data eng + ML combined | ML-first teams | Platform teams |

**Decision heuristic:**
- Already running Airflow for ETL? → Airflow (avoid second orchestrator)
- AWS-native org, want managed infra? → SageMaker Pipelines
- Small ML team, fast iteration? → Metaflow (lowest overhead per engineer)
- Platform team building infra for many teams? → Kubeflow or SageMaker Pipelines

---

## Feature Store Comparison

| Dimension | Feast (OSS) | SageMaker Feature Store | Tecton | Hopsworks |
|-----------|------------|------------------------|--------|-----------|
| **Hosting** | Self-hosted | AWS managed | SaaS | Self-hosted or SaaS |
| **Streaming features** | Limited | Kinesis integration | First-class | First-class |
| **Point-in-time joins** | Yes | Yes | Yes | Yes |
| **Online latency** | 5–10ms (Redis) | 5–15ms | 5–10ms | 5–10ms |
| **Transformation at serving** | No | No | Yes | Yes |
| **Multi-cloud** | Yes | AWS only | Yes | Yes |
| **Ops overhead** | High | Low | Low (SaaS) | Medium |
| **Cost** | Infrastructure only | Pay per operation | $$$+ | Infrastructure |
| **Best for** | Full control, multi-cloud | AWS teams, managed | Streaming features, SaaS budget | On-prem, full platform |

**The training-serving skew test:** Before choosing any feature store, ask: "Can I use the same feature definition for both offline training data and online serving requests?" If yes, you've solved the skew problem. Feast, Tecton, and SageMaker Feature Store all answer yes.

---

## Model Monitoring Strategy Comparison

| Strategy | When to Use | Label Availability | Cost | Detection Lag |
|---------|------------|-------------------|------|---------------|
| **Statistical drift (KS, PSI, χ²)** | Always — no labels needed | Not required | Low | Minutes–hours |
| **Prediction distribution monitoring** | Always — watch output shift | Not required | Low | Minutes |
| **Performance monitoring** | When labels arrive promptly | Required within hours | Medium | Hours–days |
| **Business metric monitoring** | High-stakes decisions | Implicit (click, purchase) | Low | Hours |
| **Shadow model comparison** | Major model updates | Not required | High (run two models) | Minutes |
| **Human review sampling** | Regulated domains, NLP | Expensive to generate | High | Days |

**The label delay problem:** For many real-world tasks, ground truth arrives late:
- Fraud detection: chargebacks arrive 60–90 days later
- Loan default: months to years
- Medical diagnosis: follow-up required

When labels are delayed, rely on input distribution monitoring (drift detection) as the early warning system. Performance monitoring is the lagging indicator that confirms the problem.

**PSI vs KS test:**
- PSI (Population Stability Index): industry standard in credit/fraud, gives a continuous severity score, better for scorecard monitoring
- KS test: more statistically rigorous, gives p-value, better for feature-level drift testing
- Use PSI for summary-level production monitoring; use KS for feature-level investigation

---

## Model Deployment Strategies

| Strategy | Risk | Rollback Speed | Infrastructure Cost | Use When |
|---------|------|----------------|--------------------|---------|
| **Blue-Green** | Low | Instant (DNS flip) | 2× (run both) | Major model rewrites, need instant rollback |
| **Canary (% traffic)** | Low | Fast (shift traffic back) | 1.1–1.5× | Standard model updates, gradual confidence building |
| **Shadow** | Zero (no production impact) | N/A | 2× | Validating before any user exposure |
| **A/B test** | Low | Fast | 1.5× | Comparing model variants with statistical rigor |
| **Rolling update** | Medium | Slow | 1× | Cost-sensitive, can tolerate brief mixed versions |
| **Champion-Challenger** | Low | Fast | 1.1× | Continuous improvement with conservative guardrails |

**The shadow deployment pattern in detail:**

```python
# Shadow: new model runs but its predictions are not served
# Used for 24–72 hours before any user exposure

class ShadowDeployment:
    def __init__(self, champion_model, challenger_model):
        self.champion = champion_model
        self.challenger = challenger_model
        self.comparison_log = []

    def predict(self, features: dict) -> dict:
        champion_pred = self.champion.predict(features)

        # Run challenger asynchronously (don't block serving latency)
        import threading
        def log_challenger():
            challenger_pred = self.challenger.predict(features)
            self.comparison_log.append({
                "champion": champion_pred,
                "challenger": challenger_pred,
                "features": features,
                "timestamp": time.time(),
            })
        threading.Thread(target=log_challenger, daemon=True).start()

        return champion_pred  # serve only champion

# After 24h, analyze comparison_log:
# - Do predictions agree? (high agreement = safe to canary)
# - Where do they disagree? (understand challenger's change surface)
# - Which predictions were correct? (if labels available)
```

---

## Batch vs Online Feature Serving

| Dimension | Batch Features | Online Features (Feature Store) |
|-----------|---------------|--------------------------------|
| **Latency** | N/A (offline only) | < 10ms |
| **Freshness** | Hours–days | Seconds–minutes (streaming) |
| **Cost** | Low (S3 storage) | Higher (Redis/DynamoDB) |
| **Complexity** | Low | Higher (dual store maintenance) |
| **Use case** | Training, offline scoring | Real-time inference |

**When batch features are sufficient for production:**
- Credit scoring run once per day per customer (batch inference)
- Email recommendation computed nightly
- Fraud models with 1-hour acceptable latency

**When you need online features:**
- Transaction fraud: model must run in < 200ms at checkout
- Real-time pricing or personalization
- Dynamic ad targeting

**The dual-write problem:** When both batch and streaming pipelines update the same feature, there's risk of inconsistency. Solutions:
1. **Lambda architecture:** Batch layer for accuracy, speed layer for recency; merge at serving time
2. **Kappa architecture:** Single streaming pipeline that handles both; simpler but requires streaming for all features
3. **Feature store platform (Tecton):** Handles this automatically

---

## Experiment Tracking: MLflow vs W&B

| Dimension | MLflow | W&B |
|-----------|-------|-----|
| **Self-hostable** | Yes | Yes (W&B Server, $$) |
| **Data residency** | Full control | Cloud by default |
| **Model registry** | Full-featured | Full-featured |
| **Hyperparameter optimization** | No (use Optuna/Ray Tune) | Built-in (Sweeps, Bayesian) |
| **Visualization** | Basic | Rich, interactive |
| **Team collaboration** | Limited | First-class |
| **Integration breadth** | Wide (any framework) | Wide |
| **Cost** | Free (OSS) + hosting | $0 free / $50+/mo teams |
| **Best for** | Cost control, AWS-native, compliance | Teams, rich visualization, sweeps |

**Hybrid approach (what many production teams use):**
- MLflow for model registry, model serving, and compliance (self-hosted, auditable)
- W&B for experiment visualization and hyperparameter sweeps (cloud, accessible)
- Log run metadata to both

---

## SageMaker Model Monitor vs Custom Monitoring

| Dimension | SageMaker Model Monitor | Custom (Evidently + CloudWatch) |
|-----------|------------------------|--------------------------------|
| **Setup effort** | Low (wizard-based) | Medium |
| **Flexibility** | Limited (preset detectors) | Full control |
| **Statistical tests** | Basic (min/max/mean, simple drift) | Any (KS, PSI, MMD, custom) |
| **Cost** | Per monitoring job ($0.20/hour) | Processing cost only |
| **LLM/embedding monitoring** | No | Yes (Evidently Descriptors) |
| **Custom metrics** | Limited | Unlimited |
| **Alerting** | CloudWatch → SNS | CloudWatch → any |
| **Best for** | Tabular models, AWS-native, simple drift | Complex models, embedding drift, custom logic |

---

## Retraining Trigger: Schedule vs Event-Driven

| Trigger Type | Pros | Cons | Best For |
|-------------|------|------|---------|
| **Time-based (cron)** | Predictable, simple, easy to audit | Retrains even when unnecessary; misses sudden drift | Stable data, regulatory schedules |
| **Drift-triggered** | Reactive to actual distribution change | May retrain too frequently; drift ≠ always bad | Dynamic environments, rapid data changes |
| **Performance-triggered** | Directly tied to model quality | Requires labeled data; label delay reduces responsiveness | High-stakes decisions with fast label arrival |
| **Data volume threshold** | Simple, data-centric | Doesn't measure quality | Data-hungry models, append-only datasets |
| **Hybrid (schedule + drift gate)** | Balanced | More complex logic | Most production systems |

**The hybrid trigger pattern (recommended):**
```python
# Retrain if: (1) weekly schedule AND (2) data has grown > 10% OR drift detected
# This avoids unnecessary retraining while ensuring freshness

def should_retrain(
    last_retrain: datetime,
    data_volume_pct_increase: float,
    drift_detected: bool,
    min_retrain_interval_days: int = 7,
) -> tuple[bool, str]:
    days_since_retrain = (datetime.utcnow() - last_retrain).days

    if days_since_retrain < min_retrain_interval_days:
        return False, "Too soon since last retrain"

    if drift_detected:
        return True, "Data drift detected"

    if data_volume_pct_increase > 0.10:
        return True, f"Data grew {data_volume_pct_increase:.0%} since last retrain"

    if days_since_retrain > 30:
        return True, "Scheduled monthly retrain"

    return False, "No trigger condition met"
```
