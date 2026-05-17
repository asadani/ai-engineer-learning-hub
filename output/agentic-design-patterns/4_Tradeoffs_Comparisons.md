# Tradeoffs & Comparisons

## Pattern Selection Matrix

| Pattern | Latency | Cost | Reliability | Complexity | Best When |
|---------|---------|------|------------|------------|-----------|
| **Single LLM call** | Lowest | Lowest | Highest | Lowest | Task fits in one prompt |
| **Prompt chaining** | Low | Low | High | Low | Sequential, predictable steps |
| **Routing** | Low | Low | High | Low | Multiple distinct input types |
| **Parallelization** | Low (wall clock) | Medium | High | Medium | Independent subtasks |
| **ReAct (single agent)** | Variable | Medium | Medium | Medium | Open-ended tool-using tasks |
| **Plan-Execute** | Higher | Higher | Medium-High | Medium | Complex multi-step tasks |
| **Reflection** | 2–3× higher | 2–3× higher | Higher quality | Low | Quality-sensitive generation |
| **Multi-agent orchestration** | Highest | Highest | Variable | High | Tasks exceeding single-agent scope |

**Design philosophy**: Start at the top of this table. Add complexity only when simpler patterns demonstrably fail.

---

## Single Agent vs Multi-Agent

| Dimension | Single Agent | Multi-Agent |
|-----------|-------------|-------------|
| **Coordination overhead** | None | High (orchestrator calls, message passing) |
| **Context window pressure** | High (all state in one window) | Lower per agent (distributed context) |
| **Task specialization** | One model does everything | Specialist models per subtask |
| **Failure isolation** | All-or-nothing | One subagent fails, others continue |
| **Observability** | One trace | N traces to correlate |
| **Latency** | Sequential tool calls | Parallel subagents possible |
| **Cost** | Lower (fewer LLM calls) | Higher (orchestrator + N workers) |
| **Testing** | Test one system | Test each agent + integration |
| **When to use** | Tasks completable in < 20 tool calls with < 8k context | Long-horizon tasks, specialized expertise needed, parallel work |

**The multi-agent overhype trap**: Most tasks that seem to require multi-agent systems can be solved with a single well-prompted agent with good tools. Multi-agent introduces failure surfaces at every agent handoff. Add agents when:
1. The context window for a single agent is genuinely insufficient
2. Parallel execution meaningfully reduces latency (and the subtasks are truly independent)
3. Specialization genuinely requires different system prompts/model choices (e.g., a reasoning model plans, a fast model executes)

---

## LangGraph vs CrewAI vs AutoGen vs Raw API

| Dimension | LangGraph | CrewAI | AutoGen | Raw API |
|-----------|-----------|--------|---------|---------|
| **Control level** | Fine-grained (graph nodes/edges) | Medium (roles/tasks) | Medium (conversation protocol) | Full |
| **Learning curve** | Medium | Low | Medium | Low |
| **State management** | Explicit, typed | Implicit | Conversation history | Manual |
| **Checkpointing** | Built-in | Limited | Limited | Manual |
| **Streaming** | Built-in | Limited | Limited | Built-in |
| **HITL support** | First-class (interrupt/resume) | Limited | `human_input_mode` | Manual |
| **Debugging** | LangSmith integration, graph visualization | Limited | Chat history | Manual |
| **Production maturity** | High | Medium | Medium | Highest |
| **Best for** | Production systems, complex state, HITL | Multi-role prototyping, quick experiments | Conversational multi-agent | Maximum control, small systems |

**My production recommendation**: LangGraph for anything that goes to production. Raw API + custom orchestration for small, stable single-agent systems. CrewAI for rapid prototyping. AutoGen for research/exploration.

---

## Synchronous vs Asynchronous Agent Execution

| Model | Latency | Resource Use | Error Handling | Use Case |
|-------|---------|-------------|----------------|----------|
| **Synchronous** | Blocks user | Low (one at a time) | Simple (throw/catch) | Short tasks, interactive |
| **Async (asyncio)** | Non-blocking | Concurrent (same process) | Requires gather/shield | Parallel subagents, I/O-bound |
| **Message queue (SQS/Celery)** | Background | Scalable (N workers) | Retry, DLQ | Long-running, batch |
| **Streaming (SSE/WebSocket)** | Immediate first token | Low | Client reconnect | Interactive streaming UX |

