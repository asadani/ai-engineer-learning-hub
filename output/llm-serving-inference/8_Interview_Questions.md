# Interview Questions & Model Answers

## L5 (Senior Engineer) — Inference Fundamentals

---

### Q1: Why is LLM inference memory-bandwidth-bound rather than compute-bound? What are the implications for hardware selection?

**Model Answer:**

During the decode phase of autoregressive generation, the GPU performs a matrix-vector multiplication: multiply the model's weight matrices (d_model × d_ffn) against a single vector (the current token's hidden state). This operation has very low arithmetic intensity — roughly 2 FLOPs per byte of weight loaded (one multiply, one add, read once).

For comparison: a typical dense GPU workload (training, prefill with large batches) has arithmetic intensity of 50–200 FLOPs/byte. The hardware peak is ~50 FLOPs/byte on H100 (ratio of peak FLOPS / peak memory bandwidth = 1.98 PetaFLOPS / 3.35 TB/s ≈ 591 FLOPs/byte). Decode at batch_size=1 runs at ~4 FLOPs/byte — the GPU is doing 150× fewer FLOPs per byte of memory access than it's capable of.

**Implications:**
- More GPU memory bandwidth is more valuable than more FLOP throughput for decode. An A100 SXM (2 TB/s) serves a 70B model at ~30 tokens/sec; an H100 SXM (3.35 TB/s) serves the same model at ~50 tokens/sec. The additional FLOPS of the H100 aren't the bottleneck — the bandwidth is.
- Quantization helps more than you'd expect: int4 halves weight bytes read, directly doubling bandwidth-bound throughput (before dequantize overhead).
- Batching is the primary lever: at batch_size=64, each memory access amortizes across 64 tokens simultaneously. Arithmetic intensity scales with batch size, eventually becoming compute-bound at large enough batches.
- Hardware comparisons: A100 80GB (2 TB/s HBM) vs H100 SXM (3.35 TB/s): H100 is 1.7× faster for decode. H100 vs A10G (600 GB/s): 5.6× faster — the A10G is a terrible choice for large-model decode.
- AMD MI300X (5.3 TB/s HBM): theoretically faster than H100 for memory-bound decode, though CUDA ecosystem advantages often outweigh raw bandwidth for production deployments.

---

### Q2: Explain how PagedAttention works and why it was a breakthrough over prior KV cache management.

**Model Answer:**

**The problem with naive KV cache management:**

Before PagedAttention, serving systems allocated a contiguous block of GPU memory for the KV cache of each request, sized for `max_sequence_length`. If you supported 8k-token contexts, every request got 8k worth of KV cache memory reserved upfront, even if the actual request is only 200 tokens.

This created two problems:
1. **Internal fragmentation**: A 200-token request uses only 2.5% of its allocated KV block. The other 97.5% is wasted until the request finishes.
2. **External fragmentation**: You can't fill the leftover 97.5% with a different request because it's not a contiguous block.

In practice, naive KV cache utilization was 30–40% — most GPU memory was reserved but empty.

**PagedAttention's solution (inspired by virtual memory):**

The KV cache is divided into fixed-size blocks (e.g., 16 tokens each). These blocks are tracked via a per-sequence block table that maps logical positions to physical memory locations. Physical blocks don't need to be contiguous — the block table handles the mapping.

When a request starts, it gets no upfront allocation. As tokens are generated, new blocks are allocated from the free pool on demand. When a request finishes, all its blocks return to the free pool immediately.

**Results:**
- Near-zero internal fragmentation (only the last block is partially used)
- Near-zero external fragmentation (blocks are fixed-size, always reusable)
- KV cache utilization: 90–95%
- Throughput improvement vs. prior ORCA implementation: 2–23× depending on workload (more improvement when request length variance is high)

**Bonus: prefix caching becomes trivial.** Blocks shared between requests (same system prompt) can be reference-counted — they're only freed when the last referencing request finishes. The vLLM `--enable-prefix-caching` feature is a direct consequence of PagedAttention's block design.

---

### Q3: What is the difference between TTFT, TPOT, and ITL? How would you diagnose a situation where TTFT is good but users complain about "choppy" streaming?

**Model Answer:**

