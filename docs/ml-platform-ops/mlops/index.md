# MLOps

Principal-level interview prep notes on productionizing machine learning — feature stores, experiment tracking, CI/CD for models, drift monitoring, retraining pipelines, and governance.

---

## Contents

| # | File | Words | Focus |
|---|------|-------|-------|
| 1 | [High Level Overview](1_High_Level_Overview.md) | 1,036 | ML system iceberg, lifecycle, failure modes, maturity levels, 4 pillars |
| 2 | [Key Technical Concepts](2_Key_Technical_Concepts.md) | 1,759 | Feature stores (Feast), experiment tracking (MLflow), model registry, CI/CD for ML, data versioning (DVC), drift detection (Evidently, PSI, KS), serving (BentoML, SageMaker), retraining pipeline (SageMaker Pipelines) |
| 3 | [Products & Tools](3_Products_Tools.md) | 1,077 | MLflow, W&B, DVC, Feast, Tecton, SageMaker Pipelines, Airflow, Metaflow, Evidently, Arize, Great Expectations |
| 4 | [Tradeoffs & Comparisons](4_Tradeoffs_Comparisons.md) | 1,537 | Orchestrator comparison, feature store comparison, deployment strategies, monitoring approaches, retraining trigger patterns |
| 5 | [Use Cases](5_Use_Cases.md) | 1,447 | Real-time fraud detection, NLP retraining pipeline, recommendation system, LLM governance, regulatory model (SR 11-7) |
| 6 | [Measurement & Evaluation](6_Measurement_Evaluation.md) | 1,203 | Data quality eval, drift detection (PSI/KS/JS), model performance, serving health, pipeline reliability |
| 7 | [What to Measure & How](7_What_to_Measure_How.md) | 1,415 | Metrics tables (data quality/drift/performance/infra/pipeline), CloudWatch instrumentation, alerting YAML |
| 8 | [Interview Questions](8_Interview_Questions.md) | 3,342 | 10 tiered Q&As (L5/L6/L7+) with model answers |

**Total: ~12,816 words**

---

## Key Themes

### 1. The 95% Problem
Model code is ~5% of a production ML system. The other 95% — data pipelines, feature stores, serving infrastructure, monitoring, CI/CD — is what determines whether the system actually works. Teams that focus only on model accuracy and ignore the infrastructure ship unreliable systems.

### 2. Training-Serving Skew Is the Most Common Production Failure
Features computed differently in training vs serving cause silent model degradation. The fix: define feature computation once and use it for both (feature store). Every MLOps design review should start with: "How do we guarantee feature consistency?"

### 3. Monitoring Requires Multiple Signals
- **Data quality:** catches upstream pipeline failures (immediate)
- **Feature drift:** leading indicator of model degradation (hours)
- **Performance metrics:** lagging indicator requiring labels (days to months)
- **Business metrics:** implicit labels from user behavior (hours)

No single signal is sufficient. Design for all four layers.

### 4. Deployment Strategy Determines Recovery Time
Every model deployment should have a rollback plan that takes < 5 minutes. Canary deployments (traffic weight shifting) give you this. Full redeployments don't. The investigation happens after the rollback, not during.

### 5. The Label Delay Problem
For fraud, credit, medical, and many other high-stakes domains, ground truth arrives weeks to months after the prediction. Build proxy monitoring (drift detection, business metrics, prediction distribution) that works without labels. Don't wait for labels before detecting problems.

---

## MLOps Maturity Quick Reference

| Level | What You Have | What You're Missing |
|-------|--------------|---------------------|
| **0 — Manual** | Notebooks, ad-hoc training, manual deploy | Everything below |
| **1 — Reproducible** | Experiment tracking, data versioning, git | Automated pipeline, monitoring |
| **2 — Automated** | CI/CD for models, quality gates, basic monitoring | Drift detection, feature store, event-driven retraining |
| **3 — Full MLOps** | Feature store, drift-triggered retraining, A/B infra, automated rollback | — |

---

## Tool Landscape Summary

| Category | AWS-native | Open Source | SaaS |
|----------|-----------|------------|------|
| Experiment tracking | SageMaker Experiments | **MLflow** | **W&B** |
| Data versioning | — | **DVC** | — |
| Feature store | SageMaker Feature Store | **Feast** | **Tecton** |
| Pipeline orchestration | **SageMaker Pipelines** | Airflow, **Metaflow**, Kubeflow | Prefect |
| Model registry | SageMaker Model Registry | **MLflow Registry** | W&B |
| Model serving | **SageMaker Endpoints** | BentoML, vLLM | Seldon |
| Drift / monitoring | SageMaker Model Monitor | **Evidently** | **Arize**, WhyLabs |
| Data quality | Glue Data Quality | **Great Expectations** | Monte Carlo |

**Bold** = most commonly used in practice (2025)

---

## Critical Interview Distinctions

**Data drift vs concept drift:** Data drift = P(X) shifts (inputs look different). Concept drift = P(Y|X) shifts (same inputs, different correct outputs). Data drift is detectable without labels; concept drift requires labels to confirm. Concept drift is more dangerous — it means the model's learned knowledge is wrong, not just its input distribution.

**Feature store vs feature engineering:** Feature engineering is the code that computes features. A feature store is the infrastructure that stores, versions, and serves features consistently between training and production. You can do feature engineering without a feature store (but you'll probably have skew).

**PSI vs KS test:** PSI (Population Stability Index) is a single summary statistic for distribution shift — widely used in credit/finance, gives a severity level (< 0.1 = stable, 0.1–0.2 = slight, > 0.2 = significant). KS test is a statistical hypothesis test that gives a p-value (is the shift statistically significant?). Use PSI for dashboards and alerting thresholds; KS for rigorous feature-level investigation.

**Canary vs shadow deployment:** Canary = new model serves a % of users (they see the new model's outputs). Shadow = new model runs but outputs are not served (users see the champion). Shadow is zero-risk but can't capture business metric feedback. Canary is the right choice for most production deployments; shadow is appropriate before any user exposure of a high-stakes change.

**Scheduled vs drift-triggered retraining:** Scheduled is predictable and auditable — run every Monday, know exactly when the model was last trained. Drift-triggered is responsive — retrain when the world changes, not on a calendar. Best practice: schedule as the baseline, drift as an additional trigger, with a minimum interval guard to prevent thrashing.


---

!!! info "Official Sources & Further Reading"

    - [Google Cloud — MLOps: continuous delivery & automation pipelines](https://cloud.google.com/architecture/mlops-continuous-delivery-and-automation-pipelines-in-machine-learning)
    - [Sculley et al. (2015) — Hidden Technical Debt in ML Systems](https://papers.nips.cc/paper_files/paper/2015/hash/86df7dcfd896fcaf2674f757a2463eba-Abstract.html)
    - [MLflow — documentation](https://mlflow.org/docs/latest/index.html)
    - [Feast — feature store documentation](https://docs.feast.dev/)
    - [Evidently — ML monitoring documentation](https://docs.evidentlyai.com/)


!!! tip "Related Topics"

    - [Evals in AI](../evals-in-ai/)
    - [Precision, Recall, F1 & AI Metrics](../precision-recall-f1-and-ai-metrics/)
    - [LLM Observability & LLMOps](../llm-observability-llmops/)
    - [AI Safety & Guardrails](../ai-safety-guardrails/)
    - [Cost Optimization for AI Pipelines](../../llm-engineering/cost-optimization-ai-pipeline/)
    - [Data-Driven Architecture](../../architecture/data-driven-architecture/)
