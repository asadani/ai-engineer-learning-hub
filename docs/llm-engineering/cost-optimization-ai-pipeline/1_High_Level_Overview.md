# Cost Optimization in AI Pipelines

## The Economics Problem

AI inference is expensive in a way that traditional software is not. A SQL query costs microseconds; an LLM call costs 10–1000ms and $0.001–$0.10. A RAG pipeline with embedding, retrieval, reranking, and generation can easily cost $0.05–$0.50 per user query. At scale, this becomes the dominant operating expense.

**The math that matters:**
```
Daily cost = (queries/day) × (tokens/query) × (price/token)

Example: 100k queries/day × 2,000 tokens × $0.003/1k tokens = $600/day = $219k/year
Same workload with 10× optimization = $22k/year
```

This is why cost optimization is a first-class engineering concern, not an afterthought.

---

## Where the Money Goes

### Inference Cost Breakdown (typical RAG pipeline)

| Component | Tokens/Request | % of Cost | Optimization Lever |
|-----------|---------------|-----------|-------------------|
| **System prompt** | 500–2,000 | 10–20% | Compress, cache |
| **Retrieved context** | 1,000–8,000 | 30–50% | Fewer/shorter chunks, rerank to top-k |
| **Conversation history** | 0–4,000 | 0–30% | Summarize, prune |
| **User query** | 20–200 | 1–3% | No optimization (user-controlled) |
| **LLM output** | 200–2,000 | 15–25% | Output length constraints |

**The retrieved context is the largest lever** — changing from top-10 to top-3 chunks with a good reranker cuts input tokens 50–70% with minimal quality loss.

### The Three Cost Pillars

**1. Inference cost** — API calls to hosted LLMs (OpenAI, Anthropic, Bedrock)
- Charged per token (input + output, different rates)
- Output tokens typically 3–5× more expensive than input
- Latency ≠ cost: a slow model call and a fast one may cost the same

**2. Compute cost** — Self-hosted GPU instances, embedding servers, rerankers
- EC2 p4d.24xlarge (8× A100 80GB) = $32/hour on-demand, ~$10/hour Spot
- GPU utilization is often 10–30% on typical inference workloads — massive waste
- Right-sizing and utilization optimization matter more than model choice

**3. Operational overhead** — Storage (vector DB, model weights), data transfer, monitoring
- Vector DB storage: ~$0.10–$0.25/GB/month (Pinecone, OpenSearch)
- Model weights: Llama 3 70B FP16 = 140GB = ~$14/month in S3 + $0.10/GB transfer
- Often overlooked until scale hits

---

## The Optimization Hierarchy

Apply these in order. Earlier wins are cheaper to implement and often larger:

```
1. Request reduction         ← don't call the API you don't need to
   ├── Semantic caching      ← cache near-identical queries
   ├── Short-circuit logic   ← classifier routes cheap queries to cheap models
   └── Batch deduplication   ← deduplicate before sending

2. Input token reduction     ← send fewer tokens per call
   ├── Prompt compression    ← LLMLingua, selective retrieval
   ├── Context window mgmt   ← summarize history, top-k chunks
   └── System prompt caching ← Anthropic prompt caching (90% discount)

3. Model right-sizing        ← use the cheapest model that meets quality bar
   ├── Model routing         ← small model for simple queries, large for hard
   ├── Fine-tuned small model← beats GPT-4 on narrow domain at 10× lower cost
   └── Quantized local model ← self-hosted INT4/INT8 for latency-insensitive

4. Output optimization       ← reduce output tokens
   ├── Constrained generation← JSON schema, max_tokens
   └── Structured extraction ← avoid verbose prose when structured is enough

5. Infrastructure efficiency ← squeeze hardware utilization
   ├── Continuous batching   ← vLLM/TGI batch concurrent requests
   ├── Spot instances        ← 60–80% discount with checkpointing
   └── Right-size instances  ← GPU memory ↔ model size match
```

---

## Cost vs Quality: The Fundamental Tradeoff

Every optimization trades something. The key mental model:

```
Quality = f(model_capability, context_richness, prompt_quality)
Cost    = g(model_price, input_tokens, output_tokens, request_count)

Optimization target: maximize Quality/Cost ratio
Not: minimize Cost (that gives you a free tier model with 0 context)
Not: maximize Quality (that gives you Opus with 128k context on every request)
```

**The Pareto frontier principle**: For most production tasks, 80% of the quality of the expensive solution is achievable at 20% of the cost with targeted optimization. The last 20% of quality often costs 4× more. Know which queries need the expensive path.

---

## When Cost Optimization Becomes Critical

**At scale thresholds (rule of thumb):**
- < 10k queries/day: Optimize readability and correctness, not cost
- 10k–100k queries/day: Focus on caching and model routing
- 100k–1M queries/day: Prompt compression, fine-tuned smaller models
- 1M+ queries/day: Self-hosted inference, full-stack optimization

**When unit economics break:**
- Cost per query > willingness to pay → product is not viable
- Inference cost > 50% of revenue → margin is unsustainable
- Cost grows faster than revenue (super-linear scaling) → architecture problem

---

## The Self-Hosted vs. API Decision

**Stay on API (Anthropic/OpenAI/Bedrock) when:**
- < 1M tokens/day per model (GPU not amortized)
- Rapid model iteration needed (skip MLOps overhead)
- Team lacks GPU infra expertise
- Need bleeding-edge models (self-hosting lags by months)

**Move to self-hosted (vLLM/TGI) when:**
- 5M+ tokens/day sustained load → GPU pays for itself in weeks
- Data residency/compliance requires it
- Latency SLAs require < 100ms TTFT (co-located GPU)
- Fine-tuned model provides domain advantage and API doesn't support it

**Hybrid (most common at scale):**
- Self-hosted for commodity tasks (embedding, reranking, classification)
- API for frontier reasoning tasks (complex generation, tool use)
- Route based on query complexity + cost budget

---

## Key Mental Models

**Tokens are the unit of cost.** Every architectural decision converts to token consumption. Adding a tool result? +500 tokens. Keeping conversation history? +2,000 tokens. The principal engineer thinks in tokens before implementing features.

**Cache early, cache aggressively.** A cache hit is free. Even a 20% hit rate on a $0.01/query pipeline saves $200k/year at 1M queries/day. Semantic caching is underutilized because it's harder than exact caching — but it's the highest-leverage optimization.

**Quality gates, not quality maximization.** Define the minimum acceptable quality for each use case. Route to the cheapest model that clears that bar. Don't use Opus when Haiku clears the bar.

**Measure before optimizing.** Token costs are invisible without instrumentation. Build cost attribution from day one — per-user, per-feature, per-query-type. You can't optimize what you can't see.
