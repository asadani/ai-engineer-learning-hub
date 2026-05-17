# What to Measure & How

## Core Cost Metrics by Layer

### Spend Metrics

| Metric | Definition | Target | Alert | Collection Method |
|--------|-----------|--------|-------|------------------|
| **Cost per request (p50)** | Median cost of one LLM call | Baseline | > 2× baseline | Per-call logging × pricing |
| **Cost per request (p99)** | 99th pct cost (catch outliers) | < 10× p50 | > 20× p50 | Per-call logging |
| **Cost per successful task** | Total cost ÷ successful completions | Baseline | > 2× baseline | Cost + eval outcome join |
| **Daily total spend** | All API + GPU costs per day | Budget | > 80% budget | CloudWatch billing + custom |
| **Monthly cost trend** | MoM change in AI spend | Flat or decreasing | > 20% MoM increase | Billing dashboard |
| **Cost per DAU** | Daily spend ÷ daily active users | Track baseline | > 2× baseline | Spend ÷ product analytics |
| **Cost per feature** | Spend attributed to each feature | Track per feature | Feature > 30% of total unexpectedly | Tagged per-call logging |

### Token Efficiency Metrics

| Metric | Definition | Target | Alert | Collection Method |
|--------|-----------|--------|-------|------------------|
| **Input tokens per request** | Avg input tokens/call by feature | Baseline | > 1.5× baseline | response.usage.input_tokens |
| **Output tokens per request** | Avg output tokens/call | Baseline | > 2× baseline | response.usage.output_tokens |
| **Output/input ratio** | output_tokens / total_tokens | < 30% | > 50% (overly verbose) | Token ratio calculation |
| **Token waste rate** | (max_tokens - actual_output) / max_tokens | < 50% | > 80% (over-provisioned) | max_tokens vs actual |
| **Tokens per quality point** | Total tokens / quality score | Minimize | > 20% degradation | Tokens + LLM judge score |

### Cache Metrics

| Metric | Definition | Target | Alert | Collection Method |
|--------|-----------|--------|-------|------------------|
| **Prompt cache hit rate** | cache_read_tokens / total_input_tokens | > 50% (if cacheable) | < 20% | usage.cache_read_input_tokens |
| **Cache savings %** | (cost_without_cache - actual_cost) / cost_without_cache | > 40% (if caching) | < 15% | Calculated |
| **Semantic cache hit rate** | Cache hits / total queries | > 20% (if deployed) | < 5% | Semantic cache middleware |
| **Cache stale rate** | Cached responses served but later rated poor | < 2% | > 5% | Quality eval on cached vs live |

### Model Routing Metrics

| Metric | Definition | Target | Alert | Collection Method |
|--------|-----------|--------|-------|------------------|
| **Routing distribution** | % traffic to each model tier | Match expectations | Heavy-tier > 50% unexpectedly | Feature-tagged model calls |
| **Router accuracy** | Correct tier / total (vs human labels) | > 90% | < 80% | Manual sample labeling |
| **Quality regression rate** | Tasks where cheap tier fails + escalates | < 5% | > 15% | Escalation logs |
| **Routing latency overhead** | Time added by router call | < 200ms | > 500ms | Latency tracing |
| **Savings vs baseline** | Cost vs all-top-tier baseline | Track | Savings < 30% (routing not working) | Cost comparison |

### Infrastructure Metrics (Self-Hosted)

| Metric | Definition | Target | Alert | Collection Method |
|--------|-----------|--------|-------|------------------|
| **GPU utilization** | Active GPU time / total GPU time | > 60% | < 30% | nvidia-smi, CloudWatch GPU |
| **GPU memory utilization** | VRAM used / total VRAM | 80–90% | < 50% or > 95% | nvidia-smi |
| **Throughput (tokens/sec)** | Total tokens generated per second | Maximize | < 50% of expected | vLLM metrics endpoint |
| **Queue depth** | Waiting requests in vLLM scheduler | < 10 | > 50 (need to scale) | vLLM /metrics |
| **KV cache hit rate** | Prefix cache hits / total requests | > 40% | < 10% | vLLM metrics |
| **Cost per million tokens** | Total compute cost / tokens served | Baseline | > 1.5× baseline | Billing ÷ tokens |
| **Spot interruption rate** | Interruptions / instance-days | < 0.5/day | > 2/day | EC2 Spot history |

---

## Instrumentation Implementation

