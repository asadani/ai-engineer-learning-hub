# Interview Questions & Model Answers

## L5 — Senior Engineer

---

**Q1: What is training-serving skew and how do you prevent it?**

**A:** Training-serving skew is when the feature values a model receives in production differ from what it was trained on, causing degraded performance that's difficult to detect because the model continues to return predictions without errors.

**The three root causes:**
1. **Different computation logic:** The training pipeline uses a SQL GROUP BY to compute "average purchase amount in last 30 days" on historical data. The serving code queries a real-time database using a different date window or rounding behavior. Small numeric differences compound across features into significant prediction drift.
2. **Point-in-time violations:** Training uses features as they exist today; at training time, you inadvertently join features from the future relative to the label timestamp. The model learns from information it won't have at serving time.
3. **Pipeline differences:** Training runs a Python preprocessing function; serving calls a REST API written in Java. The Java version handles edge cases differently (null → 0 vs null → -1, different string normalization).

**Prevention:**
- **Feature store:** Define feature computation once. The same transformation logic runs for both training (historical backfill) and serving (real-time lookup). Feast and SageMaker Feature Store solve this architecturally.
- **Point-in-time correct joins:** Always join training labels to features using the label timestamp, not the current timestamp. Feature stores handle this; ad-hoc SQL often doesn't.
- **Shared preprocessing code:** Package all feature transformations as a library used by both training and serving. No separate implementations.
- **Detect it:** Log training feature statistics; log serving feature statistics; compare distributions on a schedule. A divergence in mean or variance of a feature is often the first signal.

---

**Q2: You've been asked to add monitoring to a binary classifier in production. What do you monitor, what tools do you use, and what are the alerting thresholds?**

**A:** I monitor at three levels, each requiring different data:

**Level 1: Input distribution (no labels needed, runs hourly)**
Track feature-level drift using PSI for numeric features (alert > 0.20) and chi-squared test for categorical features (alert on p < 0.01). Use Evidently or SageMaker Model Monitor. Track prediction score distribution PSI as a leading indicator — if the model is scoring more transactions as high-risk this week vs last, something changed in the input or the real-world behavior.

**Level 2: Serving health (no labels needed, runs in real-time)**
Track latency p50/p99 from CloudWatch endpoint metrics (alert: p99 > 500ms). Track error rate (alert: > 1%). Track throughput against capacity limits. These are operational metrics, not ML metrics, but ML system failures often manifest here first.

**Level 3: Model performance (requires labels, runs when labels arrive)**
For fraud: chargebacks arrive 60–90 days later. Run performance checks (AUC-PR, precision at manual review threshold) on lagged data and alert if > 3% regression vs baseline. Also run slice checks — if performance is holding overall but degrading for a specific merchant category or geography, that's an early warning of a domain shift.

**The alert hierarchy:** Level 2 failures are P1 (page on-call now). Level 1 drift is P2 (Slack alert, investigate within 24h, consider triggering retraining). Level 3 regression is P1 if severe or P2 if mild (5% regression vs threshold), with a rollback playbook.

**Tools:** Evidently for open-source drift detection + Great Expectations for data quality. CloudWatch for serving metrics. S3 + Athena for storing and querying prediction logs. SageMaker Model Monitor if you're on AWS and want managed drift detection without custom code.

---

**Q3: Explain the difference between data drift, concept drift, and covariate shift. Give a concrete example of each.**

**A:**

**Data drift / feature drift** — P(X) changes; the distribution of input features shifts. The relationship between X and Y may or may not change.
- Example: A fraud model trained in January. By November, transaction amounts have inflated 20% due to economic conditions. The feature `transaction_amount` distribution has shifted. Detection: PSI on `transaction_amount` flags significant drift.

**Covariate shift** — A specific type of data drift where P(X) changes but P(Y|X) is assumed constant (same conditional relationship). The model's fundamental understanding is still correct, but the inputs look different.
- Example: An e-commerce recommendation model trained during summer has different user behavior than winter. Users browse different categories, but the relationship "users who viewed X also buy Y" holds. The model may need recalibration rather than retraining.

**Concept drift** — P(Y|X) changes; the relationship between features and labels evolves. The fundamental signal the model learned is no longer valid.
- Example: A fraud model trained before a new scam type emerges. The new scam uses features that previously indicated legitimate transactions (small amounts, familiar merchants). The underlying mapping from features to fraud has changed. Detection: performance degradation when labels arrive; no amount of distribution-matching fixes this — you need new labeled examples of the new fraud type.

