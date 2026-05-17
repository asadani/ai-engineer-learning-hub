# Tradeoffs & Comparisons

## The Security–Usability–Latency Triangle

Every guardrail picks a point on this triangle; you cannot max all three.

| Guardrail (illustrative study) | Bypass rate | False-positive rate | Latency |
|---|---|---|---|
| **NeMo Guardrails** | ~0% | ~16.2% | >1.3 s |
| **Prompt Guard** (alone) | ~38.5% | ~3.6% | Low |

Reading: maximum security (NeMo) blocks nearly everything *including* many legitimate requests and adds latency — unusable for snappy consumer UX, appropriate for high-assurance/regulated flows. Light classifiers are fast and user-friendly but leak — only acceptable inside a deeper defense stack.

## Prevention vs Detection

| | Prevention (block) | Detection (monitor) |
|---|---|---|
| Effect | Stops the request | Catches it after, enables response |
| Cost | Latency + false positives | Storage + triage |
| Use | High-severity, irreversible | Everything (always-on) |

You need both: block the worst inline, detect-and-respond on the rest (red-team evals + online monitoring).

## Single Control vs Defense-in-Depth

A single guardrail has finite bypass; chaining independent layers multiplies the attacker's cost. OWASP explicitly frames any one mechanism as a layer, not a solution. Defense-in-depth is non-negotiable for agents.

## Strict vs Permissive Operating Point

| | Strict (low bypass) | Permissive (low FPR) |
|---|---|---|
| Risk posture | Safety-first | UX-first |
| Cost | Over-refusal, user friction, latency | Higher residual risk |
| Fit | Regulated, irreversible actions, minors | Low-stakes, reversible, internal |

Tune per surface — the same app may run strict on a payments tool and permissive on a search box.

## Build vs Buy Guardrails

Open models (Llama Guard, ShieldGemma, Granite Guardian) + NeMo/Guardrails AI cover most needs; building a bespoke classifier is justified only for a domain taxonomy nothing covers. Don't hand-roll; orchestrate proven components.

## Agent-Specific Trade: Autonomy vs Safety

More agent autonomy = more capability and more blast radius (Excessive Agency, LLM06). The lever is *least privilege + human-in-the-loop on irreversible actions*, not removing capability wholesale. Gate on irreversibility, not on "is this AI-generated."

## Common Failure Modes

- **Guardrail-as-silver-bullet** — one classifier, no other layers.
- **Trusting retrieved/tool/agent content** — indirect injection wide open.
- **Over-broad tool scope** — text exploit becomes data exfiltration / irreversible action.
- **Unsanitized model output downstream** — XSS/SQLi/RCE (Improper Output Handling).
- **No red-teaming in CI** — resistance assumed, never measured.
- **One operating point everywhere** — over-refusal on safe surfaces, under-protection on dangerous ones.
- **No cost/rate limits** — Unbounded Consumption (wallet-drain DoS).