```python
import boto3
import time
from dataclasses import dataclass, field
from typing import Any
import anthropic

client = anthropic.Anthropic()

MODEL_PRICING = {
    "claude-opus-4-6":           {"input": 15.00, "output": 75.00},
    "claude-sonnet-4-6":         {"input": 3.00,  "output": 15.00},
    "claude-haiku-4-5-20251001": {"input": 0.80,  "output": 4.00},
}
CACHE_DISCOUNT = 0.10    # cache reads are 10% of input price
CACHE_WRITE_SURCHARGE = 1.25  # cache writes are 125% of input price

@dataclass
class CallMetrics:
    call_id: str
    feature: str
    user_id: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    latency_ms: float
    cost_usd: float
    error: str | None = None

def calculate_cost(model: str, input_t: int, output_t: int, cache_read_t: int, cache_write_t: int) -> float:
    p = MODEL_PRICING.get(model, {"input": 3.00, "output": 15.00})
    regular_input = input_t - cache_read_t - cache_write_t
    return (
        regular_input    * p["input"]
        + cache_read_t   * p["input"]  * CACHE_DISCOUNT
        + cache_write_t  * p["input"]  * CACHE_WRITE_SURCHARGE
        + output_t       * p["output"]
    ) / 1_000_000

class CostInstrumentedClient:
    def __init__(self, cw_namespace: str = "AI/CostOptimization"):
        self.cw = boto3.client("cloudwatch", region_name="us-east-1")
        self.namespace = cw_namespace

    def call(
        self,
        messages: list[dict],
        model: str,
        feature: str,
        user_id: str,
        system: Any = None,
        max_tokens: int = 1024,
        **kwargs,
    ) -> tuple[str, CallMetrics]:
        import uuid
        call_id = str(uuid.uuid4())
        start = time.perf_counter()
        error = None

        try:
            params = dict(model=model, max_tokens=max_tokens, messages=messages, **kwargs)
            if system:
                params["system"] = system
            response = client.messages.create(**params)

            u = response.usage
            cache_read = getattr(u, "cache_read_input_tokens", 0) or 0
            cache_write = getattr(u, "cache_creation_input_tokens", 0) or 0

            metrics = CallMetrics(
                call_id=call_id,
                feature=feature,
                user_id=user_id,
                model=model,
                input_tokens=u.input_tokens,
                output_tokens=u.output_tokens,
                cache_read_tokens=cache_read,
                cache_write_tokens=cache_write,
                latency_ms=(time.perf_counter() - start) * 1000,
                cost_usd=calculate_cost(model, u.input_tokens, u.output_tokens, cache_read, cache_write),
            )
            self._emit(metrics)
            return response.content[0].text, metrics

        except Exception as e:
            metrics = CallMetrics(
                call_id=call_id, feature=feature, user_id=user_id, model=model,
                input_tokens=0, output_tokens=0, cache_read_tokens=0, cache_write_tokens=0,
                latency_ms=(time.perf_counter() - start) * 1000,
                cost_usd=0.0, error=str(e),
            )
            self._emit(metrics)
            raise

    def _emit(self, m: CallMetrics):
        dims = [{"Name": "Feature", "Value": m.feature}, {"Name": "Model", "Value": m.model}]
        self.cw.put_metric_data(
            Namespace=self.namespace,
            MetricData=[
                {"MetricName": "CostPerCall",      "Value": m.cost_usd,         "Unit": "None",         "Dimensions": dims},
                {"MetricName": "InputTokens",      "Value": m.input_tokens,     "Unit": "Count",        "Dimensions": dims},
                {"MetricName": "OutputTokens",     "Value": m.output_tokens,    "Unit": "Count",        "Dimensions": dims},
                {"MetricName": "CacheReadTokens",  "Value": m.cache_read_tokens,"Unit": "Count",        "Dimensions": dims},
                {"MetricName": "LatencyMs",        "Value": m.latency_ms,       "Unit": "Milliseconds", "Dimensions": dims},
                {"MetricName": "IsError",          "Value": 1 if m.error else 0,"Unit": "Count",        "Dimensions": dims},
            ],
        )
```

---

## CloudWatch Alerting Rules

