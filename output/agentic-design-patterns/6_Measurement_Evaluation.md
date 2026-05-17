# Measurement & Evaluation

## Why Evaluating Agents Is Hard

Standard LLM evaluation (single prompt → single output → compare to reference) doesn't apply to agents:
- Agent outputs are stochastic **and** path-dependent (same goal, different sequence of tool calls, different result)
- No single ground truth — the "correct" research trajectory for a question might have multiple valid paths
- Failure can happen at any step in a long chain, and compound in non-obvious ways
- The end result may be correct even when the intermediate steps were wrong (lucky path)

---

## Evaluation Framework: Three Levels

### Level 1: Step-Level Evaluation (Tool Call Quality)

```python
def evaluate_tool_selection(
    trajectory: list[dict],
    reference_trajectory: list[dict],
) -> dict:
    """Did the agent use the right tools in roughly the right order?"""

    # Tool selection accuracy: did the agent call expected tools?
    expected_tools = {step["tool"] for step in reference_trajectory if step.get("tool")}
    actual_tools = {step["tool"] for step in trajectory if step.get("tool")}

    precision = len(expected_tools & actual_tools) / len(actual_tools) if actual_tools else 0
    recall = len(expected_tools & actual_tools) / len(expected_tools) if expected_tools else 0

    # Tool argument quality: were arguments correct?
    arg_scores = []
    for ref_step in reference_trajectory:
        if ref_step.get("tool"):
            matching = find_matching_tool_call(ref_step, trajectory)
            if matching:
                arg_scores.append(score_arguments(ref_step["input"], matching["input"]))

    return {
        "tool_precision": precision,
        "tool_recall": recall,
        "tool_f1": 2 * precision * recall / (precision + recall + 1e-9),
        "argument_quality": sum(arg_scores) / len(arg_scores) if arg_scores else 0,
        "extra_steps": len(actual_tools) - len(expected_tools & actual_tools),
        "missing_steps": len(expected_tools) - len(expected_tools & actual_tools),
    }
```

### Level 2: Trajectory-Level Evaluation

```python
def evaluate_trajectory(trajectory: list[dict]) -> dict:
    """Evaluate the quality of the agent's reasoning process."""
    return {
        # Efficiency: fewer steps is better (for same quality outcome)
        "steps_to_completion": len(trajectory),

        # Backtracking: did agent revisit steps it already did?
        "backtrack_rate": count_repeated_actions(trajectory) / len(trajectory),

        # Tool failure handling: when tools fail, does agent recover?
        "error_recovery_rate": evaluate_error_recovery(trajectory),

        # Reasoning quality: was the thinking coherent and grounded?
        "reasoning_coherence": llm_judge_reasoning(
            [s for s in trajectory if s["type"] == "reasoning"]
        ),

        # Redundant calls: called the same tool with the same args twice
        "redundant_call_rate": count_redundant_calls(trajectory) / len(trajectory),
    }
```

### Level 3: Outcome Evaluation

```python
def evaluate_outcome(
    task: str,
    agent_output: str,
    ground_truth: str | None,
    rubric: dict,
    use_llm_judge: bool = True,
) -> dict:
    """Evaluate the final output quality."""
    results = {}

    # Exact match (for tasks with deterministic answers)
    if ground_truth:
        results["exact_match"] = normalize(agent_output) == normalize(ground_truth)

    # Semantic match (for longer-form outputs)
    if ground_truth:
        from bert_score import score
        _, _, f1 = score([agent_output], [ground_truth], lang="en")
        results["semantic_match_f1"] = f1.mean().item()

    # LLM-as-judge on rubric
    if use_llm_judge:
        results["rubric_scores"] = llm_judge_on_rubric(task, agent_output, rubric)

    # Task-specific metrics
    results["format_compliance"] = validate_output_format(agent_output, rubric.get("format"))

    return results
```

---

## Agent-Specific Evaluation Metrics

### Task Success Rate

```python
import asyncio, json
from dataclasses import dataclass

@dataclass
class AgentEvalResult:
    task_id: str
    success: bool
    steps_taken: int
    tokens_used: int
    latency_seconds: float
    error: str | None = None
    trajectory: list = None

async def run_eval_suite(
    agent,
    test_cases: list[dict],
    concurrency: int = 5,
) -> dict:
    """Run a full evaluation suite and report aggregate metrics."""
    semaphore = asyncio.Semaphore(concurrency)

    async def run_single(test_case):
        async with semaphore:
            import time
            start = time.perf_counter()
            try:
                result, trajectory = await agent.run(
                    test_case["input"],
                    return_trajectory=True,
                )
                success = evaluate_success(result, test_case)
                return AgentEvalResult(
                    task_id=test_case["id"],
                    success=success,
                    steps_taken=len(trajectory),
                    tokens_used=sum(s.get("tokens", 0) for s in trajectory),
                    latency_seconds=time.perf_counter() - start,
                    trajectory=trajectory,
                )
            except Exception as e:
                return AgentEvalResult(
                    task_id=test_case["id"],
                    success=False,
                    steps_taken=0,
                    tokens_used=0,
                    latency_seconds=time.perf_counter() - start,
                    error=str(e),
                )

    results = await asyncio.gather(*[run_single(tc) for tc in test_cases])

    return {
        "task_success_rate": sum(r.success for r in results) / len(results),
        "mean_steps": sum(r.steps_taken for r in results) / len(results),
        "mean_tokens": sum(r.tokens_used for r in results) / len(results),
        "mean_latency_s": sum(r.latency_seconds for r in results) / len(results),
        "error_rate": sum(1 for r in results if r.error) / len(results),
        "p99_latency_s": sorted(r.latency_seconds for r in results)[int(0.99 * len(results))],
        "total_cost_usd": estimate_cost(results),
        "n_tasks": len(results),
    }
```

