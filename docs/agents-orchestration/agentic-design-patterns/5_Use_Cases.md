# Use Cases & Real-World Applications

## 1. Research & Synthesis Agent (ReAct + Parallelization)

**Context**: An internal competitive intelligence agent that, given a company name, produces a structured briefing covering products, financials, news, leadership, and strategic positioning.

```python
import asyncio
from anthropic import AsyncAnthropic

client = AsyncAnthropic()

RESEARCH_SYSTEM = """You are a competitive intelligence analyst. Research companies thoroughly and produce structured briefings.

Use your tools iteratively: search broadly first, then dig into promising results, then verify key claims.
Always cite your sources. If you can't find reliable information on a topic, say so explicitly."""

SYNTHESIS_SYSTEM = """You synthesize research findings from multiple specialist researchers into a coherent executive briefing.
Resolve contradictions between sources. Flag any information you cannot verify."""

# Specialist agents for each research area
async def research_area(company: str, area: str, area_tools: list) -> tuple[str, str]:
    """Research one area in parallel."""
    messages = [{"role": "user", "content": f"Research {area} for {company}. Be thorough."}]

    for _ in range(8):  # max 8 steps per specialist
        response = await client.messages.create(
            model="claude-sonnet-4-6",  # cheaper model for workers
            max_tokens=2048,
            system=RESEARCH_SYSTEM,
            tools=area_tools,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            text = next((b.text for b in response.content if hasattr(b, "text")), "")
            return area, text

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = await execute_tool_async(block.name, block.input)
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
        messages.append({"role": "user", "content": tool_results})

    return area, "Research incomplete — max iterations reached"


async def research_company(company: str) -> str:
    """Orchestrate parallel research across 5 areas, synthesize with Claude Opus."""
    areas = [
        ("Products & Technology", product_tools),
        ("Financials & Business Model", finance_tools),
        ("Recent News & Events", news_tools),
        ("Leadership & Culture", people_tools),
        ("Competitive Positioning", strategy_tools),
    ]

    # Parallel research across all areas
    area_results = await asyncio.gather(*[
        research_area(company, area_name, tools)
        for area_name, tools in areas
    ])

    # Synthesize with Opus (more capable model for synthesis)
    synthesis_prompt = f"Synthesize these research findings about {company} into an executive briefing:\n\n"
    for area, result in area_results:
        synthesis_prompt += f"## {area}\n{result}\n\n"

    synthesis = await client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4096,
        system=SYNTHESIS_SYSTEM,
        messages=[{"role": "user", "content": synthesis_prompt}],
    )
    return synthesis.content[0].text
```

**Production numbers**: 5 parallel research agents × 8 steps × avg 2s/step = 16 seconds wall clock time (vs 80 seconds serial). Opus for synthesis (~4k tokens) + 5 Sonnet workers (~10k tokens each) = ~54k tokens total. At Claude pricing ≈ $0.15 per briefing.

---

## 2. Software Engineering Agent (Plan-Execute + Code Tools)

**Context**: A developer co-pilot that can take a feature request and implement it across a codebase: read relevant files, understand the architecture, write the code, run tests, fix failures.

```python
from langgraph.graph import StateGraph, END
from typing import TypedDict, Annotated
import operator, subprocess, os

class CodingState(TypedDict):
    task: str
    plan: list[dict]
    current_step: int
    code_changes: dict  # {filepath: new_content}
    test_results: list[dict]
    messages: Annotated[list, operator.add]
    status: str

# Tools available to the coding agent
coding_tools = [
    {
        "name": "read_file",
        "description": "Read the contents of a file. Use to understand existing code before modifying.",
        "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    },
    {
        "name": "write_file",
        "description": "Write content to a file. Creates the file if it doesn't exist.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
    },
    {
        "name": "run_tests",
        "description": "Run the test suite. Returns test results including any failures with stack traces.",
        "input_schema": {
            "type": "object",
            "properties": {"test_path": {"type": "string", "default": "tests/"}},
        },
    },
    {
        "name": "search_codebase",
        "description": "Search for a pattern in the codebase. Returns file paths and line numbers.",
        "input_schema": {
            "type": "object",
            "properties": {"pattern": {"type": "string"}, "file_pattern": {"type": "string", "default": "**/*.py"}},
            "required": ["pattern"],
        },
    },
]

def planning_node(state: CodingState) -> CodingState:
    """Create an implementation plan before writing any code."""
    response = llm.invoke([
        SystemMessage(content="You are an expert software engineer. Create a detailed implementation plan."),
        HumanMessage(content=f"Plan the implementation of this feature:\n{state['task']}\n\nList each step with: file to modify/create, what change to make, why.")
    ])
    plan = parse_plan_json(response.content)
    return {"plan": plan, "current_step": 0, "status": "executing"}

def execution_node(state: CodingState) -> CodingState:
    """Execute one step of the plan."""
    step = state["plan"][state["current_step"]]
    # Agent executes the step (read relevant files, write changes)
    result = run_agent_step(step, state["messages"])
    return {
        "current_step": state["current_step"] + 1,
        "messages": [AIMessage(content=f"Completed step {state['current_step']}: {result}")],
    }

def test_and_fix_node(state: CodingState) -> CodingState:
    """Run tests and fix failures in a loop (max 3 attempts)."""
    for attempt in range(3):
        test_results = run_test_suite()
        if all(t["passed"] for t in test_results):
            return {"status": "complete", "test_results": test_results}

        # Fix failures
        failures = [t for t in test_results if not t["passed"]]
        fix_code_for_failures(failures)

    return {"status": "tests_failing", "test_results": test_results}
```