```yaml
# cloudwatch_alarms.yaml

alarms:
  - name: AISpendDailyBudgetAlert
    metric: DailyTotalCost
    namespace: AI/CostOptimization
    statistic: Sum
    period: 86400     # 1 day
    threshold: 800    # 80% of $1,000/day budget
    comparison: GreaterThanThreshold
    severity: warning
    action: slack
    message: "AI daily spend at ${value:.2f} — 80% of $1,000/day budget consumed"

  - name: AICostSpikePerFeature
    metric: CostPerCall
    namespace: AI/CostOptimization
    statistic: Average
    period: 3600      # 1 hour
    threshold: 0.05   # $0.05/call avg (10× typical Haiku call)
    comparison: GreaterThanThreshold
    severity: warning
    action: slack
    message: "Average cost per call exceeded $0.05 on feature {dimensions.Feature} — investigate"

  - name: CacheHitRateLow
    metric: CacheReadTokens
    # Alarm if cache reads drop significantly (prompt cache invalidation or bug)
    statistic: Sum
    period: 3600
    threshold_pct: 0.20  # alert if cache_read / total_input < 20%
    severity: warning
    message: "Prompt cache hit rate dropped below 20% — check for system prompt changes"

  - name: OutputTokenRatioHigh
    # Output tokens > 40% of total = overly verbose model, likely wasted tokens
    metric: OutputTokenRatio
    threshold: 0.40
    comparison: GreaterThanThreshold
    severity: info
    message: "Output token ratio {value:.0%} — consider max_tokens constraints or structured output"

  - name: HighCostUserDetected
    metric: CostPerUser
    statistic: Maximum
    period: 3600
    threshold: 10.0   # any single user spending > $10/hour
    severity: critical
    action: pagerduty
    message: "User ${dimensions.UserId} spent ${value:.2f} in the last hour — possible abuse or runaway agent"

  - name: GPUUtilizationLow
    # Self-hosted only: GPU idle = money wasted
    metric: GPUUtilization
    namespace: AI/Infrastructure
    statistic: Average
    period: 900      # 15 minutes
    threshold: 30    # < 30% GPU utilization
    comparison: LessThanThreshold
    severity: warning
    action: slack
    message: "GPU utilization at {value:.0%} — consider scale-in or Spot hibernation"
```

---

## Grafana Dashboard Panels

```python
# Key panels for an AI cost optimization dashboard

DASHBOARD_PANELS = [
    # Row 1: Spend overview
    {
        "title": "Daily Spend vs Budget",
        "type": "gauge",
        "query": "sum(increase(ai_cost_per_call_total[24h]))",
        "thresholds": [{"color": "green", "value": 0}, {"color": "yellow", "value": 800}, {"color": "red", "value": 1000}],
    },
    {
        "title": "Cost by Feature (7d)",
        "type": "pie_chart",
        "query": "sum by (feature) (increase(ai_cost_per_call_total[7d]))",
    },
    {
        "title": "Cost per Request Trend",
        "type": "time_series",
        "query": "avg by (feature) (ai_cost_per_call)",
        "annotations": ["deployment markers", "prompt changes"],
    },

    # Row 2: Token efficiency
    {
        "title": "Token Distribution (Input vs Output)",
        "type": "stacked_bar",
        "queries": [
            "sum(increase(ai_input_tokens_total[1h])) by (model)",
            "sum(increase(ai_output_tokens_total[1h])) by (model)",
            "sum(increase(ai_cache_read_tokens_total[1h])) by (model)",
        ],
    },
    {
        "title": "Cache Hit Rate",
        "type": "stat",
        "query": "sum(ai_cache_read_tokens_total) / sum(ai_input_tokens_total)",
        "unit": "percentunit",
    },

    # Row 3: Model routing
    {
        "title": "Model Routing Distribution",
        "type": "pie_chart",
        "query": "sum by (model) (increase(ai_calls_total[24h]))",
    },
    {
        "title": "Cost Savings vs All-Premium Baseline",
        "type": "stat",
        "query": "1 - (sum(ai_cost_total) / sum(ai_baseline_cost_total))",
        "unit": "percentunit",
    },
]
```

---

## Cost Anomaly Detection

```python
import numpy as np
from scipy import stats

def detect_cost_anomalies(
    hourly_costs: list[float],
    window: int = 24,     # 24-hour rolling baseline
    threshold_z: float = 3.0,  # 3 standard deviations = anomaly
) -> list[int]:
    """Return indices of anomalous cost hours."""
    anomalies = []
    for i in range(window, len(hourly_costs)):
        baseline = hourly_costs[i - window:i]
        current = hourly_costs[i]
        z_score = (current - np.mean(baseline)) / (np.std(baseline) + 1e-9)
        if z_score > threshold_z:
            anomalies.append(i)
    return anomalies

# Example: detect when a new deployment doubles per-request cost
# (common when a new feature adds a second LLM call or large context)
```
