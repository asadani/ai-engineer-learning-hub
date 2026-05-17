# Products & Tools

## Static Analysis & Linting

### mypy
- **What**: Static type checker; enforces `Protocol` contracts, catches LSP violations at type level, validates DIP (if you annotate abstractions correctly)
- **SOLID relevance**: DIP and LSP violations often manifest as type errors — mypy catches them at development time
- **Key flags**: `--strict` (enables all checks), `--disallow-untyped-defs`, `--check-untyped-defs`
- **Limitation**: Does not catch behavioral LSP violations (only signature mismatches); does not enforce SRP

```bash
mypy src/ --strict --ignore-missing-imports
```

### Ruff
- **What**: Extremely fast Python linter (replaces flake8 + isort + many plugins); written in Rust
- **SOLID relevance**: Rules `B` (bugbear), `C90` (McCabe complexity), `N` (naming) catch SRP-adjacent issues; complexity thresholds flag classes/functions doing too much
- **2026 status**: Defacto standard; has largely displaced flake8, isort, pyupgrade in new projects

```toml
# pyproject.toml
[tool.ruff]
select = ["E", "F", "B", "C90", "N", "UP"]
[tool.ruff.mccabe]
max-complexity = 10  # flag functions with CC > 10
```

### pylint
- **What**: Deep static analysis; checks for too many arguments, too many instance attributes, too many public methods
- **SOLID relevance**: `too-many-instance-attributes` (SRP), `too-many-public-methods` (SRP), `too-many-arguments` (ISP)
- **Tradeoff**: Slow; high false-positive rate on Pythonic code; often requires extensive `.pylintrc` tuning

```ini
# .pylintrc
[DESIGN]
max-args = 7
max-attributes = 10
max-public-methods = 20
```

### Radon
- **What**: Computes cyclomatic complexity (CC), maintainability index (MI), raw metrics (LOC, SLOC)
- **SOLID relevance**: High CC in a single function/class = SRP violation; `radon cc` with grade F = refactor target

```bash
radon cc src/ -s -a          # complexity with scores
radon mi src/ -s             # maintainability index
radon cc src/ --min B        # show only high-complexity items
```

### SonarQube / SonarCloud
- **What**: Enterprise code quality platform; detects code smells, duplications, complexity, security hotspots
- **SOLID relevance**: "God class" smell = SRP violation; "Switch statement" smell = OCP violation; coupling metrics for DIP
- **When to use**: Team codebases, CI/CD quality gates, regulated industries; overkill for solo projects

---

## Testing Frameworks (SOLID enables these)

### pytest
- **Connection to SOLID**: SRP and DIP make code unit-testable; if you can't write a focused pytest unit test for a class without spinning up infrastructure, that's a DIP/SRP smell
- **Fixtures**: implement DIP naturally — inject dependencies per test via `@pytest.fixture`

```python
@pytest.fixture
def order_service():
    return OrderService(
        repo=InMemoryOrderRepository(),
        notifier=FakeNotifier(),
    )

def test_place_order_saves_to_repo(order_service: OrderService):
    order = Order(id="123", user=User(email="a@b.com"))
    order_service.place_order(order)
    assert order_service._repo.get("123") == order
```

### pytest-mock / unittest.mock
- **Connection to SOLID**: Heavy mocking is a sign of DIP violations — if you mock `requests.get` directly, you're not inverting the dependency. DIP-compliant code injects `HttpClient(Protocol)`, which you replace with a fake, not a mock.
- **When mocks are appropriate**: External systems you can't fake (time, random, OS); third-party clients with complex state

### hypothesis
- **Connection to LSP**: Property-based testing is the strongest tool for catching LSP violations — generate random inputs and assert that all subtypes satisfy the same postconditions as the base

```python
from hypothesis import given, strategies as st

@given(st.integers(min_value=1), st.integers(min_value=1))
def test_all_shapes_area_positive(width, height):
    for ShapeClass in [Rectangle, Square, Triangle]:
        shape = ShapeClass(width, height)
        assert shape.area() > 0  # LSP: all subtypes satisfy this postcondition
```

---

## Frameworks Embodying SOLID Principles

### FastAPI
- **DIP**: `Depends()` system is built-in dependency injection — handlers declare abstract dependencies, FastAPI resolves them
- **ISP**: Pydantic models as narrow request/response schemas — each endpoint gets exactly the fields it needs
- **SRP**: Route handlers are thin; business logic lives in injected services

### SQLAlchemy (with Repository pattern)
- **DIP**: Define `Repository(Protocol)` → implement with `SQLAlchemyUserRepository`; swap to `InMemoryUserRepository` in tests
- **OCP**: SQLAlchemy's event system (`@event.listens_for`) lets you extend DB behavior without modifying model classes

### Django (with caveats)
- **SRP**: Django's MTV (Model-Template-View) is an attempt at SRP; fat models and fat views are common Django SRP violations
- **DIP**: Django's signal system is a form of OCP/DIP — attach handlers without modifying signal senders
- **Note**: Django's tight coupling to its ORM makes DIP at the repository level harder — `django-injector` helps

### Celery
- **OCP/DIP**: Tasks are registered handlers; new task types extend the system without modifying the worker. Abstract base tasks via `bind=True` and base class for shared behavior.

---

## Code Architecture Tools

### `dependency-injector`
- Python DI container library; declarative wiring of object graphs
- Supports `Factory`, `Singleton`, `Resource` (with lifecycle), `Callable` providers
- Works with FastAPI, Flask, Django, CLI apps

### `lagom`
- Lightweight Python DI container; auto-wires based on type hints — zero configuration for simple cases
- Less ceremonial than `dependency-injector` for medium-sized projects

### `punq`
- Minimalist DI container; ~200 LOC; good for understanding DI container internals

### `returns` (dry-python)
- Functional SOLID: `Result`, `Maybe`, `IO` containers that make function effects explicit — a functional take on DIP and SRP at the function level

---

## Architecture Patterns That Encode SOLID

| Pattern | SOLID Principles Encoded |
|---------|--------------------------|
| **Repository Pattern** | DIP (abstract data access), SRP (data access separated from business logic) |
| **Service Layer** | SRP (orchestration separated from domain logic) |
| **Command/Query Separation (CQS)** | SRP (reads separated from writes), ISP (callers depend only on what they need) |
| **Strategy Pattern** | OCP (new algorithms without modifying context), DIP |
| **Observer/Event Pattern** | OCP (new handlers without modifying emitters), DIP |
| **Decorator Pattern** | OCP (extend behavior without modifying decorated class) |
| **Hexagonal Architecture (Ports & Adapters)** | DIP (domain depends on ports/protocols, not adapters), SRP |
| **Plugin System** | OCP (new plugins without modifying core), DIP |