**Why the distinction matters operationally:**
- Data drift: may be addressable by recalibrating or reweighting without full retraining
- Covariate shift: can sometimes be corrected via importance weighting during training
- Concept drift: requires new labeled data and full retraining; the hardest to detect early (it's invisible until labels arrive)

---

**Q4: What is a model registry and why do teams need one beyond just versioning model files in S3?**

**A:** A model registry is a versioned catalog of trained models with metadata, lifecycle state management, and deployment governance — not just file storage.

The key capabilities beyond S3:
1. **Lifecycle state machine:** `None → Staging → Production → Archived`. You can query "what model version is currently in production?" and get an answer that's enforced by the system, not by a spreadsheet.
2. **Metadata linkage:** Each version links to its training run (hyperparameters, metrics, dataset version, code commit). You can answer "what data was this model trained on?" from the registry, not from someone's memory.
3. **Approval gates:** Promote to production requires an explicit action (human or CI). This creates an audit trail: who approved, when, with what metrics justification.
4. **Deployment automation:** Serving infrastructure subscribes to registry events. When a model is approved to Production, a Lambda triggers a SageMaker endpoint update. No manual deploy steps.
5. **Rollback:** "Roll back to the previous production model" is a registry operation that takes 30 seconds, not an engineering war room.

**Without a model registry:** you have a folder in S3 named `fraud_model_v3_FINAL_really_final.pkl`, no link to the training run that produced it, no knowledge of who approved it for production, no automated way to roll back, and a 2-hour incident when something goes wrong.

---

## L6 — Staff Engineer

---

**Q5: Design the MLOps architecture for a fraud detection system serving 50M transactions/day with a 200ms SLA. Focus on the tradeoffs you'd make.**

**A:** I'd design around three constraints: latency, freshness, and reliability — and these create explicit tradeoffs.

**Serving architecture:**
SageMaker endpoint with 2 production variants (primary + dark canary). Multi-AZ with auto-scaling triggered on InvocationsPerInstance. P99 budget: 200ms total = ~10ms feature retrieval + ~30ms inference + ~160ms buffer for downstream decision engine.

**Feature strategy:**
The latency SLA eliminates any feature that requires a batch join at serving time. I'd split into two tiers:
- **Real-time features** (Redis, < 5ms): transaction velocity counts, session features, device reputation scores. Computed by a Flink/Kinesis Analytics job from the transaction stream.
- **Near-real-time features** (DynamoDB via SageMaker Feature Store, < 10ms): customer behavior aggregates refreshed every 5 minutes.
- **Batch features** (materialized to online store nightly): customer lifetime value, historical default rates.

**Tradeoff #1: Feature freshness vs latency.** I chose 5-minute refresh for behavioral aggregates rather than real-time. True real-time would require Flink → online store with sub-second lag, but the engineering complexity and cost aren't justified by the marginal fraud detection improvement. Fraud patterns don't shift in seconds.

**Tradeoff #2: Model complexity vs serving latency.** LightGBM at 30ms p99 rather than a deep neural network at 100ms. At 50M tx/day, the latency budget matters more than squeezing 2% more AUC.

**Monitoring:**
- SageMaker Model Monitor + Evidently: hourly drift check on feature PSI
- CloudWatch on serving metrics: alert at p99 > 150ms (before SLA breach)
- Prediction distribution PSI: alert if output score distribution shifts (leading indicator, no labels needed)
- Performance check with 90-day lagged chargebacks: AUC-PR + precision at manual review cap

**Retraining:**
Weekly scheduled retraining as baseline. Drift-triggered retraining (Evidently → EventBridge → SageMaker Pipeline) if critical feature PSI > 0.2 or prediction score PSI > 0.15. Quality gate: must pass 85% AUC-PR threshold and not regress by > 3% on holdout before promotion.

**Rollback:**
SageMaker variant weights — shift 100% traffic back to archived version in < 60 seconds via API call. No redeployment needed.

---

**Q6: Your team is about to deploy a new version of a credit scoring model. What's your deployment plan, and what would make you abort and roll back?**

**A:** Credit scoring has regulatory weight (FCRA, ECOA compliance) and high-stakes outcomes. The deployment plan is more conservative than a typical ML model.

**Pre-deployment (1–2 weeks before):**
- Shadow deployment: route 10% of traffic to the new model; capture its predictions without serving them. Compare predictions to champion model. If agreement rate < 80%, investigate before any user exposure — large prediction changes require review.
- Run regulatory back-test: validate new model on Q4 holdout data. Generate model card documenting training data, performance metrics, fairness analysis, and approval chain.
- Get human approval from the model risk management team (per SR 11-7). Document this in the model registry.

**Deployment: phased canary**
- Hour 0: 5% canary weight to new model. Monitor latency, error rate, prediction distribution PSI.
- Hour 24: If metrics hold, increase to 25%.
- Day 3: 50% if business metrics (approval rate, exception rate) within expected range.
- Day 7: 100% production if all gates passed.

**Rollback triggers (automatic):**
- Error rate > 1% on new variant → immediate rollback via weight shift
- P99 latency > 500ms on new variant → rollback
- Prediction score distribution PSI > 0.15 vs champion → halt canary, investigate

**Rollback triggers (manual, requires review):**
- Approval rate deviates > 5% from expected (could indicate legitimate model improvement or systematic bias)
- Any regulatory complaint or consumer dispute suggesting model error
- Slice metric disparity increases beyond 0.10 across demographic groups

**The principle:** Canary deployments mean rollback is always < 5 minutes (shift traffic weights back). The investigation happens after the rollback, not during. Never leave users on a potentially broken model while debugging.

---

**Q7: What is the label delay problem in production ML monitoring, and what techniques do you use to detect model degradation before labels arrive?**

**A:** Label delay is when ground truth arrives significantly after the prediction. Examples:
- Fraud: chargeback arrives 60–90 days after the transaction
- Loan default: months to years
- Medical diagnosis: follow-up test required
- Churn: subscription cancels weeks after the model said "at risk"

**The problem:** Your monitoring is blind during the delay window. If the model degraded in January, you won't see performance metrics until March when January's chargebacks arrive. By then, you've been serving bad predictions for months.

**Proxy detection techniques (no labels needed):**

1. **Prediction score distribution monitoring (PSI):** Track the distribution of model output scores. If a fraud model that typically produces scores with mean 0.15 suddenly shifts to mean 0.25, something changed — either the input data or the model's behavior. PSI on output scores is a fast leading indicator. Alert threshold: PSI > 0.15.

2. **Input feature drift:** Feature drift precedes performance degradation. If transaction amounts, merchant categories, or device fingerprints shift significantly, the model is operating outside its training distribution. KS test on numeric features, chi-squared on categorical. Alert: > 30% of features drifted.

3. **Business metric monitoring:** Even without ML-specific labels, business metrics react to model quality. Fraud model: manual review team's workload, chargeback rate, false positive complaints. Recommendation model: click-through rate, conversion. These are available in near-real-time and correlate with model quality.

4. **Short-delay proxy labels:** For some domains, you can engineer fast proxies. For fraud, "merchant dispute filed within 7 days" is available faster than "chargeback resolved in 90 days" and correlates strongly with final fraud labels.

5. **Champion-challenger comparison:** Run a shadow model trained on more recent data alongside production. If the shadow model's predictions diverge significantly, it's a signal the production model is stale even without final labels.

**The operational answer:** Design your monitoring stack to trigger retraining from drift signals (fast, no labels) and validate retraining decisions from performance signals (slow, with labels). Don't wait for labels to start investigating.

---

## L7+ — Principal Engineer

---

**Q8: You're building an MLOps platform to be used by 50 data science teams across a large company. What are the hardest problems and how do you design for them?**

**A:** The hard problems are not the technical ones — tooling exists for all of them. The hard problems are organizational: how do you build a platform that 50 teams actually adopt and trust.

**Problem 1: Heterogeneous use cases.** Fraud team needs < 200ms latency with real-time features. NLP team needs 4GB models served on GPU. Recommendation team needs batch scoring of 10M users nightly. A single platform must handle all of these without forcing every team to use the same architecture. **Solution:** Build modular primitives (feature store, model registry, monitoring) that compose rather than a rigid end-to-end workflow. Teams own their training pipelines; the platform provides the shared components they opt into.

**Problem 2: Adoption vs standardization tension.** If the platform is too opaque, teams build their own shadow infrastructure. If it's too prescriptive, teams reject it. **Solution:** Make the default path easy and the right thing. Contribute pre-built CI templates (GitHub Actions, SageMaker Pipeline templates) that work for 80% of use cases. For the other 20%, expose escape hatches — the feature store has a custom transformation API, the monitoring framework accepts custom metrics.

**Problem 3: Production readiness governance.** Without a process, teams deploy models with no monitoring, no rollback plan, and no documentation. One incident damages trust in ML broadly. **Solution:** Implement a production readiness checklist as a GitHub PR check that blocks deployment: monitoring configured, drift thresholds set, rollback plan documented, quality gate passing, model card generated. Make it automated, not a bureaucratic form.

**Problem 4: Data lineage and reproducibility at scale.** 50 teams, 200 models in production, data comes from 30 different sources. A regulatory audit asks: "For this credit scoring model deployed 6 months ago, what training data was used and was it fair?" Without systematic lineage, this is a multi-week fire drill. **Solution:** Every training run must log: data source URIs + versions (DVC hash), code commit SHA, docker image hash, hyperparameters. The model registry links model version → training run → all of the above. Automate this via a training wrapper that teams use instead of calling `mlflow.start_run()` directly.

**Problem 5: Platform reliability.** If the feature store goes down, 50 teams' models degrade simultaneously. The platform becomes a blast radius multiplier. **Solution:** Design for graceful degradation. Models must have fallback behavior (stale features, rule-based fallback) when platform components fail. SLAs for platform components must be stricter than the SLAs of the models they serve.

---

**Q9: Debate this claim: "Every ML model in production needs continuous retraining triggered by drift detection."**

**A:** This is mostly wrong, and the teams that implement it naively create more problems than they solve.

**Where the claim fails:**

Drift detection triggering retraining assumes: (1) detected drift implies degraded performance, and (2) retraining on new data will fix it. Both assumptions are often wrong.

(1) Distribution shift can improve model performance. If training data was biased toward one demographic and production traffic becomes more representative, PSI fires — but you shouldn't retrain to match the training distribution, you should celebrate that the model is now seeing the population it's supposed to serve.

(2) Retraining on shifted data doesn't guarantee better predictions. If the shift is due to a labeling pipeline bug that started injecting mislabeled examples, retraining accelerates the degradation. You need to understand the root cause of drift before you pull the trigger.

**Where the claim holds:**

For narrow-domain, high-volume models with fast label feedback and rapidly evolving patterns — fraud, real-time bidding, news recommendation — automated retraining triggered by drift makes sense and is necessary. The models decay within weeks without it.

**The right design:**

Retraining triggers should be **conditions on multiple signals**, not a single drift alert:
- Drift detected AND
- Data quality checks pass AND
- Human review confirms the drift is real, not a monitoring artifact AND
- (If labels available) Performance has regressed

The pipeline should also include a **retrain quality gate** — if retraining on the new data doesn't produce a better model than the current champion, don't deploy. Automated retraining without this gate can break production when the triggering distribution change was a data error.

**My answer to the debate:** Continuous retraining is the right goal for a mature ML platform. But "triggered by drift detection" must be one signal in a multi-signal system, not an automatic binary trigger. The fastest path to production instability is an automated pipeline that retrains and redeploys in response to every drift alert.

---

**Q10: How do you build MLOps for LLM applications, and how does it differ from classical ML MLOps?**

**A:** LLM MLOps shares the same goals as classical MLOps — reproducibility, automation, monitoring, governance — but almost every implementation detail differs.

**What's the same:**
- Experiment tracking (MLflow/W&B) — still valuable; track prompt versions as hyperparameters
- Model registry — still needed, but what you register is a (base model + adapter weights + prompt config) bundle, not a standalone model file
- Deployment automation — same canary/blue-green patterns apply
- Quality gates — still block bad versions from reaching production

**What fundamentally differs:**

**Evaluation:** Classical models have clear numeric metrics (AUC-PR, RMSE). LLM output quality is multidimensional and subjective — accuracy, helpfulness, format compliance, safety, tone. Requires LLM-as-judge at scale and human spot-checks, not just automated metrics. Build an eval pipeline that runs LLM judge on a golden dataset (200–500 examples with human reference outputs) before every deployment.

**Monitoring:** You can't monitor LLM output quality with statistical drift tests on numeric values. Monitor:
- Input token length distribution (user query complexity shifting)
- Output token length distribution (model becoming more verbose or terse)
- Embedding drift on inputs and outputs (semantic shift in what users ask and model responds)
- LLM-judge quality score trend (run judge on 5% sample; track rolling average)
- Hallucination rate (specific to domain — fact-checkable claims)

**Versioning:** A "model version" is now: base model version + fine-tune adapter hash + system prompt version + retrieval configuration. Any of these changing constitutes a new version. All must be tracked together in the registry. Prompt changes are deployments, not just config changes — they affect model behavior as much as weight changes.

**Retraining:** For fine-tuned LLMs, retraining is a full fine-tuning run (hours on GPU), not a 30-minute gradient boost job. This changes the economics: retrain less frequently, validate more thoroughly before deploying. The trigger for retraining is typically: human preference ratings dropping below threshold, hallucination rate increasing, or new domain data available (quarterly).

**Cost:** LLM inference cost is 10–1000× classical ML inference cost. Cost-per-request is a first-class metric in LLM MLOps in a way it rarely is for tabular models. Build per-feature, per-user cost attribution from day one.

**The synthesis:** The pipeline phases (validate → train → eval → register → deploy → monitor → trigger) are the same. The tooling for each phase is different and often more complex because LLM quality is harder to measure automatically. The principal engineer's job is to decide which quality signals are reliable enough to automate (format compliance, hallucination on known facts) and which require human review (tone, helpfulness) — and build a system that combines both without requiring a human to review every deployment.
