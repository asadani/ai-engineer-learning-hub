# What to Measure & How

## Core Agent Metrics by Layer

### Reliability Metrics

| Metric | Definition | Target | Alert | Collection |
|--------|-----------|--------|-------|------------|
| **Task success rate** | Completed correctly / total attempts | > 80% | < 65% | Eval suite + prod sampling |
| **Task completion rate** | Reached any terminal state (not stuck) | > 95% | < 85% | Agent run logs |
| **Human escalation rate** | Tasks requiring HITL intervention | Track baseline | > 2× baseline | HITL event logs |
| **Error rate (unhandled)** | Exceptions not caught by agent | < 1% | > 3% | Application error logs |
| **Tool error rate** | Tool calls returning error responses | < 5% | > 15% | Per-tool metrics |
| **Max-iteration hit rate** | Tasks stopped by iteration limit | < 5% | > 15% | Agent run logs |
| **Context saturation rate** | Tasks stopped by context limit | < 3% | > 10% | Token counter |

### Efficiency Metrics

| Metric | Definition | Target | Alert | Collection |
|--------|-----------|--------|-------|------------|
| **Mean steps per task** | Avg tool calls to complete | Baseline | > 2× baseline | Agent run logs |
| **Redundant call rate** | Duplicate tool calls / total calls | < 5% | > 15% | Trajectory analysis |
| **Backtrack rate** | Steps reversing prior progress | < 10% | > 20% | Trajectory analysis |
| **Token efficiency** | Quality score / tokens used | Maximize | Degradation > 20% | Quality eval + token logs |
| **Planning quality** | Did plan match actual execution? | > 0.7 match | < 0.5 | Plan vs execution diff |

### Latency Metrics

| Metric | Definition | Target (interactive) | Target (async) | Collection |
|--------|-----------|---------------------|----------------|------------|
| **E2E latency p50** | Median task completion time | < 15s | < 5 min | Distributed trace |
| **E2E latency p99** | 99th percentile completion | < 60s | < 30 min | Distributed trace |
| **TTFT (first token)** | Time to first streamed token | < 500ms | N/A | Streaming trace |
| **Step latency p50** | Median time per agent step | < 3s | < 10s | Per-step timing |
| **Tool latency p99** | 99th pct time in tool execution | < 5s | < 30s | Per-tool timing |

### Cost Metrics

| Metric | Definition | Target | Alert | Collection |
|--------|-----------|--------|-------|------------|
| **Cost per task (USD)** | Infra + API cost / completed task | < $0.10 | > $0.50 | Token counter × price |
| **Input token rate** | Input tokens / sec across all runs | Maximize | Budget exceeded | Token logs |
| **Output token rate** | Output tokens / sec | Maximize | Budget exceeded | Token logs |
| **Cost per success** | Total cost / successful tasks | Track baseline | > 2× baseline | Cost ÷ success rate |
| **Daily spend** | Total API + compute cost per day | Budget | > 120% budget | CloudWatch billing |

---

## Instrumentation Implementation

```python
import time, json, uuid
from dataclasses import dataclass, field, asdict
from typing import Any

@dataclass
class StepTrace:
    step_num: int
    timestamp: float
    reasoning: str
    tool_name: str | None
    tool_input: dict | None
    tool_output: str | None
    input_tokens: int
    output_tokens: int
    latency_ms: float

@dataclass
class RunTrace:
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task: str = ""
    start_time: float = field(default_factory=time.time)
    steps: list[StepTrace] = field(default_factory=list)
    terminal_state: str = ""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_latency_s: float = 0.0
    cost_usd: float = 0.0
    error: str | None = None

    def add_step(self, step: StepTrace):
        self.steps.append(step)
        self.total_input_tokens += step.input_tokens
        self.total_output_tokens += step.output_tokens
        self.total_latency_s += step.latency_ms / 1000

    def finalize(self, terminal_state: str):
        self.terminal_state = terminal_state
        self.total_latency_s = time.time() - self.start_time
        self.cost_usd = estimate_cost(self.total_input_tokens, self.total_output_tokens)

    def to_cloudwatch(self) -> list[dict]:
        """Format for CloudWatch PutMetricData."""
        dims = [{"Name": "AgentType", "Value": "research_agent"}]
        return [
            {"MetricName": "TaskSuccess", "Value": 1 if self.terminal_state == "success" else 0,
             "Unit": "Count", "Dimensions": dims},
            {"MetricName": "StepsPerTask", "Value": len(self.steps),
             "Unit": "Count", "Dimensions": dims},
            {"MetricName": "E2ELatency", "Value": self.total_latency_s * 1000,
             "Unit": "Milliseconds", "Dimensions": dims},
            {"MetricName": "CostPerTask", "Value": self.cost_usd,
             "Unit": "None", "Dimensions": dims},
            {"MetricName": "TotalTokens",
             "Value": self.total_input_tokens + self.total_output_tokens,
             "Unit": "Count", "Dimensions": dims},
        ]
```

