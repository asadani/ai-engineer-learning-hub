# What to Measure & How

## Eval System Observability

Running evals is only half the work — you need visibility into eval pipeline health, result trends, and cost to operate them sustainably.

---

## Metrics Checklist

| Metric Name | Type | Target SLO | Collection Method |
|-------------|------|------------|-------------------|
| **faithfulness** | Gauge (0–1) | > 0.85 | RAGAS / LLM-as-judge per query |
| **answer_relevance** | Gauge (0–1) | > 0.80 | RAGAS / LLM-as-judge |
| **context_precision** | Gauge (0–1) | > 0.70 | RAGAS |
| **context_recall** | Gauge (0–1) | > 0.80 | RAGAS |
| **answer_correctness** | Gauge (0–1) | > 0.75 | RAGAS with ground truth |
| **retrieval_hit_rate@5** | Gauge (0–1) | > 0.90 | Offline eval against labeled set |
| **retrieval_mrr@5** | Gauge (0–1) | > 0.80 | Offline eval |
| **task_success_rate** (agents) | Gauge (0–1) | > 0.85 | Binary outcome per task |
| **safety_refusal_accuracy** | Gauge (0–1) | > 0.99 | Automated safety test suite |
| **over_refusal_rate** | Gauge (0–1) | < 0.05 | Benign test suite |
| **eval_cost_usd_per_run** | Gauge | < budget | LLM call cost tracking |
| **eval_latency_seconds** | Histogram | p99 < 300s for 1K samples | Eval pipeline timing |
| **judge_human_agreement_r** | Gauge | ≥ 0.80 | Monthly calibration run |
| **dataset_staleness_days** | Gauge | < 180 days | Dataset metadata |
| **regression_alerts_triggered** | Counter | 0 on stable releases | CI/CD eval gate |
| **implicit_satisfaction_score** | Gauge (0–1) | > 0.85 | Thumbs up/(up+down) ratio |
| **escalation_rate** | Gauge | < 0.10 | % queries escalated to human |
| **response_abandon_rate** | Gauge | < 0.05 | Session analytics |
| **llm_judge_score_std_dev** | Gauge | < 0.15 | Re-run same queries, measure variance |
| **eval_coverage** (% traffic sampled) | Gauge | ≥ 5% | Production sampling config |

---

## Production Eval Sampling Pipeline

```python
import asyncio
import random
from dataclasses import dataclass, field
from typing import Callable

@dataclass
class ProductionEvalConfig:
    sample_rate: float = 0.05          # 5% of production queries
    judge_model: str = "claude-haiku-4-5"  # cheap judge for online evals
    judge_dimensions: list[str] = field(default_factory=lambda: [
        "faithfulness", "answer_relevance"
    ])
    alert_threshold: float = 0.70      # alert if rolling avg drops below
    window_size: int = 100             # rolling window for averaging

class ProductionEvalSampler:
    def __init__(self, config: ProductionEvalConfig, metrics_client) -> None:
        self._config = config
        self._metrics = metrics_client
        self._scores: dict[str, list[float]] = {d: [] for d in config.judge_dimensions}

    async def maybe_eval(
        self,
        question: str,
        context: list[str],
        answer: str,
        trace_id: str,
    ) -> None:
        """Called after every production response. Evaluates a sample."""
        if random.random() > self._config.sample_rate:
            return  # skip non-sampled queries

        asyncio.create_task(
            self._eval_and_record(question, context, answer, trace_id)
        )

    async def _eval_and_record(self, question, context, answer, trace_id) -> None:
        for dimension in self._config.judge_dimensions:
            try:
                score = await llm_judge(
                    judge_model=self._config.judge_model,
                    dimension=dimension,
                    question=question,
                    context=context,
                    answer=answer,
                )
                self._scores[dimension].append(score)
                self._metrics.gauge(f"eval.online.{dimension}", score)

                # Rolling window alert
                window = self._scores[dimension][-self._config.window_size:]
                rolling_avg = sum(window) / len(window)
                if len(window) >= 50 and rolling_avg < self._config.alert_threshold:
                    self._metrics.increment("eval.online.alert",
                                          tags={"dimension": dimension})
                    await self._send_alert(dimension, rolling_avg, trace_id)
            except Exception as e:
                self._metrics.increment("eval.online.error",
                                       tags={"dimension": dimension})
```

---

## CI/CD Eval Integration

```yaml
# .github/workflows/eval.yml
name: LLM Eval Gate

on:
  pull_request:
    paths:
      - "src/prompts/**"
      - "src/pipelines/**"
      - "src/retrievers/**"

jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run eval suite
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          pip install -r requirements-eval.txt
          python scripts/run_eval.py \
            --golden-set data/eval_sets/golden_v4.jsonl \
            --baseline-file metrics/baselines/main.json \
            --output-file metrics/results/pr_${{ github.event.pull_request.number }}.json \
            --n-samples 200 \
            --threshold-ratio 0.97

      - name: Post eval results to PR
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const results = JSON.parse(fs.readFileSync(
              `metrics/results/pr_${{ github.event.pull_request.number }}.json`
            ));
            const body = `## Eval Results\n${formatResultsTable(results)}`;
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body
            });
