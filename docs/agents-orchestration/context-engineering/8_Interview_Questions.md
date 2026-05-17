# Interview Questions & Scenarios

## L5 — Foundations

**Q1. Context engineering vs prompt engineering?**
Prompt engineering optimizes a single human-authored instruction. Context engineering designs the *whole system* that assembles everything the model sees each turn — instructions, tools, memory, retrieved data, compacted history, output format — dynamically, especially for agents and RAG. Prompt engineering is a subcomponent of context engineering.

**Q2. What is lost-in-the-middle and how do you engineer around it?**
LLM recall over long context is U-shaped: strong at the start/end, weak in the middle. Engineer around it by reranking retrieved chunks so the most relevant sit at the edges, placing critical instructions at the top and restating the decisive constraint near the end, and never assuming presence in context implies use — verify with position-sweep evals.

**Q3. Why doesn't a bigger context window solve the problem?**
Windows are roughly plateauing in 2026, and irrelevant tokens actively degrade quality while raising cost and latency. Capacity isn't strategy; the lever is selection, compression, and placement within whatever window you have.

## L6 — Design & Tradeoffs

**Q4. Design context management for an agent that runs 200 turns of tool calls.**
Treat the window as a budget. Structured auto-compaction at ~95% utilization into a schema (goal, constraints, decisions, artifacts, next step) so truncation never drops the objective; offload bulky tool outputs to a store and keep IDs/summaries; isolate risky sub-tasks in sub-agents returning distilled results; keep task statement + active artifact at context edges. Measure success-vs-turn and post-compaction regression.

**Q5. Compaction vs truncation — when each, and what's the failure mode of truncation?**
Truncation drops oldest tokens — cheap but typically discards the goal/constraints set early in the session, the classic failure. Compaction summarizes old turns into key facts/decisions — costs a model call but preserves intent. Use structured compaction for any stateful/long task; truncate only genuinely disposable history.

**Q6. RAG vs long-context for a 300-page manual the agent must reference.**
Retrieval: chunk structure-aware with overlap, retrieve per-question, rerank relevant chunks to the edges. Long-context dump costs more per call and suffers lost-in-the-middle on a document that size. Long-context is fine only for small, must-see-all inputs; at this scale, selective retrieval wins on recall and cost.

## L7+ — Principal

**Q7. Your agent demos perfectly but fails in production at long sessions. Diagnose.**
Almost certainly a context failure, not a model failure. Check window utilization over turns (exhaustion), whether truncation is dropping the goal, lost-in-the-middle burying the active instruction, and post-compaction regressions. Instrument a per-turn context-budget breakdown and a success-vs-turn curve; the inflection point localizes the cause. Fix with structured compaction + isolation + edge placement, then re-measure tokens-per-successful-task.

**Q8. How do you prove a context change is an improvement, not just fewer tokens?**
Token reduction alone is meaningless. A/B the strategy on a golden suite measuring *task success and tokens together*; require quality-delta ≈ 0 at the lower token budget. Add a lost-in-the-middle position sweep and long-run stability simulation. Gate deploys on context-recall in CI. The north-star metric is tokens-per-successful-task, not raw context size.

**Q9. Where does context engineering sit relative to RAG, memory, and prompt engineering — and why is it the high-leverage layer in 2026?**
It subsumes them: RAG is the "select" lever, memory feeds "select/compress," prompt engineering is part of "structure/instructions." In agentic systems it decides, every step, what the next call sees — so it gates quality, cost, latency, and long-horizon reliability simultaneously. Teams that treat context as a measured budget ship reliable agents; teams that don't ship demo-ware.

## Rapid-Fire

- *Karpathy's one-liner?* Filling the context window with just the right information.
- *U-shaped curve implication?* Critical content at the edges, not the middle.
- *Cheapest big win in RAG context?* Smart, structure-aware chunking.
- *Truncation's classic bug?* Dropping the goal (oldest tokens).
- *North-star metric?* Task success per token.
