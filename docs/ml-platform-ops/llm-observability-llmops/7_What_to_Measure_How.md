# What to Measure & How

## Metrics Tables

### Quality (online)
| Metric | Definition | Alert |
|---|---|---|
| Online judge score | sampled rubric mean | drop vs baseline |
| User-feedback rate | 👍/👎, edits, retries | 👎/retry rising |
| Hallucination/groundedness | unsupported claims (RAG) | > threshold |
| Refusal / over-refusal | refused / wrongly-refused | spike |
| Schema-valid rate | parseable outputs | < 0.99 |

### Cost / Efficiency
| Metric | Definition | Target |
|---|---|---|
| Cost / request (by feature) | $ tokens incl. thinking | budgeted |
| Tokens / successful task | input+output per success | ↓ trend |
| Cost by prompt.version | spend per version | no silent jump |
| Cache hit rate | prompt-cache hits | per design |

### Latency / Reliability
| Metric | Definition | Alert |
|---|---|---|
| Request p95 / p99 | end-to-end | > SLO |
| TTFT (streaming) | time to first token | > SLO |
| Tool-call success | non-error / calls | < 0.98 |
| Error-trace rate | failed traces / total | spike |

## Instrumentation (OTel GenAI)

```python
from opentelemetry import trace
tracer = trace.get_tracer("llm-app")

with tracer.start_as_current_span("chat") as s:
    s.set_attribute("gen_ai.operation.name", "chat")
    s.set_attribute("gen_ai.request.model", model)
    s.set_attribute("session.id", session_id)
    s.set_attribute("feature", "support_reply")
    s.set_attribute("prompt.name", "reply_v7")
    s.set_attribute("prompt.version", "v7")
    resp = call_model(...)
    s.set_attribute("gen_ai.usage.input_tokens", resp.usage.input)
    s.set_attribute("gen_ai.usage.output_tokens", resp.usage.output)
    s.set_attribute("gen_ai.response.finish_reasons", resp.finish)
    # attach online-eval scores as they arrive
    s.set_attribute("eval.schema_valid", schema_ok)
```

Set `OTEL_SEMCONV_STABILITY_OPT_IN` to dual-emit legacy + new attribute names during the experimental→stable migration. Redact PII before export.

## Alerting Rules (sketch)

- `online_judge_score` ↓ > X% vs 7-day baseline (segmented by prompt.version) → page owner.
- `cost_per_request` by feature > budget for 15m → warn; 2× → page.
- `request_p95 > SLO` 5m → page; `tool_call_success < 0.98` → warn.
- New `gen_ai.request.model` value observed (provider drift) → notify.
- `schema_valid_rate < 0.99` after a deploy → rollback candidate.

## Dashboard Checklist

- Trace explorer: session → spans, filter by feature/prompt.version/model.
- Quality: online judge + user feedback trend, segmented by version.
- Cost: spend by feature/user/prompt.version/model; tokens-per-success.
- Latency/reliability: p95/p99, TTFT, tool success, error-trace rate.
- Safety: refusal, PII-leak, toxicity flags.
- Drift: quality/cost/behavior keyed to model & prompt version.