```

---

## Eval Cost Tracking

LLM-as-judge has non-trivial cost at scale. Track it explicitly.

```python
@dataclass
class EvalCostTracker:
    judge_model: str
    costs: dict[str, float] = field(default_factory=dict)  # model -> $/1M tokens

    # 2026 pricing (approximate)
    MODEL_COSTS = {
        "claude-haiku-4-5": {"input": 0.80, "output": 4.00},    # cheapest, good for filtering
        "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},  # best quality/cost
        "claude-opus-4-6": {"input": 15.00, "output": 75.00},   # most accurate judge
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "gpt-4o": {"input": 5.00, "output": 15.00},
    }

    def estimate_eval_run_cost(
        self,
        n_samples: int,
        n_metrics: int = 4,
        avg_input_tokens: int = 800,  # question + context + response + judge prompt
        avg_output_tokens: int = 150, # score + reasoning
    ) -> dict:
        costs = self.MODEL_COSTS.get(self.judge_model, {})
        input_cost = n_samples * n_metrics * avg_input_tokens / 1_000_000 * costs.get("input", 0)
        output_cost = n_samples * n_metrics * avg_output_tokens / 1_000_000 * costs.get("output", 0)
        return {
            "total_usd": input_cost + output_cost,
            "per_sample_usd": (input_cost + output_cost) / n_samples,
            "input_cost_usd": input_cost,
            "output_cost_usd": output_cost,
        }

# Examples for 1000-sample eval, 4 RAGAS metrics:
# claude-haiku-4-5:  ~$0.60  → use for PR gate evals
# claude-sonnet-4-6: ~$2.50  → use for weekly comprehensive evals
# claude-opus-4-6:   ~$12.50 → use for quarterly calibration only
```

---

## Eval Result Dashboard (Grafana / CloudWatch)

### Key panels to build

```
┌──────────────────────────────────────────────────────┐
│  QUALITY TREND (30-day rolling)                       │
│  faithfulness  ████████░░  0.84  ↓ from 0.87 (alert) │
│  ans_relevance ████████████ 0.91  ↑ stable            │
│  ctx_precision ███████░░░░  0.73  stable              │
├──────────────────────────────────────────────────────┤
│  PRODUCTION SAMPLING (live)                           │
│  Sample rate: 5% | Last 1h: 47 evals | Avg: 0.83     │
│  Alerts triggered today: 2                            │
├──────────────────────────────────────────────────────┤
│  EVAL COST (this month)                               │
│  PR gate evals: $8.20 (82 runs × $0.10)              │
│  Production sampling: $4.50/day                      │
│  Total: $143 (vs $200 budget)                        │
├──────────────────────────────────────────────────────┤
│  DATASET HEALTH                                       │
│  Golden set: 1,247 samples | Last updated: 14 days   │
│  Category coverage: 8 categories, entropy 2.4 nats   │
│  Judge calibration (last run): pearson_r = 0.83 ✓    │
└──────────────────────────────────────────────────────┘
```

---

## Alerts and Escalation

```python
EVAL_ALERTS = [
    {
        "name": "FaithfulnessRegression",
        "condition": "rolling_100_avg(faithfulness) < 0.80",
        "severity": "critical",
        "action": "page_oncall + block_deployments",
    },
    {
        "name": "EvalDatasetStale",
        "condition": "dataset_staleness_days > 180",
        "severity": "warning",
        "action": "create_jira_ticket(resample_eval_set)",
    },
    {
        "name": "JudgeCalibrationDrift",
        "condition": "judge_human_agreement_r < 0.75",
        "severity": "warning",
        "action": "recalibrate_judge + notify_ml_team",
    },
    {
        "name": "SafetyTestFailure",
        "condition": "safety_refusal_accuracy < 0.99",
        "severity": "critical",
        "action": "block_deployment + page_safety_team",
    },
]
```

---

## Eval Ops Runbook

**Weekly**:
- Run full 1000-sample eval on golden set; compare to baseline; update trending dashboard
- Review production sampling alerts from last 7 days; add failure cases to golden set

**Monthly**:
- Run judge calibration against 200 fresh human annotations; update calibration metrics
- Review dataset health (staleness, diversity, coverage); resample if needed
- Update baselines if a significant improvement has been validated

**Quarterly**:
- Full human eval run on 200 stratified samples
- Re-run model selection eval if new foundation model versions released
- Adversarial/red-team eval sweep on safety and jailbreak test suite
- Update CLAUDE.md with any new eval procedures or metric changes
