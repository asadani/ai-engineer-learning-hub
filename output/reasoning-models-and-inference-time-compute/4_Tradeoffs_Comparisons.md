# Tradeoffs & Comparisons

## Reasoning Model vs Standard Model

| | Standard LLM | Reasoning model |
|---|---|---|
| Hard multi-step accuracy | Lower | Higher |
| Latency | Low | High (thinking) |
| Cost | Output tokens | Thinking + output tokens (often 5–50×) |
| Prompting | CoT scaffolding helps | Goal/constraints; *don't* hand-author CoT |
| Best for | Most tasks (extraction, chat, classification) | Math, code, science, planning, hard logic |

Default to standard; escalate to reasoning only where evals show the task needs it.

## RL (RLVR/GRPO) vs Distillation

| | RLVR on the model | Distill from a big reasoner |
|---|---|---|
| Capability ceiling | Highest (can exceed teacher) | ~teacher quality |
| Cost | High (RL compute) | ~1/10 GPU hours |
| Data need | Verifiable rewards / verifiers | Teacher traces |
| Use | Build a frontier reasoner | Deploy reasoning cheaply |

Practical rule: RL to *create* reasoning capability; distillation to *ship* it economically.

## More Test-Time Compute: Helps vs Hurts

| Regime | Effect |
|---|---|
| Too little thinking | Underperforms on hard problems |
| Right budget | Peak accuracy |
| Too much thinking | Overthinking: accuracy can *decline*, cost/latency balloon |

The test-time-compute paradox: the accuracy-vs-compute curve is humped, not monotone. Tune the budget per task class with evals.

## Opaque vs Visible Reasoning Trace

| | Opaque (o-series) | Visible (R1 `<think>`) |
|---|---|---|
| Debuggability | Low | High |
| Distillable | No (by design) | Yes |
| Safety of trace | Hidden (can't leak) | Can surface unsafe intermediate text |
| Token/context cost | Hidden but billed | In-context, must manage |

## Hosted vs Open Reasoning

| | Hosted (o-series/Gemini) | Open (R1 / distills) |
|---|---|---|
| Peak capability | Frontier | Strong, closing gap |
| Control / on-prem | No | Yes (MIT R1) |
| Cost control | Effort tiers, opaque | Full control; distill for cheap |
| Drift risk | Provider updates | You pin weights |

## Common Failure Modes

- **Reasoning model for simple tasks** — pure cost/latency waste, no quality gain.
- **Thinking budget left at max** — overthinking + runaway spend (the paradox ignored).
- **Hand-authoring CoT for reasoning models** — constrains/derails internal reasoning.
- **RL-from-scratch on a small model** when distillation is ~10× cheaper for similar quality.
- **No cost attribution on thinking tokens** — invisible budget blowup (see *LLM Observability*).
- **Benchmarking on contaminated sets** — inflated reasoning scores.