---

## OpenTelemetry for Distributed Agent Tracing

When agents call subagents, each hop needs to be part of the same distributed trace:

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

tracer = trace.get_tracer("agent.tracer")

async def traced_agent_step(step_name: str, parent_ctx=None):
    """Wrap each agent step in an OpenTelemetry span."""
    with tracer.start_as_current_span(
        f"agent.step.{step_name}",
        context=parent_ctx,
        kind=trace.SpanKind.INTERNAL,
    ) as span:
        span.set_attribute("agent.step_name", step_name)
        start = time.perf_counter()
        try:
            result = await execute_step(step_name)
            span.set_attribute("agent.success", True)
            return result
        except Exception as e:
            span.record_exception(e)
            span.set_attribute("agent.success", False)
            raise
        finally:
            span.set_attribute("agent.duration_ms", (time.perf_counter() - start) * 1000)
```

---

## Domain-Specific Agent Eval Targets

| Agent Type | Primary Metric | Target | Secondary | Notes |
|-----------|---------------|--------|-----------|-------|
| **Research agent** | Factual accuracy (LLM-judge) | > 85% | Citation rate, steps taken | Measure on dated knowledge questions |
| **Code agent** | Pass@1 on test suite | > 75% | Format compliance | Execute in sandbox |
| **Customer support** | First-contact resolution rate | > 70% | Escalation rate, CSAT | Track vs human baseline |
| **Data analysis** | Analyst agreement rate | > 80% | Code correctness | Use analyst spot-checks |
| **DevOps agent** | MTTR (mean time to resolve) | < 15 min | False alarm rate | Measure on historical incidents |
| **Document processing** | Field extraction accuracy | > 97% | Schema validity | Per-field F1 |
| **Multi-agent orchestration** | End-to-end task success | > 75% | Worker utilization | Harder — measure compound |

---

## Alerting Policy for Production Agents

```yaml
# CloudWatch / Prometheus alerting rules

alerts:
  - name: AgentTaskSuccessRateLow
    condition: task_success_rate_1h < 0.65
    severity: critical
    action: pagerduty + slack
    message: "Agent task success rate dropped to {value:.1%} — investigate immediately"

  - name: AgentCostSpike
    condition: cost_per_task_1h > cost_per_task_24h_baseline * 2
    severity: warning
    action: slack
    message: "Agent cost per task 2× above 24h baseline: ${value:.3f}/task"

  - name: AgentMaxIterationsHigh
    condition: max_iteration_hit_rate_1h > 0.15
    severity: warning
    action: slack
    message: "15%+ of agent runs hitting iteration limit — tasks may be too complex or model is looping"

  - name: AgentToolErrorRateHigh
    condition: tool_error_rate_1h > 0.15
    severity: warning
    action: slack
    message: "Tool error rate {value:.1%} — check tool health: {top_failing_tools}"

  - name: AgentContextSaturation
    condition: context_saturation_rate_1h > 0.10
    severity: warning
    action: slack
    message: "10%+ of tasks hitting context limit — review task complexity or add summarization"

  - name: PromptInjectionDetected
    condition: prompt_injection_events_5m > 0
    severity: critical
    action: pagerduty
    message: "Prompt injection attempt detected in agent tool outputs"
```
