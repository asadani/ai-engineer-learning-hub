# High-Level Overview

## What It Is

**Context engineering** is the practice of designing the *entire* set of tokens an LLM sees at inference time — instructions, tools, memory, retrieved knowledge, conversation history, and output format — so the model has exactly what it needs and nothing that distracts it. Andrej Karpathy popularized the framing: "the delicate art and science of filling the context window with just the right information."

It is distinct from **prompt engineering**: prompt engineering optimizes a single human-authored instruction; context engineering designs the *system* that assembles context dynamically, turn after turn, especially for agents and RAG.

## The Core Problem It Solves

In 2026 most production LLM failures are not the model being incapable — they are the model being given the wrong context: missing the key fact, burying it among irrelevant retrieved chunks, or exhausting the window mid-task. Three structural pressures:

1. **Context windows stopped growing exponentially.** Window sizes are roughly plateauing; you can no longer "just use a bigger window." The lever shifted to *selection, compression, and placement*.
2. **More tokens can hurt.** Irrelevant or low-signal context measurably degrades output quality and raises cost and latency. Bigger ≠ better.
3. **Agents accumulate context.** Multi-turn, tool-using agents can span hundreds of turns with token-heavy tool results; without active management they hit the window ceiling and fail or drift.

## The Context Budget

Think of the window as a fixed budget allocated across competing claimants:

```
[ system / instructions ] [ tool definitions ] [ long-term memory ]
[ retrieved knowledge ] [ recent history (compacted) ] [ user turn ] → [ output ]
```

Every token in one bucket is a token unavailable to another. Context engineering is the discipline of allocating that budget deliberately and re-deriving the allocation every turn.

## The Four Levers (mental model)

1. **Select** — retrieve/choose only what this turn needs (dynamic, task-aware).
2. **Compress** — summarize/compact history and bulky tool output; prompt compression (e.g., LLMLingua).
3. **Place** — exploit the U-shaped recall curve: most critical content at the start/end, not buried in the middle.
4. **Structure** — clear delimiters and typed sections (XML/JSON tags, markdown) so the model can parse instructions vs memory vs data.

## Where It Sits

Context engineering wraps and subsumes prompt engineering and RAG. RAG is "select"; prompt engineering is part of "structure/instructions"; memory systems feed "select/compress." In agentic systems it is the layer that decides, every step, what the next model call sees — arguably the highest-leverage layer in the 2026 stack.

## Why It's a Named Discipline Now

The shift from single-shot prompting to long-running agents made ad-hoc context handling untenable. Teams that treat context as a designed, measured budget ship reliable agents; teams that don't ship agents that work in demos and fail at turn 50.
