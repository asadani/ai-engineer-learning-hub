# Key Technical Concepts

## 1. Attention Mechanics & KV Cache

Transformer attention computes Q, K, V projections for every token. During autoregressive decoding, the key insight is that **K and V for all previous tokens don't change** — only the new token adds new K, V vectors. The KV cache stores all past K and V tensors so they don't need to be recomputed.

**KV cache memory formula:**
```
kv_cache_bytes = 2 × num_layers × num_kv_heads × head_dim × seq_len × bytes_per_element
```

For Llama-3-8B (32 layers, 8 KV heads, head_dim=128, bf16=2 bytes):
```python
num_layers = 32
num_kv_heads = 8
head_dim = 128
seq_len = 8192
bytes_per_element = 2  # bf16

kv_per_token = 2 * num_layers * num_kv_heads * head_dim * bytes_per_element
# = 2 × 32 × 8 × 128 × 2 = 131,072 bytes = 128 KB per token

total_kv = kv_per_token * seq_len
# = 128 KB × 8192 = 1 GB for one request at 8k context
```

With GQA (Grouped Query Attention, used in Llama-3), `num_kv_heads < num_attention_heads`, reducing KV cache by `num_heads / num_kv_heads` — e.g., 8:32 ratio = 4× reduction.

---

## 2. PagedAttention & Continuous Batching (vLLM's Core Innovation)

**The fragmentation problem**: Classical KV cache pre-allocates a contiguous memory block for max_seq_len per request. Even if most requests are short, GPU memory fragments and the "reserved but unused" memory can't be used for other requests.

**PagedAttention** (Kwon et al., 2023) borrows virtual memory concepts:
- KV cache is divided into fixed-size **blocks** (e.g., 16 tokens each)
- A **block table** maps logical sequence positions to physical GPU memory blocks
- Blocks can be non-contiguous in physical memory
- Blocks from completed requests are immediately freed and reused

**Result**: Near-zero internal fragmentation, near-zero external fragmentation. Memory utilization jumps from ~30% (naive) to >95%.

**Continuous batching** (orca-style): Instead of waiting for all requests in a batch to finish before accepting new ones, the scheduler continuously checks for finished requests and immediately fills those GPU slots with new requests. This is the `--max-num-seqs` parameter in vLLM.

```python
# vLLM engine internals (simplified concept)
class LLMEngine:
    def step(self):
        # Schedule: pick which sequences get GPU time this step
        scheduled = self.scheduler.schedule()

        # Run one decode step for all scheduled sequences
        outputs = self.model_runner.execute_model(scheduled)

        # Process outputs: some sequences finish (EOS), free their blocks
        for seq_group, output in zip(scheduled.seq_groups, outputs):
            if output.is_finished():
                self.scheduler.free(seq_group)
                # Those blocks are immediately available for new sequences
```

---

## 3. Flash Attention

Standard attention computes the full N×N attention matrix, materializing it in HBM:
```
Attention = softmax(QK^T / sqrt(d_k)) × V
```
For sequence length N=8192, the attention matrix is 8192×8192 = 64M entries × 2 bytes = 128MB **per layer per head per batch element** — read and written to slow HBM multiple times.

**Flash Attention** (Dao et al., 2022) uses **online softmax** and **kernel fusion**:
1. Tiles Q, K, V into blocks that fit in SRAM (fast, on-chip cache)
2. Computes attention in blocks, maintaining running softmax statistics
3. Never materializes the full N×N matrix in HBM
4. One kernel launch does the entire attention operation

**Impact**:
- Memory: O(N²) → O(N) in HBM
- Speed: 2–4× faster attention on A100; up to 8× on H100
- Enables longer contexts: 32k, 128k context becomes practical

**Flash Attention 2** (2023): Better parallelism across sequence dimension, fewer non-matmul FLOPS. ~2× over FA1.

**Flash Attention 3** (2024): H100-specific, uses FP8 Tensor Cores, ping-pong warp scheduling, achieves ~75% theoretical peak FLOPS utilization.

```python
# Using Flash Attention in PyTorch (via xformers or native FA2)
from flash_attn import flash_attn_qkvpacked_func, flash_attn_func

# Native Flash Attention 2 in PyTorch 2.0+
with torch.backends.cuda.sdp_kernel(
    enable_flash=True, enable_math=False, enable_mem_efficient=False
):
    output = torch.nn.functional.scaled_dot_product_attention(
        query, key, value, attn_mask=None, dropout_p=0.0, is_causal=True
    )
```

---

## 4. Quantization Deep Dive

### Weight-only Quantization

**GPTQ** (Frantar et al., 2022): Post-training quantization using second-order gradient information. For each row of the weight matrix, find quantized values that minimize reconstruction error. Processes one column at a time, updating remaining columns to compensate.
- int4: ~4× weight compression, 1–2% quality loss on most benchmarks
- Requires calibration dataset (~128 samples)
- GPU inference only (weights stored as int4, dequantized to fp16 at compute time)