### Key Metrics for Production Agents

| Metric | Definition | Target | Alert Threshold |
|--------|-----------|--------|----------------|
| **Task success rate** | % of tasks reaching correct terminal state | > 80% | < 60% |
| **Mean steps to completion** | Avg tool calls per task | Depends on task | 2× expected |
| **Backtrack rate** | % of steps that revisit prior state | < 10% | > 25% |
| **Tool error rate** | % of tool calls that return errors | < 5% | > 15% |
| **Human escalation rate** | % of tasks requiring HITL | Track baseline | 2× baseline |
| **Context saturation rate** | % of tasks hitting context limit | < 5% | > 15% |
| **Token efficiency** | Task quality / tokens used | Maximize | Track degradation |
| **Cost per task** | USD per completed task | Track baseline | 2× baseline |
| **E2E latency p50/p99** | Task completion time | < 30s p50 | > 2 min p99 |

---

## Trajectory Evaluation with LLM-Judge

For complex tasks without clear ground truth, use LLM-as-judge on the reasoning trajectory:

```python
TRAJECTORY_JUDGE_PROMPT = """Evaluate this AI agent's trajectory on a research task.

Task: {task}

Agent's trajectory (reasoning + actions):
{trajectory}

Final output:
{final_output}

Rate on each dimension (1-5):
1. **Goal coherence**: Did the agent stay focused on the original task?
2. **Tool selection**: Did it use appropriate tools for each subtask?
3. **Information synthesis**: Did it correctly integrate information across steps?
4. **Efficiency**: Did it avoid unnecessary steps or redundant actions?
5. **Output quality**: Is the final output accurate, complete, and well-structured?

For each dimension, provide: score (1-5), one-sentence justification.
Also provide: overall pass/fail and critical issues (if any)."""

async def judge_trajectory(
    task: str,
    trajectory: list[dict],
    final_output: str,
    judge_model: str = "claude-opus-4-6",
) -> dict:
    trajectory_str = format_trajectory_for_judge(trajectory)
    response = await client.messages.create(
        model=judge_model,
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": TRAJECTORY_JUDGE_PROMPT.format(
                task=task, trajectory=trajectory_str, final_output=final_output
            )
        }]
    )
    return parse_judge_scores(response.content[0].text)
```

---

## Regression Testing for Agents

```python
# Golden trajectory suite: hand-crafted test cases with expected outcomes
GOLDEN_TESTS = [
    {
        "id": "research-001",
        "task": "What were the top 3 AI model launches in Q4 2025?",
        "expected_tools_used": ["search_web", "search_web"],  # at least 2 searches
        "expected_answer_contains": ["claude", "gemini", "gpt"],  # case-insensitive
        "max_steps": 8,
        "success_criteria": "contains_all_required_info",
    },
    {
        "id": "code-001",
        "task": "Write a Python function to find the nth Fibonacci number using memoization",
        "expected_tools_used": ["execute_python"],  # must test the code
        "success_criteria": "code_passes_tests",
        "test_cases": [{"input": 10, "expected": 55}, {"input": 0, "expected": 0}],
    },
]

async def run_regression_suite(agent, test_suite=GOLDEN_TESTS) -> bool:
    """Run regression suite before deploying a new agent version."""
    results = await run_eval_suite(agent, test_suite)
    print(f"Task success rate: {results['task_success_rate']:.1%}")
    print(f"Mean steps: {results['mean_steps']:.1f}")
    print(f"Mean cost: ${results['total_cost_usd'] / results['n_tasks']:.3f}/task")

    # Gate: must pass > 85% of golden tests
    return results["task_success_rate"] > 0.85
```

---

## Observability Checklist for Production Agents

Every production agent deployment should instrument:

**Per-step observability:**
- [ ] Step number and wall-clock timestamp
- [ ] Reasoning/thinking trace (text)
- [ ] Tool name called (or "none" for final response)
- [ ] Tool input (truncated to 500 chars for logs)
- [ ] Tool output (truncated to 500 chars)
- [ ] Tokens used this step (input + output)
- [ ] Latency for this step (ms)

**Per-run observability:**
- [ ] Unique run ID (for correlation)
- [ ] Total steps taken
- [ ] Total tokens consumed
- [ ] Total cost (USD)
- [ ] Total wall-clock time (seconds)
- [ ] Terminal state (success / max_iterations / error / human_escalation)
- [ ] Error details if applicable

**Aggregate metrics (Grafana/CloudWatch dashboard):**
- [ ] Task success rate (rolling 24h, 7d)
- [ ] Mean/p99 steps per task
- [ ] Mean/p99 cost per task
- [ ] Mean/p99 latency per task
- [ ] Tool error rate by tool name
- [ ] Human escalation rate
- [ ] Prompt injection detection events
