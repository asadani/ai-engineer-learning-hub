# Measurement & Evaluation

## Benchmarking Inference Throughput

The canonical tool is `vllm bench` (formerly `benchmark_throughput.py` and `benchmark_serving.py`).

```bash
# Offline throughput benchmark (saturate GPU, measure max tokens/sec)
python -m vllm.entrypoints.benchmark_throughput \
  --model meta-llama/Meta-Llama-3.1-8B-Instruct \
  --tensor-parallel-size 2 \
  --input-len 512 \
  --output-len 256 \
  --num-prompts 1000 \
  --dtype bfloat16 \
  --quantization awq

# Online serving latency benchmark (realistic request distribution)
# First, start server:
python -m vllm.entrypoints.openai.api_server \
  --model meta-llama/Meta-Llama-3.1-8B-Instruct \
  --tensor-parallel-size 2

# Then benchmark:
python -m vllm.entrypoints.benchmark_serving \
  --backend vllm \
  --model meta-llama/Meta-Llama-3.1-8B-Instruct \
  --dataset-name sharegpt \
  --dataset-path ShareGPT_V3_unfiltered_cleaned_split.json \
  --request-rate 10 \         # requests per second
  --num-prompts 500 \
  --percentile-metrics ttft,tpot,itl,e2el \
  --metric-percentiles "50,90,99"
```

**Key metrics output:**
```
Throughput: 1523.45 requests/s
Total input tokens: 512000, output tokens: 128000
Request throughput: 31.23 req/s
Input token throughput: 15996.3 tokens/s
Output token throughput: 3999.1 tokens/s

Time to First Token (TTFT):
  P50: 142.3ms   P90: 287.1ms   P99: 891.2ms

Time Per Output Token (TPOT):
  P50:  18.7ms   P90:  22.3ms   P99:  31.5ms

Inter-token Latency (ITL):
  P50:  18.7ms   P90:  23.1ms   P99:  35.2ms

E2E Request Latency:
  P50: 1.14s     P90: 2.31s     P99: 5.87s
```

---

## GPU Utilization Profiling

**DCGM (Data Center GPU Manager)** — production monitoring on NVIDIA GPUs:

```bash
# GPU utilization breakdown
dcgmi dmon -e 1001,1002,1003,1004,1005,1006,1007,1009,1010,1011
# 1001: SM utilization
# 1002: Memory utilization (HBM bandwidth %)
# 1003: Encoder utilization
# 1004: Decoder utilization
# 1005: SM Active (useful smsp active)
# 1006: SM Occupancy
# 1009: Memory bandwidth utilization
# 1010: NVLink bandwidth
# 1011: PCIe bandwidth

# Simpler: nvidia-smi dmon
nvidia-smi dmon -s pucvmet -d 1
```

**NVIDIA Nsight Systems** — detailed kernel profiling:

```bash
# Profile a vLLM inference run
nsys profile \
  --trace=cuda,cudnn,cublas,nvtx \
  --output=vllm_profile \
  python -m vllm.entrypoints.benchmark_throughput \
  --model meta-llama/Meta-Llama-3.1-8B-Instruct \
  --num-prompts 100

# Open in Nsight Systems GUI: nsys-ui vllm_profile.nsys-rep
```

**What to look for in the profile:**
- `flash_attn_fwd` kernel duration (attention compute — should dominate during prefill)
- `Reduce` all-reduce kernels (TP communication overhead — minimize)
- Memory copy (H2D/D2H) operations (weight loading, KV transfer)
- GPU idle time (queue stalls, scheduling overhead)
- SM utilization during decode steps (typically 5–20% — expected for memory-bound phase)

---

## MFU and MBU: True Efficiency Metrics

**MFU (Model FLOP Utilization)**: What fraction of theoretical GPU FLOP capacity is being used by the model.

```python
def compute_mfu(
    model_params: int,
    batch_size: int,
    seq_len: int,
    tokens_per_second: float,
    gpu_peak_flops: float,  # e.g., H100 SXM5 bf16: 1.98e15 FLOPS
) -> float:
    """
    Transformer forward pass FLOPs ≈ 6 * N * T
    where N = model parameters, T = sequence length (tokens)
    For prefill: flops = 6 * params * seq_len * batch_size
    """
    flops_per_token = 6 * model_params  # approximate
    actual_flops = flops_per_token * tokens_per_second
    return actual_flops / gpu_peak_flops

# Example: Llama-3-8B on H100, decode at 1000 tokens/sec
mfu = compute_mfu(
    model_params=8e9,
    batch_size=1,
    seq_len=1,
    tokens_per_second=1000,
    gpu_peak_flops=1.98e15,  # H100 bf16
)
# mfu ≈ 0.024 (2.4%) — typical for single-request decode
# With batch_size=128: mfu ≈ 40–60% — much better
```