**AWQ** (Lin et al., 2023): Activation-aware Weight Quantization. Key insight: not all weights are equally important. The 1% of weights corresponding to **salient activations** (large activation magnitudes) cause most quantization error. AWQ identifies these via activation statistics and scales those channels before quantization.
- Better than GPTQ at int4, especially on instruction-following tasks
- `autoawq` library; supported natively in vLLM
- Channel-wise scaling, no explicit heuristic — purely data-driven

**GGUF / llama.cpp quantization schemes:**
| Format | Bits/weight | Quality vs fp16 | Use case |
|--------|-------------|-----------------|----------|
| `Q2_K` | ~2.6 bits | Poor | Memory-constrained |
| `Q4_K_M` | ~4.5 bits | Good (recommended) | CPU/MPS inference |
| `Q5_K_M` | ~5.7 bits | Very good | Higher quality CPU |
| `Q6_K` | ~6.6 bits | Near-lossless | Close to fp16 |
| `Q8_0` | 8 bits | Lossless for most | Fast CPU, larger files |

The `_K` variants use k-quants (quantize blocks with shared scale factors). The `_M` suffix denotes "medium" importance tensor placement — some tensors (attention + output layers) are quantized less aggressively.

### Activation Quantization

**SmoothQuant** (Xiao et al., 2022): Migrates quantization difficulty from activations to weights. Large activation outliers (common in LLMs) are smoothed by dividing activations by per-channel scale factors and multiplying weights by the same factors. Makes both activations and weights quantization-friendly for W8A8 (int8 weights + int8 activations).

**LLM.int8()** (Dettmers et al., 2022): Mixed-precision decomposition. Outlier activation channels (>0.1% of features, but carrying most signal) are kept in fp16; the remaining 99.9% of weights/activations are quantized to int8. Near-lossless at 8-bit.

```python
# Using bitsandbytes int8/int4 in Hugging Face
from transformers import AutoModelForCausalLM, BitsAndBytesConfig
import torch

# 4-bit NF4 quantization (for fine-tuning: QLoRA)
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
    bnb_4bit_quant_type="nf4",  # NormalFloat4 — better than int4 for normally-distributed weights
)
model = AutoModelForCausalLM.from_pretrained(
    "meta-llama/Meta-Llama-3-70B-Instruct",
    quantization_config=bnb_config,
    device_map="auto",
)
```

---

## 5. Speculative Decoding

**Problem**: Each decode step is a full forward pass through all N layers of a large model for a single token — extremely wasteful.

**Solution**: Use a small "draft" model (same architecture, fewer layers/parameters) to speculatively propose k tokens. Then run the large "target" model once to verify all k tokens in parallel.

```
Draft model proposes: ["The", "cat", "sat", "on", "the"]  (5 tokens, 5 fast passes)
Target model verifies:     ✓      ✓     ✓     ✗            (1 pass, checks all 4)
Accept tokens 1–3, reject token 4, use target's prediction for position 4
Net result: 3 tokens generated in 1 large-model forward pass (vs 3 passes normally)
```

**Acceptance rate** (α): The fraction of draft tokens accepted by the target. Depends on draft model quality and the generation distribution. Typical α = 0.7–0.85 for matched model families.

**Speedup**: `1 / (1 - α^k)` roughly. At α=0.8, k=5: ~2.8× latency reduction.

**Variants**:
- **Medusa** (Cai et al., 2024): Adds multiple decoding heads to the target model itself. No separate model; heads predict tokens k+1 through k+n simultaneously.
- **EAGLE** (Li et al., 2024): Auto-regressive speculative decoding with a lightweight draft model trained to match the target's feature distributions. State-of-art acceptance rates.
- **Lookahead decoding**: Uses Jacobi iteration to generate multiple tokens in parallel without a separate model.

```python
# vLLM speculative decoding config
from vllm import LLM, SamplingParams

llm = LLM(
    model="meta-llama/Meta-Llama-3.1-70B-Instruct",
    speculative_model="meta-llama/Meta-Llama-3.1-8B-Instruct",
    num_speculative_tokens=5,
    tensor_parallel_size=4,
)
```

---

## 6. Tensor Parallelism & Pipeline Parallelism

**Tensor Parallelism (TP)**: Split individual weight matrices across GPUs. Each GPU holds a vertical slice. For MLP layers:
```
GPU0: W[:, 0:d/2]     GPU1: W[:, d/2:d]
Each GPU computes half the output; results are all-reduced (summed)
```
- Requires NVLink for low latency all-reduce (NVLink: 600 GB/s vs PCIe: 64 GB/s)
- TP=4 on one node: ideal for 70B models on 4× A100 80GB
- Communication overhead scales with batch size × d_model

