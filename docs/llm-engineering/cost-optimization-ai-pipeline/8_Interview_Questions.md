# Interview Questions & Model Answers

## L5 — Senior Engineer

---

**Q1: Your RAG pipeline costs $0.02 per query. The PM says it needs to be under $0.005. Walk me through how you'd approach cutting cost by 75% without degrading quality.**

**A:** I'd attack in three stages, each measurable before moving to the next.

**Stage 1 — Measure first (1 day):** Instrument every call to capture input tokens, output tokens, cache hits, and latency. Break down cost by component: system prompt, retrieved context, conversation history, output. In practice, retrieved context is usually 50–70% of input token cost. I need real data before optimizing.

**Stage 2 — Quick wins with near-zero quality risk:**
- **Prompt caching:** If the system prompt is > 500 tokens and static, add `cache_control: ephemeral`. Cache reads are 90% cheaper. A 2,000-token system prompt called 1,000 times/day: without cache = $0.0016/call just for system prompt; with cache = $0.00016. Zero quality risk, one line of code.
- **Reduce retrieved chunks with reranker:** Switch from top-10 to top-3 using a cross-encoder reranker (free self-hosted model, 20ms latency). Input tokens drop 70% on the retrieval portion. Quality loss: < 2% based on every benchmark I've seen — the marginal value of chunks 4–10 is tiny if the reranker is good.

**Stage 3 — Model routing:**
Add a lightweight classifier (Haiku, 50ms, < $0.0001) to label queries as simple/moderate/complex. Route simple queries (factual lookup, "what is X") to Haiku, only complex multi-step queries to Sonnet. On a typical enterprise knowledge base, 60–70% of queries are simple. Haiku is ~4× cheaper than Sonnet.

**Validate before shipping:** Run A/B test — 10% of traffic on new path, compare quality via LLM judge on 500 query sample. Ship when acceptable rate > 95%.

Expected result: Prompt cache saves ~25%, top-3 retrieval saves ~40%, model routing saves ~40% on routed traffic = blended ~70–75% reduction. If that's not enough, look at fine-tuning Haiku on domain-specific data.

---

**Q2: What is Anthropic's prompt caching, how does it work mechanically, and when does it NOT save money?**

**A:** Prompt caching stores the KV cache state (the computed key-value matrices for the attention mechanism) at a marked prefix boundary. When a subsequent request shares that prefix up to the marked point, the model skips re-computing the KV cache for those tokens and reads from the stored cache instead.

**Pricing:** Cache writes cost 1.25× the input token price (25% surcharge), paid when the cache is first written or refreshed. Cache reads cost 0.10× the input token price (90% discount). TTL is 5 minutes (refreshed on each cache read).

**When it DOESN'T save money:**
1. **Low request rate:** If you make fewer than 1.25 requests per 5-minute TTL window, you pay the write surcharge but don't recoup it through enough reads. Break-even is approximately 1.25 calls/5min = ~15 calls/hour.
2. **Dynamic prefixes:** The cache only works if the prefix up to the `cache_control` boundary is identical across requests. If you interpolate user-specific data into the system prompt, no two requests share a prefix — the cache never hits.
3. **Short system prompts:** Caching overhead isn't worth it for < 200-token system prompts. The absolute savings are too small.
4. **Output-dominated workloads:** If you're generating 2,000 output tokens per request but only have a 200-token input, input optimization (including caching) has minimal cost impact — output tokens are 3–5× more expensive per token anyway.

**Best candidates for caching:** Long static system prompts (instructions, tool definitions), static knowledge base excerpts, multi-turn conversations where you cache the growing history at a fixed point.

---

**Q3: Explain semantic caching. Why is the threshold selection critical, and how would you determine the right threshold for a production system?**

**A:** Semantic caching returns a previously computed response when a new query is sufficiently similar (measured by cosine similarity of embeddings) to a cached query, rather than calling the LLM.

**Threshold selection is critical** because it directly determines the quality-cost tradeoff:
- Too high (0.99): Only near-identical queries hit the cache. Hit rate < 5%. Cost savings negligible.
- Too low (0.85): "What is Kafka?" and "How does Kafka compares to RabbitMQ?" might both hit the same cache entry. The second question gets a wrong answer silently.

