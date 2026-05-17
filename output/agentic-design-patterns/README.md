# Agentic Design Patterns

Principal-level interview prep notes on building production AI agents — patterns, tools, evaluation, and operational tradeoffs.

---

## Contents

| # | File | Words | Focus |
|---|------|-------|-------|
| 1 | [High Level Overview](1_High_Level_Overview.md) | 996 | What agents are, pattern taxonomy, compounding error math, when NOT to use agents |
| 2 | [Key Technical Concepts](2_Key_Technical_Concepts.md) | 2,348 | Tool-use loop, ReAct, Plan-Execute, Reflection, Multi-agent, Memory types, HITL, Prompt injection defense |
| 3 | [Products & Tools](3_Products_Tools.md) | 1,523 | LangGraph, CrewAI, AutoGen, MCP, Browser/code tools, LangSmith, Arize Phoenix |
| 4 | [Tradeoffs & Comparisons](4_Tradeoffs_Comparisons.md) | 1,307 | Pattern selection matrix, single vs multi-agent, framework comparison, termination policies |
| 5 | [Use Cases](5_Use_Cases.md) | 1,724 | Research synthesis, software engineering agent, customer support HITL, data analysis, document pipeline, DevOps agent |
| 6 | [Measurement & Evaluation](6_Measurement_Evaluation.md) | 1,273 | 3-level eval framework, LLM-judge trajectory eval, regression suite, observability checklist |
| 7 | [What to Measure & How](7_What_to_Measure_How.md) | 1,131 | Metrics tables (reliability/efficiency/latency/cost), CloudWatch/OTel instrumentation, alert rules |
| 8 | [Interview Questions](8_Interview_Questions.md) | 4,291 | 11 tiered Q&As (L5/L6/L7+) with model answers |

**Total: ~14,593 words**

---

## Key Themes

### 1. The Fundamental Principle: Minimal Viable Agent
Start with a single LLM call. Add prompt chaining if the task has sequential steps. Add tools if the task needs real-world access. Add an agent loop only when you need dynamic decision-making. Add multiple agents only when a single agent genuinely can't fit the task. **Each step adds failure surfaces.**

### 2. The Compounding Error Problem
If each step in an N-step agent succeeds with probability p, the full task succeeds with probability p^N. A 10-step agent at 95% per step = 60% overall. This isn't a reason to avoid agents — it's a reason to:
- Make individual steps highly reliable (clear tools, constrained actions, validation)
- Design checkpointing so failures don't restart from zero
- Keep N small by using powerful tools that compress multiple steps

### 3. Irreversibility is the Risk Axis
Categorize every tool by reversibility, not just capability. Read-only tools: always automate. Reversible write tools: automate with logging. Irreversible tools: require explicit human approval, dry-run first, maintain audit log. The pattern: gate on irreversibility, not on "is this AI-generated."

### 4. Memory Architecture Determines Scalability
Four memory types serve different purposes:
- **Working (in-context)**: Fast, zero-latency, lost on session end — current task state
- **Episodic (vector store)**: Cross-session retrieval by similarity — past experiences and examples
- **Semantic (knowledge base)**: Structured facts — domain knowledge that doesn't change per task
- **Procedural (system prompt)**: Always-present instructions — how to behave, not what to know

In-context memory pressure is the #1 practical challenge. Design token budgets from the start.

### 5. Human-in-the-Loop is a Feature, Not a Failure
Production agents should have well-defined escalation triggers. The LangGraph `interrupt()` primitive is the right abstraction: pause execution, surface context to the human, resume with their input. Set SLAs on human response times; if no response in N minutes, fall back gracefully (don't leave the customer waiting).

---

## Pattern Selection Quick Reference

| Situation | Pattern |
|-----------|---------|
| Single-turn question answering | Single LLM call |
| Extract fields, classify, summarize (fixed steps) | Prompt chaining |
| Different input types need different handling | Routing |
| N independent subtasks that can run at once | Parallelization (fan-out/fan-in) |
| Open-ended task requiring tool use with dynamic decisions | ReAct (single agent loop) |
| Complex multi-step task with known structure | Plan-Execute |
| Quality matters more than speed/cost (reports, code review) | Reflection (generate → critique → revise) |
| Task exceeds single-agent context or needs parallel workers | Multi-agent orchestration |
| Production action with real-world side effects | HITL at irreversible boundaries |

---

## Framework Decision Guide

| Use LangGraph when | Use raw Anthropic API when | Use CrewAI when |
|-------------------|---------------------------|-----------------|
| Production deployment | Single stable agent < 20 steps | Rapid prototyping |
| HITL / interrupt-resume required | No complex state | Role-based agent narrative |
| Complex state across multi-step graph | Full control desired | Demo / experiments |
| Checkpointing needed for long tasks | No external dependencies | Non-production |
| Multi-agent with shared state | Small team, simple system | |

---

## Critical Interview Distinctions

**Prompt chaining ≠ agent loop**: Chaining is fixed steps with no dynamic routing. An agent loop decides at runtime which tool to call next. Use chaining when the sequence is known; use an agent when it's not.

**ReAct ≠ Plan-Execute**: ReAct interleaves reasoning and acting on each step (emergent planning). Plan-Execute separates an upfront planning phase from execution (explicit planning). Plan-Execute is more predictable; ReAct is more flexible for novel situations.

**Multi-agent ≠ better**: Most tasks that seem to need multiple agents can be solved with one agent and better tools. Multi-agent introduces: N×failure surfaces at handoffs, harder observability (N traces to correlate), higher cost (orchestrator + all workers). Add agents when context window is genuinely insufficient, parallelization meaningfully reduces latency, or specialization requires different model choices.

**Evaluation at 3 levels**: Step-level (right tools, right arguments), trajectory-level (efficient path, low backtrack rate), outcome-level (correct answer, format compliance). A correct answer via a wrong trajectory is a signal of fragility, not reliability.

**Prompt injection defense**: Label all external data with XML tags (`<user_content>`, `<tool_result>`). Don't pass raw tool outputs directly as system-level instructions. Re-serialize structured data rather than string-interpolating it. Treat external content as data, never as instructions.
