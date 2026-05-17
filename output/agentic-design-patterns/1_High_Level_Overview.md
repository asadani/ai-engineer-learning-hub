# Agentic Design Patterns — High-Level Overview

## What "Agentic" Means

An **agent** is a system where an LLM drives a control flow loop: it observes state, reasons about it, selects an action, executes that action (via tool calls), observes the result, and iterates until it reaches a terminal state or hands off to a human. The defining property is **autonomy** — the model decides what to do next, not a hard-coded script.

The shift from "LLM call" to "agentic system" is a shift from:
```
Input → Single LLM call → Output
```
to:
```
Goal → [Observe → Reason → Act → Observe → ...]* → Result
```

This loop is what makes agents powerful for complex, multi-step tasks — and what makes them hard to reason about, test, and operate in production.

---

## The Agentic Capability Stack

```
┌──────────────────────────────────────────────────────────┐
│                   Multi-Agent Systems                     │
│    Orchestrator ↔ Subagents ↔ Specialists                 │
├──────────────────────────────────────────────────────────┤
│                  Single-Agent Patterns                    │
│    ReAct • Plan-Execute • Reflection • Self-Correction    │
├──────────────────────────────────────────────────────────┤
│                   Core Capabilities                       │
│    Tool Use • Memory • Context Management • Handoff       │
├──────────────────────────────────────────────────────────┤
│                   Foundation                              │
│    LLM with strong instruction following + function call  │
└──────────────────────────────────────────────────────────┘
```

Each layer adds capability and complexity. Most production systems should use the minimum layer needed to accomplish the task. The temptation to build multi-agent systems when single-agent systems suffice is the #1 source of accidental complexity in the field.

---

## The Core Patterns Taxonomy

| Pattern | What It Is | Best For |
|---------|-----------|---------|
| **Prompt chaining** | Sequential LLM calls, output of one feeds next | Multi-step transformation with predictable steps |
| **Routing** | LLM classifies input → dispatches to specialist | Many input types, different handling per type |
| **Parallelization** | Fan-out: multiple LLM calls run concurrently | Independent sub-tasks with combinable results |
| **ReAct** | Reason → Act → Observe loop (single agent) | Open-ended tasks requiring tool use |
| **Plan-then-Execute** | Agent plans all steps first, then executes | Complex tasks where planning improves quality |
| **Reflection** | Agent critiques and revises its own output | Quality-sensitive tasks; self-improvement loops |
| **Tool use / function calling** | LLM invokes external APIs, functions, DBs | Any task requiring external information or actions |
| **Multi-agent orchestration** | Orchestrator delegates to specialist subagents | Tasks too complex or broad for one agent |
| **Human-in-the-loop** | Agent pauses, asks human for clarification/approval | High-stakes actions, ambiguous inputs |

---

## Why Agents Are Hard to Build Right

### The Compounding Error Problem

In a 5-step agent loop where each step is 90% reliable:
```
P(all 5 steps correct) = 0.90^5 = 0.59
P(all 10 steps correct) = 0.90^10 = 0.35
P(all 20 steps correct) = 0.90^20 = 0.12
```

This means reliability degrades rapidly with task length. A 90% per-step accuracy that looks fine in isolation becomes a 12% end-to-end success rate over a 20-step task. Designing agents for production means obsessing over per-step reliability, adding checkpointing, and building graceful degradation.

### Emergent Failure Modes Specific to Agents

- **Sycophancy in tool choice**: The agent selects tools that confirm its initial hypothesis rather than tools that might falsify it
- **Hallucinated tool calls**: Agent invokes a tool with plausible-but-wrong arguments, the tool fails silently, and the agent continues with incorrect state
- **Unrecoverable state**: Agent takes an irreversible action (send email, delete file, charge card) mid-loop before validating the decision
- **Context window saturation**: Long loops accumulate observations until the context window fills, causing earlier context to be lost and earlier decisions to be forgotten
- **Goal drift**: Over many steps, the agent's interpretation of the original goal drifts, optimizing for a subtly different objective
- **Prompt injection**: Tool outputs (web pages, database results, emails) contain adversarial instructions that hijack the agent's next action

### The Fundamental Production Tension

More capable agents (longer loops, more tools, more autonomy) require more careful failure handling, better observability, tighter permission boundaries, and more expensive per-step costs. The right design is the minimum autonomy needed to accomplish the task reliably, not the maximum autonomy the technology enables.

---

## Five Design Principles for Production Agents

**1. Prefer determinism over autonomy where possible.** Use agentic autonomy only for the parts of the workflow that genuinely require it. Hardcode the parts you can.

**2. Build checkpoints before irreversible actions.** Before the agent takes any action that can't be undone (send, delete, write, charge), either verify with a human or assert preconditions in code.

**3. Scope tools to the minimum necessary.** An agent with read-only tools cannot accidentally corrupt state. An agent with filesystem access should not also have internet access unless required. Defense in depth.

**4. Make the loop observable.** Every agent step should produce structured logs: what the agent was thinking (reasoning trace), what tool it called, what the tool returned, what decision it made next. You cannot debug what you cannot observe.

**5. Design for interruption and resumability.** Long-running agents will fail mid-run. Design state management so any run can be resumed from the last checkpointed step rather than restarted from scratch.

---

## When NOT to Use an Agent

An agentic system is the wrong tool when:
- **The task has a known, fixed structure**: If you can enumerate all the steps in advance, use a pipeline, not an agent. Determinism is more valuable than flexibility for fixed-structure tasks.
- **The task is a single LLM call with a long prompt**: Many "agentic" use cases reduce to well-engineered prompts. Don't add agent infrastructure to dress up a single call.
- **Latency is critical and predictable**: Agents have variable latency (unknown number of steps). If you need p99 latency < 1s, an agent is almost certainly the wrong architecture.
- **Cost needs to be bounded tightly**: Agent loops can make unexpected numbers of LLM calls. If per-request cost must be bounded, prefer a pipeline with a known number of calls.
