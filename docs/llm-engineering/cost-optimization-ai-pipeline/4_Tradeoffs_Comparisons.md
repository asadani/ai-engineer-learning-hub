# Tradeoffs & Comparisons

## Optimization Strategy Matrix

| Strategy | Cost Reduction | Implementation Effort | Quality Risk | Latency Impact | Best When |
|----------|---------------|----------------------|--------------|----------------|-----------|
| **Prompt caching** | 50–90% on cached tokens | Low (1 API param) | None | None / slight improvement | Long static system prompt / docs |
| **Semantic caching** | 20–80% (hit rate dependent) | Medium (vector store + threshold tuning) | Low (if threshold tuned) | Faster on hits | High query overlap, stable topic |
| **Model routing** | 40–70% | Medium (router model + eval harness) | Medium (router errors) | Router adds 50–200ms | Wide query complexity distribution |
| **Prompt compression** | 30–60% on input tokens | Medium (LLMLingua setup) | Low–Medium | Compression adds latency | Long retrieved contexts |
| **Fine-tuned small model** | 5–20× on inference | High (data, training, eval, deploy) | Low if done right | Can reduce latency | Narrow domain, high volume |
| **Batching / Batch API** | 50% (Batch API) | Low | None | High latency (async) | Non-interactive workloads |
| **Output constraints** | 20–50% on output tokens | Low (max_tokens + schema) | Low | Can improve (shorter) | Structured extraction tasks |
| **Self-hosted inference** | 10–100× vs API | Very High (MLOps) | None (model same) | Can improve (co-located) | > 5M tokens/day sustained |
| **Smaller context window** | Proportional to cut | Low | Depends on context importance | Improves | Retrieval quality sufficient with top-k |

---

## API vs Self-Hosted: The Full Decision Framework

### Total Cost of Ownership Comparison

```
Scenario: 10M tokens/day input, 2M tokens/day output

API (Claude Haiku):
  Input:  10M × $0.80/MTok  = $8.00/day
  Output:  2M × $4.00/MTok  = $8.00/day
  Total: $16/day = $480/month = $5,760/year

Self-hosted (Llama 3.1 8B on g5.2xlarge):
  Instance:     g5.2xlarge = $1.52/hr on-demand, $0.55/hr Spot
  Throughput:   ~500 tok/s at 50% GPU utilization
  Required:     (10M + 2M) tok/day / (500 tok/s × 86400s × 0.5 util) ≈ 0.56 instances
  Instance cost: 1 instance × $1.52/hr × 24hr = $36/day on-demand, $13/day Spot
  S3/storage:   negligible ($5/month for model weights)
  Ops overhead: Engineer time (harder to quantify — assume $500/month for maintenance)
  Total Spot:   $13 + $17 (ops amortized) = $30/day = $900/month

Compare: $480/month API vs $900/month self-hosted for 10M tokens/day?
API wins here — volume too low to amortize ops overhead.

At 100M tokens/day:
  API: $4,800/month
  Self-hosted (scaled to 5 Spot instances): $1,500/month
  Self-hosted wins by 3.2×
```

**Decision thresholds (rule of thumb):**
- < 10M tokens/day: API (SaaS, zero ops, frontier models)
- 10M–100M tokens/day: Hybrid (API for frontier, self-hosted for commodity)
- 100M+ tokens/day: Self-hosted dominates for established workloads

---

## Caching Strategy Comparison

| Cache Type | Hit Rate | Latency | Quality | Complexity | Storage Cost |
|-----------|---------|---------|---------|------------|-------------|
| **Exact string match** | < 5% (unique queries) | < 1ms | Perfect | Trivial | Minimal |
| **Anthropic prompt cache** | 100% on static prefix | Same as API | Perfect (same model) | Trivial (1 param) | Managed by Anthropic |
| **Semantic cache (0.98)** | 5–15% | 5–20ms (embed + search) | ~100% (very similar) | Medium | Vector DB |
| **Semantic cache (0.95)** | 15–40% | 5–20ms | ~99% (paraphrases) | Medium | Vector DB |
| **Semantic cache (0.90)** | 30–60% | 5–20ms | ~95% (related queries) | Medium | Vector DB |
| **Response template** | 80–95% | < 1ms | Depends on template | High | Key-value store |

**The semantic cache threshold tradeoff:**
- Lowering threshold → higher hit rate → more cost savings, but higher risk of stale/wrong responses
- Threshold should be empirically set by measuring quality at each threshold on your actual query distribution
- Never deploy semantic cache without A/B testing against ground truth on a holdout set

---

## Model Size vs Quality vs Cost (2025 Benchmarks)

| Model | Context | MMLU | Coding (HumanEval) | Input $/MTok | Output $/MTok | Best For |
|-------|---------|------|-------------------|-------------|--------------|---------|
| Claude Haiku 4.5 | 200K | ~75% | ~72% | $0.80 | $4.00 | Classification, extraction, simple QA |
| Claude Sonnet 4.6 | 200K | ~88% | ~87% | $3.00 | $15.00 | General purpose, RAG, tool use |
| Claude Opus 4.6 | 200K | ~92% | ~91% | $15.00 | $75.00 | Complex reasoning, research, planning |
| GPT-4o mini | 128K | ~82% | ~87% | $0.15 | $0.60 | High-volume, cost-sensitive |
| Llama 3.1 8B (self-hosted) | 128K | ~73% | ~68% | ~$0.001 | ~$0.001 | Self-hosted, high volume, narrow domain |
| Llama 3.1 70B (self-hosted) | 128K | ~88% | ~80% | ~$0.01 | ~$0.01 | Self-hosted frontier-quality, A100 cluster |