**Pipeline Parallelism (PP)**: Split transformer layers across nodes. GPU0 runs layers 1–20, GPU1 runs layers 21–40. Data flows as a pipeline — while GPU1 processes batch k, GPU0 processes batch k+1.
- Bubble overhead: `(num_stages - 1) / num_microbatches`. Minimize by using many microbatches.
- Lower bandwidth requirement than TP (point-to-point vs all-reduce)
- Used for multi-node serving (inter-node bandwidth too low for TP)

**Expert Parallelism (for MoE models)**: Each GPU hosts a subset of experts. Tokens are routed to the appropriate expert GPU. Used for Mixtral-style MoE serving.

```python
# vLLM multi-GPU serving
from vllm import LLM

# Tensor parallel across 4 GPUs (same node, NVLink)
llm = LLM(
    model="meta-llama/Meta-Llama-3.1-70B-Instruct",
    tensor_parallel_size=4,
    dtype="bfloat16",
    gpu_memory_utilization=0.90,
    max_model_len=8192,
)

# Pipeline + Tensor parallel across 8 GPUs (2 nodes)
llm = LLM(
    model="meta-llama/Meta-Llama-3-405B-Instruct",
    tensor_parallel_size=4,
    pipeline_parallel_size=2,
    distributed_executor_backend="ray",
)
```

---

## 7. Structured Output & Constrained Decoding

For production use cases requiring JSON, SQL, or other structured output, unconstrained generation risks malformed output. Two approaches:

**Logit masking**: At each decode step, a grammar/schema engine computes which token IDs are valid at the current position. Invalid tokens get logit = -∞. The model samples only from valid continuations.

```python
# vLLM guided generation
from vllm import LLM, SamplingParams
from pydantic import BaseModel

class ExtractedEntity(BaseModel):
    name: str
    type: str
    confidence: float

llm = LLM(model="meta-llama/Meta-Llama-3.1-8B-Instruct")
sampling_params = SamplingParams(
    temperature=0.1,
    guided_decoding_backend="outlines",  # or "lm-format-enforcer"
)
# Pass JSON schema directly
outputs = llm.generate(
    prompts=["Extract entities from: 'Apple acquired Beats in 2014'"],
    sampling_params=sampling_params,
    guided_options={"json": ExtractedEntity.model_json_schema()},
)
```

**Grammar-based constraints** (via `outlines`, `lm-format-enforcer`, `guidance`): Build a finite-state automaton from a grammar (JSON Schema, Regex, EBNF). At each token, the FSA tells us which tokens advance the automaton — only those are allowed.

Performance overhead: ~5–15% decode throughput reduction from the logit masking computation.

---

## 8. GGUF Format & llama.cpp

**GGUF** (GPT-Generated Unified Format): The binary format used by llama.cpp and its ecosystem. Successor to GGML. Self-contained: weights, tokenizer, metadata all in one file.

Key design properties:
- Memory-mapped: the OS loads only what's needed from the file — enables partial GPU offload
- Layer-granular GPU offload: `--n-gpu-layers N` loads first N layers to GPU, rest on CPU/RAM
- Supports all k-quant types
- Platform-independent (x86, ARM, Apple Silicon, CUDA, ROCm, Vulkan, Metal)

**AirLLM**: Memory-efficient inference via layer-by-layer computation with model sharding across CPU/disk. Enables running 70B models on 4GB GPU by loading and unloading transformer layers one at a time. Impractically slow (minutes per response) but enables exploration on consumer hardware.

```python
# AirLLM: extreme memory efficiency
from airllm import AutoModel

# Splits model into layer segments stored on disk/CPU
# Each decode step loads only the needed layers
model = AutoModel.from_pretrained(
    "meta-llama/Llama-2-70b-chat-hf",
    compression="4bit",  # optional compression
)
output = model.generate(
    input_ids,
    max_new_tokens=20,
    use_cache=True,
    return_dict_in_generate=True,
)
```

---

## 9. Prefill-Decode Disaggregation

Advanced serving optimization used at hyperscaler scale:

**Problem**: Prefill is compute-bound (high arithmetic intensity), decode is memory-bandwidth-bound (low arithmetic intensity). Running them on the same GPU under-utilizes the compute during decode and stalls decode during prefill.

**Solution**: Dedicate separate GPU pools to prefill and decode.
- **Prefill fleet**: optimized for throughput (large batches, chunked prefill, H100 compute utilization)
- **Decode fleet**: optimized for memory bandwidth (A100/H100 with high HBM bandwidth, lower utilization acceptable)

The KV cache state from prefill must be transferred to decode fleet — this is the engineering challenge. Typical approach: NVLink/NVSwitch within a node for free; across nodes via RDMA/InfiniBand at 200Gb/s.

Systems implementing this: DistServe (OSS), Mooncake (Moonshot AI), Fireworks.ai's inference infrastructure, Google's internal LLM serving.

**When it matters**: At > 10,000 RPM, the GPU utilization difference between co-located and disaggregated serving becomes significant enough to justify the operational complexity.