- **TTFT (Time to First Token)**: Elapsed time from request submission to the first generated token arriving at the client. Dominated by prefill time (processing all input tokens) plus queueing. User perceives this as "thinking time."
- **TPOT (Time Per Output Token)**: Average time per generated token over the full response. `TPOT = (E2E_latency − TTFT) / output_tokens`.
- **ITL (Inter-Token Latency)**: Time between *consecutive* token arrivals at the client. This is what determines whether streaming feels smooth. If tokens arrive at uniform intervals (e.g., 20ms each), the experience is smooth. If tokens arrive in bursts (0ms, 0ms, 0ms, 300ms, 0ms...), it feels choppy even if average TPOT is fine.

**Why ITL can be high even when TPOT is acceptable:**

The most common cause of choppy streaming is **chunked prefill interrupting decode**. In a multi-tenant serving engine, a new request arrives with a 4,000-token system prompt. The engine starts prefilling it, which takes 600ms of GPU time. During those 600ms, all in-flight decode steps are paused — existing streaming requests generate no new tokens. The user sees a 600ms gap in the token stream.

**Diagnosis steps:**
1. Check `vllm:inter_token_latency_seconds_bucket` histogram — if there's a long tail at p99 but p50 is fine, the distribution is bimodal (most tokens arrive fast, occasional large gaps).
2. Correlate ITL spikes with `vllm:num_requests_running` jumps — if ITL spikes coincide with new large requests entering service, chunked prefill is the cause.
3. Check `--enable-chunked-prefill`: if disabled, large prefill requests block decode entirely. Enabling it breaks prefill into 512-2048 token chunks interleaved with decode steps.
4. Check `--max-num-batched-tokens`: if too large, a single scheduler step can consume GPU for too long, causing decode stalls.

**Fix**: Enable chunked prefill (`--enable-chunked-prefill`) with `--max-num-batched-tokens 2048`. This caps each scheduler step to 2048 tokens — prefill requests are split across multiple steps, allowing decode tokens to be interleaved. ITL variance drops significantly.

---

### Q4: Walk me through the GPTQ vs AWQ tradeoff for int4 weight quantization. Which would you choose for a new production deployment?

**Model Answer:**

Both are post-training, weight-only quantization methods targeting int4 (4 bits/weight). They differ in what they optimize and how they get there.

**GPTQ** uses second-order gradient information (the Hessian of the weight reconstruction loss). For each row of each weight matrix, it finds the int4 values that minimize the squared reconstruction error, processing one column at a time and updating remaining columns to compensate for each quantization decision. This is mathematically sound but computationally expensive (~1–4 hours for 70B on A100) and requires a calibration dataset.

**AWQ** (Activation-aware Weight Quantization) takes a different insight: not all weights are equally important. Weights connected to high-activation channels cause disproportionate quantization error. AWQ identifies these "salient" weight channels via activation statistics, scales them up before quantization (making them harder to quantize but preserving more precision where it matters), and scales the activations correspondingly. This per-channel scaling is hardware-friendly and doesn't change the int4 storage format.

**Quality comparison at int4:**
- AWQ generally has 10–20% lower perplexity degradation vs. GPTQ on most benchmarks
- AWQ is especially better on instruction-following, code generation, and reasoning tasks
- GPTQ with `desc_act=True` (activation ordering) closes the gap but increases inference overhead

**Practical considerations:**
- More pre-quantized AWQ checkpoints are available on HuggingFace hub (TheBloke → bartowski conversions shifted from GPTQ to AWQ/GGUF)
- vLLM supports both natively with similar performance
- GGUF Q4_K_M (llama.cpp) is not directly comparable — it's optimized for CPU/MPS, not GPU

**My choice for a new GPU-based production deployment**: AWQ int4 by default. Better quality, simpler calibration (data-independent for the scaling step), and excellent vLLM support. Fall back to GPTQ if a pre-quantized AWQ checkpoint isn't available for the model.

---

### Q5: Explain speculative decoding. When is the 2–3× speedup realistic vs. when is it negligible?

**Model Answer:**

Speculative decoding exploits the asymmetry between generating tokens and verifying them. A small "draft" model (7× fewer parameters than the target) proposes k tokens sequentially. The large target model then verifies all k tokens in a single forward pass, accepting or rejecting each based on whether the token probability ratio exceeds a threshold. Accepted tokens advance the sequence; the first rejected token is replaced with the target's choice.

The speedup comes because: (a) k draft tokens cost k × (draft_model_latency) which is cheap, and (b) the verification pass generates up to k tokens in the time of one large-model forward pass.

