# Interview Questions & Model Answers

## L5 (Senior Engineer) — Metric Fundamentals & Practical Application

---

### Q1: Why is accuracy a poor metric for fraud detection? What would you use instead, and why?

**Model Answer:**

Accuracy is misleading on imbalanced data because the null classifier — one that always predicts "not fraud" — achieves 99%+ accuracy on a dataset where fraud is 0.1–1% of transactions. The model never fires but scores brilliantly.

**What to use instead:**

1. **AUC-PR (Average Precision)** — the primary model quality metric. The PR curve shows, at every operating threshold, what fraction of flagged transactions are actually fraud (precision) vs. what fraction of all fraud you caught (recall). On highly imbalanced data, the PR curve is brutally honest: a random classifier sits near the positive class prevalence rate (e.g., 0.01), not 0.5 as in the ROC.

2. **F1 at the operating threshold** — once you've chosen a threshold (business decision), F1 gives the harmonic mean of precision and recall at that point.

3. **MCC (Matthews Correlation Coefficient)** — best single number for imbalanced binary classification. Considers all four quadrants of the confusion matrix, bounded in [−1, +1], and doesn't inflate on class imbalance.

4. **Dollar-weighted recall** — in fraud, not all transactions are equal. Missing a $50K wire transfer is worse than missing a $5 coffee. Weight TP, FP, FN by transaction amount.

**Why not AUC-ROC?** At 99% class imbalance, even a weak model gets high AUC-ROC because FPR's denominator is TN (990 of them), so a few hundred false positives barely register on the x-axis. The PR curve exposes this.

---

### Q2: Explain precision and recall to a product manager who needs to decide the operating threshold for a content moderation model.

**Model Answer:**

Imagine the model reviews 10,000 posts per hour. At your current threshold:

- **Precision = 0.92**: Of every 100 posts the model removes, 92 genuinely violated policy, 8 were incorrectly removed (false positives). Those 8 users got content wrongly taken down.

- **Recall = 0.78**: Of every 100 posts that actually violate policy, the model catches 78 and misses 22 (false negatives). Those 22 violations stay up.

**The tradeoff**: Lowering the threshold catches more violations (recall goes up) but also flags more legitimate content (precision goes down). Raising the threshold reduces wrongful removals (precision goes up) but more violations slip through (recall goes down).

**The product question is**: What's worse for our platform — over-removal (user backlash, chilling effect, potential legal exposure) or under-removal (policy violations staying up, advertiser risk, regulatory pressure)?

For most platforms: content around child safety requires very high recall (cannot miss). Comment spam can tolerate more false positives. Set the threshold to satisfy the recall requirement for your highest-risk content category, then accept the resulting precision.

---

### Q3: You train a binary classifier and get AUC-ROC = 0.94, but your colleague says the model is useless. How is this possible?

**Model Answer:**

This happens with severe class imbalance. AUC-ROC measures discriminative ability (can the model rank positives above negatives?) but is insensitive to imbalance because it uses FPR = FP/(FP+TN) — with thousands of true negatives, even large numbers of false positives barely move FPR.

**Check AUC-PR:** If the dataset is 0.1% positive, a model with AUC-ROC = 0.94 might have AUC-PR = 0.08 (barely above the baseline of 0.001 = prevalence rate). The precision-recall curve reveals that at every useful recall level, precision is catastrophically low.

**Concrete example**: 10,000 samples, 10 positives. A model that puts 90% of positives in the top 5% of scores could have AUC-ROC ≈ 0.97, but if those top 5% contain 500 samples, that's precision = 9/500 = 1.8%. Every alert generates 55 false positives per true positive — operationally worthless.

**The colleague is right to be concerned.** Always pair AUC-ROC with AUC-PR on imbalanced data.

---

### Q4: What's the difference between macro, micro, and weighted F1? When would each lead you astray?

**Model Answer:**

For a 3-class problem with counts [800, 150, 50] and class F1s [0.90, 0.75, 0.40]:

- **Macro F1 = (0.90 + 0.75 + 0.40) / 3 = 0.683** — treats all classes equally regardless of size. Good if all classes genuinely matter equally. Can be penalized by rare classes; useful for highlighting minority class problems.

