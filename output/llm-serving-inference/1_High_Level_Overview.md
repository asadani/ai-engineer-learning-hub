# LLM Serving & Inference — High-Level Overview

## What It Is

LLM serving is the engineering discipline of taking a trained transformer model and making it serve predictions reliably, efficiently, and economically at production scale. It sits at the intersection of distributed systems, GPU hardware, and systems programming — and it is where most of the cost and most of the latency in an LLM-powered product lives.

The key distinction from classical model serving:

- **Autoregressive generation**: LLMs generate one token at a time, each step depending on all previous tokens. This creates a fundamentally sequential bottleneck that doesn't parallelize the way a single-pass classifier does.
- **Memory-bound, not compute-bound**: At inference time (not training), the GPU is bottlenecked on memory bandwidth (reading weights + KV cache) rather than FLOP throughput. A GPU with 2× the FLOPS but the same memory bandwidth produces similar throughput.
- **Variable-length requests**: Input and output lengths vary wildly. Batching requests of different lengths efficiently is a hard scheduling problem that classical serving (fixed-size tensors) was never designed for.

---

## The Inference Stack

```
┌────────────────────────────────────────────────────────────────────┐
│                        Client / Application                        │
├────────────────────────────────────────────────────────────────────┤
│                    Gateway / Router Layer                          │
│         (LiteLLM, OpenRouter, custom Nginx/Envoy)                  │
│    • Model routing       • Auth/rate limiting    • Cost tracking   │
├────────────────────────────────────────────────────────────────────┤
│                    Inference Engine Layer                          │
│         (vLLM, TGI, TensorRT-LLM, llama.cpp, MLC-LLM)            │
│    • Continuous batching  • KV cache mgmt  • CUDA kernels          │
├────────────────────────────────────────────────────────────────────┤
│                    Model / Weight Layer                            │
│         (fp16, bf16, int8, int4, GPTQ, AWQ, GGUF)                 │
│    • Quantization         • Tensor parallelism  • Flash Attention  │
├────────────────────────────────────────────────────────────────────┤
│                    Hardware Layer                                  │
│         (H100, A100, L40S, RTX 4090, CPU, Apple Silicon)          │
│    • HBM bandwidth        • NVLink          • PCIe topology        │
└────────────────────────────────────────────────────────────────────┘
```

---

## Why It's Hard: The Memory Wall

A Llama-3-70B model in bf16 (2 bytes/param) requires:
- **Weight memory**: 70B × 2 = **140 GB** — requires 2× H100 (80GB HBM each) minimum
- **KV cache**: Each token in the sequence consumes `2 × num_layers × num_kv_heads × head_dim × bytes_per_element`. For a 32k-token context with Llama-3-70B, the KV cache alone is ~30 GB per request.
- **Activation memory**: Proportional to batch size × sequence length

At inference, the bottleneck isn't FLOPS — it's **HBM bandwidth**. An H100 SXM5 has 3.35 TB/s HBM bandwidth. Reading the 140GB of weights takes `140 / 3350 ≈ 42ms` per forward pass regardless of how many CUDA cores are running. This is why arithmetic intensity (FLOPs per byte of memory access) is the key inference metric.

---

## The Three Core Optimization Axes

### 1. Reduce Memory Footprint
- **Quantization**: Compress weights from fp16 (2B) to int8 (1B) or int4 (0.5B). 4× compression with ~1–3% quality loss at int4 with good methods (AWQ, GPTQ).
- **Model sharding**: Tensor parallelism splits weight matrices across GPUs; pipeline parallelism splits layers across GPUs.
- **Speculative decoding**: Run a small "draft" model to propose k tokens, then verify with the large model in one forward pass. Up to 3× speedup on latency for the same quality.

### 2. Maximize GPU Utilization
- **Continuous batching** (PagedAttention): Instead of static batch sizes, pack requests together dynamically. Old request completes → new request fills its slot immediately. The single most impactful serving optimization: 23× throughput improvement in the original vLLM paper.
- **Flash Attention**: Fused CUDA kernel that reorders attention computation to minimize HBM reads. Reduces memory complexity of attention from O(n²) to O(n) in memory. Critical for long-context.
- **Chunked prefill**: Split long input prompts into chunks, interleave with generation tokens from other requests to avoid GPU stalls.

### 3. Reduce Precision Requirements
- **Mixed precision**: Compute in fp16/bf16, accumulate in fp32. Standard since 2019.
- **KV cache quantization**: Cache key/value tensors in int8/fp8 — reduces KV cache memory by 2-4×, allows longer contexts or larger batches.
- **Weight-only vs activation quantization**: Weight-only (GPTQ, AWQ) is simpler and works offline; activation quantization (SmoothQuant, LLM.int8()) requires calibration data.

---

## The Prefill vs Decode Distinction

Every LLM request has two distinct phases:

| Phase | What Happens | Bottleneck | Parallelism |
|-------|-------------|------------|-------------|
| **Prefill** | Process all input tokens in parallel | Compute-bound (matrix-matrix multiply) | Full GPU utilization, easy to batch |
| **Decode** | Generate one token at a time, autoregressively | Memory-bandwidth-bound (matrix-vector multiply) | Limited — each request is sequential |

Prefill is like training: high arithmetic intensity, GPU is compute-saturated. Decode is like inference on a single example: low arithmetic intensity, GPU mostly waits for memory.

**Practical implication**: A server doing long-context prefill starves short decode requests of GPU time. Production systems separate prefill and decode onto different GPU pools (**disaggregated prefill**) — used by Google, Fireworks, and others.

---

## The TTFT / TPS / E2E Latency Triangle

Three metrics govern the user experience of LLM serving:

- **TTFT (Time to First Token)**: Latency from request submission to first generated token. Dominated by prefill time. User sees this as "thinking time." Critical for interactive use cases.
- **TPS (Tokens Per Second)**: Decode throughput. User sees this as "typing speed." For a conversational model, 30–50 TPS is smooth; below 15 TPS feels slow.
- **E2E latency**: TTFT + (output_tokens / TPS). Total time to complete the response.

**The tradeoff**: Larger batches improve TPS but increase TTFT (requests wait for a full batch). Small batches (or single-request serving) minimize TTFT but waste GPU capacity on decode. Continuous batching is the engineering solution that decouples these.

---

## Serving Tiers by Use Case

| Use Case | Latency Target | Throughput Need | Typical Setup |
|----------|---------------|----------------|---------------|
| Interactive chat | TTFT < 500ms, TPS > 30 | Low-medium | vLLM on A100/H100, small batch |
| RAG / agentic (w/ tool calls) | TTFT < 1s, E2E < 5s | Medium | vLLM + speculative decoding |
| Batch summarization / extraction | E2E < 30s | High | TGI or TRT-LLM, large batch |
| On-device / edge | 5–15 TPS on CPU/Apple Silicon | Single user | llama.cpp, GGUF q4_K_M |
| High-volume API | p50 < 1s, p99 < 5s | Very high | Multi-replica vLLM, load balancer |