**How I'd determine the threshold:**

1. **Build a labeled dataset:** Collect 500–1,000 real query pairs from production logs. For each pair, have human annotators label whether the same response would be appropriate for both queries (same intent, same answer expected).

2. **Measure precision-recall at each threshold:** For thresholds from 0.80 to 0.99 in 0.01 increments:
   - Precision: of pairs the cache would serve as identical, what % actually have the same correct answer?
   - Recall: of pairs that truly deserve the same answer, what % does the cache capture?

3. **Set threshold at the precision-recall tradeoff point** where precision > 99% (you can't tolerate wrong answers) and recall is maximized. Typically 0.93–0.97 for English queries on the same domain.

4. **Monitor in production:** Track both cache hit rate and quality metrics (thumbs up/down, escalation rate). If quality drops after cache deployment, raise the threshold.

**Additional safeguards:** Never cache responses to queries containing personal information, time-sensitive questions ("what's today's stock price"), or queries with explicit instructions to be fresh. Use TTL expiration (24 hours max) on cached entries.

---

**Q4: What is the Anthropic Batch Messages API, and what workloads should and shouldn't use it?**

**A:** The Batch Messages API is an asynchronous variant of the standard Messages API that accepts up to 10,000 requests in a single batch call and processes them asynchronously, returning results within 1–24 hours. The cost is 50% of standard on-demand pricing.

**Should use:**
- Nightly analytics pipelines (summarize today's support tickets, classify content, generate reports)
- Offline document processing (embed or analyze a corpus)
- Evaluation runs (run a model against your test suite — no user is waiting)
- Dataset generation or synthetic data labeling
- Weekly email summaries, recommendation refresh, batch classification

**Should NOT use:**
- Interactive user-facing features (user is waiting for a response)
- Anything with a latency SLA under 24 hours
- Real-time alerting or on-call systems
- Streaming outputs (Batch API returns complete responses only)

**Implementation consideration:** Design a status polling mechanism or use webhook callbacks. Never block a user thread on a batch job. Common pattern: submit batch → store batch_id in DynamoDB → Lambda polls on schedule → writes results back → downstream systems pick up results.

---

## L6 — Staff Engineer

---

**Q5: Design the cost optimization architecture for an LLM-powered search product that will scale from 10k to 10M queries/day over 18 months. What changes at each order of magnitude?**

**A:** Design for growth by building the measurement layer first, then adding optimization layers as volume justifies the complexity.

**Phase 1: 10k queries/day ($X/day, typically < $50)**
- Don't optimize prematurely. Ship with a good model (Sonnet), prompt cache on system prompt, top-5 retrieval.
- Instrument everything: tokens per call, cost per feature, latency percentiles, quality scores from user feedback.
- Build the cost attribution dashboard now — you need it for every future decision.

**Phase 2: 100k queries/day (10×, roughly $300–500/day)**
- **Semantic caching** is now worth implementing. 20% hit rate × $400/day = $80/day savings = ~$29k/year.
- **Tighten retrieval:** Switch from top-5 to top-3 with a cross-encoder reranker. Reduces input tokens ~40% on retrieval component.
- **Max_tokens discipline:** Audit every feature's max_tokens. Any feature set to 2,048 that averages 300 actual output tokens is wasting 1,748 tokens/call.

**Phase 3: 1M queries/day (10×, roughly $2,000–5,000/day)**
- **Model routing is now mandatory.** Build an LLM classifier or rule-based router that sends simple queries (60–70% of volume) to Haiku. This alone gives 50–60% cost reduction on routed traffic.
- **Fine-tuning evaluation:** At 1M queries/day, training a fine-tuned Haiku on domain data costs a one-time $2–5k but reduces per-query cost by another 30–50% on tasks where it can match Sonnet quality. Compute ROI.
- **Prompt compression for long documents:** If users are searching against long documents, implement LLMLingua-style compression on retrieved context.

**Phase 4: 10M queries/day (10×, $15,000–50,000/day)**
- **Self-hosted inference is now the dominant decision.** At this volume, a cluster of Spot instances running vLLM with Llama 70B AWQ is 20–50× cheaper per token than API.
- Keep the API path for fallback and for tasks requiring frontier models (complex reasoning, novel domains).
- Deploy custom embedding model self-hosted — at 10M queries/day, even Titan Embed costs $100/day; BGE-M3 on 2 g5.xlarge instances = $5/day.
- **Traffic shaping:** Implement token budgets per user/customer tier to prevent runaway costs.

**The architectural principle:** Every layer of optimization (cache → routing → fine-tune → self-host) has a fixed engineering cost and a variable savings that scales with volume. Start optimizing the layer with the best ROI at your current scale.

---

**Q6: You're leading a post-mortem after a single misconfigured feature caused $30,000 in unexpected LLM API costs over a weekend. What went wrong, what controls should have been in place, and what do you implement going forward?**

**A:** Root cause is almost always one of three failure modes:

**Common failure modes:**
1. **Runaway agent loop:** An agentic feature got into a retry loop, calling the API thousands of times on a single user session. No per-session token budget, no max iteration guard, no circuit breaker.
2. **Accidental context stuffing:** A new feature passed the full database dump instead of selected records into the context. A developer mistake that bypassed review because no per-call cost alert was configured.
3. **Viral traffic:** Unexpected traffic spike with no daily spend cap — cost scaled linearly with traffic and nobody was alerted until Monday.

**Controls that should exist (layered defense):**

**Per-call safeguards (code-level):**
```python
# Every LLM call should have:
max_tokens=256,  # explicit ceiling, not the default 4096
# Input token guard before the call:
if len(tokenize(context)) > 8000:
    raise ValueError(f"Context too large: {len} tokens. Check retrieval configuration.")
```

**Per-session budget (runtime):**
```python
# Agent loops must have termination policy:
TerminationPolicy(max_iterations=20, max_tokens=50_000, max_consecutive_errors=3)
```

**Per-feature daily spend cap (infrastructure):**
- CloudWatch Alarm on `CostPerCall` by feature — alert if average cost exceeds 3× baseline
- CloudWatch Alarm on cumulative daily spend by feature — page on-call if any single feature exceeds $500/day

**Hard stop (billing layer):**
- LiteLLM proxy with `max_budget: 1000.0, budget_duration: "1d"` — API returns 429 when budget exceeded
- Bedrock Service Quotas: set per-model token quotas per AWS account

**Process controls:**
- Any new feature with LLM calls requires a cost review in the PR (calculate: requests/day × avg tokens × price = $/day)
- Load test new LLM features before production — include cost in the load test output
- On-call rotation includes a daily AI cost review at 9 AM, not just incident response

**The organizational lesson:** Cost alerts should wake someone up. Treat a 10× cost spike the same as a 10× error rate spike — it's a production incident.

---

**Q7: Compare fine-tuning a small model vs. prompt engineering a large model for a high-volume narrow task. How do you decide, and what are the risks of each?**

**A:**

**Prompt engineering a large model:**
- Development cost: low (hours to days)
- Quality: high out of the box on well-defined tasks
- Inference cost: high ($3–15/MTok for Sonnet/Opus)
- Risks: prompt brittleness (small wording changes can break outputs), model updates may change behavior without warning, high cost at scale

**Fine-tuning a small model:**
- Development cost: high (data collection, training, evaluation, deployment pipeline, maintenance)
- Quality: matches or exceeds large model on narrow task if data quality is high
- Inference cost: low ($0.80/MTok for Haiku, or ~$0.001/MTok self-hosted)
- Risks: catastrophic forgetting, distribution shift over time, training-serving skew, data quality determines quality ceiling

**Decision framework:**

Definitely fine-tune if:
- Volume > 500k requests/month (ROI positive in < 1 month)
- Task is well-defined with stable distribution (classification, extraction, specific format generation)
- Labeled data exists or can be generated cheaply via GPT-4o labeling
- Inference latency matters and a smaller model is faster

Stick with prompting if:
- Volume < 100k/month (fine-tuning not cost-justified)
- Task evolves rapidly (re-training every few weeks is expensive)
- Novel reasoning, open-ended generation, or tasks requiring broad world knowledge
- Team lacks MLOps capacity to maintain a deployed fine-tuned model

**The hybrid approach (what I've done in production):** Use GPT-4o to generate 10,000 labeled examples on your task (takes a few hours, costs ~$50). Train a fine-tuned Haiku. Compare on 500-sample holdout. If Haiku achieves > 95% of GPT-4o's performance, deploy Haiku. Keep GPT-4o on 5% of traffic as a quality canary — if Haiku quality drifts, you catch it without a full regression.

**The silent risk with fine-tuning:** Models can be very good at the training distribution and silently fail on out-of-distribution inputs. Build a "confidence fallback" — if the fine-tuned model's response triggers low-confidence signals (unexpected format, short output, specific error keywords), fall back to the large model and log the case for retraining.

---

## L7+ — Principal Engineer

---

**Q8: Your company is spending $2M/year on LLM inference. The board wants to cut it in half without reducing product quality. You have 6 months. Walk me through your full strategy.**

**A:** This is a program, not a project. I'd run it in three parallel workstreams.

**Workstream 1: Visibility (Month 1, prerequisite for everything)**

You cannot cut $1M from a budget you can't see. First step: build complete cost attribution — per feature, per model, per customer tier. What I've found every time I've done this: 20% of features drive 80% of cost, and at least one of those is misconfigured or running a much more expensive model than necessary for its task.

Deliverable: a Grafana/CloudWatch dashboard showing daily spend by feature and model, with 90-day trend. This alone usually surfaces 2–3 quick wins that pay for the investigation.

**Workstream 2: Optimization layers (Months 2–5, highest-ROI first)**

Using the attribution data, rank features by spend × optimization potential:

*Tier 1 — Zero-risk, < 1 week each:*
- Prompt caching on all static system prompts. Expect 30–50% savings on input tokens for prompt-heavy features.
- `max_tokens` audit. Any feature with max_tokens > 2× median actual output tokens is a candidate.
- Batch API for any non-interactive workload (analytics, offline processing). 50% discount, no quality change.

*Tier 2 — Low-risk, 1–4 weeks each:*
- Retrieval reduction + reranker: top-10 → top-3. 40–60% savings on retrieval context.
- Model routing on highest-volume features. Route 60–70% of simple queries to Haiku.
- Semantic caching on features with overlapping query distributions.

*Tier 3 — Higher investment, months-scale:*
- Fine-tune Haiku on top-3 highest-volume, narrow-domain features. This typically requires 4–8 weeks but yields 5–10× inference cost reduction on those features.
- For any feature consuming 10M+ tokens/day: evaluate self-hosted inference ROI.

**Workstream 3: Governance (Month 1 onward)**

No optimization survives without process change. Implement:
- Cost review as part of feature design (pre-mortem: what does this cost at 10×, 100× traffic?)
- Automated alerts: any feature that spends 2× its weekly baseline triggers a Slack alert
- Monthly cost review meeting — the same rigor as a reliability review
- Per-customer-tier token budgets enforced at the API gateway layer

**Expected results with full execution:**
- Prompt caching: -25% on prompt-heavy features
- Retrieval reduction: -40% on RAG features (often the biggest spend bucket)
- Model routing: -45% on high-volume conversational features
- Fine-tuning top 3 features: -70% on those specific features
- Batch API for offline: -50% on non-interactive workloads
- Blended: ~50–60% reduction is achievable at most companies with this profile

**What I'd tell the board:** The $1M cut is achievable, but it requires 3–6 months of sustained engineering investment. The ROI is clear (>10:1), but the work is real — it's not a config change. And the structural change (governance + cost culture) is what prevents it from creeping back up.

---

**Q9: What are the most common ways AI inference costs silently grow in production, and how do you build a system that detects and prevents each one?**

**A:** Silent cost growth is the norm, not the exception. The mechanisms:

**1. Context window accumulation in conversations**
As users have longer sessions, more history gets passed on each turn. A chat feature that's cheap per turn becomes expensive after 20 turns because the 21st turn is passing 15k tokens of history. Nobody notices because cost-per-turn metrics look flat while cost-per-session grows.

*Detection:* Track token distribution, not just average. A rising p99 input token count is the signal. Alert when p99 exceeds 2× p50 (indicates long-tail sessions dragging up average cost).
*Prevention:* Conversation summarization after N turns, hard context window cap with graceful truncation.

**2. Feature creep in system prompts**
Product managers add instructions to system prompts ("also always mention our premium plan when relevant") one sentence at a time. Nobody tracks that the system prompt grew from 300 to 2,000 tokens over 6 months.

*Detection:* Version-control your system prompts. Log the token count of the system prompt in every call. Alert when system prompt tokens change by > 10%.
*Prevention:* Code-review system prompt changes the same as code changes. Treat them as deployments with cost implications.

**3. Retrieval quantity drift**
A developer changes `top_k` from 3 to 10 during debugging and never reverts. Or a data quality improvement means more chunks now score above the retrieval threshold.

*Detection:* Log retrieved chunk count alongside token count. Alert on retrieved_chunks > configured_top_k or average_retrieved_tokens > 2× baseline.

**4. Model upgrade without cost check**
Someone upgrades from Haiku to Sonnet for "better quality" on a high-volume feature without measuring whether quality actually improved enough to justify 4× cost.

*Prevention:* Require a cost + quality A/B test before model upgrades on any feature > 10k calls/day. Route 5% to new model, measure quality delta and cost delta for 1 week.

**5. Embedding model drift**
The embedding model's token count changes (tokenizer update, vocabulary expansion) and you're suddenly paying for 20% more tokens than before.

*Detection:* Track tokens-per-document for your corpus. Alert on > 5% change after embedding model updates.

**The meta-solution:** Every LLM feature should emit `input_tokens`, `output_tokens`, `cache_read_tokens`, and `model` on every call. Store 90 days. Alert on week-over-week cost increases > 15% at the feature level. This catches every one of the above patterns automatically.

---

**Q10: Debate this claim: "At scale, every AI company should self-host their own models rather than paying API providers."**

**A:** This is seductively simple and mostly wrong. The nuanced answer:

**Where the claim holds:**
At very high sustained volume on stable, narrow tasks — say 100M+ tokens/day on a single well-understood use case like document classification — self-hosting a quantized Llama model on Spot instances beats API pricing by 10–50×. The math is unambiguous at that scale. AWS, Anthropic's largest customers, and any company that's done the infrastructure work correctly will get there eventually on their commodity inference paths.

**Where the claim fails:**

*The frontier model problem:* Self-hosting means you're running yesterday's models. The latest Claude Opus or GPT-4o isn't available for self-hosting. The 6–12 month lag between frontier model release and open weights availability means you're making a permanent trade: lower cost vs lower capability. For complex reasoning, code generation, and novel tasks, this tradeoff is often unfavorable.

*The ops cost is real and often underestimated:* A self-hosted inference cluster requires: GPU procurement (6-month lead times for H100s), CUDA driver management, vLLM or TGI deployment and tuning, distributed tracing for debugging, model weight management (versioning, A/B rollouts), SRE on-call rotation for GPU failures, and capacity planning. For a team of 5 engineers, this is a full-time job for 1–2 people permanently. Unless you have 100M+ tokens/day to amortize against, the break-even often doesn't hold when you add real ops costs.

*Model diversity penalty:* Most companies don't have one LLM use case, they have fifteen. Self-hosting means deploying and maintaining separate clusters for each model size and type, or a shared cluster with complex scheduling. API providers handle this for free.

**The right answer:** Hybrid architecture. Use API for frontier model tasks, complex reasoning, and anything with low volume. Self-host for commodity tasks at high volume: embedding, classification, simple extraction, reranking. The decision should be made per-use-case based on a total cost of ownership calculation that honestly includes ops time, not just GPU dollars.

A principal engineer's job is to build the cost attribution system that tells you which use cases have crossed the self-hosting break-even threshold, not to dogmatically choose one or the other.
