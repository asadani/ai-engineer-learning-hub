# Key Technical Concepts

## Lost-in-the-Middle

LLM retrieval accuracy over long context follows a **U-shaped curve**: information at the *beginning* and *end* of the window is recalled well; information in the *middle* is often missed, even within nominal context limits. Engineering implications: rank retrieved chunks so the most relevant sit at the edges; put critical instructions at the top and restate the decisive constraint near the end; never assume "it's in context" equals "the model used it."

## Compaction & Summarization

When history grows, you must shrink it without losing decisions:

- **Recursive/rolling summarization** — periodically replace old turns with a condensed summary of key facts, decisions, and open threads.
- **Auto-compact** — agent runtimes (e.g., Claude Code) trigger compaction when the window crosses a threshold (~95%), summarizing the full trajectory so the agent can continue.
- **Structured compaction** — summarize into a schema (goal, constraints, decisions, artifacts, next step) rather than prose, so nothing load-bearing is lost.

Compaction beats naive truncation because truncation drops the *oldest* tokens, which often contain the goal and constraints.

## Prompt Compression

Token-level compression (e.g., **LLMLingua / LongLLMLingua**) removes low-information tokens from prompts/context using a small model, preserving meaning while cutting tokens — useful for bulky retrieved passages and few-shot blocks. Tradeoff: compute + a small fidelity risk; measure task quality before/after.

## Retrieval as Context (the "Context Engine")

RAG in 2026 is less "embed + top-k" and more a **context engine**: hybrid retrieval (vector + keyword), metadata filtering, structure-aware chunking with overlap, query expansion, **reranking**, and summarization of retrieved sets before insertion. Smart chunking is one of the highest-ROI changes available. The goal is high *context precision*: relevant tokens up, irrelevant tokens out.

## Memory Tiers

| Tier | Holds | Mechanism | Lifetime |
|---|---|---|---|
| Working (in-context) | current task state | the window itself | the turn/session |
| Short-term | recent turns, condensed | rolling summary | session |
| Long-term | durable facts, preferences, artifacts | vector/DB store, retrieved on demand | cross-session |

Context engineering decides *what gets promoted/demoted between tiers and what is retrieved back in* each turn.

## Context Isolation (sub-agents / scratchpads)

Give sub-tasks their own context so the parent window isn't polluted: a sub-agent works in an isolated context and returns only a distilled result; scratchpad/notes externalize intermediate work to a file/tool and read back only what's needed. This bounds context growth and the compounding-error problem.

## Context Offloading

Move bulky state out of the window and reference it: write large tool outputs to a store and pass an ID/summary; keep the plan in an external artifact the agent reads selectively. The window holds pointers and summaries, not raw payloads.

## Structure & Delimiters

Models parse better when context is typed and delimited: separate `instructions`, `tools`, `memory`, `retrieved`, `history`, `user` with explicit tags (XML/JSON/markdown). Clear structure reduces instruction/data confusion and is also a prompt-injection mitigation (data is fenced, not interpreted as instructions).

## The Quantified Win

Well-engineered context-aware systems report retaining ~90%+ of critical information while cutting context size by roughly two-thirds — directly improving quality, latency, and cost simultaneously.
