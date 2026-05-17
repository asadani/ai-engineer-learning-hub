# Key Technical Concepts

## Pattern 1: Strategy

### Intent
Define a family of algorithms, encapsulate each one, and make them interchangeable. Lets the algorithm vary independently from clients that use it.

### Structure
```
Context ──── holds ──── Strategy(Protocol)
                              ▲
              ┌───────────────┼───────────────┐
       ConcreteStrategyA  ConcreteStrategyB  ConcreteStrategyC
```

### Python Implementation

```python
from typing import Protocol
from decimal import Decimal
from dataclasses import dataclass

@dataclass
class Order:
    subtotal: Decimal
    customer_tier: str

class DiscountStrategy(Protocol):
    def calculate(self, order: Order) -> Decimal: ...

class NoDiscount:
    def calculate(self, order: Order) -> Decimal:
        return Decimal("0")

class PremiumDiscount:
    def calculate(self, order: Order) -> Decimal:
        return order.subtotal * Decimal("0.15")

class VolumeDiscount:
    def __init__(self, threshold: Decimal, rate: Decimal) -> None:
        self._threshold = threshold
        self._rate = rate

    def calculate(self, order: Order) -> Decimal:
        if order.subtotal >= self._threshold:
            return order.subtotal * self._rate
        return Decimal("0")

class PricingEngine:
    def __init__(self, strategy: DiscountStrategy) -> None:
        self._strategy = strategy

    # Strategy can also be swapped at runtime
    def set_strategy(self, strategy: DiscountStrategy) -> None:
        self._strategy = strategy

    def final_price(self, order: Order) -> Decimal:
        discount = self._strategy.calculate(order)
        return order.subtotal - discount
```

### Functional Strategy (Pythonic Alternative)

When strategies are simple single-method callables, use `Callable` directly:

```python
from typing import Callable

DiscountFn = Callable[[Order], Decimal]

def no_discount(order: Order) -> Decimal:
    return Decimal("0")

def premium_discount(order: Order) -> Decimal:
    return order.subtotal * Decimal("0.15")

class PricingEngine:
    def __init__(self, discount_fn: DiscountFn = no_discount) -> None:
        self._discount_fn = discount_fn

    def final_price(self, order: Order) -> Decimal:
        return order.subtotal - self._discount_fn(order)
```

Use a class-based Strategy when the strategy carries state or configuration. Use `Callable` when it's a pure function.

### Key Mechanics
- **Context** holds a reference to the strategy interface, never to concrete strategies
- **Strategy selection** happens at the composition root (main/DI container) or via a Factory
- **Runtime swapping** (`set_strategy`) enables dynamic behavior change — useful for feature flags, A/B testing
- Eliminates `if/elif` chains on type/enum values — each branch becomes a class

---

## Pattern 2: Factory Method & Abstract Factory

### Intent
**Factory Method**: Define an interface for creating an object, but let subclasses decide which class to instantiate.
**Abstract Factory**: Provide an interface for creating families of related objects without specifying concrete classes.

### Factory Method — Python

The "factory method" in Python is most naturally a classmethod, a standalone function, or a `__init_subclass__` registry — not necessarily the subclass override version from GoF.

```python
from typing import Protocol
from enum import Enum

class StorageBackend(Protocol):
    def save(self, key: str, data: bytes) -> None: ...
    def load(self, key: str) -> bytes: ...

class S3Backend:
    def __init__(self, bucket: str) -> None: self._bucket = bucket
    def save(self, key: str, data: bytes) -> None: ...
    def load(self, key: str) -> bytes: ...

class LocalFileBackend:
    def __init__(self, base_dir: str) -> None: self._base_dir = base_dir
    def save(self, key: str, data: bytes) -> None: ...
    def load(self, key: str) -> bytes: ...

class InMemoryBackend:
    def __init__(self) -> None: self._store: dict[str, bytes] = {}
    def save(self, key: str, data: bytes) -> None: self._store[key] = data
    def load(self, key: str) -> bytes: return self._store[key]

# Factory function (most common Pythonic form)
def create_storage_backend(backend_type: str, **kwargs) -> StorageBackend:
    backends = {
        "s3": lambda: S3Backend(bucket=kwargs["bucket"]),
        "local": lambda: LocalFileBackend(base_dir=kwargs["base_dir"]),
        "memory": lambda: InMemoryBackend(),
    }
    if backend_type not in backends:
        raise ValueError(f"Unknown backend: {backend_type!r}. Valid: {list(backends)}")
    return backends[backend_type]()
```