**Realistic 2–3× speedup conditions:**
- Draft and target are from the same family (Llama-3.1-8B drafting for Llama-3.1-70B) — distributions are aligned
- Low temperature (0.0–0.3): greedy or near-greedy generation, high acceptance rate (α ≈ 0.85–0.90)
- Output is constrained/structured: code, JSON, repetitive patterns — draft model predicts well
- Memory permits: both models must fit simultaneously in GPU memory

**Negligible or negative speedup conditions:**
- High temperature (0.8–1.0) creative generation: draft model diverges from target distribution, α drops to 0.5–0.6, overhead of running draft model exceeds savings
- Very short responses (< 30 tokens): setup overhead dominates
- High-throughput batch workloads: GPU is already compute-saturated during decode (because large batch makes it compute-bound). Adding a draft model contends for FLOPS and memory bandwidth
- Mismatched model families: draft and target have different tokenizers or pre-training distributions

**The break-even point**: Speculative decoding improves latency when α > `1 − (1/k)`, where k is the number of speculative tokens. For k=5, you need α > 0.8 to break even. Measure α empirically on your production request distribution before committing to the architecture.

---

## L6 (Staff Engineer) — System Design

---

### Q6: Design a multi-tenant LLM inference platform on AWS that serves 50 customer teams, each with fine-tuned LoRA adapters. Targets: < 500ms TTFT for interactive users, < $2/M output tokens blended cost.

**Model Answer:**

**Key constraints:**
- 50 LoRA adapters — can't load all 50 simultaneously in GPU memory (32 adapters × 64-rank adapter for 8B ≈ 32 × 0.5GB ≈ 16GB overhead)
- < 500ms TTFT for interactive traffic
- $2/M output tokens: on a g5.12xlarge (4× A10G 24GB, ~$5.67/hr), 8B AWQ int4 achieves ~800 output tokens/sec → $5.67/3600/0.0008 = $1.97/1K tokens = $1,970/1M — too expensive. Need p4de.24xlarge (8× A100 80GB, ~$32/hr) at ~4,000 output tokens/sec → $32/3600/0.004 = $2.22/1M output. Close — use Spot for async batch to bring blended cost down.

**Architecture:**

```
ALB
 ├─ /v1/chat/completions (interactive)
 │     └─ vLLM Service (EKS, p4de.24xlarge)
 │          • Llama-3.1-8B-AWQ base
 │          • enable-lora, max-loras=8, max-cpu-loras=50
 │          • All 50 adapters cached in CPU RAM (~25GB total)
 │          • Top-8 most-used adapters hot in GPU
 │          • Adapter LRU eviction: least recently used → CPU
 │
 └─ /v1/batch (async jobs)
       └─ SQS → Lambda → vLLM on Spot p4d (detachable)
            • Same base + adapters
            • Spot interruption → SQS message visibility timeout → retry
```

**vLLM deployment:**
```python
llm = LLM(
    model="llama-3.1-8b-awq",
    enable_lora=True,
    max_lora_rank=64,
    max_loras=8,
    max_cpu_loras=50,      # all adapters in CPU RAM
    gpu_memory_utilization=0.88,
    tensor_parallel_size=4,  # 4× A100 for 8B = headroom for large batches
    enable_prefix_caching=True,
    enable_chunked_prefill=True,
)
```

**Routing:** LiteLLM proxy in front of vLLM, configured with per-customer API keys that map to the correct adapter name. LiteLLM passes the adapter as a header to vLLM's custom endpoint.

**Adapter warm-up policy:** Track per-customer request rate. Pre-warm top-8 adapters (by 7-day rolling request volume) to GPU at startup. Background job re-evaluates every hour; hot-swap adapters with > 50 RPH moving into top-8.

**Cost model:**
- Interactive: p4de.24xlarge on-demand, 3 replicas behind ALB = $96/hr. At 50% utilization, serves ~6,000 output tokens/sec → blended $96/3600/0.006 = $4.44/M output. Over budget.
- Mitigation: mix with Bedrock on-demand for overflow spikes. At 80% self-hosted + 20% Bedrock ($2.00/M), blended = $4.44 × 0.8 + $2.00 × 0.2 = $3.95/M. Still high.
- Use g5.48xlarge (8× A10G, $16.29/hr) for 8B instead: ~3,000 output tokens/sec → $16.29/3600/0.003 = $1.51/M output. Under budget. TTFT target harder to hit — validate against SLO.
- Async batch: p4d Spot at 70% discount → $9.60/hr for same workload as on-demand $32/hr.

