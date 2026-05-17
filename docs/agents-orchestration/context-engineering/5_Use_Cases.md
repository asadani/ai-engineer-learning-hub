# Use Cases & Real-World Applications

## 1. Long-Horizon Agent Loop

A DevOps agent runs 200+ tool-heavy turns. Strategy: structured **auto-compact** at ~95% window into a schema (goal, constraints, completed steps, artifacts, next action); **offload** large command outputs to files, keep only IDs/summaries in context; **isolate** risky sub-tasks in sub-agents that return distilled results. Outcome: the agent survives long horizons without drift or window exhaustion.

## 2. Coding Agent

A code agent must hold repo facts, the task, and recent edits. Strategy: retrieve only the files/symbols relevant to the current step (selection), keep a running summary of decisions, place the task statement and the active file at the *edges* of context (lost-in-the-middle), externalize the plan to a scratchpad file read selectively. Outcome: accurate edits without paging the whole repo into the window.

## 3. Support Assistant

Per ticket: fetch customer record + last N interactions (compacted) + top reranked KB passages + policy snippet, fenced with explicit tags. History older than the session is summarized; long-term preferences come from a memory store on demand. Outcome: grounded, policy-compliant answers at a fraction of naive token cost.

## 4. Document Workflow (contract review)

Large contracts exceed useful single-prompt recall. Strategy: structure-aware chunking with overlap, retrieve clause-relevant chunks per question, rerank to edges, compress boilerplate with LLMLingua, synthesize. Outcome: higher clause-level recall than dumping the full document into a long context.

## 5. Multi-Agent Research

An orchestrator spawns isolated researcher sub-agents; each works in its own context and returns a structured brief. The orchestrator's window holds only briefs + plan, never raw sub-agent transcripts. Outcome: bounded orchestrator context and reduced compounding error.

## 6. Personalized Assistant with Long-Term Memory

Durable user facts/preferences live in a long-term store; each session retrieves only the relevant subset into working context, and new salient facts are written back at session end. Outcome: continuity across sessions without carrying full history.

## Pattern Summary

| Need | Technique |
|---|---|
| Survive long agent runs | Structured compaction + offloading |
| Bound multi-agent growth | Context isolation / sub-agents |
| High recall on big docs | Chunking + rerank-to-edges |
| Cheap bulky context | Prompt compression |
| Cross-session continuity | Long-term memory + per-turn retrieval |
| Avoid injection/confusion | Typed, delimited context sections |