**MBU (Memory Bandwidth Utilization)**: More relevant for decode.

```python
def compute_mbu(
    model_params: int,
    bytes_per_param: float,  # 2 for bf16, 0.5 for int4
    tokens_per_second: float,
    gpu_memory_bandwidth: float,  # H100 SXM5: 3.35e12 bytes/sec
) -> float:
    """
    Decode: reads all model weights once per token
    """
    bytes_per_token = model_params * bytes_per_param
    actual_bandwidth = bytes_per_token * tokens_per_second
    return actual_bandwidth / gpu_memory_bandwidth

# Llama-3-8B bf16 at 500 tok/sec on H100
mbu = compute_mbu(
    model_params=8e9,
    bytes_per_param=2,
    tokens_per_second=500,
    gpu_memory_bandwidth=3.35e12,
)
# mbu ≈ 0.024 / 3.35 ≈ 0.24 (24%) — low, lots of room to batch more
# With batch_size=32: ~75% MBU — near optimal
```

**Key insight**: A healthy decode workload should target **60–80% MBU**. Below 40% means the batch is too small (wasting bandwidth). Above 85% means you're close to memory saturation and TTFT/TPS will degrade.

---

## Load Testing with Realistic Distributions

Real request distributions are not uniform. ShareGPT and LMSYS-Chat are standard realistic datasets.

```python
import asyncio
import aiohttp
import time
import numpy as np
from dataclasses import dataclass

@dataclass
class RequestResult:
    ttft_ms: float
    total_tokens: int
    e2e_ms: float
    error: str | None = None

async def send_request(
    session: aiohttp.ClientSession,
    url: str,
    prompt: str,
    max_tokens: int,
) -> RequestResult:
    start = time.perf_counter()
    ttft = None

    payload = {
        "model": "llama-3",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "stream": True,
    }

    try:
        async with session.post(f"{url}/v1/chat/completions", json=payload) as resp:
            total_tokens = 0
            async for line in resp.content:
                if line.startswith(b"data: "):
                    if ttft is None:
                        ttft = (time.perf_counter() - start) * 1000
                    chunk_data = line[6:].decode()
                    if chunk_data.strip() != "[DONE]":
                        total_tokens += 1

            e2e = (time.perf_counter() - start) * 1000
            return RequestResult(ttft_ms=ttft or 0, total_tokens=total_tokens, e2e_ms=e2e)
    except Exception as e:
        return RequestResult(ttft_ms=0, total_tokens=0, e2e_ms=0, error=str(e))


async def load_test(
    url: str,
    prompts: list[str],
    target_rps: float,
    duration_seconds: int = 60,
) -> dict:
    results = []
    connector = aiohttp.TCPConnector(limit=500)

    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = []
        start = time.perf_counter()
        prompt_idx = 0

        while time.perf_counter() - start < duration_seconds:
            # Poisson arrival process
            sleep_time = np.random.exponential(1.0 / target_rps)
            await asyncio.sleep(sleep_time)

            prompt = prompts[prompt_idx % len(prompts)]
            task = asyncio.create_task(
                send_request(session, url, prompt, max_tokens=256)
            )
            tasks.append(task)
            prompt_idx += 1

        results = await asyncio.gather(*tasks)

    ttfts = [r.ttft_ms for r in results if not r.error]
    e2es = [r.e2e_ms for r in results if not r.error]
    errors = [r for r in results if r.error]

    return {
        "total_requests": len(results),
        "error_rate": len(errors) / len(results),
        "ttft_p50": np.percentile(ttfts, 50),
        "ttft_p99": np.percentile(ttfts, 99),
        "e2e_p50": np.percentile(e2es, 50),
        "e2e_p99": np.percentile(e2es, 99),
        "throughput_rps": len(results) / duration_seconds,
    }
```

---

## Quantization Quality Evaluation

Before deploying a quantized model to production, validate quality regression:

```python
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from datasets import load_dataset

def evaluate_perplexity(model, tokenizer, dataset_name="wikitext", split="test") -> float:
    """Standard perplexity evaluation on WikiText-2."""
    dataset = load_dataset(dataset_name, "wikitext-2-raw-v1", split=split)
    text = "\n\n".join(dataset["text"])

    encodings = tokenizer(text, return_tensors="pt")
    max_length = 2048
    stride = 512
    nlls = []

    for begin_loc in range(0, encodings.input_ids.size(1) - max_length, stride):
        end_loc = begin_loc + max_length
        input_ids = encodings.input_ids[:, begin_loc:end_loc].to(model.device)
        target_ids = input_ids.clone()
        target_ids[:, :-stride] = -100  # only evaluate stride tokens

        with torch.no_grad():
            outputs = model(input_ids, labels=target_ids)
            neg_log_likelihood = outputs.loss

        nlls.append(neg_log_likelihood)

    ppl = torch.exp(torch.stack(nlls).mean())
    return ppl.item()

# Compare baseline vs quantized
# fp16: ppl ≈ 5.68 (Llama-3-8B on WikiText-2)
# AWQ int4: ppl ≈ 5.79 (+0.11 = 1.9% degradation — acceptable)
# GGUF Q4_K_M: ppl ≈ 5.82 (+0.14 = 2.5% degradation)
# GGUF Q2_K: ppl ≈ 6.41 (+0.73 = 12.8% — significant)
```

**Task-specific evaluation** (more predictive than perplexity for production):

```python
# Evaluate on your actual task distribution, not generic benchmarks
def evaluate_on_task(model_path: str, task_examples: list[dict]) -> dict:
    """Evaluate instruction following + output quality on domain samples."""
    from vllm import LLM, SamplingParams

    llm = LLM(model=model_path, quantization="awq")
    prompts = [ex["prompt"] for ex in task_examples]
    references = [ex["reference"] for ex in task_examples]

    outputs = llm.generate(prompts, SamplingParams(temperature=0.0, max_tokens=512))

    # Measure: exact match, format compliance, semantic similarity (BERTScore)
    from bert_score import score as bert_score
    predictions = [o.outputs[0].text for o in outputs]
    P, R, F1 = bert_score(predictions, references, lang="en")

    format_pass = sum(
        1 for p in predictions if is_valid_format(p)
    ) / len(predictions)

    return {
        "bertscore_f1": F1.mean().item(),
        "format_compliance": format_pass,
        "n_samples": len(predictions),
    }
```

---

## SLO Definition and Burn Rate Alerting

Define SLOs before going to production, not after:

```python
# SLO definition for LLM serving
SLOs = {
    "ttft_p50_ms": 300,    # 50% of requests start within 300ms
    "ttft_p99_ms": 2000,   # 99% within 2 seconds
    "tps_p50": 25,          # 50th percentile tokens/sec during decode
    "e2e_p99_ms": 10000,   # 99% complete within 10 seconds
    "error_rate": 0.001,    # 0.1% error budget
    "gpu_oom_rate": 0.0001, # near-zero OOM tolerance
}

# Error budget burn rate (SRE concept applied to LLM serving)
def compute_burn_rate(
    observed_violation_rate: float,
    slo_target: float,  # e.g., 0.99 = 99% requests within TTFT target
    window_hours: int = 1,
) -> float:
    """
    Burn rate > 1 means you're consuming error budget faster than it replenishes.
    Burn rate > 14.4 for 1-hour window → alert (will exhaust 30-day budget in 2 hours)
    """
    error_budget = 1 - slo_target  # e.g., 0.01 = 1%
    actual_error_rate = 1 - (1 - observed_violation_rate)
    return actual_error_rate / error_budget
```

**CloudWatch metrics for AWS-deployed vLLM:**

```python
import boto3

cw = boto3.client("cloudwatch")

def publish_inference_metrics(
    ttft_ms: float,
    tokens_generated: int,
    e2e_ms: float,
    model_id: str,
):
    cw.put_metric_data(
        Namespace="LLMServing",
        MetricData=[
            {"MetricName": "TTFT", "Value": ttft_ms, "Unit": "Milliseconds",
             "Dimensions": [{"Name": "ModelID", "Value": model_id}]},
            {"MetricName": "TokensGenerated", "Value": tokens_generated, "Unit": "Count",
             "Dimensions": [{"Name": "ModelID", "Value": model_id}]},
            {"MetricName": "E2ELatency", "Value": e2e_ms, "Unit": "Milliseconds",
             "Dimensions": [{"Name": "ModelID", "Value": model_id}]},
        ],
    )

# CloudWatch Alarm: TTFT p99 > 3s for 5 consecutive 1-minute periods
# → SNS → PagerDuty
```