---

### Q7: You're running vLLM in production and see OOM errors during peak traffic. Walk through your diagnosis and mitigation playbook.

**Model Answer:**

OOM in vLLM is almost always caused by the KV cache running out of GPU memory, not by the model weights themselves (those are static). The KV cache grows with: number of concurrent requests × average sequence length × KV cache bytes per token.

**Diagnosis steps:**

**Step 1 — Check KV cache utilization just before the OOM:**
```bash
# From Prometheus/Grafana
vllm:gpu_cache_usage_perc > 0.98  # consistently near 100% before crash
```
If it's at 98–100% before the OOM, the KV cache was full and new requests couldn't get blocks.

**Step 2 — Check concurrent request count:**
```bash
vllm:num_requests_running at OOM time
```
If this is at or above `max_num_seqs`, the scheduler shouldn't have admitted more requests. OOM despite staying within max_num_seqs suggests unexpectedly long sequences.

**Step 3 — Check for very long requests:**
The most common hidden cause: a user sends a 50k-token document for summarization. The KV cache for that single request consumes massive memory. Check `max_model_len` — if this is set higher than the model's pre-training context, vLLM may attempt to allocate KV cache for sequences longer than expected.

**Step 4 — Check for prefix caching bloat:**
With `--enable-prefix-caching`, cached prefix blocks are retained until evicted. Under memory pressure, they should be evicted, but there are edge cases. Check `vllm:gpu_prefix_cache_hit_rate` — very high hit rate with high `gpu_cache_usage_perc` suggests cached prefixes are filling memory.

**Mitigations (in order of invasiveness):**

1. **Immediate**: Lower `--max-num-seqs` by 20% to reduce concurrent requests. This increases queue depth but prevents OOM.

2. **Lower `--gpu-memory-utilization`**: Default 0.90, lower to 0.85 — vLLM pre-allocates KV cache from this fraction of available GPU memory. Lower = more headroom for weight activations.

3. **Reduce `--max-model-len`**: If you set 32k but most requests are < 4k, reducing to 8k dramatically reduces max KV cache per sequence and enables more concurrent requests.

4. **Enable KV cache quantization**: `--kv-cache-dtype fp8` on H100 halves KV cache memory, doubling effective capacity.

5. **Add GPU capacity**: Scale the EKS node group to add a replica. With a load balancer, requests distribute across replicas.

6. **Structured rejection**: Return 503 with `Retry-After: 5s` when `num_requests_waiting > N` — prevent queues from growing unboundedly during traffic spikes.

**Root cause prevention**: Set conservative `--max-num-seqs` and `--max-model-len` for your actual workload distribution. Profile p99 sequence lengths from production logs, not just average. If you support unbounded context, implement server-side truncation at the gateway.

---

### Q8: Describe the prefill-decode disaggregation pattern. When does the operational complexity justify the implementation?

**Model Answer:**

In a co-located serving setup, prefill (compute-bound) and decode (memory-bandwidth-bound) compete for the same GPU. A long prefill request monopolizes the GPU for hundreds of milliseconds, stalling all in-flight decode steps. Chunked prefill mitigates this by interleaving, but doesn't eliminate the resource contention.

**Disaggregated prefill-decode** assigns separate GPU pools:
- **Prefill pool**: receives fresh requests, runs the full forward pass on all input tokens (high compute utilization, optimized for throughput on long contexts)
- **Decode pool**: receives the KV cache state from the prefill worker and runs autoregressive decoding (optimized for low latency, high concurrency)

The critical engineering challenge is **KV cache transfer**: after prefill, all KV tensors (which may be several GB for a long-context request) must be sent to the decode worker. On the same node: NVLink at 600 GB/s. Across nodes: RDMA/InfiniBand at 200 Gb/s (25 GB/s) — much slower.

For a 4k-token request on Llama-3-70B (KV cache ≈ 4k × 128KB/token = 512MB), the cross-node transfer takes 512MB / 25GB/s ≈ 20ms — acceptable. For a 32k-token context: 32 × 512MB = 4GB → 160ms transfer overhead. This can dominate TTFT at long contexts.

**When does disaggregation justify the complexity?**

