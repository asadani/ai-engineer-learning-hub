# Tradeoffs & Comparisons

## OTel-Native vs Proprietary Tracing

| | OTel GenAI conventions | Proprietary SDK |
|---|---|---|
| Lock-in | Low (swap backends) | High |
| Backend choice | Any compliant (Langfuse/Phoenix/Datadog/…) | One vendor |
| Maturity | client spans stable; agent spans experimental | Vendor-mature, vendor-specific |
| 2026 default | ✅ instrument once to the standard | Only for a vendor-unique feature |

## Online vs Offline Evaluation

| | Offline | Online |
|---|---|---|
| When | Pre-deploy gate | Continuous in prod |
| Strength | Reproducible, labeled | Catches real-world + provider drift |
| Weakness | Misses unseen distribution | No ground truth; judge bias |
| Verdict | Need **both** | Need **both** |

Offline gates change; online catches what the golden set and provider updates didn't.

## Sampling vs Full Capture

| | Full capture | Sampled |
|---|---|---|
| Cost / storage | High | Controlled |
| Debuggability | Every trace available | May miss the one you need |
| Practice | Capture all *metadata*; sample *full I/O* and *judge evals*; always keep error traces | |

Tail-based sampling (keep slow/errored/flagged traces) is the principal-level default.

## LLM-as-Judge vs Human vs Heuristic (online)

| | LLM-judge | Human review | Heuristic/guardrail |
|---|---|---|---|
| Scale | High | Low | High |
| Cost | Low | High | Lowest |
| Bias/limits | Position/verbosity bias; needs calibration | Gold but slow | Shallow (schema, regex, classifier) |
| Use | Bulk online scoring | Calibration + audits | Cheap always-on checks |

Layer all three: heuristics always-on, LLM-judge on a sample, humans to calibrate the judge.

## Build vs Buy

| | Build in-house | Buy/adopt OSS or SaaS |
|---|---|---|
| Time | Slow | Fast |
| OTel compliance | You own it | Provided |
| When | Truly unique needs | Almost always (Langfuse/Phoenix are OSS) |

## Common Failure Modes

- **APM-only** — HTTP 200 hides confident-wrong answers; no trace = no root cause.
- **Vendor SDK lock-in** — re-instrumentation cost when you outgrow it; avoid by using OTel.
- **No cost attribution** — can't find the feature/prompt burning budget.
- **No online eval** — quality regressions and provider model shifts go unnoticed (no label to alert on).
- **PII in traces** — redaction retrofitted post-incident.
- **Agent spans assumed stable** — they're experimental; use the stability opt-in for safe migration.