### Self-Registering Factory (OCP-compliant)

Using `__init_subclass__` to auto-register without modifying the factory:

```python
class StorageBackend:
    _registry: dict[str, type] = {}

    def __init_subclass__(cls, backend_type: str, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        StorageBackend._registry[backend_type] = cls

    @classmethod
    def create(cls, backend_type: str, **kwargs) -> "StorageBackend":
        if backend_type not in cls._registry:
            raise ValueError(f"Unknown backend: {backend_type!r}")
        return cls._registry[backend_type](**kwargs)

class S3Backend(StorageBackend, backend_type="s3"):
    def __init__(self, bucket: str) -> None: ...

class LocalFileBackend(StorageBackend, backend_type="local"):
    def __init__(self, base_dir: str) -> None: ...

# Adding a new backend: just define the class. Factory never changes.
backend = StorageBackend.create("s3", bucket="my-bucket")
```

### Abstract Factory — Python

Abstract Factory creates families of related objects. Most relevant when you need an entire ecosystem of compatible objects (e.g., test doubles vs. production objects).

```python
from typing import Protocol

class NotificationFactory(Protocol):
    def create_email_sender(self) -> EmailSender: ...
    def create_sms_sender(self) -> SmsSender: ...
    def create_push_sender(self) -> PushSender: ...

class ProductionNotificationFactory:
    def create_email_sender(self) -> EmailSender:
        return SesEmailSender(region="us-east-1")
    def create_sms_sender(self) -> SmsSender:
        return TwilioSmsSender(account_sid=settings.TWILIO_SID)
    def create_push_sender(self) -> PushSender:
        return FcmPushSender(api_key=settings.FCM_KEY)

class TestNotificationFactory:
    def create_email_sender(self) -> EmailSender:
        return CapturingEmailSender()
    def create_sms_sender(self) -> SmsSender:
        return CapturingSmsProvider()
    def create_push_sender(self) -> PushSender:
        return NullPushSender()

# In application startup
factory: NotificationFactory = (
    TestNotificationFactory() if settings.TESTING
    else ProductionNotificationFactory()
)
```

---

## Pattern 3: Decorator

### Intent
Attach additional responsibilities to an object dynamically. Provides a flexible alternative to subclassing for extending functionality.

### Two Decorator Concepts in Python
1. **GoF Structural Decorator**: Wraps an object with the same interface, adding behavior
2. **Python Language Decorator**: `@decorator` syntax — a callable that wraps a callable

Both are genuinely useful and distinct.

### GoF Structural Decorator

```python
from typing import Protocol

class DataProcessor(Protocol):
    def process(self, data: str) -> str: ...

class BaseProcessor:
    def process(self, data: str) -> str:
        return data.strip()

class LoggingDecorator:
    def __init__(self, wrapped: DataProcessor) -> None:
        self._wrapped = wrapped

    def process(self, data: str) -> str:
        import logging, time
        start = time.perf_counter()
        result = self._wrapped.process(data)
        elapsed = (time.perf_counter() - start) * 1000
        logging.info("process() took %.2fms, output_len=%d", elapsed, len(result))
        return result

class EncryptionDecorator:
    def __init__(self, wrapped: DataProcessor) -> None:
        self._wrapped = wrapped

    def process(self, data: str) -> str:
        result = self._wrapped.process(data)
        return encrypt(result)  # adds encryption layer

class ValidationDecorator:
    def __init__(self, wrapped: DataProcessor, max_len: int = 1000) -> None:
        self._wrapped = wrapped
        self._max_len = max_len

    def process(self, data: str) -> str:
        if len(data) > self._max_len:
            raise ValueError(f"Input too long: {len(data)} > {self._max_len}")
        return self._wrapped.process(data)

# Composing decorators (order matters: validation runs first, then logging, then base)
processor: DataProcessor = ValidationDecorator(
    LoggingDecorator(
        BaseProcessor()
    )
)
```