**Key design decision**: Tests run in a sandboxed environment (Docker container) that mirrors production. The agent cannot break production — it can only break the sandbox. This is the permission boundary that makes irreversible-action risk manageable.

---

## 3. Customer Support Agent with HITL Escalation

**Context**: A first-line support agent that handles routine issues autonomously and escalates complex or high-stakes issues to human agents.

```python
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt

class SupportState(TypedDict):
    customer_id: str
    issue: str
    resolution_steps: list[str]
    escalation_reason: str | None
    messages: Annotated[list, operator.add]

ESCALATION_TRIGGERS = [
    "refund > $500",
    "account compromise suspected",
    "legal threat",
    "repeated failed resolution (> 2 attempts)",
    "customer explicitly requests human",
]

def should_escalate(state: SupportState) -> str:
    """Classify whether this case needs human attention."""
    for trigger in ESCALATION_TRIGGERS:
        if matches_escalation_trigger(state["issue"], trigger, state["resolution_steps"]):
            return "escalate"
    return "handle"

def escalation_node(state: SupportState) -> SupportState:
    """Pause for human agent to take over."""
    human_action = interrupt({
        "type": "escalation",
        "customer_id": state["customer_id"],
        "issue": state["issue"],
        "ai_attempted_steps": state["resolution_steps"],
        "escalation_reason": state["escalation_reason"],
        "suggested_resolution": generate_resolution_suggestion(state),
    })
    # When human resumes: human_action contains their resolution
    return {"messages": [SystemMessage(content=f"Human resolved: {human_action['resolution']}")]}

def resolve_node(state: SupportState) -> SupportState:
    """Attempt automated resolution."""
    response = llm_with_tools.invoke(state["messages"])
    # Execute tool calls: check_account, process_refund, reset_password, etc.
    return {"resolution_steps": state["resolution_steps"] + [extract_action(response)]}
```

**SLA design**: Set a 2-minute human response timeout on escalations. If no human picks up within 2 minutes, auto-respond to the customer with an ETA and queue position. This prevents agent escalations from causing worse customer experience than full automation.

---

## 4. Data Analysis Agent (Tool-Heavy + Reflection)

**Context**: A business intelligence agent that, given a question ("Why did revenue drop in Q3?"), queries databases, generates and executes Python analysis code, creates visualizations, and produces an analytical narrative.

```python
ANALYST_SYSTEM = """You are a data analyst with SQL and Python expertise. Approach analysis rigorously:
1. Start with data exploration before drawing conclusions
2. Verify hypotheses with multiple queries
3. Acknowledge data limitations and uncertainty
4. Use code to compute — never guess numbers"""

async def data_analysis_agent(question: str, db_connection, data_tools) -> dict:
    messages = [{"role": "user", "content": question}]
    artifacts = []  # charts, tables produced during analysis

    for step in range(20):
        response = await client.messages.create(
            model="claude-opus-4-6",
            max_tokens=4096,
            system=ANALYST_SYSTEM,
            tools=data_tools,
            messages=messages,
            thinking={"type": "enabled", "budget_tokens": 4000},  # extended thinking for analysis planning
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            break

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                if block.name == "execute_python":
                    result = await execute_in_sandbox(block.input["code"])
                    if result.get("chart"):
                        artifacts.append(result["chart"])
                elif block.name == "query_database":
                    result = await db_connection.execute(block.input["sql"])
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)})

        messages.append({"role": "user", "content": tool_results})

    # Reflection pass: critique the analysis
    narrative = extract_narrative(messages)
    critique = await self_critique(question, narrative, messages)

    if critique["has_issues"]:
        # One more pass to address critique
        messages.append({"role": "user", "content": f"Improve the analysis based on this critique: {critique['feedback']}"})
        final_response = await client.messages.create(model="claude-opus-4-6", max_tokens=4096, messages=messages)
        narrative = final_response.content[0].text

    return {"narrative": narrative, "artifacts": artifacts, "queries_run": count_queries(messages)}
```

