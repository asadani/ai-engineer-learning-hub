# Cost Optimization in AI Pipelines

Principal-level interview prep notes on cutting LLM inference and infrastructure costs without sacrificing quality — from prompt caching to self-hosted inference.

---

## Contents

| # | File | Words | Focus |
|---|------|-------|-------|
| 1 | [High Level Overview](1_High_Level_Overview.md) | 988 | Cost pillars, optimization hierarchy, API vs self-hosted decision, scale thresholds |
| 2 | [Key Technical Concepts](2_Key_Technical_Concepts.md) | 2,137 | Prompt caching, semantic caching, model routing, prompt compression, batching, output constraints, KV cache, fine-tuning ROI, embedding cost |
| 3 | [Products & Tools](3_Products_Tools.md) | 1,181 | LiteLLM, LangFuse, AWS Bedrock, SageMaker, Helicone, GPUStack/Ollama, W&B |
| 4 | [Tradeoffs & Comparisons](4_Tradeoffs_Comparisons.md) | 1,633 | Strategy matrix, API vs self-hosted TCO, caching threshold tradeoffs, model size vs quality vs cost, quantization impact |
| 5 | [Use Cases](5_Use_Cases.md) | 1,818 | Document classification pipeline (91% cost reduction), RAG optimization, conversation compression, Batch API, multi-tenant budgets, self-hosted vLLM |
| 6 | [Measurement & Evaluation](6_Measurement_Evaluation.md) | 1,445 | Cost attribution instrumentation, A/B testing framework, quality-cost evaluation, cache effectiveness metrics |
| 7 | [What to Measure & How](7_What_to_Measure_How.md) | 1,582 | Metrics tables (spend/token efficiency/cache/routing/infra), CloudWatch alarms, Grafana panels, anomaly detection |
| 8 | [Interview Questions](8_Interview_Questions.md) | 3,414 | 10 tiered Q&As (L5/L6/L7+) with model answers |

**Total: ~14,198 words**

---

## Key Themes

### 1. Measurement First, Always
You cannot optimize a cost you can't see. Build cost attribution (per-call token logging, feature tagging, per-user breakdown) before implementing any optimization. The measurement layer invariably surfaces 2–3 high-value quick wins — a misconfigured feature using Opus when Haiku would do, a system prompt that grew from 300 to 2,000 tokens unnoticed.

### 2. The Optimization Hierarchy
Apply in order — each layer compounds:
1. **Request reduction** — semantic caching, deduplication (highest leverage, zero quality risk)
2. **Input token reduction** — prompt caching, top-k chunk reduction, history compression
3. **Model right-sizing** — routing queries to cheaper models by complexity
4. **Output constraints** — max_tokens, structured extraction instead of prose
5. **Infrastructure efficiency** — self-hosted inference, continuous batching, quantization

### 3. Quality Gates, Not Quality Maximization
Define the minimum acceptable quality bar per use case. Route to the cheapest model that clears it. The difference between "maximize quality" and "meet quality bar" is often 5–10× in cost at scale.

### 4. Scale Changes Everything
At 10k queries/day, don't optimize prematurely. At 100k/day, semantic caching and retrieval reduction pay off. At 1M/day, model routing and fine-tuning become mandatory. At 10M+/day, self-hosted inference dominates. Every optimization has a fixed engineering cost and a variable savings — right-size the investment to the volume.

### 5. Governance Prevents Cost Creep
Silent cost growth is the norm: context window accumulation, system prompt feature creep, retrieval quantity drift, model upgrades without cost checks. The fix is process: per-feature daily spend alerts, cost review as part of feature design, and treating a 2× cost spike as a production incident.

---

## Optimization Quick Reference

| Technique | Cost Reduction | Effort | Quality Risk | Min Scale |
|-----------|---------------|--------|--------------|-----------|
| **Prompt caching** | 50–90% on cached prefix | Trivial | None | Any |
| **Batch API** | 50% on async workloads | Low | None | Any |
| **Top-k retrieval reduction** (10→3) | 40–60% input tokens | Low | Low (with reranker) | Any |
| **Output max_tokens** | 20–50% output tokens | Low | Low | Any |
| **Semantic caching** | 20–80% (hit-rate dependent) | Medium | Low–Medium | 10k queries/day |
| **Model routing** | 40–60% blended | Medium | Medium (router errors) | 100k queries/day |
| **Prompt compression** | 30–50% input tokens | Medium | Low–Medium | 100k queries/day |
| **Fine-tuned small model** | 5–20× inference cost | High | Low if done right | 500k queries/month |
| **Self-hosted inference** | 10–50× vs API | Very High | None | 10M tokens/day |