- **Weighted F1 = (0.90×800 + 0.75×150 + 0.40×50) / 1000 = 0.848** — weights by class frequency. Dominated by the majority class. A model that completely ignores the 50-sample class still shows high weighted F1.

- **Micro F1** — aggregates TP/FP/FN across classes before computing. On multiclass problems often ≈ weighted F1. Not useful when class imbalance matters.

**How each misleads:**
- Macro: a model mediocre on all classes gets 0.75, identical to a model excellent on 2/3 classes but failing the minority. Doesn't expose *which* classes are broken.
- Weighted: hides minority class failures. "F1 = 0.90" looks great while the rare-but-critical class is at 0.20.
- Micro: same issue as weighted — majority class dominates.

**Production recommendation:** Report weighted F1 for overall system health, and **always also report per-class F1 separately** for any class that has special business importance (rare disease, fraud type, etc.).

---

### Q5: What is ECE (Expected Calibration Error) and why does it matter beyond AUC-ROC?

**Model Answer:**

**Calibration** measures whether predicted probabilities match empirical frequencies. AUC-ROC measures ranking quality (did higher-scoring items rank above lower-scoring items?). These are independent properties.

A model can have AUC-ROC = 0.95 (excellent ranking) but horrible calibration: when it says "90% probability," the true positive rate might be only 60%.

**ECE formula**: Group predictions into B equal-width bins by predicted probability. For each bin, compute |mean(predicted prob) − mean(actual positive rate)|. Weighted average by bin size gives ECE. ECE < 0.05 is well-calibrated.

**When calibration matters critically:**
- **Risk scoring / credit decisions**: "This applicant has 12% default probability" informs whether to issue a $10K vs $50K credit line. If that 12% is actually 25%, every decision downstream is wrong.
- **Clinical tools**: "72% probability of malignancy" informs biopsy decision. If the model says 72% but true rate is 45%, surgeons are making decisions on wrong priors.
- **Cost-benefit calculations**: If you're modeling expected value of an action (expected fraud loss = P(fraud) × amount), probability accuracy feeds directly into monetary decisions.
- **Downstream models**: If probabilities are fed into another model as features, poor calibration propagates.

**Fix calibration post-hoc**: Platt scaling (logistic regression on sigmoid of scores) or isotonic regression (`CalibratedClassifierCV` in sklearn). Always calibrate on a held-out calibration set, not training data.

---

## L6 (Staff Engineer) — System Design & Metric Architecture

---

### Q6: You're designing a production ML system for medical image diagnosis. Walk me through how you would select, compute, monitor, and alert on metrics end-to-end.

**Model Answer:**

**Metric selection (based on task characteristics):**
The task is binary classification with extreme class imbalance (e.g., 1–5% cancer prevalence) and asymmetric costs: FN (missed cancer) is catastrophic; FP (unnecessary biopsy) is harmful but recoverable.

Primary: **Recall ≥ 0.97 at chosen operating threshold** (the clinical requirement, agreed with radiologists).
Secondary: **AUC-PR** (model quality, threshold-agnostic), **ECE** (calibration for radiologist trust).
Operational: **False Positive Rate** (drives biopsy rate, directly impacts patient experience and cost), **inference latency p99** (workflow integration).
Never: Accuracy.

**Threshold selection:**
Use `roc_curve()` to find all thresholds where recall ≥ 0.97. Among those, pick the one minimizing FPR (maximizing precision). This is done offline on a validation set. The threshold is then frozen as a clinical parameter, separate from model weights.

**Offline evaluation pipeline:**
Run on a held-out test set with prospectively collected labels (same-distribution as deployment cohort). Evaluate:
- Recall at clinical threshold (hard requirement)
- AUC-PR (soft target > 0.70 given prevalence)
- Subgroup analysis: age groups, imaging equipment, institution
- Fairness: equalized recall across demographic groups (FN rate must not be higher for any subgroup — missing cancer in one population is inequitable)

**Production logging schema:**
Every prediction emits: trace_id, timestamp, model_version, predicted_probability, predicted_label, image_metadata (patient_age_bucket, equipment_id, institution). Ground truth (biopsy result) arrives asynchronously 1–14 days later, joined on trace_id.

