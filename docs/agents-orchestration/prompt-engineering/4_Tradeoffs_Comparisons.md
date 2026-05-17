# Tradeoffs & Comparisons

## Prompt vs RAG vs Fine-Tuning

| | Prompt engineering | RAG | Fine-tuning |
|---|---|---|---|
| Fixes | Ambiguity, format, behavior | Missing/changing knowledge | Style, format, latent skill |
| Cost | ~0 | Medium (infra) | High (training + ops) |
| Latency added | ~0 | Retrieval | ~0 after merge |
| Iteration speed | Minutes | Hours | Days |
| First choice? | **Yes** | When knowledge is the gap | When prompt+RAG measured insufficient |

Default ladder: exhaust evaluated prompting first; escalate only on measured failure.

## Zero-shot vs Few-shot

| | Zero-shot | Few-shot |
|---|---|---|
| Tokens | Low | Higher |
| Best for | Common tasks, capable models | Specific formats, conventions, edge cases |
| Risk | Under-specification | Bad/biased examples teach bad behavior; lost-in-the-middle |

Start zero-shot on 2026 models; add few-shot only where evals show a format/convention gap.

## Manual vs Programmatic Optimization (DSPy)

| | Manual | DSPy-style |
|---|---|---|
| Effort | Low upfront | Setup + metric + dataset |
| Ceiling | Human intuition | Metric-driven search |
| Reproducible | Weak | Strong |
| Use when | Low-stakes, fast | High-stakes, plateaued, must be defensible |

## Standard vs Reasoning-Model Prompting

| | Standard model | Reasoning model |
|---|---|---|
| CoT scaffolding | Helps | Often hurts (model reasons internally) |
| Prompt style | Steps + structure | Goal + constraints + output; minimal hand-holding |
| Few-shot reasoning | Useful | Can constrain/derail reasoning |
| Cost driver | Output tokens | Thinking tokens (budget them) |

Matching technique to model class is the most-tested 2026 nuance.

## Long Prompt vs Decomposition

A long do-everything prompt is cheap (one call) but flaky and hard to debug. Decomposition is reliable and localizable but adds calls/orchestration. Decompose when a single prompt fuses multiple tasks or when failures aren't attributable.

## Common Failure Modes

- **Playground-driven shipping** — no eval set, no regression test, no rollback.
- **Magic-phrase chasing** instead of removing ambiguity / decomposing.
- **Prose-parsing** instead of constrained output.
- **CoT on reasoning models** — degrades quality and burns thinking tokens.
- **Few-shot with unrepresentative examples** — teaches the wrong distribution.
- **Ignoring prompt sensitivity** — a prompt that passes once but is unstable across paraphrases/inputs.