It's worth it when:
1. **Traffic volume > 5,000 RPM**: Below this, the throughput improvement doesn't offset the operational overhead (separate deployments, KV transfer infrastructure, more complex orchestration).
2. **Mixed-length workload**: If you have both long-context requests (RAG, document processing) and short-context interactive requests competing on the same fleet. The long requests disproportionately impact TTFT for short requests without disaggregation.
3. **Strong TTFT SLO on interactive traffic**: If your SLO is TTFT < 200ms, even with chunked prefill you may violate this during periods of heavy prefill load. Disaggregation gives you direct control.
4. **Cost optimization at scale**: Prefill is compute-bound → prefer H100 NVLink (more compute). Decode is memory-bound → acceptable on A100 or even L40S (more memory bandwidth per dollar). Different hardware for different phases = better cost efficiency.

**Operational complexity introduced:**
- Two separate deployment types with different auto-scaling policies
- KV transfer service (NCCL/RDMA) between pools
- Routing logic: request lands on prefill worker, gets KV state, is handed to decode worker
- Failure mode: if decode worker fails mid-generation, request must restart from scratch

**My recommendation**: Start with chunked prefill (free, just a flag). Add disaggregation only when chunked prefill still doesn't meet the TTFT SLO under load. Mooncake and DistServe have published that disaggregation provides 50–100% throughput improvement over co-located at high load — but both papers measure at much higher QPS than most teams ever reach.

---

## L7+ (Principal / Distinguished) — Architecture & Strategy

---

### Q9: Your CTO asks: "Should we build our own inference infrastructure or use managed APIs?" Walk through the decision framework.

**Model Answer:**

This is fundamentally a build-vs-buy decision with an added dimension: the strategic value of inference capability. My framework has four axes:

**Axis 1 — Volume and unit economics**

Managed API pricing is convenient but expensive at scale. Run the math:

- Bedrock Claude 3.5 Sonnet: ~$3/M input, ~$15/M output
- Self-hosted Llama-3.1-70B on p4de.24xlarge Spot: ~$0.50/M input, ~$2/M output (including infra, on-call)

The crossover point depends on load. At 1M output tokens/day, managed API = $15/day. Self-hosting = ~$2/day but requires engineering investment. At 100M output tokens/day, you save ~$1.3M/month on output tokens alone — easily justifies a team.

Typical crossover: > $20,000/month on API spend → self-hosting is worth investigating seriously.

**Axis 2 — Model requirements**

Can a managed model meet your requirements?
- If you need a proprietary foundation model (Claude, GPT-4) — managed is the only option
- If an open-source model (Llama, Mistral, Qwen) is sufficient for your quality bar — self-hosting is viable
- If you need fine-tuning on proprietary data that can't leave your environment — self-hosting may be required regardless of cost

**Axis 3 — Latency and reliability SLOs**

Managed APIs are shared infrastructure. SLOs are typically 99.5% availability with no latency guarantees. During peak periods, managed API p99 latency can spike 5–10×. If your product needs hard TTFT SLAs (e.g., < 500ms p99 at all times), self-hosting gives control that managed APIs don't.

On the other hand: self-hosted GPU infrastructure has its own reliability challenges — CUDA OOM, driver issues, hardware failures. A team of 2 engineers self-hosting GPU infra will have less actual uptime than Bedrock until they've operated it for 12+ months.

**Axis 4 — Strategic differentiation**

Is inference infrastructure core to your competitive moat? If you're building a product *on top of* LLMs, probably not — optimize for speed to market. If you're building an AI services company where inference cost and latency are the product, yes.

**My recommendation structure:**

- **0–$10K/month API spend**: Use managed API exclusively. Engineering cost of self-hosting exceeds savings.
- **$10K–$50K/month**: Use managed API for production. Begin benchmarking open-source model quality for your task. Hedge with LiteLLM so you can switch.
- **$50K–$200K/month**: Hybrid. Self-host the high-volume, well-characterized workloads (batch processing, standardized prompts). Keep managed API for variable/interactive traffic.
- **> $200K/month**: Build and operate self-hosted serving infrastructure. Justified economically; invest in proper SRE capacity.

---

### Q10: Describe how you would approach running LLMs on a budget at a startup: free tier, $500/month, $5K/month. What's the architecture at each tier?

**Model Answer:**

**Free / $0 tier:**

Primary option: Groq (free tier with rate limits), Together.ai free credits, Google Gemini Flash free tier. For development and prototyping, these are entirely sufficient.

