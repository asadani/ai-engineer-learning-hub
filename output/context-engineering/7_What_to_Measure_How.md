# What to Measure & How

## Metrics Tables

### Context Efficiency
| Metric | Definition | Target |
|---|---|---|
| Context precision | relevant tokens / total context tokens | ↑ (track trend) |
| Context recall | required facts present / required facts | > 0.95 |
| Tokens per successful task | input tokens / successful completions | ↓ |
| Compression ratio | tokens after / tokens before curation | report w/ quality |
| Quality delta @ compression | task success curated vs raw | ≈ 0 (no loss) |

### Long-Horizon (agents)
| Metric | Definition | Alert |
|---|---|---|
| Success @ turn N | success rate by turn bucket | sharp drop at high N |
| Compaction events / run | # auto-compactions | unexpected spike |
| Post-compaction regression | failures attributable to a compaction | > 1% |
| Window utilization p95 | peak context fill | sustained > 95% |

### Cost / Latency
| Metric | Definition |
|---|---|
| Input-token cost / task | $ on context |
| TTFT vs context size | latency sensitivity to prompt length |
| Retrieval+rerank+compress overhead | added latency of curation pipeline |

## Instrumentation

Use OTel **GenAI semantic conventions** so token accounting is portable:

```python
with tracer.start_as_current_span("chat gpt") as s:
    s.set_attribute("gen_ai.usage.input_tokens", usage.input)
    s.set_attribute("gen_ai.usage.output_tokens", usage.output)
    # custom breakdown of the context budget this turn
    s.set_attribute("ctx.tokens.instructions", n_instr)
    s.set_attribute("ctx.tokens.tools", n_tools)
    s.set_attribute("ctx.tokens.memory", n_mem)
    s.set_attribute("ctx.tokens.retrieved", n_ret)
    s.set_attribute("ctx.tokens.history", n_hist)
    s.set_attribute("ctx.compaction", did_compact)   # event flag
```

Emit a span event on each compaction with before/after token counts so post-compaction regressions are attributable.

## Alerting Rules (sketch)

- `window_utilization_p95 > 0.95` sustained → compaction not keeping up (warn).
- `post_compaction_regression > 1%` → compaction lossy; review summarizer (page on-call owner).
- `tokens_per_successful_task` trending up with flat quality → context bloat regression.
- `context_recall < 0.95` on golden set in CI → block deploy.

## Dashboard Checklist

- Per-turn context-budget breakdown (stacked: instructions/tools/memory/retrieved/history).
- Success-vs-turn curve for agent flows.
- Tokens-per-successful-task trend (the north-star efficiency metric).
- Compaction event timeline with before/after sizes and any regressions.
- Lost-in-the-middle position-accuracy chart (periodic offline job).