### Python Language Decorator (functional)

```python
import functools
import time
import logging
from typing import Callable, TypeVar, ParamSpec

P = ParamSpec("P")
T = TypeVar("T")

def retry(max_attempts: int = 3, exceptions: tuple = (Exception,)):
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_exc = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    logging.warning("Attempt %d/%d failed: %s", attempt + 1, max_attempts, e)
            raise last_exc
        return wrapper
    return decorator

def timed(func: Callable[P, T]) -> Callable[P, T]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        start = time.perf_counter()
        result = func(*args, **kwargs)
        logging.info("%s took %.3fs", func.__qualname__, time.perf_counter() - start)
        return result
    return wrapper

@retry(max_attempts=3, exceptions=(ConnectionError, TimeoutError))
@timed
def fetch_embeddings(texts: list[str]) -> list[list[float]]:
    return embedding_client.embed(texts)
```

**Critical detail**: `@functools.wraps(func)` is mandatory — it preserves `__name__`, `__doc__`, `__annotations__`, and `__wrapped__`. Without it, the decorator breaks `help()`, mypy inference, and logging that uses `func.__qualname__`.

### Class-Based Decorator (stateful)

```python
class RateLimiter:
    def __init__(self, calls_per_second: float) -> None:
        self._min_interval = 1.0 / calls_per_second
        self._last_call: float = 0.0

    def __call__(self, func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            now = time.monotonic()
            wait = self._min_interval - (now - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()
            return func(*args, **kwargs)
        return wrapper

@RateLimiter(calls_per_second=10)
def call_llm(prompt: str) -> str: ...
```

---

## Pattern 4: Observer

### Intent
Define a one-to-many dependency between objects so that when one object changes state, all its dependents are notified and updated automatically.

### Structure
```
Subject (Observable) ─── maintains ─── list[Observer]
      │                                      ▲
      │ notifies on state change        ┌────┴────┐
      ▼                            ObserverA  ObserverB
   Event/notification
```

### Python Implementation

```python
from typing import Protocol, TypeVar, Generic
from dataclasses import dataclass, field
from collections import defaultdict

# Typed event system
@dataclass(frozen=True)
class OrderPlaced:
    order_id: str
    customer_email: str
    total: float

@dataclass(frozen=True)
class PaymentFailed:
    order_id: str
    reason: str

Event = OrderPlaced | PaymentFailed  # Union type as event discriminant

class EventHandler(Protocol):
    def handle(self, event: Event) -> None: ...

class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[type, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: type, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

    def publish(self, event: Event) -> None:
        for handler in self._handlers.get(type(event), []):
            handler.handle(event)

# Handlers
class WelcomeEmailHandler:
    def handle(self, event: Event) -> None:
        if isinstance(event, OrderPlaced):
            send_email(event.customer_email, "Order Confirmed", f"Order {event.order_id}")

class AnalyticsHandler:
    def handle(self, event: Event) -> None:
        if isinstance(event, OrderPlaced):
            analytics.track("order_placed", {"order_id": event.order_id})

class InventoryHandler:
    def handle(self, event: Event) -> None:
        if isinstance(event, OrderPlaced):
            inventory_service.reserve(event.order_id)

# Wiring
bus = EventBus()
bus.subscribe(OrderPlaced, WelcomeEmailHandler())
bus.subscribe(OrderPlaced, AnalyticsHandler())
bus.subscribe(OrderPlaced, InventoryHandler())

# Domain code publishes, never knows about handlers
bus.publish(OrderPlaced(order_id="o-123", customer_email="x@y.com", total=99.0))
```

### Auto-Registering Observer via `__init_subclass__`

```python
class DomainEventHandler:
    _registry: dict[type, list[type]] = defaultdict(list)

    def __init_subclass__(cls, handles: type, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        DomainEventHandler._registry[handles].append(cls)

    def handle(self, event) -> None:
        raise NotImplementedError

class SendConfirmationEmail(DomainEventHandler, handles=OrderPlaced):
    def handle(self, event: OrderPlaced) -> None:
        send_email(event.customer_email, ...)

# All handlers registered automatically; event bus iterates _registry
```

