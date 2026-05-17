# Products & Tools

## Agent Frameworks

### LangGraph (LangChain)

Graph-based agent orchestration. Nodes are functions (LLM calls, tool calls, human review); edges are state transitions. Built-in support for cycles, checkpointing, streaming, and human-in-the-loop.

```python
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from typing import TypedDict, Annotated
import operator

# State schema: everything the graph needs to track
class AgentState(TypedDict):
    messages: Annotated[list, operator.add]  # append-only message list
    task_status: str
    iterations: int

# Define LLM
llm = ChatAnthropic(model="claude-opus-4-6").bind_tools(tools)

# Node: call the LLM
def call_model(state: AgentState) -> AgentState:
    response = llm.invoke(state["messages"])
    return {
        "messages": [response],
        "iterations": state["iterations"] + 1,
    }

# Node: execute tools
tool_node = ToolNode(tools)

# Conditional edge: should we call tools or stop?
def should_continue(state: AgentState) -> str:
    last_message = state["messages"][-1]
    if state["iterations"] >= 10:
        return "end"  # safety limit
    if last_message.tool_calls:
        return "tools"  # go execute tools
    return "end"    # no tool calls → done

# Build the graph
builder = StateGraph(AgentState)
builder.add_node("agent", call_model)
builder.add_node("tools", tool_node)
builder.set_entry_point("agent")
builder.add_conditional_edges(
    "agent",
    should_continue,
    {"tools": "tools", "end": END},
)
builder.add_edge("tools", "agent")  # after tools, go back to agent

# Compile with checkpointing (enables resume on failure)
from langgraph.checkpoint.sqlite import SqliteSaver
checkpointer = SqliteSaver.from_conn_string(":memory:")
app = builder.compile(checkpointer=checkpointer)

# Run
config = {"configurable": {"thread_id": "run-001"}}
result = app.invoke(
    {"messages": [HumanMessage(content="Research the latest news on LLM serving")],
     "task_status": "running", "iterations": 0},
    config=config,
)
```

**LangGraph HITL (interrupt before tool execution):**
```python
from langgraph.types import interrupt, Command

def human_review_node(state: AgentState) -> Command:
    """Pause execution and wait for human approval."""
    last_tool_calls = state["messages"][-1].tool_calls

    # interrupt() pauses the graph and waits for resume()
    human_decision = interrupt({
        "type": "review_required",
        "proposed_actions": last_tool_calls,
        "context": state["messages"][-3:],
    })

    if human_decision["action"] == "approve":
        return Command(goto="tools")
    elif human_decision["action"] == "modify":
        # Inject modified tool call
        return Command(goto="tools", update={"messages": [human_decision["modified_message"]]})
    else:
        return Command(goto=END)
```

**Why LangGraph for production**: Explicit state machine makes behavior predictable and auditable. Checkpointing enables fault tolerance and human-in-the-loop. Streaming shows intermediate steps to users. Strongly typed state prevents hidden state mutation bugs.

---

### CrewAI

Role-based multi-agent framework. Agents have explicit roles, goals, and backstories. Crews coordinate agents with defined tasks and processes.

```python
from crewai import Agent, Task, Crew, Process
from crewai_tools import SerperDevTool, FileReadTool

# Define specialized agents with roles
researcher = Agent(
    role="Senior Research Analyst",
    goal="Uncover comprehensive information about a topic from multiple sources",
    backstory="You are an expert researcher with 10 years of experience synthesizing complex information. You are known for thorough, nuanced analysis.",
    tools=[SerperDevTool()],
    llm="claude-opus-4-6",
    verbose=True,
    allow_delegation=False,
    max_iter=5,
)

writer = Agent(
    role="Technical Writer",
    goal="Transform research findings into clear, actionable documentation",
    backstory="You are a technical writer who specializes in making complex technical topics accessible without losing accuracy.",
    tools=[],
    llm="claude-opus-4-6",
    allow_delegation=False,
)

critic = Agent(
    role="Quality Reviewer",
    goal="Ensure accuracy, completeness, and clarity of technical content",
    backstory="You are a meticulous reviewer who catches errors and inconsistencies. You provide specific, actionable feedback.",
    tools=[],
    llm="claude-opus-4-6",
)

# Define tasks (what each agent does)
research_task = Task(
    description="Research the current state of LLM inference optimization techniques. Cover: quantization, speculative decoding, continuous batching, and emerging methods.",
    agent=researcher,
    expected_output="A detailed research summary with specific technical details, benchmarks, and source citations.",
)

write_task = Task(
    description="Using the research summary, write a technical blog post suitable for senior engineers.",
    agent=writer,
    expected_output="A 1500-word blog post with code examples and concrete recommendations.",
    context=[research_task],  # depends on research_task output
)

review_task = Task(
    description="Review the blog post for technical accuracy and clarity. Provide specific improvement suggestions.",
    agent=critic,
    expected_output="A review with specific corrections and suggestions, plus approval/rejection decision.",
    context=[write_task],
)

# Assemble crew
crew = Crew(
    agents=[researcher, writer, critic],
    tasks=[research_task, write_task, review_task],
    process=Process.sequential,  # or Process.hierarchical (manager coordinates)
    verbose=True,
    memory=True,  # enable cross-task memory
)

result = crew.kickoff(inputs={"topic": "LLM inference optimization"})
```

