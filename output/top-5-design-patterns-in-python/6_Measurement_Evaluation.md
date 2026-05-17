# Measurement & Evaluation

## How to Evaluate Pattern Application Quality

Pattern quality is not binary (used/not used) — it's measured by whether the pattern achieves its stated goal: reduced cost of change, improved testability, and cleaner collaboration between components.

---

## Metrics per Pattern

### Strategy Pattern Quality Signals

| Signal | Good | Bad |
|--------|------|-----|
| `if/elif` chains on type/string in service code | 0 | ≥ 1 (OCP violation) |
| Adding new variant requires modifying existing class | No | Yes |
| Unit test can swap strategy without mocking framework | Yes | No |
| Strategy has `__init__` params for configuration | Expected | Strategy holds mutable global state |

```bash
# Detect if/elif chains on known discriminator patterns
grep -rn "if.*type.*==" src/ | grep -v test
grep -rn "elif.*provider\|elif.*backend\|elif.*format" src/
```

### Factory Pattern Quality Signals

| Signal | Good | Bad |
|--------|------|-----|
| Adding new product type requires modifying factory | No (registry) | Yes (new elif) |
| Concrete class instantiation in domain/service layers | None | Multiple |
| Factory handles unknown types with clear error | `ValueError` with valid options | `KeyError` / `None` |

```bash
# Detect concrete instantiation in domain layer (should be zero)
grep -rn "= Stripe\|= Postgres\|= Redis\|= boto3\|= httpx.Client(" src/domain/ src/application/
```

### Decorator Pattern Quality Signals

| Signal | Good | Bad |
|--------|------|-----|
| `@functools.wraps` used on every wrapper | Yes | No — `__name__`, `__doc__` broken |
| Decorator stack depth | ≤ 4 stacked decorators | 8+ stacked decorators (readability) |
| GoF Structural Decorator preserves Protocol interface | Yes | Wrapper doesn't implement same Protocol |
| Cross-cutting concern (logging, retry) not duplicated across functions | Yes (one decorator) | Copy-pasted in each function |

```bash
# Find functions with missing @functools.wraps (heuristic: wrapper that doesn't call wraps)
grep -n "def wrapper" src/ -A 3 | grep -v "functools.wraps"
```

### Observer Pattern Quality Signals

| Signal | Good | Bad |
|--------|------|-----|
| Handler failure isolates (other handlers still run) | Yes (`return_exceptions=True`) | No (one failure blocks others) |
| Domain service imports observer/handler modules | No | Yes (coupling) |
| Handlers are independently testable | Yes | Handlers call each other directly |
| Event types are immutable value objects | `@dataclass(frozen=True)` | Mutable dict events |

```bash
# Detect handler coupling: domain imports from handlers
grep -rn "from.*handlers import\|import.*handler" src/domain/
```

### Repository Pattern Quality Signals

| Signal | Good | Bad |
|--------|------|-----|
| Domain service unit tests require DB connection | No | Yes |
| SQL/ORM queries in domain/service layer | None | `session.query(...)` in service |
| Repository has > 20 methods | Review (SRP) | Likely splitting needed |
| `InMemory` implementation exists for tests | Yes | No (mock-only testing) |

```bash
# Detect ORM in domain layer
grep -rn "session\|query\|\.filter\|\.objects\." src/domain/ src/application/
```

---

## Test Coverage as Pattern Proxy

### Unit Test Ratio (Domain Purity)

```bash
# Count test files vs source files in domain layer
ls src/domain/*.py | wc -l
ls tests/unit/domain/*.py | wc -l
# Target: 1:1 or better
```

If domain layer unit tests have high coverage but require extensive mocking (`@patch` calls > 3 per test), Repository and Strategy patterns are incomplete.

### Integration Test Boundary

```bash
pytest tests/unit/ -v --tb=short     # zero infrastructure — fast, < 5s
pytest tests/integration/ -v         # needs DB/Redis/queue — slower, CI only
```

Pattern quality is demonstrated when unit tests run without any infrastructure. Target: domain layer tests < 5 seconds total.

---

## Static Analysis for Pattern Detection

### `ast` Module — Detecting Anti-Patterns Programmatically

```python
import ast
import sys
from pathlib import Path

def find_isinstance_in_domain(path: str) -> list[tuple[str, int]]:
    """Find isinstance() calls in domain layer — LSP/Strategy smell."""
    violations = []
    for pyfile in Path(path).rglob("*.py"):
        tree = ast.parse(pyfile.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "isinstance":
                    violations.append((str(pyfile), node.lineno))
    return violations

violations = find_isinstance_in_domain("src/domain")
if violations:
    print("isinstance() in domain layer (Strategy/Observer pattern smell):")
    for path, line in violations:
        print(f"  {path}:{line}")
    sys.exit(1)
```

### Detecting Missing `@functools.wraps`

```python
def find_unwrapped_decorators(path: str) -> list[tuple[str, int]]:
    """Find inner 'wrapper' functions that don't call functools.wraps."""
    violations = []
    for pyfile in Path(path).rglob("*.py"):
        tree = ast.parse(pyfile.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "wrapper":
                has_wraps = any(
                    isinstance(stmt, ast.Expr) and
                    isinstance(stmt.value, ast.Call) and
                    "wraps" in ast.dump(stmt.value)
                    for stmt in ast.walk(node)
                )
                if not has_wraps:
                    violations.append((str(pyfile), node.lineno))
    return violations
```

---

## Benchmark: Testability Before/After Pattern Application

The clearest measure of pattern ROI is test execution time and infrastructure requirements.

| Scenario | Before Pattern | After Pattern |
|----------|---------------|--------------|
| Unit test suite runtime | 45s (hits DB) | 2s (InMemory) |
| Test DB setup required | Yes | No |
| Mocks per test (avg) | 6 | 1 |
| Adding new payment provider | 3 files changed | 1 new file |
| Adding new notification channel | `NotificationService` modified | 1 new class registered |

Track these metrics via CI timing (`pytest --durations=10`) and PR diff size for feature additions.

---

## Code Review Checklist per Pattern

**Strategy**
- [ ] Is the Strategy injected via constructor (not created inside the using class)?
- [ ] Is there a `Protocol` or `ABC` defining the strategy interface?
- [ ] Can the strategy be swapped without modifying the context class?

**Factory**
- [ ] Does the factory return an abstract type (`Protocol`), not a concrete type?
- [ ] Is there a clear error message for unknown types?
- [ ] Adding a new product type: does it require modifying the factory function? (Should be no for registry-based)

**Decorator**
- [ ] Does every wrapper function use `@functools.wraps`?
- [ ] Is the decorator composable (works when stacked with other decorators)?
- [ ] For GoF structural: does the decorator implement the same Protocol as the wrapped object?

**Observer**
- [ ] Are event types immutable (`@dataclass(frozen=True)`)?
- [ ] Does the publisher have zero imports from handler modules?
- [ ] Does the event bus catch and log handler exceptions rather than propagating them?

**Repository**
- [ ] Does the `Protocol` return domain objects, not ORM rows?
- [ ] Does an `InMemory` implementation exist for tests?
- [ ] Is there zero SQL/ORM code in the domain/application layer?