**Monitoring:**
- Rolling window (last 500 predictions with labels): recall, FPR, ECE. Alert if recall drops below 0.95 (warning) or 0.93 (critical — page on-call).
- Input drift: pixel intensity distribution, image artifact rate. Can detect scanner firmware changes before they affect model performance.
- Label distribution: if the cancer rate in logged cases shifts from baseline, investigate (could be population shift or labeling process issue).

**CI gate:**
Every model update must pass a regression test: recall ≥ 97% × 0.99 = 0.9603 on the held-out set (3-sigma buffer). Fail CI if any subgroup drops more than 2pp on recall.

---

### Q7: How would you evaluate a RAG-based Q&A system end-to-end? What metrics at each stage?

**Model Answer:**

A RAG pipeline has three distinct failure modes, each requiring different metrics:

**1. Retrieval quality** (does the system find the right documents?):
- **Context Precision** (RAGAS): of the chunks retrieved, what fraction were actually relevant to the query? Low precision = noise in context window, which degrades generation.
- **Context Recall** (RAGAS): of all the relevant chunks that exist in the corpus, what fraction were retrieved? Low recall = missing information, guaranteed to cause hallucination on questions requiring that info.
- **Hit Rate@k**: for a given query, was a relevant doc in the top k? Useful for binary relevance.
- **MRR@k**: where does the first relevant document appear? Matters when the generator strongly attends to the first chunks.

**2. Generation quality** (given correct context, does the model answer well?):
- **Faithfulness** (RAGAS / LLM-judge): is every claim in the response grounded in the retrieved context? The number one failure mode. A response that sounds good but contradicts the retrieved documents is a hallucination.
- **Answer Relevance**: does the response actually address what was asked? Detects rambling or off-topic answers.
- **Answer Correctness**: end-to-end semantic similarity to a reference answer (requires ground truth). Less sensitive than faithfulness for detecting new failure modes.

**3. Safety and operational**:
- **Refusal accuracy**: for out-of-scope queries or queries the context can't answer, does the model say "I don't know" rather than fabricate?
- **Format compliance**: does the response match the required schema/structure?
- **E2E latency p99**: retrieval + reranking + generation. Degradation here often signals retrieval index health issues.

**Tricky evaluation design questions:**
- **Synthetic vs. real queries**: synthetic test sets (using GPT-4 to generate Q&As from your corpus) are fast to create but may not reflect actual user query distribution. Mix both.
- **LLM-judge calibration**: the same model family as the one you're evaluating may be too lenient on its own outputs. Use a different judge model or a fine-tuned evaluator.
- **Test set contamination**: if you evaluate faithfulness using the same document chunks that are in the retrieval corpus, you're measuring the judge, not the system.

**Online A/B:**
Ground truth metrics (faithfulness, answer correctness) require expensive labeling. In production, use implicit signals: session continuation rate (did the user keep chatting or abandon?), thumbs up/down, escalation to human agent. These are noisy but provide signal at scale.

---

### Q8: You inherit a recommendation system. The offline NDCG@10 looks strong at 0.83, but the business is unhappy. What's likely wrong?

**Model Answer:**

High NDCG with business dissatisfaction is a classic metric/value misalignment. Several causes:

**1. Popularity bias (most common)**: The model recommends popular items to everyone. NDCG@10 looks great because popular items have high relevance labels (historically, users clicked on them), but catalog coverage might be 3% — 97% of items never get recommended. Business loses long-tail revenue, artists/creators complain about unfair exposure, and the system amplifies existing popularity rather than discovering novelty.
- **Diagnose**: Calculate catalog coverage = |unique recommended items| / catalog size. Expected: >20–30%. If it's 3–5%, you have a popularity problem.
- **Fix**: Diversity-aware reranking (MMR — Maximal Marginal Relevance), exposure fairness constraints, novelty bonuses.

**2. Offline/online metric divergence**: NDCG was computed on historical interaction data, which reflects old user preferences, past UI layouts, and prior recommendation policies. The metric optimizes for clicks — but the business wants revenue, engagement time, or return visits. Clicks ≠ conversions ≠ satisfaction.
- **Diagnose**: A/B test a variant with lower offline NDCG but different item mix. Measure downstream business metrics.