For self-hosted local development: Ollama + Llama-3.1-8B on a MacBook Pro M3 (20+ tokens/sec, zero cost). Use this for all development, testing, and CI.

Key principle at this tier: don't build infrastructure. Use LiteLLM with the OpenAI interface so swapping providers is a config change, not a code change.

**$500/month tier:**

Infrastructure options:
- Lambda Labs: RTX 4090 GPU cloud at ~$0.50/hr. Can run Llama-3.1-8B at ~80 tokens/sec. $500/month = 1,000 hours of GPU time = practically always-on for one GPU.
- Runpod or Vast.ai: Similar pricing, spot instances available for 50% less.

Architecture:
- Single vLLM instance on RTX 4090 (24GB VRAM), 8B AWQ int4 model
- llama.cpp server as fallback (less overhead, simpler)
- Cloudflare Tunnel for HTTPS endpoint (no ingress cost)
- LiteLLM proxy for OpenAI compatibility + caching
- Redis (free tier on Railway or Upstash) for semantic caching — hits cache for repeated queries, extending effective throughput
- For bursts beyond 80 tokens/sec: fallback to Groq's free tier in LiteLLM routing

This setup handles ~100K output tokens/day comfortably.

**$5K/month tier:**

Now it's worth proper cloud infrastructure:
- AWS g5.12xlarge (4× A10G 24GB): $2.00/hr on-demand, $0.80/hr on Spot. $5K/month covers ~208 hrs on-demand or 520 hrs on Spot.
- Spot + SQS for async batch: $0.80/hr × 24 = $19.20/day on Spot for batch processing.
- Architecture: EKS with managed node groups, vLLM on g5.12xlarge, two on-demand replicas for interactive + Spot pool for batch. ALB routing. CloudWatch dashboards + alerts.
- Model: Llama-3.1-70B on 4× A10G (tight — may require Q4 quantization) or 8B for faster/cheaper serving
- Bedrock as overflow for spikes (pay-per-token, no infrastructure)
- At this spend level, also seriously evaluate Bedrock Provisioned Throughput — if traffic is consistent, often more cost-effective than EC2

The step-change insights:
- At $0: use APIs, don't build
- At $500: self-host one small model, use LiteLLM for abstraction + caching
- At $5K: proper infra, separate interactive from batch, start building cost dashboards

---

### Q11: What are the failure modes of naively deploying a 70B model in production that you'd only discover under load?

**Model Answer:**

This is experience-driven — things that look fine in a dev environment and only surface with real traffic:

**1. KV cache OOM during traffic spikes**

In development you test with 10 concurrent requests. In production, a traffic spike sends 500 concurrent requests before auto-scaling kicks in. The KV cache is calculated for `max_model_len × max_num_seqs`. If requests have variable length (some RAG queries have 8k context), the actual memory consumption is 3–5× higher than p50 estimates. The server OOMs.

Fix: Set `--max-model-len` to the p99 request length, not the maximum. Implement server-side truncation at the gateway. Set conservative `--max-num-seqs` with headroom.

**2. Head-of-line blocking from long-context requests**

One customer sends a 32k-token document for summarization. Prefill takes 8 seconds. All other in-flight streaming responses are paused for 8 seconds. Users see their streams freeze. TTFT p50 looks fine; ITL p99 is catastrophic.

Fix: Enable `--enable-chunked-prefill`. Implement request length limits at the API gateway (reject requests > 8k tokens unless using the "batch" endpoint). Separate long-context requests to a different deployment.

**3. Tensor parallel all-reduce overhead under load**

With TP=4 (4 GPUs), every decode step requires an all-reduce across all 4 GPUs. In a dev test with 5 requests, the overhead is negligible — the all-reduce completes in 0.5ms. Under load with 64 concurrent sequences, the all-reduce still takes 0.5ms but now occupies a larger fraction of the decode step. Worse: NVLink PCIe topology matters. If the 4 GPUs aren't on the same NVSwitch fabric, all-reduce bandwidth drops 5–10× and becomes the bottleneck.

Check: `nvidia-smi topo -m` — verify all GPUs are NVLink-connected, not just PCIe. On AWS: p4d.24xlarge has NVLink; g5.12xlarge has only PCIe (TP=4 is suboptimal; TP=2 or single-GPU is often better).

**4. Swap-induced latency spikes**

