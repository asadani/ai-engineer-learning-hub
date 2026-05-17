# What to Measure & How

## Core Serving Metrics by Layer

### Request Latency Metrics

| Metric | Definition | Target (interactive) | Target (batch) | Collection Method |
|--------|-----------|---------------------|----------------|-------------------|
| **TTFT p50** | Time from request to first token (50th pct) | < 300ms | N/A | Trace: timestamp(first_token) − timestamp(request) |
| **TTFT p99** | Same, 99th percentile | < 2s | N/A | Trace |
| **TPOT p50** | Time Per Output Token, median | < 40ms (>25 TPS) | < 200ms | Trace: (e2e − ttft) / output_tokens |
| **ITL p99** | Inter-token latency 99th pct | < 80ms | N/A | Trace: time between consecutive token emissions |
| **E2E p50** | Total request latency | < 2s | < 60s | Trace: response_complete − request_received |
| **E2E p99** | Same, 99th percentile | < 10s | < 120s | Trace |
| **Queue time** | Time spent waiting for GPU slot | < 100ms | N/A | Engine: scheduled_time − arrival_time |

### Throughput Metrics

| Metric | Definition | Target | Collection Method |
|--------|-----------|--------|-------------------|
| **Input token throughput** | Total input tokens/sec across all requests | Maximize | Engine metrics endpoint |
| **Output token throughput** | Total output tokens/sec | Maximize | Engine metrics endpoint |
| **Request throughput (RPS)** | Completed requests/sec | Maximize | Application metrics |
| **Batch size** | Average concurrent sequences per step | 60–80% of max_num_seqs | vLLM metrics |
| **GPU token rate** | Tokens/sec per GPU | >1,500 (8B bf16 A100) | compute output_tps / num_gpus |

### GPU Resource Metrics

| Metric | Definition | Target | Collection Method |
|--------|-----------|--------|-------------------|
| **GPU utilization (SM %)** | % of SMs active | 60–90% (prefill), 10–30% (decode) | `dcgmi`, `nvidia-smi` |
| **HBM bandwidth utilization** | % of theoretical bandwidth used | 60–85% (decode bound) | DCGM metric 1009 |
| **KV cache utilization** | % of KV cache blocks occupied | 70–90% | vLLM `/metrics` endpoint |
| **GPU memory used (GB)** | Total HBM consumption | < 92% of capacity | `nvidia-smi` |
| **NVLink bandwidth** | All-reduce traffic (TP workloads) | < 80% of peak | DCGM metric 1010 |

### Reliability Metrics

| Metric | Definition | Target | Collection Method |
|--------|-----------|--------|-------------------|
| **Error rate** | 5xx responses / total requests | < 0.1% | Application metrics |
| **OOM rate** | CUDA out-of-memory errors / requests | < 0.01% | Engine logs, alerting |
| **Timeout rate** | Requests exceeding latency budget | < 0.5% | Application metrics |
| **Format failure rate** | Responses failing schema validation | < 0.5% | Post-processing validator |
| **Retry rate** | Requests requiring retry | < 1% | LiteLLM metrics |

---

## vLLM Native Prometheus Metrics

vLLM exposes metrics at `GET /metrics` in Prometheus format:

```bash
# Start with metrics enabled (default)
python -m vllm.entrypoints.openai.api_server \
  --model meta-llama/Meta-Llama-3.1-8B-Instruct \
  --port 8000

# Scrape
curl http://localhost:8000/metrics
```

**Key vLLM Prometheus metrics:**

```
# Scheduling
vllm:num_requests_running              # currently executing
vllm:num_requests_waiting              # in queue
vllm:num_requests_swapped             # swapped to CPU (should be 0)

# Latency histograms
vllm:e2e_request_latency_seconds_bucket{...}
vllm:time_to_first_token_seconds_bucket{...}
vllm:time_per_output_token_seconds_bucket{...}
vllm:inter_token_latency_seconds_bucket{...}

# Throughput
vllm:prompt_tokens_total              # cumulative input tokens
vllm:generation_tokens_total          # cumulative output tokens

# Cache
vllm:gpu_cache_usage_perc             # KV cache % used (0.0–1.0)
vllm:cpu_cache_usage_perc             # CPU KV cache % (if enabled)
vllm:gpu_prefix_cache_hit_rate        # prefix cache hit rate

# GPU
vllm:avg_generation_throughput_toks_per_s
vllm:avg_prompt_throughput_toks_per_s
```

**Prometheus + Grafana dashboard config:**

```yaml
# prometheus.yml scrape config
scrape_configs:
  - job_name: "vllm"
    static_configs:
      - targets: ["vllm-server:8000"]
    metrics_path: "/metrics"
    scrape_interval: 5s
```