**When to use each:**
- User is waiting and task < 30s → synchronous + streaming
- Task > 30s → background job + polling/webhook
- Multiple subagents → async gather with semaphore
- 1M+ tasks → queue-based worker pool

---

## Tool Choice: Breadth vs Depth

**Broad tool set** (many tools, each narrowly scoped):
- `search_news`, `search_academic`, `search_products`, `search_code` (vs. one `search` tool)
- Pros: LLM selects more precisely, less likely to use wrong search type
- Cons: Long tool definitions consume context; LLM may be confused by too many similar tools
- Use when: tasks are domain-specific and tool selection matters

**Narrow tool set** (few tools, each broadly capable):
- One `search(query, type=news|academic|product)` tool
- Pros: Shorter system prompt, less choice paralysis, easier maintenance
- Cons: LLM must know the `type` parameter; harder to validate correct usage
- Use when: tools are clearly distinct and model reliably understands parameters

**Rule of thumb**: 3–7 tools is optimal for most single agents. Beyond 10 tools, the model's tool selection accuracy noticeably degrades unless the tools are very clearly differentiated.

---

## Memory Tradeoffs

| Memory Type | Scope | Persistence | Retrieval | Cost | Use Case |
|-------------|-------|-------------|-----------|------|----------|
| **In-context (working)** | Current session | None (lost on end) | Immediate | Token cost | Current task state |
| **Summarized context** | Current session | None | Immediate (compressed) | Summarization cost | Long sessions |
| **Episodic (vector store)** | Cross-session | Permanent | Semantic similarity | Storage + retrieval | Past experiences |
| **Semantic (knowledge)** | Cross-session | Permanent | Semantic similarity | Storage + retrieval | Facts and knowledge |
| **External (database)** | Cross-session | Permanent | Exact/structured query | DB query cost | Structured records |
| **Procedural (system prompt)** | Always | Permanent | Always present | System prompt tokens | How to do things |

**Context window pressure is the #1 practical challenge in production agents.** Every tool result, every reasoning trace, every prior exchange consumes tokens. Design for token efficiency from the start: truncate tool outputs, summarize old history, use semantic memory for long-running tasks.

---

## Streaming vs Batch for Agent Outputs

**Streaming (SSE/WebSocket):**
- User sees reasoning traces and partial outputs in real time
- Reduces perceived latency (user can read early output while agent continues)
- Enables early interruption (user sees wrong direction and stops it)
- Required for interactive products (chatbots, co-pilots)
- Complexity: client must handle partial/chunked responses; error recovery is harder

**Batch:**
- Simpler: just wait for completion and return the result
- Better for pipeline integration (downstream system expects complete output)
- Easier error handling and retry logic
- Appropriate for: API integrations, batch processing, non-interactive workflows

**In LangGraph**: `app.stream()` for streaming, `app.invoke()` for batch. Both use the same graph; just different consumption patterns.

---

## Termination Conditions: Safety vs Progress

Agent loops must have robust termination logic. The three termination signals:

**1. Successful completion**: The model explicitly signals it's done (via `end_turn` stop reason or a final-answer pattern in the response).

**2. Max iterations / budget exceeded**: Hard safety limit. Never trust the model alone to decide when to stop — a confused model will loop forever.

**3. Tool failure threshold**: If N consecutive tool calls fail, abort the loop. A model that keeps retrying a broken tool will waste money without progress.

```python
class TerminationPolicy:
    def __init__(self, max_iterations=20, max_tokens=50_000, max_consecutive_errors=3):
        self.max_iterations = max_iterations
        self.max_tokens = max_tokens
        self.max_consecutive_errors = max_consecutive_errors
        self.iterations = 0
        self.total_tokens = 0
        self.consecutive_errors = 0

    def check(self, step_result: StepResult) -> tuple[bool, str]:
        self.iterations += 1
        self.total_tokens += step_result.tokens_used
        self.consecutive_errors = 0 if step_result.success else self.consecutive_errors + 1

        if self.iterations >= self.max_iterations:
            return True, f"Max iterations ({self.max_iterations}) reached"
        if self.total_tokens >= self.max_tokens:
            return True, f"Token budget ({self.max_tokens:,}) exhausted"
        if self.consecutive_errors >= self.max_consecutive_errors:
            return True, f"Too many consecutive errors ({self.consecutive_errors})"
        return False, ""
```
