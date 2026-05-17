# What to Measure & How

## Metrics Tables

### Quality
| Metric | Definition | Target |
|---|---|---|
| Held-out pass rate | suite passes / total | per task SLA |
| Format-compliance rate | schema-valid / outputs | ~100% (constrained) |
| Sensitivity spread | max−min pass across paraphrases | small (stable) |
| Abstain correctness | correct null/needs_human / should-abstain | high |
| Regression delta | new version − baseline on suite | ≥ 0 to ship |

### Safety
| Metric | Definition | Alert |
|---|---|---|
| Over-refusal rate | refused valid requests | rising |
| Injection-resistance | adversarial inputs handled safely | < target → block |
| Hallucination rate (grounded tasks) | unsupported claims / answers | > threshold |

### Cost / Latency
| Metric | Definition |
|---|---|
| Tokens / successful task | incl. few-shot + thinking tokens |
| Latency p95 / task | end-to-end |
| Cost delta vs prior version | $ per 1k tasks |

## Versioning & Governance

- Prompts live in **git or a prompt manager**, semver'd, code-reviewed.
- Each prompt version is bound to an **eval dataset + score**.
- **CI gate**: PR touching a prompt runs the suite; below-threshold blocks merge.
- **Rollback**: deploy by label/alias so a regressing prompt reverts instantly.
- Prompt changes are change-managed like code deploys (who/when/why logged).

## Instrumentation

Bind production traces to the prompt version using OTel GenAI conventions:

```python
with tracer.start_as_current_span("chat") as s:
    s.set_attribute("gen_ai.request.model", model)
    s.set_attribute("prompt.name", "extract_invoice")
    s.set_attribute("prompt.version", "v7")
    s.set_attribute("gen_ai.usage.input_tokens", usage.input)
    s.set_attribute("gen_ai.usage.output_tokens", usage.output)
    s.set_attribute("format.valid", schema_ok)   # for compliance metric
```

Sample production outputs into an offline judge job to track quality drift per prompt version.

## Alerting Rules (sketch)

- CI: suite score < threshold on a prompt PR → block.
- Prod: `format_valid_rate < 0.99` → warn (decoding/contract drift).
- Prod: `over_refusal` or `hallucination_rate` trending up after a prompt deploy → auto-rollback candidate.
- `tokens_per_successful_task` jump after a version change → cost regression review.

## Dashboard Checklist

- Pass rate + sensitivity spread per prompt version (release gate view).
- Format-compliance and abstain-correctness trends.
- Safety panel: over-refusal, injection resistance, hallucination.
- Cost/latency per successful task by prompt version.
- Prod-vs-eval quality gap (drift signal).
