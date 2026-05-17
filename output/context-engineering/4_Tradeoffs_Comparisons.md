# Tradeoffs & Comparisons

## More Context vs Better Context

| | Stuff the window | Curate the window |
|---|---|---|
| Quality | Degrades with irrelevant tokens; lost-in-the-middle | Higher; signal concentrated |
| Cost / latency | High (linear+ in tokens) | Lower |
| Eng effort | Low | Higher (retrieval, rerank, compaction) |
| 2026 verdict | Anti-pattern | Default |

A bigger context window is a capacity, not a strategy.

## Compaction vs Truncation

| | Truncation | Compaction (summary) |
|---|---|---|
| Mechanism | Drop oldest tokens | Summarize old turns into key facts/decisions |
| Risk | Loses goal/constraints (often oldest) | Summary may omit a detail |
| Cost | ~free | Extra model call |
| Use | Cheap, low-stakes, short tasks | Long agent loops, multi-turn |

Prefer structured compaction for anything stateful; truncate only when history is genuinely disposable.

## RAG vs Long-Context (put it all in the prompt)

| | RAG / selective context | Long-context dump |
|---|---|---|
| Token cost | Low | High |
| Recall of buried facts | Higher (relevant chunks at edges) | Lower (lost-in-the-middle) |
| Freshness | Index updates instantly | Re-send every call |
| Best when | Large/changing corpus | Small, must-see-all corpus |

Long-context is a convenience for small fixed inputs; it is not a substitute for retrieval at scale.

## Memory Designs

| Design | Pro | Con |
|---|---|---|
| Full history | Nothing lost | Explodes; lost-in-the-middle; costly |
| Rolling summary | Bounded, cheap | Lossy; summary drift |
| Summary + retrieval of raw on demand | Bounded *and* recoverable detail | More moving parts |
| Sub-agent isolation | Bounds growth + error | Coordination overhead |

The summary-plus-retrieval hybrid is the principal-level default for long-running agents.

## Prompt Compression: When It Pays

Pays when bulky, low-entropy context dominates tokens (long docs, verbose few-shots). Doesn't pay for short, information-dense prompts (compression overhead/fidelity risk exceeds savings). Always A/B task quality, not just token count.

## Common Failure Modes

- **Context stuffing** — dumping everything "just in case"; quality and cost both suffer.
- **Truncating the goal** — oldest-first truncation discards the objective set early in the session.
- **Middle burial** — decisive instruction placed mid-context and ignored.
- **Unbounded agent history** — no compaction → window exhaustion at scale.
- **Untyped context** — instructions and data unfenced → confusion and injection exposure.
- **Optimizing tokens, not task success** — compressing until quality silently drops.