```python
# Alerting rules (prometheus rules.yml)
groups:
  - name: vllm_alerts
    rules:
      - alert: VLLMHighTTFT
        expr: histogram_quantile(0.99, rate(vllm:time_to_first_token_seconds_bucket[5m])) > 3
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "TTFT p99 > 3s for 2 minutes"

      - alert: VLLMKVCacheNearFull
        expr: vllm:gpu_cache_usage_perc > 0.95
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "KV cache > 95% — OOM risk imminent"

      - alert: VLLMRequestQueueDepth
        expr: vllm:num_requests_waiting > 50
        for: 3m
        labels:
          severity: warning
        annotations:
          summary: "Request queue depth > 50 for 3 minutes — scale out needed"
```

---

## Cost Metrics

| Metric | Formula | Target |
|--------|---------|--------|
| **Cost per 1M tokens (input)** | infra_cost_per_hour / (input_tps × 3600 / 1e6) | Track vs. API pricing |
| **Cost per 1M tokens (output)** | infra_cost_per_hour / (output_tps × 3600 / 1e6) | Target < $2/1M output |
| **GPU utilization efficiency** | revenue_per_gpu_hour / cost_per_gpu_hour | > 1.5× to be profitable |
| **Token/$ ratio** | tokens_served / dollar_spent | Maximize |
| **Spot savings %** | (on_demand_cost − spot_cost) / on_demand_cost | Target 60–70% for batch |

```python
# Cost tracking with LiteLLM
import litellm

def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """LiteLLM has a built-in cost map for 100+ models."""
    cost = litellm.completion_cost(
        model=model,
        prompt_tokens=input_tokens,
        completion_tokens=output_tokens,
    )
    return cost  # in USD

# For self-hosted, compute manually
def self_hosted_cost_per_token(
    instance_cost_per_hour: float,  # e.g., $32/hr for p4d.24xlarge
    output_tokens_per_second: float,  # measured throughput
    input_to_output_ratio: float = 3.0,  # typical: 3 input tokens per 1 output
) -> dict:
    tokens_per_hour = output_tokens_per_second * 3600
    input_tokens_per_hour = tokens_per_hour * input_to_output_ratio
    return {
        "output_cost_per_1M": instance_cost_per_hour / (tokens_per_hour / 1e6),
        "input_cost_per_1M": instance_cost_per_hour / (input_tokens_per_hour / 1e6),
        "total_tokens_per_dollar": (tokens_per_hour * (1 + input_to_output_ratio)) / instance_cost_per_hour,
    }

# p4d.24xlarge ($32/hr) running Llama-3-70B at 2,000 output tokens/sec:
# output_cost_per_1M = 32 / (7,200,000 / 1e6) = $4.44/1M output tokens
# Compare: Bedrock claude-3-haiku at $1.25/1M output — self-hosting wins at scale
```

---

## Production Dashboard Checklist

**Real-time (1-minute resolution):**
- [ ] TTFT p50, p95, p99 (trend + alert threshold)
- [ ] TPS (output tokens/sec) per replica
- [ ] Active request count vs max_num_seqs
- [ ] Queue depth (requests waiting)
- [ ] GPU memory used % + KV cache %
- [ ] Error rate (5xx / total)

**5-minute aggregations:**
- [ ] Request throughput (RPS)
- [ ] Input/output token throughput
- [ ] Prefix cache hit rate (if enabled)
- [ ] GPU utilization (SM %, HBM bandwidth %)
- [ ] Cost per 1M tokens (computed from infra cost / tokens served)

**Hourly:**
- [ ] Format failure rate (post-processing validation)
- [ ] Retry rate (from LiteLLM or gateway)
- [ ] P99 latency trend over 6 hours
- [ ] Spot interruption rate (if using Spot instances)

**Daily:**
- [ ] Total tokens served
- [ ] Total infra cost vs token revenue
- [ ] Model quality spot-check (LLM-judge on sample)
- [ ] Quantization quality drift (perplexity on held-out set)

---

## Domain-Specific Serving Targets Reference Card

| Use Case | Model Size | TTFT p50 | TTFT p99 | TPS | Setup |
|----------|-----------|---------|---------|-----|-------|
| Interactive chat | 8B | < 150ms | < 800ms | > 40 | vLLM TP=1, A100 |
| Agentic / tool-use | 70B | < 500ms | < 2s | > 20 | vLLM TP=4, A100×4 |
| RAG Q&A (short context) | 8B | < 200ms | < 1s | > 35 | vLLM + prefix cache |
| RAG Q&A (long context 32k) | 70B | < 2s | < 8s | > 15 | vLLM TP=4, chunked prefill |
| Batch summarization | 8B | N/A | N/A | > 500 TPS | vLLM max batch, AWQ |
| Code completion (inline) | 3B | < 100ms | < 400ms | > 80 | vLLM TP=1, speculative |
| Local / on-device | 8B Q4 | < 500ms | N/A | > 25 | llama.cpp, Q4_K_M |
| Document extraction | 8B | N/A | N/A | > 200 TPS | vLLM TP=2, temp=0 |
