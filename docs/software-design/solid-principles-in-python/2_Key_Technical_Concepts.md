# Key Technical Concepts

## S — Single Responsibility Principle (SRP)

> A class should have one, and only one, reason to change.

"Reason to change" maps to **actor** — a person or system that requests the change. SRP says one class should serve one actor.

### Violation

```python
class UserService:
    def get_user(self, user_id: int) -> dict:
        # DB concern
        return db.execute("SELECT * FROM users WHERE id = ?", user_id)

    def send_welcome_email(self, user: dict) -> None:
        # Email concern
        smtp.send(user["email"], "Welcome!", "Hello...")

    def export_to_csv(self, users: list[dict]) -> str:
        # Reporting concern
        return "\n".join(",".join(str(v) for v in u.values()) for u in users)
```

Three actors: DB admin (changes schema), marketing (changes email copy), reporting team (changes export format). One change to any of them requires modifying this class.

### Compliant

```python
class UserRepository:
    def get(self, user_id: int) -> User: ...
    def save(self, user: User) -> None: ...

class WelcomeEmailSender:
    def send(self, user: User) -> None: ...

class UserCsvExporter:
    def export(self, users: list[User]) -> str: ...
```

### Python-Specific Notes
- Use `dataclass` for pure data objects (no behavior) — they're inherently SRP-compliant.
- A common SRP smell in Python: a module with 10+ top-level functions across unrelated concerns. Split into submodules.
- `__init__.py` that re-exports from multiple submodules is fine; it doesn't violate SRP itself.

---

## O — Open/Closed Principle (OCP)

> Software entities should be open for extension but closed for modification.

The goal: add new behavior without editing existing, tested code. Achieved through abstraction — the abstraction is closed (stable), implementations are open (extensible).

### Violation

```python
class ReportFormatter:
    def format(self, data: dict, format_type: str) -> str:
        if format_type == "json":
            return json.dumps(data)
        elif format_type == "csv":
            return ",".join(str(v) for v in data.values())
        elif format_type == "xml":  # adding a new format requires modifying this class
            ...
```

Every new format type requires a `elif` branch in existing code — modifying tested, deployed logic.

### Compliant (using Protocol)

```python
from typing import Protocol

class Formatter(Protocol):
    def format(self, data: dict) -> str: ...

class JsonFormatter:
    def format(self, data: dict) -> str:
        return json.dumps(data)

class CsvFormatter:
    def format(self, data: dict) -> str:
        return ",".join(str(v) for v in data.values())

class ReportService:
    def __init__(self, formatter: Formatter) -> None:
        self._formatter = formatter

    def generate(self, data: dict) -> str:
        return self._formatter.format(data)
```

Adding XML support: write `XmlFormatter`, pass it in. `ReportService` never changes.

### Python-Specific Patterns for OCP
- **`functools.singledispatch`**: extend behavior by type without modifying existing dispatch logic
- **Plugin registries**: `dict[str, Callable]` as a dispatch table — register new handlers without modifying the router
- **`__init_subclass__`**: auto-register subclasses into a registry on class definition

```python
class Handler:
    _registry: dict[str, type] = {}

    def __init_subclass__(cls, event_type: str, **kwargs):
        super().__init_subclass__(**kwargs)
        Handler._registry[event_type] = cls

class OrderCreatedHandler(Handler, event_type="order.created"):
    def handle(self, event: dict) -> None: ...

# New handlers added without modifying routing logic
```

---

## L — Liskov Substitution Principle (LSP)

> If S is a subtype of T, objects of type T may be replaced with objects of type S without altering correctness.

Barbara Liskov (1987). The practical implication: a subclass must honor the **contract** of its base class — not just its interface, but its behavioral invariants, pre/post conditions.

### Violation

```python
class Rectangle:
    def set_width(self, w: int) -> None: self._width = w
    def set_height(self, h: int) -> None: self._height = h
    def area(self) -> int: return self._width * self._height

class Square(Rectangle):
    def set_width(self, w: int) -> None:
        self._width = w
        self._height = w  # maintains square invariant, but breaks Rectangle contract

    def set_height(self, h: int) -> None:
        self._width = h
        self._height = h
```

```python
def resize(rect: Rectangle) -> None:
    rect.set_width(5)
    rect.set_height(10)
    assert rect.area() == 50  # passes for Rectangle, FAILS for Square
```

Square is geometrically a rectangle but is not a `Rectangle` in the Liskov sense.

### LSP Contract Rules
1. **Preconditions** cannot be strengthened in a subclass (accept at least what the parent accepts)
2. **Postconditions** cannot be weakened (guarantee at least what the parent guarantees)
3. **Invariants** of the base class must be preserved
4. **Exceptions**: subclass may only throw exceptions the parent throws, or subtypes of them