**3. Evaluation set leakage / easy positives**: The test items are dominated by items the user has already purchased/watched — trivially predictable by popularity-based or CF methods. True recommendation value is predicting cold-start preferences and serendipitous discoveries.
- **Diagnose**: What's the overlap between training and test items? If >60%, your evaluation is too easy.

**4. Temporal leakage**: Training on past interactions to predict future ones, but the train/test split was random rather than temporal. The model sees future items at training time, artificially inflating NDCG.

**5. User heterogeneity**: Macro NDCG averages over users, masking bad performance for key segments (new users, high-LTV users, mobile-only users). The users unhappy with recommendations might not be reflected in the average.
- **Diagnose**: Compute NDCG by user segment. If the top 10% revenue-generating users have NDCG@10 = 0.45 while casual users have 0.90, you know where to invest.

---

### Q9: Explain BERTScore. Why is it better than ROUGE for summarization, and what are its failure modes?

**Model Answer:**

**ROUGE** counts n-gram overlaps between generated and reference text. It's fast and interpretable but:
- Penalizes synonyms: "car" ≠ "automobile" in ROUGE, even though semantically identical.
- Rewards verbatim copying over paraphrase — which can incentivize extractive over abstractive summaries.
- No word order sensitivity beyond n-gram structure.
- Human correlation: ~0.3–0.5. Weak.

**BERTScore** embeds both the candidate and reference sentences using a contextual language model (default: `microsoft/deberta-xlarge-mnli` for English). For each token in the candidate, it finds the most similar token in the reference using cosine similarity on contextual embeddings. Precision = average of max-similarity for each candidate token; Recall = same for reference tokens; F1 = harmonic mean.

Why it's better:
- Captures semantic equivalence: "automobile" scores near 1.0 against "car"
- Context-sensitive: the same word in different contexts gets different embeddings
- Human correlation: 0.7–0.85, much better than ROUGE

**BERTScore failure modes:**
1. **Length bias**: Shorter candidates tend to get higher precision (fewer tokens to get "wrong") but lower recall. F1 partially corrects this but doesn't eliminate it.
2. **Hallucination blindness**: A candidate that adds fabricated but semantically coherent sentences scores well on BERTScore because those sentences look similar to *some* reference token. BERTScore doesn't penalize for information not in the reference.
3. **Factual error blindness**: "The Eiffel Tower is in London" has high BERTScore against "The Eiffel Tower is in Paris" because the embedding similarity is high (same entities, similar structure) despite being factually wrong. **Use SummaC or QuestEval for factual consistency**.
4. **Domain shift**: BERTScore trained on general English underperforms on technical/scientific text or low-resource languages. Choose a domain-appropriate model.
5. **Metric saturation**: On easy tasks, most models score >0.90 — the metric doesn't discriminate between good and excellent summaries in the top tier.

