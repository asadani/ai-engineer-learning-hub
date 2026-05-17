# Measurement & Evaluation

## The Cost Attribution Problem

Most teams don't know their actual cost per feature or per user because:
1. Token usage isn't logged at the application level — it's buried in API billing
2. Multiple features share the same API key, making attribution impossible
3. Cost metrics aren't correlated with quality metrics, so optimizations are blind

**The goal**: Build a cost measurement system that gives you cost per query, per feature, per user, and per model — correlated with quality scores — so you can make informed optimization decisions.

---

## Instrumentation Architecture

```python
import time, uuid, json
from dataclasses import dataclass, field, asdict
from typing import Any
import anthropic

client = anthropic.Anthropic()

# Pricing table (update as models change)
MODEL_PRICING = {
    "claude-opus-4-6":            {"input": 15.00, "output": 75.00},
    "claude-sonnet-4-6":          {"input": 3.00,  "output": 15.00},
    "claude-haiku-4-5-20251001":  {"input": 0.80,  "output": 4.00},
}

def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = MODEL_PRICING.get(model, {"input": 3.00, "output": 15.00})
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000

@dataclass
class LLMCallRecord:
    call_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    feature: str = ""               # "rag-search", "summarize", "classify"
    user_id: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    cache_cost_usd: float = 0.0     # cost from cache reads (at discount)
    error: str | None = None
    quality_score: float | None = None  # filled in later by eval pipeline

    def total_cost_usd(self) -> float:
        return self.cost_usd + self.cache_cost_usd

def instrumented_call(
    messages: list[dict],
    model: str,
    system: list | str | None = None,
    max_tokens: int = 1024,
    feature: str = "unknown",
    user_id: str = "anonymous",
    **kwargs,
) -> tuple[str, LLMCallRecord]:
    record = LLMCallRecord(feature=feature, user_id=user_id, model=model)
    start = time.perf_counter()

    try:
        create_kwargs = dict(
            model=model,
            max_tokens=max_tokens,
            messages=messages,
            **kwargs,
        )
        if system:
            create_kwargs["system"] = system

        response = client.messages.create(**create_kwargs)
        record.latency_ms = (time.perf_counter() - start) * 1000
        record.input_tokens = response.usage.input_tokens
        record.output_tokens = response.usage.output_tokens

        # Capture prompt cache usage if available
        if hasattr(response.usage, "cache_read_input_tokens"):
            record.cache_read_tokens = response.usage.cache_read_input_tokens or 0
        if hasattr(response.usage, "cache_creation_input_tokens"):
            record.cache_write_tokens = response.usage.cache_creation_input_tokens or 0

        # Calculate costs (cache reads at 10% of input price)
        pricing = MODEL_PRICING.get(model, {"input": 3.00, "output": 15.00})
        record.cost_usd = calculate_cost(model, record.input_tokens, record.output_tokens)
        record.cache_cost_usd = (record.cache_read_tokens * pricing["input"] * 0.10
                                  + record.cache_write_tokens * pricing["input"] * 1.25) / 1_000_000

        return response.content[0].text, record

    except Exception as e:
        record.latency_ms = (time.perf_counter() - start) * 1000
        record.error = str(e)
        raise
    finally:
        emit_metric(record)  # always log, even on error

def emit_metric(record: LLMCallRecord):
    """Emit to CloudWatch and write to DynamoDB for cost analysis."""
    import boto3
    cw = boto3.client("cloudwatch", region_name="us-east-1")

    dims = [
        {"Name": "Feature", "Value": record.feature},
        {"Name": "Model", "Value": record.model},
    ]
    cw.put_metric_data(
        Namespace="AI/CostOptimization",
        MetricData=[
            {"MetricName": "CostPerCall", "Value": record.total_cost_usd(),
             "Unit": "None", "Dimensions": dims},
            {"MetricName": "InputTokens", "Value": record.input_tokens,
             "Unit": "Count", "Dimensions": dims},
            {"MetricName": "OutputTokens", "Value": record.output_tokens,
             "Unit": "Count", "Dimensions": dims},
            {"MetricName": "CacheReadTokens", "Value": record.cache_read_tokens,
             "Unit": "Count", "Dimensions": dims},
            {"MetricName": "LatencyMs", "Value": record.latency_ms,
             "Unit": "Milliseconds", "Dimensions": dims},
        ],
    )
```

---

## Cost Attribution Dashboard Queries