vLLM will "swap" KV cache blocks from GPU to CPU RAM when GPU memory is under pressure, to avoid rejecting waiting requests. CPU RAM is 100–200× slower than GPU HBM. A request whose KV blocks get swapped will experience 2–10× higher decode latency. This is invisible in metrics unless you specifically track `vllm:num_requests_swapped`.

Fix: Set `--swap-space 0` to disable swapping entirely (fail-fast rather than degrade). Or set `--swap-space 4` (4GB CPU swap) and monitor swap utilization — alert if consistently non-zero.

**5. TOKENIZER parallelism warning → deadlock**

HuggingFace tokenizers use Rust-backed parallel tokenization. When spawned in multiprocessing contexts (as vLLM does), setting `TOKENIZERS_PARALLELISM=true` can deadlock worker processes after a fork. You see this as workers that stop responding with no error message — just silence.

Fix: Always set `TOKENIZERS_PARALLELISM=false` in the environment before starting vLLM. It's in vLLM's startup code now but double-check in custom deployments.

**6. Auto-scaling lag killing the user experience**

GPU instances take 5–10 minutes to provision and start vLLM (model loading for 70B = 3–4 minutes alone). A traffic spike that exhausts all replicas will see every request fail for 8–15 minutes while scaling completes. Classic if you rely on reactive auto-scaling.

Fix: Proactive scaling (maintain 20% headroom above observed peak). Use Kubernetes HPA based on `vllm:num_requests_waiting` rather than CPU/GPU metrics — the waiting queue is the true signal of saturation. Pre-warm replacement instances with the model before bringing them into rotation.

---

### Q12: How does GGUF quantization (Q4_K_M, Q5_K_M, etc.) work internally? What does the K mean, and why is it better than naive int4?

**Model Answer:**

Standard int4 quantization maps each weight to one of 16 values. The simplest approach is per-tensor: compute a scale factor for the entire tensor as `scale = max(abs(weights)) / 7`, then quantize each weight as `round(w / scale)`. This is fast but poor quality — outlier weights force the scale to be large, wasting resolution on the average weights.

**Per-group quantization** improves this by computing a separate scale factor for every G=32 or G=128 consecutive weights. Outliers in one group don't pollute the scale for other groups. GPTQ and AWQ both use group sizes of 128; GGUF uses block sizes of 32 (Q-series) or larger (K-series).

**The K in K-quants stands for "k-quantization"** — a more sophisticated scheme introduced by llama.cpp. K-quants don't just quantize weights; they also quantize the scales themselves at a different precision.

Here's how Q4_K_M works:
- Weights are divided into "super-blocks" of 256 values
- Each super-block is divided into 8 "sub-blocks" of 32 values
- Each sub-block has a 6-bit scale (more precision for scale factors than the 8-bit used in older formats)
- The 8 sub-block scales within a super-block share a 16-bit "super-scale"
- Actual weight values: 4 bits each

The result: instead of wasting 8 bits on each scale for 32 weights, you use 6 bits per sub-block scale and a shared 16-bit super-scale. The scale overhead is reduced without sacrificing scale precision.

**The M and S suffixes** (Medium and Small) refer to mixed-precision within a single model:
- In `Q4_K_M`: most layers use Q4_K; the attention output layers and feed-forward layers deemed most "important" by heuristics are promoted to Q5_K or Q6_K
- In `Q5_K_M`: similarly, key layers are promoted to Q6_K

Why mixed precision? The embedding layer, lm_head (final projection to vocabulary), and attention layers handle more information flow and are more sensitive to quantization. Promoting these to slightly higher precision (5–6 bits instead of 4) with minimal memory cost gives a notable quality improvement.

**Practical quality comparison (Llama-3-8B on WikiText-2 perplexity):**
```
fp16:       5.68 (baseline)
Q8_0:       5.69 (+0.01 = near-lossless)
Q6_K:       5.75 (+0.07 = excellent)
Q5_K_M:     5.78 (+0.10 = very good)
Q4_K_M:     5.82 (+0.14 = good — recommended for CPU)
Q3_K_M:     6.03 (+0.35 = acceptable)
Q2_K:       6.41 (+0.73 = significant degradation)
```

For CPU deployment, Q4_K_M is the recommended sweet spot: ~4.5 bits/weight, fits 8B model in ~5GB RAM, quality within 2.5% of fp16, and optimized SIMD kernels in llama.cpp make it faster than Q5_K_M for the same quality.
