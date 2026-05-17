# LLM Serving & Inference

**Principal-level interview prep notes** — covering vLLM, TGI, TensorRT-LLM, llama.cpp, LiteLLM, quantization (GPTQ, AWQ, GGUF), speculative decoding, PagedAttention, tensor parallelism, and production inference architecture.

Generated: 2026-03-22

---

## Contents

| # | File | Words | Focus |
|---|------|-------|-------|
| 1 | [High-Level Overview](1_High_Level_Overview.md) | 1,025 | Inference stack, memory wall, prefill vs decode, TTFT/TPS/E2E triangle, serving tiers |
| 2 | [Key Technical Concepts](2_Key_Technical_Concepts.md) | 1,934 | KV cache math, PagedAttention, Flash Attention, quantization (GPTQ/AWQ/GGUF k-quants), speculative decoding, tensor/pipeline parallelism, structured output, GGUF/AirLLM, prefill-decode disaggregation |
| 3 | [Products & Tools](3_Products_Tools.md) | 1,337 | vLLM, TGI, TensorRT-LLM, llama.cpp, LiteLLM, Ollama, Bedrock, SageMaker, AutoAWQ, AutoGPTQ, Langfuse |
| 4 | [Tradeoffs & Comparisons](4_Tradeoffs_Comparisons.md) | 1,295 | vLLM vs TGI vs TRT-LLM vs llama.cpp, quantization method matrix, batching latency tradeoffs, TP scaling efficiency, speculative decoding win/loss, KV cache quantization, on-demand vs Spot |
| 5 | [Use Cases](5_Use_Cases.md) | 1,445 | Multi-tenant API gateway, low-latency chat, batch inference pipeline, on-device (M3 Max), multimodal serving, prefill-decode disaggregation, LoRA adapter multiplexing |
| 6 | [Measurement & Evaluation](6_Measurement_Evaluation.md) | 1,398 | Benchmarking tools (vllm bench), GPU profiling (DCGM, Nsight), MFU/MBU metrics, load testing, quantization quality evaluation, SLO burn rate alerting, CloudWatch setup |
| 7 | [What to Measure & How](7_What_to_Measure_How.md) | 1,273 | Metric tables (latency, throughput, GPU, reliability, cost), vLLM Prometheus metrics, alerting rules, production dashboard checklist, domain-specific targets |
| 8 | [Interview Questions](8_Interview_Questions.md) | 4,628 | 12 tiered Q&As: L5 (PagedAttention, memory-bandwidth, TTFT/ITL, quantization, speculative decoding), L6 (LoRA multiplexing system design, OOM playbook, disaggregation ROI), L7+ (build-vs-buy framework, budget tiers, production failure modes, GGUF internals) |

**Total: ~14,335 words**

---

## Key Themes

### The Inference Stack (Bottom to Top)
1. **Hardware**: HBM bandwidth is the real bottleneck for decode, not FLOP count
2. **Model format**: fp16 → AWQ/GPTQ int4 (GPU) or GGUF Q4_K_M (CPU) — 4× memory reduction
3. **Inference engine**: vLLM PagedAttention + continuous batching — 23× throughput over naive serving
4. **Gateway**: LiteLLM — unified API, fallbacks, cost tracking, semantic caching
5. **Application**: streaming over SSE, TTFT as UX proxy

### The Memory Wall
- Decode is **memory-bandwidth-bound** (not compute-bound) because it does matrix-vector (not matrix-matrix) multiply
- Target **60–80% HBM bandwidth utilization** during decode; below 40% means batch too small
- KV cache memory: `2 × layers × kv_heads × head_dim × seq_len × bytes/elem` — grows linearly with context length and concurrent requests

### Optimization Hierarchy (Most to Least Impactful)
1. Continuous batching (PagedAttention) — 23× throughput improvement
2. Flash Attention — 2–4× attention speed, O(N) vs O(N²) memory
3. Quantization (AWQ int4) — 4× memory, direct bandwidth win for decode
4. Speculative decoding — 2–3× latency at low temperature
5. Tensor parallelism — linear scaling within NVLink budget
6. Chunked prefill — eliminates head-of-line blocking
7. Prefix caching — near-100% TTFT reduction for repeated system prompts

### Production Gotchas
- **KV cache OOM spikes**: variable request length × concurrent requests > pre-allocated cache
- **ITL spikes (choppy streaming)**: large prefill requests blocking decode — fix: chunked prefill
- **TP all-reduce bottleneck**: PCIe topology kills TP efficiency — verify NVLink with `nvidia-smi topo -m`
- **Auto-scaling lag**: GPU instances take 8–15 min to warm — scale proactively on queue depth, not CPU
- **TOKENIZERS_PARALLELISM deadlock**: always `TOKENIZERS_PARALLELISM=false`

---

## Quick Reference

### Model Sizing on AWS

| Model | Format | VRAM | AWS Instance | Decode TPS | $/1M output |
|-------|--------|------|-------------|-----------|-------------|
| Llama-3.1-8B | bf16 | 18GB | g5.xlarge (1× A10G) | ~180 | ~$3.50 |
| Llama-3.1-8B | AWQ int4 | 6GB | g5.xlarge | ~250 | ~$2.50 |
| Llama-3.1-70B | bf16 | 140GB | p4de.24xlarge (8× A100) | ~400 | ~$2.20 |
| Llama-3.1-70B | AWQ int4 | 40GB | p4d.24xlarge (4× A100) | ~650 | ~$1.35 |
| Llama-3.1-405B | bf16 | 810GB | 3× p4de.24xlarge | ~150 | ~$5.90 |

### Quantization Decision Tree
```
Need CPU/edge inference? → GGUF Q4_K_M (llama.cpp)
GPU serving, quality matters most? → AWQ int4 (autoawq)
GPU serving, pre-quantized checkpoint available? → Use it (AWQ preferred)
Need lossless 8-bit? → LLM.int8() or BNB int8
H100 available? → FP8 (hardware native, near-lossless)
Extreme memory budget? → GGUF Q2_K (significant quality loss)
```