---

## AWS Services Reference

| Service | Use Case | Pricing Model | Cost Optimization Feature |
|---------|---------|---------------|--------------------------|
| **Bedrock on-demand** | Managed API, simple integration | Per token | Batch inference (-50%) |
| **Bedrock Provisioned Throughput** | Consistent high-volume | Hourly model units | 10–40% vs on-demand at volume |
| **SageMaker Real-time** | Self-hosted, low latency | Instance hours | Spot instances (-60%) |
| **SageMaker Serverless** | Bursty, cost-zero at idle | Per GB-second | No idle cost |
| **SageMaker Batch Transform** | Offline processing | Instance hours | Spot + auto-stop |
| **EC2 + vLLM** | Maximum control, highest volume | Instance hours | Spot + continuous batching |
| **Titan Embed v2** | Embeddings, AWS-native | Per token ($0.020/MTok) | Reduced dimensions (256) |

---

## Critical Interview Distinctions

**Prompt caching vs semantic caching**: Prompt caching is a model-level feature that stores KV cache state for identical token prefixes (exact match, controlled by the API provider). Semantic caching is an application-level feature that stores (embedding, response) pairs and retrieves by similarity (approximate match, controlled by you). They solve different problems and are complementary.

**Cost per token vs cost per task**: A shorter-context model call might have lower cost per token but require 3× more calls to accomplish the same task (agentic workflows). Always measure cost per successful task completion, not just per token.

**API vs self-hosted break-even**: The calculation must include ops engineering time, not just GPU dollars. At 10M tokens/day, self-hosting saves $200k/year in API costs but may require $100k/year in engineering time to maintain. The TCO analysis decides.

**Fine-tuning for quality vs for cost**: Fine-tuning is often discussed as a quality improvement technique. At principal level, it's also a cost optimization — a fine-tuned Haiku on a narrow domain can match GPT-4o at 10–20× lower inference cost. The key question is ROI: volume × savings per request vs one-time training investment.


!!! warning "2026 Update — what changed since this was written (as of May 2026)"

    - Reasoning models change the cost model: **thinking/reasoning tokens** are billed and can dominate spend. Budget and cap reasoning effort per use case, and measure cost per *successful* task, not per call.
    - Disaggregated serving (NVIDIA Dynamo 1.0) plus KV-cache tier offloading materially shifts the self-hosted TCO curve for high-volume and reasoning workloads — revisit API-vs-self-hosted thresholds with these in mind.

    **Sources:** [Anthropic — Extended thinking (reasoning-token economics)](https://docs.anthropic.com/en/docs/build-with-claude/extended-thinking) · [NVIDIA — Dynamo 1.0 production-ready](https://developer.nvidia.com/blog/nvidia-dynamo-1-production-ready/)


---

!!! info "Official Sources & Further Reading"

    - [Anthropic — Prompt caching](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching)
    - [Anthropic — Message Batches API](https://docs.anthropic.com/en/docs/build-with-claude/batch-processing)
    - [Hugging Face — Quantization (memory & cost reduction)](https://huggingface.co/docs/transformers/quantization)
    - [AWS — Machine Learning Lens (Well-Architected)](https://docs.aws.amazon.com/wellarchitected/latest/machine-learning-lens/machine-learning-lens.html)


!!! tip "Related Topics"

    - [Retrieval-Augmented Generation (RAG)](../retrieval-augmented-generation/)
    - [Fine-Tuning LLMs](../fine-tuning-llm/)
    - [LLM Serving & Inference](../llm-serving-inference/)
    - [Reasoning Models & Inference-Time Compute](../reasoning-models-inference-time-compute/)
    - [Multimodal AI & Vision-Language Models](../multimodal-ai-vision-language-models/)