### Async Observer (for I/O-bound handlers)

```python
import asyncio

class AsyncEventBus:
    def __init__(self) -> None:
        self._handlers: dict[type, list] = defaultdict(list)

    def subscribe(self, event_type: type, handler) -> None:
        self._handlers[event_type].append(handler)

    async def publish(self, event) -> None:
        handlers = self._handlers.get(type(event), [])
        await asyncio.gather(*(h.handle(event) for h in handlers))
```

---

## Pattern 5: Repository

### Intent
Mediates between the domain and data mapping layers using a collection-like interface for accessing domain objects. Decouples business logic from persistence mechanism.

### Structure
```
Domain Service ── depends on ── Repository(Protocol) ── implemented by ── SqlAlchemyRepo
                                                                      └── InMemoryRepo (tests)
                                                                      └── DynamoRepo
```

### Python Implementation

```python
from typing import Protocol
from dataclasses import dataclass
from uuid import UUID

@dataclass
class User:
    id: UUID
    email: str
    name: str
    tier: str

class UserRepository(Protocol):
    def save(self, user: User) -> None: ...
    def get(self, user_id: UUID) -> User | None: ...
    def get_by_email(self, email: str) -> User | None: ...
    def find_by_tier(self, tier: str) -> list[User]: ...
    def delete(self, user_id: UUID) -> None: ...

# SQLAlchemy implementation
class SqlAlchemyUserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, user: User) -> None:
        orm_user = UserORM.from_domain(user)
        self._session.merge(orm_user)

    def get(self, user_id: UUID) -> User | None:
        row = self._session.get(UserORM, str(user_id))
        return row.to_domain() if row else None

    def get_by_email(self, email: str) -> User | None:
        row = self._session.query(UserORM).filter_by(email=email).first()
        return row.to_domain() if row else None

    def find_by_tier(self, tier: str) -> list[User]:
        rows = self._session.query(UserORM).filter_by(tier=tier).all()
        return [r.to_domain() for r in rows]

    def delete(self, user_id: UUID) -> None:
        self._session.query(UserORM).filter_by(id=str(user_id)).delete()

# In-memory implementation for tests (zero infrastructure)
class InMemoryUserRepository:
    def __init__(self) -> None:
        self._store: dict[UUID, User] = {}

    def save(self, user: User) -> None:
        self._store[user.id] = user

    def get(self, user_id: UUID) -> User | None:
        return self._store.get(user_id)

    def get_by_email(self, email: str) -> User | None:
        return next((u for u in self._store.values() if u.email == email), None)

    def find_by_tier(self, tier: str) -> list[User]:
        return [u for u in self._store.values() if u.tier == tier]

    def delete(self, user_id: UUID) -> None:
        self._store.pop(user_id, None)
```

### Unit of Work Pattern (Repository Companion)

Repository handles single-aggregate access; Unit of Work handles transaction boundaries across multiple repositories:

```python
class UnitOfWork(Protocol):
    users: UserRepository
    orders: OrderRepository

    def __enter__(self) -> "UnitOfWork": ...
    def __exit__(self, *args) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...

class SqlAlchemyUoW:
    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def __enter__(self) -> "SqlAlchemyUoW":
        self._session = self._session_factory()
        self.users = SqlAlchemyUserRepository(self._session)
        self.orders = SqlAlchemyOrderRepository(self._session)
        return self

    def __exit__(self, exc_type, *args) -> None:
        if exc_type:
            self.rollback()
        self._session.close()

    def commit(self) -> None: self._session.commit()
    def rollback(self) -> None: self._session.rollback()

# Usage
def transfer_user_to_premium(user_id: UUID, uow: UnitOfWork) -> None:
    with uow:
        user = uow.users.get(user_id)
        user.tier = "premium"
        uow.users.save(user)
        uow.orders.update_tier_discount(user_id, "premium")
        uow.commit()  # both operations in one transaction
```