**CrewAI vs LangGraph**: CrewAI is higher-level and role-oriented — faster to set up for multi-agent workflows with clear human-like roles. LangGraph is lower-level and graph-oriented — more control over state, transitions, and fault handling. CrewAI for rapid prototyping; LangGraph for production systems that need fine-grained control.

---

### Anthropic Claude Agent SDK (claude-agent-sdk)

Lightweight SDK for building agents with Claude. Handles the tool-use loop, streaming, and multi-turn conversations.

```python
# Using the Anthropic API directly (most production deployments)
# The "SDK" for agents is primarily the messages API with tool_use

import anthropic
from anthropic import Anthropic

client = Anthropic()

class ClaudeAgent:
    def __init__(self, system_prompt: str, tools: list[dict], model: str = "claude-opus-4-6"):
        self.system_prompt = system_prompt
        self.tools = tools
        self.model = model
        self.messages = []

    def run(self, user_message: str, max_steps: int = 20) -> str:
        self.messages.append({"role": "user", "content": user_message})

        for step in range(max_steps):
            response = client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=self.system_prompt,
                tools=self.tools,
                messages=self.messages,
            )
            self.messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                return next(
                    (block.text for block in response.content if hasattr(block, "text")),
                    ""
                )

            # Execute tool calls
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = self._execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(result),
                    })

            self.messages.append({"role": "user", "content": tool_results})

        return "Max steps reached"

    def _execute_tool(self, tool_name: str, tool_input: dict) -> Any:
        # Route to registered tool implementations
        return self.tool_registry[tool_name](**tool_input)
```

**Extended Thinking for agents**: Use `thinking` budget for complex planning steps:
```python
response = client.messages.create(
    model="claude-opus-4-6",
    max_tokens=16000,
    thinking={"type": "enabled", "budget_tokens": 8000},  # think before acting
    tools=tools,
    messages=messages,
)
# The thinking block is visible in response.content for debugging
for block in response.content:
    if block.type == "thinking":
        log_thinking_trace(block.thinking)  # crucial for debugging
    elif block.type == "tool_use":
        execute_tool(block)
```

---

### OpenAI Swarm / Assistants API

```python
# OpenAI Swarm pattern: agents that can hand off to each other
from swarm import Swarm, Agent

client = Swarm()

# Triage agent hands off to specialists
def transfer_to_billing():
    return billing_agent

def transfer_to_technical_support():
    return tech_support_agent

triage_agent = Agent(
    name="Triage Agent",
    instructions="Determine if the user needs billing help or technical support. Transfer accordingly.",
    functions=[transfer_to_billing, transfer_to_technical_support],
)

billing_agent = Agent(
    name="Billing Agent",
    instructions="Handle billing inquiries. You have access to account information tools.",
    functions=[get_account_info, process_refund],
)

tech_support_agent = Agent(
    name="Technical Support",
    instructions="Handle technical issues. Escalate to human if unresolved in 3 steps.",
    functions=[check_system_status, restart_service],
)

response = client.run(
    agent=triage_agent,
    messages=[{"role": "user", "content": "My payment failed but I was still charged"}],
)
```

---

### AutoGen (Microsoft)

Conversation-based multi-agent. Agents communicate via a structured conversation protocol.

