# What to Measure & How

## Metrics Tables

### Security
| Metric | Definition | Target |
|---|---|---|
| Attack success / bypass rate | unsafe elicitations / adversarial attempts | as low as surface requires |
| ASR by category (OWASP) | bypass per LLM01…LLM10 | no category outlier |
| Blast radius | max capability reachable on success | read-only where possible |
| Jailbreak detection recall | flagged / known jailbreaks | high |

### Usability / Performance
| Metric | Definition | Alert |
|---|---|---|
| False-positive rate | legit requests blocked | > surface budget |
| Over-refusal rate | valid asks refused | rising trend |
| Guardrail latency p95 | added time per request | > UX budget |

### Operational Safety
| Metric | Definition | Alert |
|---|---|---|
| Unapproved irreversible actions | irreversible tool w/o HITL | any → page |
| Scope-violation count | calls outside granted scope | any |
| Cost/rate-limit breaches | token/wallet caps hit | spike (possible DoS) |
| PII/secret leak flags | sensitive output detections | any → page |

## Instrumentation

Attach safety signals to the same OTel traces used for observability:

```python
with tracer.start_as_current_span("chat") as s:
    s.set_attribute("safety.input_guard", in_verdict)      # allow|block|flag
    s.set_attribute("safety.output_guard", out_verdict)
    s.set_attribute("safety.injection_score", inj_score)
    s.set_attribute("safety.operating_point", "strict")     # per surface
    s.set_attribute("safety.irreversible_tool", is_irrev)
    s.set_attribute("safety.hitl_required", hitl)
    s.set_attribute("safety.hitl_approved", approved)
```

Log blocked requests (redacted) for red-team corpus growth and trend analysis.

## Alerting Rules (sketch)

- `unapproved_irreversible_actions > 0` → page immediately (containment failure).
- `pii_leak_flags > 0` or `system_prompt_leak` detected → page security.
- `attack_success_rate` ↑ vs baseline (any OWASP category) after a model/prompt/guardrail change → block/rollback.
- `false_positive_rate > surface_budget` sustained → review operating point (over-refusal hurting users).
- `cost/rate-limit breaches` spike → possible Unbounded-Consumption attack.

## Dashboard Checklist

- ASR overall and per OWASP category, trended by model/prompt/guardrail version.
- ASR–FPR–latency operating-point view per surface.
- Blast-radius / least-privilege coverage (which tools are irreversible + gated).
- HITL approvals and any unapproved irreversible attempts.
- PII/secret/system-prompt leak detections.
- Red-team CI status; cost/rate-limit breach timeline.