**The key insight**: Haiku is often 5% worse than Sonnet on open-ended tasks but essentially equal on narrow classification/extraction tasks. Fine-tune Haiku on your domain and the gap closes to < 1% at 20% of the cost.

---

## Prompt Compression: Effectiveness by Content Type

| Content Type | Compression Ratio | Quality Retention | Recommended Method |
|-------------|------------------|------------------|-------------------|
| Retrieved web pages | 50–70% | 90–95% | LLMLingua or top-k sentences |
| Conversation history | 60–80% | 85–95% | LLM summarizer (Haiku) |
| Code files | 30–50% | 70–85% | Structural pruning (keep signatures) |
| Legal/compliance docs | 20–40% | 80–90% | LLMLingua (high threshold) |
| Structured data / JSON | 40–60% | 95%+ | Schema + sample, not full dump |
| Few-shot examples | 50–70% | 90%+ | Select most relevant shots |

**When NOT to compress:**
- Tasks where precision matters (contract clauses, medical docs): compression can drop critical modifiers
- When context window is not the bottleneck
- Short prompts (< 1,000 tokens): compression overhead exceeds savings

---

## Batching Tradeoffs

| Approach | Latency | Cost | Complexity | Use Case |
|---------|---------|------|------------|---------|
| **Synchronous single request** | Lowest for one request | Standard | None | Interactive, real-time |
| **Async concurrent** (asyncio.gather) | Low wall-clock for many | Standard | Low | Parallel classification, fan-out agents |
| **Anthropic Batch API** | 1–24 hours | 50% off | Low | Offline analytics, evals, labeling |
| **vLLM continuous batching** | Low (auto-batched) | Much lower | High (self-hosted) | Self-hosted high-throughput |
| **Bedrock batch inference** | 1–24 hours | 50% off | Low | AWS-native offline workloads |

**The batch API decision rule:**
- Is the user waiting? → synchronous or async concurrent
- Is this a pipeline job? → Batch API (50% discount, no engineering cost)
- Do you need < 1s latency? → Real-time inference (API or self-hosted)

---

## Fine-Tuning vs Few-Shot Prompting: Cost/Quality

| Approach | Quality on Narrow Task | Inference Cost | Dev Cost | Maintenance |
|---------|----------------------|----------------|----------|-------------|
| **Zero-shot (large model)** | 70–85% | High | Low | Low |
| **Few-shot (large model)** | 80–92% | High (+ example tokens) | Medium | Medium (curate examples) |
| **Fine-tuned large model** | 85–95% | High (same model) | High | High |
| **Fine-tuned small model** | 80–95% (task-specific) | Low (5–20× cheaper) | High | High |
| **Fine-tuned + prompt cache** | 80–95% | Very low | High | High |

**The fine-tuning ROI formula:**
```
Monthly savings = (api_cost_baseline - finetuned_cost) × requests/month
Training cost   = data_cost + compute_cost + eval_cost (one-time)
Payback period  = training_cost / monthly_savings

Example:
  Baseline: $0.008/request with GPT-4o
  Fine-tuned Haiku: $0.0008/request (10× cheaper)
  Requests/month: 500,000
  Monthly savings: (0.008 - 0.0008) × 500k = $3,600
  Training cost: $2,000 (data generation + GPU time)
  Payback: < 1 month
```

---

## Context Window Management Tradeoffs

| Strategy | Token Savings | Quality Impact | Complexity |
|---------|--------------|----------------|------------|
| **Hard truncation** (oldest first) | High | High risk | Trivial |
| **LLM summarization of history** | 60–80% | Low | Medium (extra Haiku call) |
| **Sliding window** (keep last N turns) | Variable | Medium | Low |
| **Selective retrieval** (RAG over history) | High | Low | High |
| **Reduce retrieved chunks** (top-10 → top-3) | 50–70% | Low (with reranker) | Medium |
| **Chunk size reduction** (512 → 256 tokens) | 50% on retrieval | Low–Medium | Medium |
| **Anthropic prompt cache on system prompt** | 80–90% on system tokens | None | Trivial |

**The retrieval quantity sweet spot:**
- Retrieval systems typically show diminishing returns after top-3 to top-5 chunks
- A good reranker (cross-encoder) + top-3 beats a bad retrieval system + top-10
- Test quality at top-1, top-3, top-5, top-10: the quality delta from top-3 to top-10 is usually < 2% with a good reranker, but the token cost is 3× higher

---

## Quantization Impact on Self-Hosted Cost

| Precision | Model Size (70B) | Throughput | Memory | Quality Loss | Use When |
|----------|-----------------|------------|--------|--------------|---------|
| FP16 | 140GB | Baseline | 2× A100 80GB | None | Reference/eval only |
| INT8 (SmoothQuant) | 70GB | 1.3× | 1× A100 80GB | < 1% | Production default |
| INT4 (AWQ/GPTQ) | 35GB | 1.5–2× | 2× A40 48GB | 2–4% | High throughput |
| GGUF Q4_K_M | ~40GB | Variable (CPU) | Consumer GPU | 3–5% | Edge, small scale |
| FP8 (H100 native) | 70GB | 2× | 1× H100 80GB | < 0.5% | H100 clusters |

**The quantization decision:**
- For production serving: INT8 (SmoothQuant) is the safe choice — minimal quality loss, 2× cost savings
- For maximum throughput: AWQ INT4 + A100 cluster — 4× cost savings, acceptable quality loss on most tasks
- Never deploy quantized models without task-specific quality benchmarks — loss is non-uniform across tasks
