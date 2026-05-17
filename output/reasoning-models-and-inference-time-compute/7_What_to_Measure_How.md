# What to Measure & How

## Metrics Tables

### Accuracy / Quality
| Metric | Definition | Note |
|---|---|---|
| Task accuracy | correct / total on fresh suite | vs standard-model baseline |
| Accuracy lift | reasoning − standard, same suite | must justify cost |
| Optimal thinking budget | tokens at accuracy-vs-compute knee | per task class |
| Overthinking rate | cases worsened by more thinking | should be low |
| Calibration | confidence vs correctness | drives routing/abstain |

### Cost / Latency
| Metric | Definition | Target |
|---|---|---|
| Thinking tokens / task | reasoning tokens generated | budgeted |
| Cost / successful task | $ incl. thinking | vs standard baseline |
| Blended cost (routed) | mix of standard+reasoning | ↓ vs all-reasoning |
| Latency p95 / TTFT | end-to-end incl. thinking | within SLO |

### Routing
| Metric | Definition |
|---|---|
| Escalation rate | % routed to reasoning model |
| Escalation precision | hard tasks correctly escalated |
| Cost saved vs all-reasoning | routing ROI |

## Instrumentation

Capture reasoning tokens explicitly (OTel GenAI conventions; see *LLM Observability*):

```python
with tracer.start_as_current_span("chat o-series") as s:
    s.set_attribute("gen_ai.request.model", model)
    s.set_attribute("gen_ai.request.reasoning_effort", effort)   # low|med|high
    s.set_attribute("gen_ai.usage.input_tokens", u.input)
    s.set_attribute("gen_ai.usage.output_tokens", u.output)
    s.set_attribute("gen_ai.usage.reasoning_tokens", u.reasoning) # the cost driver
    s.set_attribute("route.tier", "reasoning")                    # vs "standard"
    s.set_attribute("verifier.passed", verified)
```

Reasoning tokens are the budget line item — make them a first-class, alertable metric.

## Alerting Rules (sketch)

- `reasoning_tokens_per_task` ↑ vs baseline (no accuracy gain) → overthinking / budget regression → page owner.
- `cost_per_successful_task (reasoning)` > budget for 15m → warn; 2× → page.
- `escalation_rate` spikes → router miscalibrated or input mix shifted.
- New reasoning model version → re-run accuracy-vs-compute + contamination-fresh suite before ramp.
- `latency_p95 > SLO` on reasoning tier → cap thinking budget / shift routing.

## Dashboard Checklist

- Accuracy lift vs standard baseline, per task class.
- Accuracy-vs-thinking-token curve (the tuning artifact) with current operating budget marked.
- Thinking tokens & cost per successful task; blended routed cost vs all-reasoning.
- Escalation rate/precision and routing ROI.
- Overthinking incidents and calibration plot.
- Latency p95/TTFT on the reasoning tier.
