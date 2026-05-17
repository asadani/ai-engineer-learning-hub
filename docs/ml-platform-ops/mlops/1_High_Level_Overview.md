# MLOps — High Level Overview

## What MLOps Actually Solves

MLOps is the engineering discipline that makes machine learning reliable in production. The core problem it solves: ML systems are uniquely brittle because they have **two failure surfaces** that traditional software doesn't.

**Traditional software failure surface:**
- Code bugs → caught by tests and CI/CD

**ML failure surfaces:**
1. Code bugs → same as traditional software
2. **Data/distribution shift** → model degrades silently without any code change. No exception is thrown. The system keeps running. Users get worse results.

MLOps builds the systems that catch failure surface #2: continuous validation of data quality, model performance, and prediction distribution in production.

---

## The ML System Iceberg

The model code is ~5% of a production ML system. The remaining 95%:

```
┌─────────────────────────────────────────────────────┐
│                    ML System                         │
│                                                     │
│  Model Code (5%)                                    │
│  ┌─────────────┐                                    │
│  │  train.py   │                                    │
│  └─────────────┘                                    │
│                                                     │
│  Supporting Infrastructure (95%)                    │
│  ┌────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │ Data       │  │ Feature      │  │ Experiment  │ │
│  │ Pipelines  │  │ Store        │  │ Tracking    │ │
│  └────────────┘  └──────────────┘  └─────────────┘ │
│  ┌────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │ Model      │  │ Serving      │  │ Monitoring  │ │
│  │ Registry   │  │ Infrastructure│  │ & Alerting │ │
│  └────────────┘  └──────────────┘  └─────────────┘ │
│  ┌────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │ CI/CD      │  │ Data         │  │ Drift       │ │
│  │ Pipelines  │  │ Versioning   │  │ Detection   │ │
│  └────────────┘  └──────────────┘  └─────────────┘ │
└─────────────────────────────────────────────────────┘
```

Teams that focus only on model code fail in production. The infra is where reliability lives.

---

## The ML Lifecycle

```
                    ┌──────────────────┐
                    │  Problem Framing │
                    │  + Data Sourcing │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  Data Validation │ ◄─── Great Expectations, Deequ
                    │  + EDA           │      Pandera, TFDV
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │ Feature          │ ◄─── Feast, Tecton, SageMaker
                    │ Engineering      │      Feature Store
                    └────────┬─────────┘
                             │
              ┌──────────────▼──────────────┐
              │   Model Training +           │ ◄─── MLflow, W&B, SageMaker
              │   Experiment Tracking        │      Training Jobs
              └──────────────┬──────────────┘
                             │
              ┌──────────────▼──────────────┐
              │   Model Evaluation +         │ ◄─── Offline evals, shadow
              │   Validation Gates           │      testing, sliced metrics
              └──────────────┬──────────────┘
                             │
              ┌──────────────▼──────────────┐
              │   Model Registry +           │ ◄─── MLflow Registry, SageMaker
              │   Staging                    │      Model Registry
              └──────────────┬──────────────┘
                             │
              ┌──────────────▼──────────────┐
              │   Deployment                 │ ◄─── Canary, Blue-Green,
              │   (Canary → Full)            │      Shadow, A/B
              └──────────────┬──────────────┘
                             │
              ┌──────────────▼──────────────┐
              │   Production Monitoring      │ ◄─── Evidently, Arize,
              │   + Drift Detection          │      WhyLabs, CloudWatch
              └──────────────┬──────────────┘
                             │ drift detected / schedule
                    ┌────────▼─────────┐
                    │   Retraining     │ ◄─── Triggered retraining,
                    │   Trigger        │      SageMaker Pipelines
                    └──────────────────┘
```

---

## Why ML Systems Fail in Production

**Training-serving skew (most common):** Features computed differently at training time (batch SQL) vs serving time (real-time lookup). The model was trained on values it never sees in production.

**Data distribution shift:** The world changes. A fraud model trained in 2023 sees different fraud patterns in 2025. A recommendation model trained in winter sees different engagement in summer.

**Label delay:** Ground truth arrives hours, days, or weeks after the prediction. You can't detect model degradation in real-time because you don't have labels yet.

**Reproducibility failure:** "The model worked last month" — but nobody tracked which dataset version, which hyperparameters, which code commit trained it. You can't reproduce it to debug.

**Feature pipeline failures:** Upstream data systems fail or change schema. Features become null or stale. The model silently receives garbage input and outputs confident garbage predictions.

---

## MLOps Maturity Levels

| Level | Characteristics | Trigger to Level Up |
|-------|----------------|---------------------|
| **0 — Manual ML** | Notebooks, manual training, manual deploy, no monitoring | Model degrades, nobody notices |
| **1 — Automated Training** | Scheduled retraining, experiment tracking, basic monitoring | Training is reproducible but deploy is manual and slow |
| **2 — Automated Pipeline** | CI/CD for models, automated eval gates, model registry, monitoring with alerts | Multiple models, multiple teams, need governance |
| **3 — Full MLOps** | Continuous training, feature store, A/B testing infra, automated rollback, drift-triggered retraining | High-velocity model deployment, regulatory requirements |

Most companies should target Level 2. Level 3 is appropriate for large ML platforms (recommendation, fraud, ads).

---

## The Four Core Pillars

**1. Reproducibility** — Given the same code, data, and config, you can reproduce any past training run exactly.
- Tools: Git + DVC (data), MLflow/W&B (experiments), Docker (environment)
- Test: Can you reproduce a model from 6 months ago? If not, Level 0.

**2. Automation** — The path from data to deployed model is a pipeline, not a person clicking through notebooks.
- Tools: SageMaker Pipelines, Kubeflow, Airflow, Metaflow
- Test: Can you retrain and redeploy with a single command / trigger?

**3. Monitoring** — You know within hours when model quality degrades, before users report it.
- Tools: Evidently, Arize Phoenix, WhyLabs, CloudWatch custom metrics
- Test: Simulate a distribution shift — does an alert fire?

**4. Governance** — Every production model is traceable to its data, code, and training run. Every deployment is approved.
- Tools: MLflow Model Registry, SageMaker Model Registry, AWS IAM
- Test: For any production model, can you answer: when was it trained, on what data, by whom, and who approved deployment?

---

## Key Vocabulary

| Term | Definition |
|------|-----------|
| **Training-serving skew** | Features computed differently in training vs production |
| **Data drift** | Input feature distribution changes over time |
| **Concept drift** | Relationship between features and labels changes |
| **Covariate shift** | P(X) changes but P(Y|X) stays the same |
| **Feature store** | Centralized system for computing, storing, and serving ML features |
| **Model registry** | Versioned catalog of trained models with metadata and lifecycle states |
| **Shadow deployment** | New model runs in production but predictions are not served; used for comparison |
| **Canary deployment** | New model serves small % of traffic; gradually increase if metrics hold |
| **Champion-challenger** | Current production model (champion) vs candidate (challenger) in A/B test |
| **Pipeline trigger** | Event that kicks off retraining (schedule, drift alert, data arrival) |
| **Lineage** | Traceable link from model → training run → dataset → raw data |
