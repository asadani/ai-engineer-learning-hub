# Tradeoffs & Comparisons

## vLLM vs TGI vs TensorRT-LLM vs llama.cpp

| Dimension | vLLM | TGI | TensorRT-LLM | llama.cpp |
|-----------|------|-----|--------------|-----------|
| **Throughput (A100)** | ★★★★ | ★★★ | ★★★★★ | ★★ (CPU: ★★★) |
| **TTFT latency** | ★★★★ | ★★★ | ★★★★★ | ★★ |
| **Setup complexity** | Low | Low | Very high | Very low |
| **Model coverage** | Very wide | Wide | NVIDIA-only archs | Wide (GGUF) |
| **Quantization** | AWQ, GPTQ, FP8, INT8 | BNB, AWQ, GPTQ | INT4, FP8, INT8 | All k-quant GGUF |
| **Speculative decoding** | Yes | Yes | Yes | Yes |
| **Multi-GPU** | TP + PP | TP | TP + PP | Partial |
| **CPU inference** | No | No | No | Yes (primary use case) |
| **Community/ecosystem** | Largest | Large | NVIDIA-enterprise | Largest (consumer) |
| **Best for** | Production GPU serving | HF-integrated deployment | Max throughput NVIDIA | Local/edge/CPU |

**Decision tree:**
- Interactive production serving → **vLLM** (default)
- Maximum throughput on locked NVIDIA hardware, weeks of lead time → **TRT-LLM**
- HuggingFace ecosystem, model hub integration, Inference Endpoints → **TGI**
- Local development, consumer GPU, edge deployment → **llama.cpp**

---

## Quantization Method Comparison

| Method | Type | Quality Loss (int4) | Speed | Memory | Calibration Needed |
|--------|------|---------------------|-------|--------|--------------------|
| **fp16/bf16** | None | 0% (baseline) | Baseline | 2B/param | No |
| **GPTQ** | Weight-only | ~1–2% | Same as fp16* | 0.5B/param | Yes (128 samples) |
| **AWQ** | Weight-only | ~0.5–1% | Same as fp16* | 0.5B/param | Yes (128 samples) |
| **GGUF Q4_K_M** | Weight-only | ~1–2% | CPU-optimal | ~4.5 bits/param | No (offline) |
| **BNB int8** | Weight+Activation | ~0.5% | 1.3× slower | 1B/param | No |
| **BNB int4 NF4** | Weight-only | ~1% (NF4 better) | Similar to int8 | 0.5B/param | No |
| **FP8 (H100)** | Weight+Activation | <0.5% | 1.5–2× faster | 1B/param | Yes |
| **SmoothQuant W8A8** | Weight+Activation | ~0.5% | 1.5× faster | 1B/param | Yes |

*GPTQ/AWQ dequantize to fp16 at compute time — memory savings don't translate to throughput savings unless memory-bandwidth-bound.

**The int4 paradox**: int4 halves memory vs int8, enabling larger batches or longer contexts. But dequantizing int4 → fp16 before matrix multiply adds overhead. Net throughput gain depends on whether you're memory-bound (yes → win) or compute-bound (no → marginal).

**AWQ vs GPTQ in practice (2026 state)**:
- AWQ generally better at int4 (better perplexity, better instruction following)
- GPTQ more mature tooling, more quantized checkpoints available on HF Hub
- Both supported natively by vLLM — use whichever has the pre-quantized checkpoint available

---

## Batch Size and Latency Tradeoff

```
Single-request serving (batch_size=1):
  TTFT: minimal (no queue wait)
  TPS: low (GPU decode underutilized)
  GPU utilization: 5–20%

Continuous batching (vLLM default):
  TTFT: depends on request arrival rate
  TPS: high (multiple requests share GPU)
  GPU utilization: 60–90%

Static large batching:
  TTFT: high (must wait for batch to fill)
  TPS: maximum
  GPU utilization: 95%+
```

The continuous batching sweet spot: target GPU utilization of 70–85%. Below that, you're wasting hardware. Above 90%, latency variance increases (requests spend time in queue).

**Practical knobs in vLLM:**
- `--max-num-seqs`: maximum concurrent sequences (directly controls batch size)
- `--max-num-batched-tokens`: limit tokens per step (prevents long-prefill starvation)
- `--scheduler-delay-factor`: trade TTFT for throughput (adds slight delay to batch more requests)

---

## Tensor Parallelism Scaling Efficiency

```
TP=1 (single GPU, Llama-3-8B on A100 80GB):
  Throughput: ~1,800 tokens/sec
  TTFT p50: ~120ms

TP=2 (2× A100, NVLink):
  Throughput: ~3,200 tokens/sec (89% scaling efficiency)
  TTFT p50: ~70ms (latency improves — weights load faster)

TP=4 (4× A100, NVLink):
  Throughput: ~5,800 tokens/sec (80% efficiency)
  TTFT p50: ~45ms

TP=8 (8× A100, NVLink):
  Throughput: ~9,200 tokens/sec (64% efficiency)
  TTFT p50: ~35ms
```