```python
import autogen

# Configuration
config_list = [{"model": "claude-opus-4-6", "api_key": "..."}]
llm_config = {"config_list": config_list, "seed": 42}

# Define agents
user_proxy = autogen.UserProxyAgent(
    name="UserProxy",
    human_input_mode="NEVER",  # fully automated; "TERMINATE" for HITL
    max_consecutive_auto_reply=10,
    is_termination_msg=lambda x: "TERMINATE" in x.get("content", ""),
    code_execution_config={"work_dir": "workspace", "use_docker": True},
)

coder = autogen.AssistantAgent(
    name="Coder",
    llm_config=llm_config,
    system_message="You are an expert Python developer. Write code to solve tasks.",
)

critic = autogen.AssistantAgent(
    name="Critic",
    llm_config=llm_config,
    system_message="Review code for correctness, security, and style. Suggest improvements.",
)

# Group chat: multiple agents in a round-robin conversation
group_chat = autogen.GroupChat(
    agents=[user_proxy, coder, critic],
    messages=[],
    max_round=12,
    speaker_selection_method="round_robin",  # or "auto" (LLM decides who speaks)
)

manager = autogen.GroupChatManager(
    groupchat=group_chat,
    llm_config=llm_config,
)

user_proxy.initiate_chat(
    manager,
    message="Build a Python script that monitors CPU usage and alerts when > 80%",
)
```

---

## Tool Libraries & Integrations

### Browser / Web Tools

```python
# Playwright-based browser tool
from playwright.async_api import async_playwright

async def browse_web(url: str, extract_selector: str = None) -> str:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(url, timeout=30000)
        await page.wait_for_load_state("networkidle")

        if extract_selector:
            content = await page.inner_text(extract_selector)
        else:
            content = await page.inner_text("body")

        await browser.close()
        return content[:5000]  # truncate to context budget

# For agents: use Playwright MCP or Browserbase for managed browser sessions
```

### Code Execution (Sandboxed)

```python
# E2B for sandboxed code execution
from e2b_code_interpreter import Sandbox

def execute_code_safely(code: str, timeout: int = 30) -> dict:
    """Execute code in an isolated E2B sandbox."""
    with Sandbox() as sandbox:
        execution = sandbox.run_code(code, timeout=timeout)
        return {
            "stdout": execution.logs.stdout,
            "stderr": execution.logs.stderr,
            "error": execution.error,
            "results": [str(r) for r in execution.results],
        }
```

### MCP (Model Context Protocol)

Anthropic's open standard for connecting agents to tools, data sources, and services:

```python
# MCP server definition (host side)
from mcp.server import Server
from mcp.types import Tool, TextContent

app = Server("database-mcp")

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="query_database",
            description="Execute a read-only SQL query against the production database",
            inputSchema={
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "SQL SELECT query (no writes allowed)"},
                    "limit": {"type": "integer", "default": 100},
                },
                "required": ["sql"],
            },
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "query_database":
        results = await db.execute_readonly(arguments["sql"], limit=arguments.get("limit", 100))
        return [TextContent(type="text", text=json.dumps(results))]

# Client side (Claude uses MCP servers via tool definitions)
# The MCP protocol handles tool discovery, invocation, and result streaming
```

---

## Observability for Agents

### LangSmith (LangChain)

```python
import os
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_API_KEY"] = "..."
os.environ["LANGCHAIN_PROJECT"] = "production-agent"

# All LangGraph/LangChain calls are automatically traced:
# - Full conversation history
# - Tool call inputs and outputs
# - Latency per step
# - Token usage per step
# - Error traces with full context
```

### Arize Phoenix (open-source)

```python
import phoenix as px
from phoenix.otel import register
from opentelemetry import trace

# Start Phoenix UI
px.launch_app()

# Register auto-instrumentation
tracer_provider = register(
    project_name="agent-traces",
    endpoint="http://localhost:6006/v1/traces",
)

# Manual span for custom agent steps
tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("agent-step") as span:
    span.set_attribute("step.number", step_num)
    span.set_attribute("tool.name", tool_name)
    span.set_attribute("tool.input", json.dumps(tool_input))
    result = execute_tool(tool_name, tool_input)
    span.set_attribute("tool.output", str(result)[:500])
```
