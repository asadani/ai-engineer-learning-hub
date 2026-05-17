# What to Measure & How

## Operational and Design Metrics

Design patterns are development-time interventions, but their effects are measurable at build time, test time, and over the lifecycle of the codebase.

---

## Metrics Checklist

| Metric Name | Type | Target SLO | Collection Method |
|-------------|------|------------|-------------------|
| **Unit test suite runtime** | Gauge (seconds) | < 10s | `pytest --tb=no -q` timing |
| **Infrastructure dependencies in unit tests** | Counter | 0 | `grep -rn "pytest.mark.integration" tests/unit/` |
| **Mock count per test (avg)** | Gauge | ≤ 2 avg, ≤ 5 max | `grep -rn "@patch\|MagicMock\|mocker\." tests/unit/ | wc -l` |
| **`isinstance` in domain/application** | Counter | 0 | `grep -rn "isinstance(" src/domain/ src/application/` |
| **ORM imports in domain layer** | Counter | 0 | `import-linter` or grep |
| **`if/elif` chains > 3 branches on type/string** | Counter | 0 | `radon` CC + manual review |
| **`@functools.wraps` coverage** | Ratio | 100% of wrappers | AST analysis script |
| **Cyclomatic complexity per class** | Gauge | Max CC ≤ 10 | `radon cc src/ -n C` |
| **Classes with > 20 public methods** | Counter | 0 | `pylint too-many-public-methods` |
| **PR size for new feature variant** | Gauge (lines) | < 50 lines (new strategy/handler) | GitHub PR diff |
| **Files changed per feature addition** | Counter | ≤ 2 (new file + wiring) | Git diff per PR |
| **Observer handler failures silenced** | Counter | 0 (logged, not silenced) | Log monitoring |
| **Repository methods count** | Gauge | ≤ 15 per repo | `radon raw -s` |
| **Concrete type annotations in domain** | Counter | 0 | `mypy --strict` violations |
| **Event type mutability violations** | Counter | 0 | `grep -rn "dataclass(" src/domain/events/` without `frozen=True` |

---

## Setting Up Pattern Health Monitoring in CI

### Step 1: Domain purity gate

```bash
# domain_purity_check.sh
echo "=== Checking domain purity ==="

# No ORM in domain
if grep -rn "sqlalchemy\|psycopg2\|django.db\|boto3\|redis\|httpx\|requests" \
    src/domain/ src/application/ 2>/dev/null | grep -v "# type: ignore"; then
  echo "FAIL: Infrastructure imports in domain/application layer"
  exit 1
fi

# No isinstance in domain (Strategy smell)
if grep -rn "isinstance(" src/domain/ 2>/dev/null; then
  echo "WARN: isinstance() in domain layer — consider Strategy/Protocol"
fi

echo "OK: Domain purity checks passed"
```

### Step 2: Observer event immutability check

```python
# scripts/check_events.py — run in CI
import ast
from pathlib import Path

events_path = Path("src/domain/events")
violations = []

for pyfile in events_path.rglob("*.py"):
    tree = ast.parse(pyfile.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            decorators = [ast.dump(d) for d in node.decorator_list]
            has_dataclass = any("dataclass" in d for d in decorators)
            has_frozen = any("frozen" in d for d in decorators)
            if has_dataclass and not has_frozen:
                violations.append(f"{pyfile}:{node.lineno} — {node.name} is not frozen=True")

if violations:
    print("\n".join(violations))
    raise SystemExit(1)
```

### Step 3: Test infrastructure isolation gate

```bash
# Ensure unit tests don't touch DB/network
pytest tests/unit/ \
  --timeout=5 \
  -p no:django \
  --no-header \
  -q

# If any test takes > 5s, it's hitting infrastructure (or has a bug)
pytest tests/unit/ --durations=5  # show 5 slowest tests
```

### Step 4: Decorator integrity check

```bash
# Find wrapper functions missing @functools.wraps
python scripts/check_decorators.py src/
# (Uses the AST script from Section 6)
```

---

## Git-Based Pattern Health Over Time

### Feature addition velocity

```bash
# How many files changed per PR in the last 20 PRs?
# (Low number = good OCP compliance — new variants are new files, not modifications)
gh pr list --state merged --limit 20 --json number,title \
  | jq -r '.[].number' \
  | xargs -I{} gh pr diff {} --stat \
  | grep "files changed" \
  | awk '{print $1}' \
  | sort -n
```

OCP-compliant codebases show PRs adding one new file (new Strategy/Handler/Repository) rather than modifying 5 existing files.

### Churn on high-abstraction files

```bash
# Factory, EventBus, base Protocol files should be stable (low churn)
# High churn on these = OCP violation (people keep modifying the factory)
git log --since="6 months ago" --format="%H" \
  | xargs -I{} git diff-tree --no-commit-id -r --name-only {} \
  | grep -E "factory|event_bus|ports\.py|protocols\.py" \
  | sort | uniq -c | sort -rn
```

If `payment_factory.py` shows 20 commits in 6 months, the factory has an `elif` chain being modified — refactor to registry.

---

## Runtime Observability Tied to Patterns

### Strategy — emit which strategy was used

```python
import structlog
log = structlog.get_logger()

class InferenceService:
    def __init__(self, backend: InferenceBackend) -> None:
        self._backend = backend

    def answer(self, question: str) -> str:
        log.info("inference.request",
                 backend=type(self._backend).__name__,
                 question_len=len(question))
        response = self._backend.complete(InferenceRequest(prompt=question))
        log.info("inference.response",
                 backend=type(self._backend).__name__,
                 latency_ms=response.latency_ms,
                 tokens=response.output_tokens)
        return response.text
```

Aggregate by `backend` in your log analytics (CloudWatch Insights or Kibana) to compare performance across Strategy implementations.

### Observer — event pipeline tracing

```python
class InstrumentedEventBus:
    async def emit(self, event) -> None:
        event_type = type(event).__name__
        handlers = self._handlers.get(type(event), [])
        log.info("event.publish", event_type=event_type, handler_count=len(handlers))

        results = await asyncio.gather(
            *(self._run_handler(h, event) for h in handlers),
            return_exceptions=True,
        )
        failures = [r for r in results if isinstance(r, Exception)]
        log.info("event.complete",
                 event_type=event_type,
                 success=len(handlers) - len(failures),
                 failures=len(failures))

    async def _run_handler(self, handler, event) -> None:
        start = time.perf_counter()
        try:
            await handler.handle(event)
            metrics.increment(f"event.handler.success",
                             tags={"handler": type(handler).__name__})
        except Exception as e:
            metrics.increment(f"event.handler.failure",
                             tags={"handler": type(handler).__name__})
            log.error("event.handler.failed",
                      handler=type(handler).__name__,
                      error=str(e), exc_info=True)
            raise
```

Dashboard metrics: `event.handler.success` and `event.handler.failure` by handler name → identifies flaky observers in production.

### Repository — query performance tracking

```python
class InstrumentedUserRepository:
    def __init__(self, wrapped: UserRepository) -> None:
        self._wrapped = wrapped

    def get(self, user_id: UUID) -> User | None:
        with metrics.timer("repo.user.get"):
            return self._wrapped.get(user_id)

    def find_by_tier(self, tier: str) -> list[User]:
        with metrics.timer("repo.user.find_by_tier"):
            result = self._wrapped.find_by_tier(tier)
            metrics.histogram("repo.user.find_by_tier.count", len(result))
            return result
```

This is the GoF Decorator applied to repository observability — the instrumented version wraps the real one, adds metrics, and passes through. Swap in or out at composition root without modifying either class.