### Python-Specific Notes
- `@override` decorator (Python 3.12+, `typing_extensions` for earlier) makes overrides explicit and mypy-checkable
- Abstract base classes (`ABC`) define the contract; mypy enforces pre/post conditions partially via type annotations
- Duck typing makes LSP violations harder to spot — a class that "looks like" a duck may violate behavioral contracts silently

```python
from typing import override

class BaseNotifier:
    def notify(self, message: str) -> None: ...

class SlackNotifier(BaseNotifier):
    @override
    def notify(self, message: str) -> None:  # mypy will catch signature mismatches
        slack_client.post(message)
```

---

## I — Interface Segregation Principle (ISP)

> Clients should not be forced to depend on interfaces they do not use.

Fat interfaces force implementors to stub out methods they don't need, creating dead code and misleading contracts.

### Violation

```python
from abc import ABC, abstractmethod

class Worker(ABC):
    @abstractmethod
    def work(self) -> None: ...
    @abstractmethod
    def eat(self) -> None: ...
    @abstractmethod
    def sleep(self) -> None: ...

class Robot(Worker):
    def work(self) -> None: ...
    def eat(self) -> None: raise NotImplementedError("Robots don't eat")  # forced stub
    def sleep(self) -> None: raise NotImplementedError("Robots don't sleep")
```

### Compliant (segregated protocols)

```python
from typing import Protocol

class Workable(Protocol):
    def work(self) -> None: ...

class Eatable(Protocol):
    def eat(self) -> None: ...

class Human:
    def work(self) -> None: ...
    def eat(self) -> None: ...

class Robot:
    def work(self) -> None: ...  # only implements what it needs

def assign_work(worker: Workable) -> None:
    worker.work()  # Robot satisfies Workable without any stubs
```

### Python-Specific Notes
- `typing.Protocol` with structural subtyping is the idiomatic Python ISP implementation — no explicit inheritance required
- `Protocol` can be composed: `class WorkingEater(Workable, Eatable, Protocol): ...`
- `runtime_checkable` decorator enables `isinstance` checks against Protocols: `@runtime_checkable class Workable(Protocol): ...`
- ISP applies to function signatures too — a function taking a full `User` object when it only needs `user.email` is an ISP violation. Pass `email: str` instead.

---

## D — Dependency Inversion Principle (DIP)

> High-level modules should not depend on low-level modules. Both should depend on abstractions. Abstractions should not depend on details. Details should depend on abstractions.

This is the most architecturally impactful SOLID principle. It drives the **hexagonal/clean architecture** pattern: core domain logic depends on abstract ports; infrastructure (DB, HTTP, messaging) implements those ports.

### Violation

```python
class OrderService:
    def __init__(self) -> None:
        self._repo = PostgresOrderRepository()  # hard-coded concrete dependency
        self._notifier = SmtpEmailNotifier()     # hard-coded concrete dependency

    def place_order(self, order: Order) -> None:
        self._repo.save(order)
        self._notifier.send(order.user.email, "Order placed")
```

`OrderService` (high-level) directly depends on `PostgresOrderRepository` (low-level). Swapping to DynamoDB requires modifying `OrderService`.

### Compliant

```python
from typing import Protocol

class OrderRepository(Protocol):
    def save(self, order: Order) -> None: ...
    def get(self, order_id: str) -> Order: ...

class Notifier(Protocol):
    def send(self, recipient: str, message: str) -> None: ...

class OrderService:
    def __init__(self, repo: OrderRepository, notifier: Notifier) -> None:
        self._repo = repo
        self._notifier = notifier

    def place_order(self, order: Order) -> None:
        self._repo.save(order)
        self._notifier.send(order.user.email, "Order placed")

# Wiring (composition root — main.py or DI container)
service = OrderService(
    repo=PostgresOrderRepository(db_url=settings.DB_URL),
    notifier=SmtpEmailNotifier(smtp_config=settings.SMTP),
)
```

In tests: `OrderService(repo=InMemoryOrderRepository(), notifier=FakeNotifier())` — no mocking framework needed.

### Python DI Patterns

**Constructor injection** (preferred): dependencies passed at `__init__` — explicit, testable, no magic.

**`dependency-injector` library**: declarative wiring for large apps with many components.

```python
from dependency_injector import containers, providers

class Container(containers.DeclarativeContainer):
    db = providers.Singleton(PostgresDB, url=config.db_url)
    order_repo = providers.Factory(PostgresOrderRepository, db=db)
    notifier = providers.Factory(SmtpEmailNotifier, config=config.smtp)
    order_service = providers.Factory(OrderService, repo=order_repo, notifier=notifier)
```

**FastAPI `Depends()`**: built-in DI for HTTP handlers — each route declares its dependencies, FastAPI resolves and injects them per request.

```python
def get_order_service(db: Session = Depends(get_db)) -> OrderService:
    return OrderService(repo=PostgresOrderRepository(db), notifier=SmtpNotifier())

@router.post("/orders")
async def create_order(order: OrderRequest, svc: OrderService = Depends(get_order_service)):
    svc.place_order(order)
```
