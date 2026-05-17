# Tradeoffs & Comparisons

## Strategy vs. Template Method

Both solve the "vary one part of an algorithm" problem but with opposite inversion:

| Dimension | Strategy | Template Method |
|-----------|---------|----------------|
| **Mechanism** | Composition — inject the variant | Inheritance — override the variant |
| **Coupling** | Loose (Context doesn't know concrete Strategy) | Tight (subclass coupled to parent) |
| **Runtime swapping** | Yes — swap strategy object | No — fixed at class definition |
| **Python idiom** | Protocol + constructor injection, or Callable | ABC + `@abstractmethod` |
| **Testability** | Inject fake strategy — no subclassing needed | Must subclass to test; partial isolation |
| **Pythonic preference** | Strongly preferred | Only for true IS-A hierarchies |

**When Template Method is still valid**: When the skeleton algorithm is complex, the invariant parts share substantial code, and variation points are few. Django's class-based views (`get_queryset`, `get_context_data`) are Template Method — the framework defines the HTTP lifecycle, you override the hooks.

---

## Factory Method vs. Abstract Factory vs. Builder

| Dimension | Factory Method | Abstract Factory | Builder |
|-----------|---------------|-----------------|---------|
| **Creates** | One product type | Family of related products | One complex product, step by step |
| **Complexity** | Low | Medium | Medium-High |
| **Use when** | One object type, multiple variants | Multiple coordinated object types | Object with many optional/required parts |
| **Python form** | Function or classmethod | Class with multiple factory methods | Fluent `Builder` class or `dataclass` + `__post_init__` |
| **Example** | `create_storage_backend("s3")` | `NotificationFactory.create_email_sender()` + `create_sms_sender()` | `QueryBuilder().select("users").where(tier="premium").limit(10).build()` |

**Builder vs. `dataclass` with defaults**: For simple objects, `dataclass` with optional fields and `__post_init__` validation replaces Builder entirely. Use explicit Builder only when construction is multi-step, order-dependent, or produces different representations (SQL string vs. ORM query).

---

## GoF Decorator vs. Python `@decorator` Syntax

This is the most Python-specific distinction and frequently misunderstood:

| Dimension | GoF Structural Decorator | Python `@decorator` |
|-----------|--------------------------|---------------------|
| **What it wraps** | Object (same interface) | Function or class |
| **Polymorphism** | Yes — wrapped and wrapper share Protocol | No — different types |
| **Composition** | Nested wrapping at runtime | Stacked at definition time |
| **State** | Wrapper can hold state | Closure or class-based decorator holds state |
| **Use case** | Add behavior to objects (logging wrapper, caching wrapper for services) | Add cross-cutting concerns to functions (retry, rate limit, timing) |
| **Replaceability** | Can swap decorator at runtime | Fixed at function definition |

```python
# GoF: wrapping an object — swap at runtime
processor = LoggingDecorator(EncryptionDecorator(BaseProcessor()))
processor = LoggingDecorator(BaseProcessor())  # runtime swap, same interface

# Python @decorator: wrapping a function — fixed at definition
@retry(3)  # cannot un-retry at runtime
@timed
def fetch_data(): ...
```

**When to use which**: GoF Structural Decorator for service/object-level cross-cutting concerns where runtime configurability matters. Python `@decorator` for function-level cross-cutting concerns (logging, caching, retry, auth) that are fixed per function.

---

## Observer vs. Event Bus vs. Message Queue

All three decouple producers from consumers, but at different scopes and with different guarantees:

| Dimension | In-Process Observer | In-Process Event Bus | Message Queue (RabbitMQ/SQS) |
|-----------|--------------------|-----------------------|------------------------------|
| **Scope** | Single object | Single process | Distributed, cross-service |
| **Delivery guarantee** | Synchronous, at-least-once in process | Synchronous or async in process | At-least-once, durable |
| **Failure isolation** | Handler exception propagates | Can catch per-handler | Consumer failure doesn't affect producer |
| **Ordering** | Preserved (list iteration) | Preserved (single process) | Not guaranteed (SQS), best-effort (Kafka) |
| **Latency** | Nanoseconds | Microseconds | 1-100ms (SQS), 1-10ms (Kafka) |
| **Use case** | Domain event side effects (email on save) | Application-layer event routing | Async inter-service communication |
| **Persistence** | None | None | Durable (survives crashes) |

**Rule of thumb**: Use in-process Observer for same-request side effects that must complete before response (e.g., audit log on create). Use message queue for work that can be deferred, retried independently, or distributed across services.

---

## Repository vs. Active Record vs. Data Mapper

These are the three dominant patterns for persistence in Python:

| Dimension | Active Record (Django ORM) | Data Mapper (SQLAlchemy) | Repository (explicit) |
|-----------|---------------------------|--------------------------|----------------------|
| **Where SQL lives** | In the model class | In the mapper/session | In the repository class |
| **Domain/DB coupling** | Tight (model IS the DB row) | Loose (domain object separate from ORM) | Loose |
| **Testability without DB** | Hard — `User.objects.create` needs DB | Medium — session can be mocked | Easy — swap InMemoryRepo |
| **Complex queries** | Manager methods proliferate | SQLAlchemy query API in repo | Explicit repo methods |
| **When to use** | CRUD-heavy apps, small teams, fast iteration | Complex domain logic, DDD | Anywhere testability matters |
| **Python frameworks** | Django | SQLAlchemy (Core or ORM) | Any |

**Production recommendation**: For CRUD-heavy microservices (create, list, update, delete), Django's Active Record is fast and appropriate. For services with business-logic-heavy domains (orders, payments, subscriptions), Repository + SQLAlchemy Data Mapper pays off in testability and flexibility.

---

## Strategy Implemented as Class vs. Callable

| Dimension | Class-based Strategy | Callable Strategy |
|-----------|---------------------|-------------------|
| **State** | Yes — `__init__` parameters | Via closure |
| **Interface** | Protocol with method name | `Callable[[Input], Output]` |
| **Composability** | Requires delegation | Easy — `composed = lambda x: f(g(x))` |
| **Discoverability** | Type annotations show method name | `Callable` is less descriptive |
| **When to use** | Multiple methods, stateful, complex | Single function, stateless |

```python
# Class: stateful, multi-method (preferred when strategy is complex)
class ExponentialRetryStrategy:
    def __init__(self, base_delay: float, max_attempts: int) -> None: ...
    def should_retry(self, attempt: int, exception: Exception) -> bool: ...
    def wait_time(self, attempt: int) -> float: ...

# Callable: stateless, single behavior (preferred for simple cases)
SortKey = Callable[[dict], Any]
sort_by_price: SortKey = lambda item: item["price"]
sort_by_name: SortKey = lambda item: item["name"]
```

---

## Pattern Overhead: When Not to Apply

| Pattern | Over-engineering signal | Better alternative |
|---------|------------------------|--------------------|
| **Strategy** | Only one strategy ever exists | Direct implementation; no pattern |
| **Factory** | Only one concrete type ever created | Direct instantiation |
| **Decorator** | Only one decorator, never composed | Just modify the function |
| **Observer** | Only one handler, always the same | Direct function call |
| **Repository** | Script or one-off data migration | Direct ORM/query call |

**The test**: if the pattern can't be demonstrated to reduce cost-of-change in a specific scenario, don't apply it. Patterns are solutions; don't apply a solution without a problem.