```sql
-- DynamoDB or Redshift schema: llm_calls(call_id, timestamp, feature, user_id, model, cost_usd, ...)

-- Top cost features (last 7 days)
SELECT feature,
       COUNT(*) as call_count,
       SUM(cost_usd) as total_cost,
       AVG(cost_usd) as avg_cost_per_call,
       SUM(cost_usd) / SUM(COUNT(*)) OVER () as pct_of_total_cost
FROM llm_calls
WHERE timestamp > NOW() - INTERVAL '7 days'
GROUP BY feature
ORDER BY total_cost DESC;

-- Cost trend by model (daily granularity for optimization tracking)
SELECT DATE_TRUNC('day', timestamp) as day,
       model,
       SUM(cost_usd) as daily_cost,
       SUM(input_tokens) as daily_input_tokens,
       SUM(output_tokens) as daily_output_tokens,
       AVG(cache_read_tokens::float / NULLIF(input_tokens, 0)) as cache_hit_rate
FROM llm_calls
GROUP BY 1, 2
ORDER BY 1, 3 DESC;

-- Identify high-cost outlier users (potential abuse or misconfiguration)
SELECT user_id,
       COUNT(*) as call_count,
       SUM(cost_usd) as total_cost,
       MAX(cost_usd) as max_single_call_cost,
       AVG(input_tokens) as avg_input_tokens
FROM llm_calls
WHERE timestamp > NOW() - INTERVAL '1 day'
GROUP BY user_id
HAVING SUM(cost_usd) > 5.0  -- flag users spending > $5/day
ORDER BY total_cost DESC;

-- Quality vs cost correlation (when quality scores are available)
SELECT feature,
       AVG(quality_score) as avg_quality,
       AVG(cost_usd) as avg_cost,
       AVG(quality_score) / NULLIF(AVG(cost_usd), 0) as quality_per_dollar
FROM llm_calls
WHERE quality_score IS NOT NULL
GROUP BY feature
ORDER BY quality_per_dollar DESC;
```

---

## A/B Testing Optimization Changes

Any cost optimization must be validated against quality before full rollout:

```python
import random
from anthropic import Anthropic

client = Anthropic()

class CostOptimizationExperiment:
    """A/B test framework for cost optimizations."""

    def __init__(self, experiment_id: str, treatment_fraction: float = 0.1):
        self.experiment_id = experiment_id
        self.treatment_fraction = treatment_fraction

    def assign_variant(self, user_id: str) -> str:
        """Deterministic assignment based on user_id hash."""
        import hashlib
        hash_val = int(hashlib.md5(f"{self.experiment_id}:{user_id}".encode()).hexdigest(), 16)
        return "treatment" if (hash_val % 100) < (self.treatment_fraction * 100) else "control"

    def run(self, user_id: str, query: str, context: str) -> dict:
        variant = self.assign_variant(user_id)

        if variant == "control":
            # Current approach: top-10 chunks, Sonnet
            response, record = instrumented_call(
                messages=[{"role": "user", "content": f"Context: {context}\n\nQuery: {query}"}],
                model="claude-sonnet-4-6",
                max_tokens=512,
                feature=f"{self.experiment_id}/control",
                user_id=user_id,
            )
        else:
            # Treatment: top-3 chunks with reranker + cached system prompt + Haiku
            compressed_context = context[:3000]  # top-3 chunks, truncated
            response, record = instrumented_call(
                messages=[{"role": "user", "content": f"Context: {compressed_context}\n\nQuery: {query}"}],
                model="claude-haiku-4-5-20251001",
                max_tokens=512,
                feature=f"{self.experiment_id}/treatment",
                user_id=user_id,
            )

        return {"response": response, "variant": variant, "cost": record.total_cost_usd()}

# Monitor experiment results:
# SELECT variant,
#        COUNT(*) as requests,
#        AVG(cost_usd) as avg_cost,
#        AVG(quality_score) as avg_quality  -- from thumbs up/down or LLM judge
# FROM llm_calls WHERE feature LIKE 'rag-optimization/%'
# GROUP BY variant
```

---

## Quality-Cost Evaluation Framework

When evaluating whether an optimization is safe to ship:

```python
from anthropic import Anthropic
import json

client = Anthropic()

QUALITY_JUDGE_PROMPT = """Compare these two AI responses to the same query and determine if Response B (optimized, cheaper) is acceptable relative to Response A (baseline).

Query: {query}

Response A (baseline, ${cost_a:.4f}):
{response_a}

Response B (optimized, ${cost_b:.4f}):
{response_b}

Rate Response B on:
1. Factual accuracy vs A (0-3): 0=wrong facts, 1=some errors, 2=mostly correct, 3=equivalent
2. Completeness vs A (0-3): 0=missing critical info, 1=incomplete, 2=mostly complete, 3=equivalent
3. Actionability vs A (0-3): 0=less actionable, 1=slightly less, 2=mostly equivalent, 3=equivalent

Output JSON: {{"accuracy": N, "completeness": N, "actionability": N, "acceptable": true|false, "notes": "..."}}
acceptable = true if all scores >= 2"""

def evaluate_optimization(
    test_queries: list[dict],
    baseline_fn,
    optimized_fn,
    judge_model: str = "claude-sonnet-4-6",
    acceptable_threshold: float = 0.95,  # 95% of responses must be acceptable
) -> dict:
    results = []
    total_cost_a = 0.0
    total_cost_b = 0.0

    for q in test_queries:
        response_a, cost_a = baseline_fn(q["query"])
        response_b, cost_b = optimized_fn(q["query"])
        total_cost_a += cost_a
        total_cost_b += cost_b

        judge_response = client.messages.create(
            model=judge_model,
            max_tokens=256,
            messages=[{
                "role": "user",
                "content": QUALITY_JUDGE_PROMPT.format(
                    query=q["query"],
                    cost_a=cost_a, response_a=response_a,
                    cost_b=cost_b, response_b=response_b,
                ),
            }],
        )
        scores = json.loads(judge_response.content[0].text)
        results.append({
            "query": q["query"],
            "acceptable": scores["acceptable"],
            "scores": scores,
            "cost_savings": cost_a - cost_b,
        })

    acceptable_rate = sum(r["acceptable"] for r in results) / len(results)
    cost_reduction = (total_cost_a - total_cost_b) / total_cost_a

    return {
        "acceptable_rate": acceptable_rate,
        "passes_threshold": acceptable_rate >= acceptable_threshold,
        "cost_reduction_pct": cost_reduction * 100,
        "total_savings_on_test_set": total_cost_a - total_cost_b,
        "results": results,
        "recommendation": "SHIP" if acceptable_rate >= acceptable_threshold else "DO NOT SHIP",
    }
```

---

## Cache Effectiveness Measurement

```python
from collections import defaultdict
import statistics

class CacheMetricsCollector:
    def __init__(self):
        self.records = []

    def record(self, total_input: int, cache_read: int, cache_write: int, cost: float):
        self.records.append({
            "total_input": total_input,
            "cache_read": cache_read,
            "cache_write": cache_write,
            "cost": cost,
        })

    def report(self) -> dict:
        if not self.records:
            return {}

        total_input = sum(r["total_input"] for r in self.records)
        total_cache_read = sum(r["cache_read"] for r in self.records)
        total_cache_write = sum(r["cache_write"] for r in self.records)
        total_cost = sum(r["cost"] for r in self.records)

        # Hypothetical cost without cache
        model_input_price = 3.00  # Sonnet example
        cost_without_cache = (total_input * model_input_price) / 1_000_000

        return {
            "total_requests": len(self.records),
            "cache_hit_rate_pct": (total_cache_read / total_input * 100) if total_input > 0 else 0,
            "tokens_served_from_cache": total_cache_read,
            "actual_cost_usd": total_cost,
            "cost_without_cache_usd": cost_without_cache,
            "savings_usd": cost_without_cache - total_cost,
            "savings_pct": ((cost_without_cache - total_cost) / cost_without_cache * 100) if cost_without_cache > 0 else 0,
        }
```

---

## Key Metrics for Cost Optimization Decisions

| Metric | Formula | Alert Threshold | Collection |
|--------|---------|-----------------|-----------|
| **Cost per request** | total_cost / request_count | > 2× baseline | Per-call logging |
| **Cost per successful task** | total_cost / successful_completions | > 2× baseline | Eval + cost join |
| **Cache hit rate** | cache_read_tokens / total_input_tokens | < 20% (if caching enabled) | Usage.cache_read_input_tokens |
| **Model routing accuracy** | correct_tier_assignments / total | < 90% | Manual labeling on sample |
| **Token efficiency** | quality_score / total_tokens | Degradation > 15% | LLM judge + token logs |
| **Output token ratio** | output_tokens / total_tokens | > 40% (high output = verbose) | Per-call logging |
| **P99 cost per request** | 99th pct of per-request cost | > 10× median | Per-call logging |
| **Daily spend vs budget** | actual_daily_cost / budget | > 80% | CloudWatch billing |
| **Cost per user** | total_cost / daily_active_users | > acceptable margin | Cost ÷ DAU |
