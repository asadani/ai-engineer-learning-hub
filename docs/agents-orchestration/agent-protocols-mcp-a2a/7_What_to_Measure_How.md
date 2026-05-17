# What to Measure & How

## Metrics Tables

### Tool / Agent Quality
| Metric | Definition | Target (typical) |
|---|---|---|
| Tool-selection accuracy | correct tool / total intents | > 95% |
| Arg-schema first-pass rate | valid args without retry | > 90% |
| Tool-call success rate | non-error results / calls | > 98% |
| A2A task completion rate | completed / submitted | > 97% |
| Retry rate | calls requiring ≥1 retry | < 10% |

### Latency
| Metric | Definition | Target |
|---|---|---|
| Handshake + tools/list | session init overhead | < 200 ms (local), < 800 ms (remote) |
| Per-tool-call p95 | round-trip | within tool SLO |
| A2A time-to-first-update | submit → first `working` | < 2 s |
| A2A task p95 duration | submit → completed | per task class |

### Reliability / Security
| Metric | Definition | Alert |
|---|---|---|
| Server availability | successful inits / attempts | < 99.5% |
| DLQ / failed-task depth | failed A2A tasks unrecovered | > 0 sustained |
| Injection-scan hits | flagged tool descs/resources | any |
| Scope violations | calls outside granted OAuth scope | any |
| Unapproved irreversible calls | irreversible tool w/o HITL | any (page) |

## Instrumentation: OTel GenAI Spans for Tool Calls

Use the OpenTelemetry **GenAI semantic conventions** (the 2026 standard) so traces are portable across Langfuse/Phoenix/Datadog without SDK changes:

```python
# one span per MCP tool call
with tracer.start_as_current_span("execute_tool inventory.get_stock") as s:
    s.set_attribute("gen_ai.operation.name", "execute_tool")
    s.set_attribute("gen_ai.tool.name", "inventory.get_stock")
    s.set_attribute("gen_ai.tool.call.id", call_id)
    s.set_attribute("mcp.transport", "streamable-http")
    s.set_attribute("mcp.server", "inventory")
    # do NOT log raw args/results if they may contain PII; redact or hash
```

For A2A, emit a span per task with `gen_ai.agent.name`, `gen_ai.agent.id`, task id, and state transitions as span events.

## Alerting Rules (sketch)

- `tool_call_success_rate < 0.98` for 5m → warn; `< 0.95` → page.
- `scope_violations > 0` or `unapproved_irreversible_calls > 0` → page immediately.
- `injection_scan_hits > 0` → page security on-call.
- `server_init_success < 0.995` for 10m → warn.
- `a2a_failed_task_depth` rising monotonically → investigate stuck delegate.

## Dashboard Checklist

- Tool-selection accuracy and arg-validity trend (quality regression signal).
- Per-server/per-tool call volume, success, latency p50/p95.
- A2A task funnel: submitted → working → completed/failed.
- Security panel: scope violations, injection hits, HITL approvals.
- Conformance CI status per endpoint.