**Production recommendation for summarization:**
Use BERTScore F1 as the primary metric for semantic quality (threshold >0.88), **and** SummaC or QuestEval for factual consistency (separately, because BERTScore won't catch hallucinations), **and** LLM-as-judge for overall coherence on a sampled 5–10% of outputs.

---

### Q10: How do you set up a CI/CD gate for ML model quality? What are the failure modes of naive approaches?

**Model Answer:**

**The goal**: Every model update should automatically pass/fail based on metric thresholds before reaching production. This prevents silent regressions.

**Naive approach 1 — Absolute threshold**: "Fail if AUC-PR < 0.70". Problem: absolute thresholds don't account for dataset difficulty. A new evaluation set (different time period, different distribution) might have a lower achievable AUC-PR even with a better model. You'll block correct improvements or allow regressions depending on dataset shift direction.

**Naive approach 2 — Compare to fixed baseline snapshot**: "Fail if AUC-PR drops more than 3% from baseline." Problem: the baseline eventually becomes stale. If data distribution shifts and the old baseline was trained on out-of-distribution data, you're regressing to a bad model.

**Better approach — Regression against the current champion:**
1. The CI evaluation set is held-out data from the **same time window** as recent production traffic (rolling, updated regularly).
2. The current production model (champion) is also evaluated on this set to get a same-dataset baseline.
3. The new model must achieve ≥ 97% of the champion's performance on all required metrics (precision, recall, AUC-PR), plus p50/p99 inference latency within 10% of champion.
4. For metrics where the new model significantly wins (>3% improvement on the primary metric), auto-promote. For mixed results, require human review.

**Statistical rigor**: A difference of +0.02 AUC-PR might or might not be meaningful depending on test set size. Use bootstrap confidence intervals (10,000 resamples) to verify the improvement is statistically significant (CI excludes 0). Or McNemar's test for paired prediction comparison.

**Failure modes in real systems:**
- **Test set contamination**: features derived from the full dataset before the train/test split (e.g., population statistics). The model has seen test-set information during training.
- **Label skew between CI and production**: CI test set from a different labeling vendor or time period than training set. Metric looks wrong because labels are inconsistently applied.
- **Shadow mode evaluation gap**: the CI evaluates on a static set; production behavior on streaming data with feedback loops is different.
- **Compound metrics masking regressions**: a composite score (weighted average of multiple metrics) can improve while individual critical metrics regress.

---

## L7+ (Principal / Distinguished) — System Architecture, Tradeoffs, and Organizational Impact

---

### Q11: Your LLM-powered product has been running for 6 months. The CEO asks for a report on "model quality." What do you tell them and what do you actually measure?

**Model Answer:**

This is fundamentally an organizational/alignment problem as much as a technical one. The CEO asking for "model quality" is likely trying to answer one of: "Is the product working?", "Are we getting better or worse?", "Should we upgrade the model?", or "Are we on the hook for any failures?"

**What not to give them**: A single number. "Our LLM scores 0.87 on faithfulness" is meaningless without context and leads to either false confidence or panic.

**What to report instead — a dashboard with three tiers:**

**Tier 1 — Business impact (what they care about):**
- Task completion rate: what % of user sessions ended with the user achieving their goal (measured by session signals, escalation rate, follow-up queries indicating confusion)?
- User satisfaction: NPS delta, explicit thumbs up/down
- Escalation to human rate: proxy for when the LLM fails hard enough that intervention is needed
- Revenue/activation impact if there's a causal link

**Tier 2 — System health (leading indicators of Tier 1):**
- Format compliance rate: if the LLM response fails schema validation, downstream code breaks. Target > 99.5%.
- Refusal accuracy: for safety-critical queries, does the model refuse appropriately?
- Hallucination rate on sampled outputs (LLM-judge on 5% of traffic): are factual claims supported by retrieved context or tool call results?
- Latency p50/p99: user experience, SLA compliance

**Tier 3 — Technical quality (used to understand root cause of Tier 2 changes):**
- Faithfulness and answer relevance (RAGAS or equivalent), calibrated against human eval periodically
- Regression tests on curated behavioral test suite: set of ~200 golden examples covering edge cases, policy boundaries, known past failure modes

**The "getting better or worse" question**: Show trend lines on Tier 1 and Tier 2 metrics over 30-day rolling windows. Model quality alone isn't the right axis — prompt changes, retrieval index updates, and traffic distribution changes all affect these numbers.

**The honest answer to the CEO**: "We have no single number for quality. The metrics that matter most are task completion rate (currently X%) and hallucination rate (currently Y%). Both are trending [direction] over the last 30 days."

---

### Q12: Describe Goodhart's Law in the context of production ML metrics. Give three production examples and how you would defend against each.

**Model Answer:**

**Goodhart's Law**: "When a measure becomes a target, it ceases to be a good measure." In ML: optimizing directly for a metric causes the system to game the metric without improving (or while degrading) the underlying construct the metric was meant to capture.

**Example 1 — Content recommendation optimizing click-through rate (CTR)**

Optimizing CTR leads to clickbait, sensationalism, and outrage-maximizing content because these have the highest CTR. Users click but don't find value. Short-term CTR goes up; long-term platform health (session length, retention, trust) degrades.

Defense:
- Multi-objective optimization: maximize a composite that includes session continuation, save rate, share rate, not just clicks.
- Include "skip" rate, "not interested" signals, and scroll-past-without-engaging as negative signals.
- Qualitative audits: human raters periodically evaluate recommendation quality on a sample, not just clicks.
- Constrain: a recommendation slot must maintain minimum diversity (by topic, source) even if pure CTR-maximization prefers fewer categories.

**Example 2 — Customer service chatbot optimizing for CSAT (satisfaction score)**

Agents optimize for CSAT by over-promising, avoiding escalation (which often leads to worse outcomes but momentary satisfaction), and giving people what they want to hear rather than accurate answers. CSAT goes up; actual problem resolution, churn, and repeat contacts for the same issue don't improve.

Defense:
- Track First Contact Resolution (FCR): did the customer's problem actually get solved, no repeat contact within 30 days?
- Measure post-resolution CSAT (did the solution hold?) not just immediate CSAT.
- Behavioral metrics: channel switching (customer goes from chat to phone = escalation signal), sentiment in follow-up tickets.

**Example 3 — LLM fine-tuned on human preference scores (RLHF)**

A model trained on preference ratings learns to be *persuasive* rather than *accurate* — longer, more confident-sounding, more elaborate responses get higher preference scores even when less accurate. Models learn sycophancy: agreeing with the user gets upvoted. "Reward hacking" — the model optimizes the reward signal without internalizing the actual intent (helpfulness, accuracy).

Defense:
- Multiple independent evaluation axes: factual accuracy (separate from perceived quality), conciseness, safety, instruction following. Don't aggregate into one score.
- Red-team evaluation: deliberately test whether the model agrees with false premises when stated confidently by the user.
- Periodically re-calibrate reward model against fresh human evaluations; reward models degrade as the policy they're evaluating shifts distribution.
- Track calibration: does expressed confidence correlate with actual correctness?

---

### Q13: When is it acceptable to evaluate an LLM using another LLM as judge (LLM-as-judge), and what are the systematic biases you need to account for?

**Model Answer:**

**When LLM-as-judge is appropriate:**
- Open-ended generation tasks where reference-based metrics (BLEU, ROUGE) are insufficient — creative writing quality, reasoning chains, explanatory depth.
- Scale: you need to evaluate 100,000 outputs per week and human evaluation is too expensive/slow for that volume.
- Dimensions that require understanding: coherence, relevance, tone, factual plausibility. These require a reader, not a token counter.
- Rapid iteration during development: LLM-judge allows quick signal in hours; human eval takes days.

**When it's not appropriate:**
- Ground-truth factual tasks: "What is the capital of France?" — use exact match or a verifiable lookup, not another LLM that might also be wrong.
- Tasks where the judge and the model being evaluated share the same training data or biases.
- Safety/policy evaluation: using an LLM to evaluate whether content is harmful risks the judge being susceptible to the same jailbreaks. Use a fine-tuned classifier or human judgment.

**Systematic biases to control for:**

1. **Verbosity bias**: LLM judges tend to prefer longer, more elaborate responses. Control by including a conciseness criterion explicitly, or by evaluating length-matched variants.

2. **Sycophancy toward self-similar outputs**: A GPT-4-based judge rates GPT-4 outputs higher than Claude outputs on the same task, and vice versa. Mitigation: use a different family judge than the model being evaluated, or average across multiple judges.

3. **Position bias**: when comparing two responses (A vs B), judges favor whichever appears first. Mitigation: always evaluate both A/B orderings and average, or evaluate each independently.

4. **Self-consistency bias**: the same LLM judge on the same prompt gives different scores on different runs. Especially for fine-grained numeric scales. Mitigation: run 3–5x and take mode/average, or use binary judgments (better/worse) rather than 1–10 scales.

5. **Calibration drift**: as the models being evaluated improve, the judge's absolute scale becomes miscalibrated. A score of 7/10 from 6 months ago is not the same as 7/10 today. Mitigation: maintain an anchor set of gold examples with known human-rated scores; re-calibrate periodically.

6. **Prompt sensitivity**: the judge score is highly sensitive to how the evaluation rubric is phrased. Two reasonable rubric wordings can produce different rank orderings. Mitigation: pilot-test your rubric against a human-labeled calibration set of 50–100 examples before deploying.

**Production best practice**: Use LLM-judge for high-volume continuous monitoring. Maintain a human-evaluated calibration set (~200 examples, re-labeled quarterly) and validate that your judge's rank ordering on this set matches human ranking (Spearman ρ > 0.8). If the judge drifts, retune the rubric or switch models.

---

### Q14: You're building a machine learning model for a lending decision. Explain the tension between predictive performance and fairness, and how you would approach metric selection in that regulatory context.

**Model Answer:**

**The fundamental tension**: Demographic fairness constraints and predictive performance are mathematically incompatible in general. Chouldechova's impossibility theorem (2017) proves that in the presence of base rate differences between groups, you cannot simultaneously achieve calibration, equal FPR, and equal FNR. You can satisfy at most two of these three criteria when group base rates differ.

**What this means practically**: If Group A has a 5% default rate and Group B has a 15% default rate, a perfectly calibrated model (predicts 5%/15% correctly) will necessarily have different approval rates between groups. If you constrain approval rates to be equal (demographic parity), you will miscalibrate. There is no free lunch.

**Regulatory context (ECOA / Fair Housing Act / CFPB guidance in the US)**:
- Disparate treatment: don't use protected attributes (race, sex, religion, national origin) as inputs — illegal regardless of predictive value.
- Disparate impact: even without using protected attributes, if outcomes differ between groups and the model cannot be justified as a "business necessity," there's legal exposure.
- Model explainability: regulators require adverse action notices — you must be able to tell an applicant why they were denied. Black-box models are difficult to defend.

**Metric selection approach:**

1. **Primary business metric**: AUC-PR or expected dollar loss (includes both false approvals that default and false denials that lose good customers). This drives model development.

2. **Fairness constraints (minimum requirements)**:
   - Calibration across groups: predicted default probability should match actual default rate within each group. A model that says "20% default risk" for Group A applicants should see ~20% of them actually default. If it says 20% for Group B but Group B defaults at 10%, your pricing is systematically wrong for that group.
   - Equal FPR: you're not blocking qualified applicants from Group B at a higher rate than Group A. Legally cleaner than equal approval rates because it's outcome-conditional.

3. **Audit pipeline:**
   - Run `equalized_odds_difference()` and `demographic_parity_difference()` from FairLearn on every model before promotion.
   - Set thresholds: flag if either measure exceeds 0.1 (10pp disparity).
   - For any disparity found: root cause analysis — is it the model, the features (which may be proxies for protected attributes), or the base rate difference?

4. **Feature selection for fairness**: Remove or transform features that serve as proxies (zip code often proxies for race; surname for national origin). Use counterfactual fairness analysis: would the score change if we altered protected-attribute proxies while holding everything else constant?

5. **Transparency**: Use an interpretable model family (gradient boosted trees with SHAP explanations) that can generate per-applicant adverse action reasons.

---

### Q15: How would you design the evaluation infrastructure for a multi-agent system where agents collaborate on complex tasks?

**Model Answer:**

Multi-agent systems break all the standard ML evaluation assumptions: there's no single input → output pair, errors compose and cascade, and the "right answer" for one agent depends on what other agents have already done.

**Evaluation dimensions I'd instrument:**

**1. Task-level outcome metrics (end-to-end)**
- **Task Success Rate**: did the multi-agent system correctly complete the end task? Binary or graded rubric.
- **Task Completion Rate**: what fraction of tasks reached a terminal state (vs. infinite loops, stuck states, or timeout)?
- **Human-in-the-loop intervention rate**: how often did the system escalate to a human? This is a leading indicator of capability gaps.
- **Error recovery rate**: when one agent makes a mistake, what fraction of tasks does the system recover from vs. compound the error?

**2. Trajectory quality metrics (process)**
Not just "did it succeed" but "how did it get there":
- **Tool call efficiency**: number of tool calls to complete task vs. optimal (human-determined minimum). High ratio = unnecessary work, wasted cost.
- **Redundant work rate**: % of tool calls that duplicate earlier calls (same API call twice, same file read twice). Indicates failure in state management.
- **Decision quality at branch points**: for tasks with known branching points, did the agent take the correct branch (requires a labeled trajectory set)?
- **Backtrack rate**: how often does the system reverse earlier decisions? Some backtracking is healthy (new information); excessive backtracking indicates poor planning.

**3. Per-agent contribution metrics**
- **Delegation accuracy**: does the orchestrator correctly route subtasks to the appropriate specialist agent? Wrong routing wastes capability.
- **Context window utilization**: are agents receiving relevant context or being overloaded with irrelevant information (causing attention dilution)?
- **Hallucination rate per agent**: fact-checks against ground truth or retrieved sources. Some agents (code generators) may hallucinate less than others (domain experts); know the per-agent rates.

**4. Robustness / adversarial metrics**
- **Prompt injection resistance**: a retrieved document contains adversarial instructions. Does the system execute them or ignore them?
- **Contradiction handling**: two agents return conflicting information. How does the system resolve it?
- **Out-of-scope graceful degradation**: tasks outside the system's training distribution — does it fail loudly (return "I can't do this") or silently (return plausible-but-wrong output)?

**Infrastructure:**
- Every agent call logs: agent_id, task_id, parent_task_id, inputs (truncated), outputs, tool_calls, latency, token usage, success/failure.
- Trajectory visualization: directed acyclic graph of agent calls, color-coded by success/failure. Invaluable for debugging cascading failures.
- Golden trajectory set: ~100 labeled task trajectories with human-annotated decision quality scores at each step. Used to validate trajectory-quality metrics.
- Shadow evaluation: run both current system and new system on the same inputs in parallel, compare trajectories automatically (e.g., edit distance between action sequences).

---

### Q16: You're a principal engineer presenting a new metric to your leadership team to replace the current evaluation metric your team has used for 3 years. The business leadership pushes back: "We've been using the old metric for years and our business is growing — why change?" How do you respond, and what evidence would you bring?

**Model Answer:**

This is the highest-stakes metric conversation: you're arguing that the measurement system itself is broken, not the model. Leadership's pushback is rational — changing metrics invalidates 3 years of trend data and creates uncertainty. You need to make the case systematically without being dismissive.

**First: Understand their real concern**. "We've been growing" conflates business success with metric validity. The business growing might be despite the metric, not because of it. But leadership needs to feel their past decisions weren't made on garbage.

**The argument I'd make:**

*"The metric was the right choice for what we were measuring in 2022. Two things have changed: our positive class prevalence dropped from 5% to 0.3% as we scaled, and our cost asymmetry shifted — a false positive is now 50× more expensive than it was then. The old metric can no longer detect regressions in these dimensions. Here's the specific failure mode we've already observed."*

**Evidence I'd bring:**

1. **A case where the old metric said things were fine but the new metric revealed a real problem** — a concrete incident where AUC-ROC held steady but AUC-PR dropped 40% (or whatever the pair is) and the production consequence was documented. This is the killer evidence.

2. **Correlation analysis between both metrics and business outcomes**: Plot old metric vs. weekly business KPI over 3 years. Plot new metric vs. same KPI. If the new metric has higher correlation with what the business actually cares about (e.g., fraud loss prevented, customer complaint rate), you've made the quantitative case.

3. **Synthetic failure mode demonstration**: construct a scenario where the old metric gives a high score to a clearly bad model (e.g., the always-predict-negative classifier on current class prevalence). Show leadership the score. "If our model degraded to this level, the old metric would show X. The new metric would show Y and trigger an alert."

4. **Migration path**: "We're not proposing to throw away 3 years of data. We'll compute both metrics for the next 6 months so you can see the relationship. When both metrics agree, we're aligned. When they diverge, we flag for investigation. At 6 months, we deprecate the old one." This lowers the perceived risk significantly.

5. **Industry standard positioning**: "AUC-PR is the FAANG/fintech industry standard for imbalanced classification. This is what our competitors are using to evaluate their fraud systems." Sometimes organizational credibility moves faster than technical argument.

**What I wouldn't do:**
- Dismiss the old metric as "wrong" — it was appropriate at the time, the world changed.
- Propose changing the metric mid-quarter when it resets trend comparisons for active OKRs.
- Win the argument in the meeting without securing a review after 6 months — you want the data to confirm your hypothesis publicly.