Scaling efficiency degrades because all-reduce communication cost grows with TP degree. Beyond TP=4, the communication overhead on PCIe (non-NVLink) dominates — only economical with NVLink interconnect.

**Rule of thumb**: TP only within a single node with NVLink. Across nodes, use pipeline parallelism (PP) or replicate independent replicas behind a load balancer.

---

## Speculative Decoding: When It Helps vs Hurts

**Helps significantly (2–3× speedup):**
- Low temperature (temperature < 0.5): greedy or near-greedy generation → high acceptance rate (α > 0.85)
- Repetitive or formulaic output (code generation, structured extraction)
- Draft model is in the same family and trained on same data (e.g., Llama-3-8B drafts for Llama-3-70B)

**Hurts or gives marginal improvement:**
- High temperature creative generation: draft model diverges, acceptance rate drops to 0.5–0.6
- Very short responses (< 50 tokens): overhead of draft model setup exceeds benefit
- High-throughput batched workloads: GPU is already saturated — adding draft model contends for the same memory bandwidth
- Mismatched model families: draft model token distributions don't match target

**Implementation consideration**: Speculative decoding uses 2× the GPU memory (both models loaded simultaneously). On a tight memory budget, you can't use it.

---

## KV Cache Quantization vs Full Precision

| Config | KV Cache Memory | Max Context @ 80GB (70B) | Quality Impact |
|--------|----------------|--------------------------|----------------|
| KV fp16 | 100% | ~12K tokens | Baseline |
| KV int8 | 50% | ~24K tokens | Negligible (<0.1 perplexity) |
| KV int4 | 25% | ~48K tokens | Small (~0.3 perplexity) |
| KV fp8 (H100) | 50% | ~24K tokens | Negligible + hardware accelerated |

KV cache quantization is one of the highest-leverage optimizations: it directly trades a small quality degradation for dramatically longer context or larger batch sizes.

```python
# vLLM KV cache quantization
llm = LLM(
    model="meta-llama/Meta-Llama-3.1-70B-Instruct",
    kv_cache_dtype="fp8",   # H100 native FP8; "auto" on older GPUs uses fp16
    tensor_parallel_size=4,
)
```

---

## Prefix Caching vs Prompt Compression

Two strategies for handling long, repeated system prompts:

**Prefix caching** (computational reuse):
- Compute KV cache for the system prompt once, reuse for all requests sharing that prefix
- Exact prefix match required (same tokens, same position)
- vLLM enables with `--enable-prefix-caching`
- ~100% TTFT reduction for the shared prefix portion
- Trade-off: cached KV blocks are pinned in GPU memory — reduces space for new requests

**Prompt compression** (reducing input size):
- Tools: LLMLingua, LLMLingua-2, Selective Context
- Compress long contexts to 10–30% of original length with minimal information loss
- Works by removing tokens with low perplexity (low information content) from the middle of context
- Reduces both prefill latency and KV cache memory
- Trade-off: irreversible loss; requires a small model pass to compress; adds ~50–200ms preprocessing latency

```python
# LLMLingua prompt compression
from llmlingua import PromptCompressor

compressor = PromptCompressor(
    model_name="microsoft/llmlingua-2-xlm-roberta-large-meetingbank",
    use_llmlingua2=True,
    device_map="cuda",
)

compressed = compressor.compress_prompt(
    long_context,
    rate=0.33,          # compress to 33% of original length
    force_tokens=["\n"],  # always keep newlines
)
print(f"Original: {len(long_context.split())} words → Compressed: {len(compressed['compressed_prompt'].split())} words")
```

---

## On-Demand vs Provisioned vs Spot for LLM Inference

| Deployment | Cost | Latency SLA | Availability | Use Case |
|-----------|------|-------------|--------------|----------|
| **Bedrock on-demand** | Pay-per-token, highest unit cost | No guarantee | 99.9% SLA | Variable traffic, experimentation |
| **Bedrock provisioned throughput** | Pay-per-model-unit-hour | Guaranteed TPS | 99.9% SLA | Consistent high traffic |
| **SageMaker on-demand** | Pay-per-instance-hour | No guarantee | 99.9% SLA | Custom models |
| **SageMaker Spot** | 60–90% discount | No guarantee | Interruptions | Batch inference |
| **Self-hosted (EKS GPU)** | EC2 cost only | Your responsibility | Your responsibility | High-volume, cost-optimized |
| **Spot EC2 + vLLM** | 70% cheaper than on-demand | Interruption risk | Variable | Async batch jobs |

**Production pattern**: Use on-demand/provisioned for synchronous user-facing traffic. Use Spot instances + SQS queue for async batch processing (summarization, embedding generation). The queue absorbs interruptions.