---

## 5. Document Processing Pipeline (Prompt Chaining)

**Context**: Process thousands of contracts per day — extract key fields, classify risk level, flag anomalous clauses, generate executive summaries. High throughput required; consistency matters more than creativity.

```python
# Prompt chaining: each stage is a deterministic LLM call, not an agent loop
from dataclasses import dataclass

@dataclass
class ContractAnalysis:
    raw_text: str
    extracted_fields: dict | None = None
    risk_classification: str | None = None
    anomalous_clauses: list[str] | None = None
    executive_summary: str | None = None

async def process_contract(contract_text: str) -> ContractAnalysis:
    result = ContractAnalysis(raw_text=contract_text)

    # Stage 1: Extract fields (structured output, temperature=0)
    result.extracted_fields = await extract_with_schema(
        text=contract_text,
        schema=ContractFields,
        system="Extract contract metadata as JSON. Be precise; if a field is not present, return null.",
    )

    # Stage 2: Risk classification (uses extracted fields as context)
    result.risk_classification = await classify_risk(
        fields=result.extracted_fields,
        full_text=contract_text[:4000],  # first 4k tokens
    )

    # Stage 3: Flag anomalous clauses (only run if medium/high risk)
    if result.risk_classification in ("medium", "high"):
        result.anomalous_clauses = await flag_anomalies(
            text=contract_text,
            standard_clauses=STANDARD_CLAUSES,
        )

    # Stage 4: Executive summary (uses all prior outputs as context)
    result.executive_summary = await generate_summary(
        fields=result.extracted_fields,
        risk=result.risk_classification,
        anomalies=result.anomalous_clauses,
    )

    return result


async def batch_process_contracts(contracts: list[str]) -> list[ContractAnalysis]:
    """Process many contracts in parallel with concurrency limit."""
    semaphore = asyncio.Semaphore(10)  # max 10 concurrent

    async def bounded_process(contract):
        async with semaphore:
            return await process_contract(contract)

    return await asyncio.gather(*[bounded_process(c) for c in contracts])
```

**Why this is NOT an agent**: The processing steps are fixed and known in advance. Using a ReAct agent here would add variable latency, harder debugging, and no quality benefit. Prompt chaining with parallelization is the right pattern for this workload.

---

## 6. Autonomous DevOps Agent (HITL for Irreversible Actions)

**Context**: An agent that monitors application health, diagnoses issues, and attempts remediation — but requires human approval before any action that affects production.

```python
READ_ONLY_TOOLS = [
    check_metrics, get_logs, describe_deployment, get_pod_status, query_database_readonly
]

WRITE_TOOLS = [
    restart_pod, scale_deployment, rollback_deployment, execute_sql_migration
]

class DevOpsAgent:
    ALWAYS_APPROVE = set()  # all write actions require approval
    READ_ONLY = {t["name"] for t in READ_ONLY_TOOLS}

    async def diagnose_and_remediate(self, alert: dict) -> dict:
        # Phase 1: Diagnosis (fully automated, read-only)
        diagnosis = await self.run_loop(
            task=f"Diagnose this alert: {alert}",
            tools=READ_ONLY_TOOLS,
            system="Diagnose the root cause. Gather evidence from metrics, logs, and service status.",
        )

        # Phase 2: Generate remediation plan
        plan = await self.generate_remediation_plan(diagnosis, alert)

        # Phase 3: Request human approval for each action
        approved_actions = []
        for action in plan["actions"]:
            approval = await self.request_human_approval(
                action=action,
                context=diagnosis,
                impact=action["estimated_impact"],
                rollback_plan=action.get("rollback"),
            )
            if approval["approved"]:
                approved_actions.append(action)
            else:
                break  # stop if any action denied

        # Phase 4: Execute approved actions
        results = []
        for action in approved_actions:
            result = await self.execute_action(action, WRITE_TOOLS)
            results.append(result)
            # Verify success before proceeding to next action
            if not result["success"]:
                await self.alert_on_call(f"Remediation step failed: {action}")
                break

        return {"diagnosis": diagnosis, "actions_taken": results}
```

**The irreversibility principle**: Categorize every tool by reversibility:
- `restart_pod`: reversible (can restart again)
- `scale_deployment`: reversible (can scale back)
- `rollback_deployment`: reversible (can re-deploy)
- `execute_sql_migration`: irreversible (requires human approval always)
- `delete_data`: irreversible (double-human approval + dry-run first)

Automate freely for reversible actions; gate all irreversible ones.
