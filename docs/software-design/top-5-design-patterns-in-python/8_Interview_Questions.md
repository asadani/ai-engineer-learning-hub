# Interview Questions & Scenarios

## Tier 1: Senior Engineer (L5)

### Q1: What problem does the Strategy pattern solve, and how does it differ from a simple `if/elif` chain?

**Model Answer**: The Strategy pattern solves the problem of varying behavior without modifying the class that uses it. A `if/elif` chain on a type string hardcodes all variants in one place — adding a new variant requires modifying tested, deployed code (OCP violation), and the class grows unboundedly. Strategy encapsulates each variant as its own class or callable, injected through a shared interface. The using class (Context) never changes — new variants are new files. The other critical difference is testability: with `if/elif`, you can only test the Context by triggering all branches; with Strategy, you test the Context with a fake strategy and test each concrete strategy independently. In Python, Strategy is implemented via `Protocol` injection or `Callable` parameter — no abstract class boilerplate needed.

---

### Q2: Explain `@functools.wraps` — what breaks without it?

**Model Answer**: `functools.wraps` copies the metadata of the wrapped function (`__name__`, `__qualname__`, `__doc__`, `__annotations__`, `__module__`, `__dict__`, `__wrapped__`) to the wrapper. Without it: `func.__name__` returns `"wrapper"` instead of the original function name — breaking logging that uses `func.__qualname__`, `help()` output, and stack traces. mypy's type inference breaks because the wrapper's signature is `(*args, **kwargs)` instead of the original signature — losing type safety entirely. `inspect.signature()` returns the wrong signature — breaking FastAPI's Depends, pytest fixture introspection, and any framework that reads function signatures. Additionally, the `__wrapped__` attribute set by `functools.wraps` allows `inspect.unwrap()` to peel back decorator layers, which is important for testing and introspection. Bottom line: never write a function decorator without `@functools.wraps(func)`.

---

### Q3: How does the Observer pattern differ from direct method calls, and when is the overhead worth it?

**Model Answer**: A direct method call is synchronous, bidirectional coupling: the caller knows the callee's interface, the callee's exceptions propagate to the caller, and adding another effect requires modifying the caller. Observer is unidirectional: the publisher emits an event and knows nothing about who handles it or how many handlers exist. The overhead is the indirection layer (the event bus, subscription mechanism, event object creation) — typically microseconds in-process. This overhead is worth it when: (1) multiple independent subsystems must react to the same event (inventory, email, analytics on order placement); (2) handlers are added/removed at runtime or by different teams; (3) handler failures should not roll back the original operation. It's not worth it for a single handler that's always present and always needs to succeed atomically with the event — use a direct call with a transaction.

---

### Q4: What is the Repository pattern and how does it improve testability?

**Model Answer**: Repository pattern provides a collection-like interface for accessing domain objects, abstracting away the persistence mechanism (SQL, NoSQL, file, in-memory). The interface is defined as a `Protocol` with methods like `save`, `get`, `find_by_*` that return domain objects, not ORM rows. This separates domain logic from persistence logic — the service layer depends on `UserRepository(Protocol)`, not on `session.query(UserORM)`. Testability improvement: tests inject `InMemoryUserRepository` (a dict-backed fake) instead of a real database. No Docker, no migrations, no test database cleanup — unit tests run in milliseconds. The structural benefit: you can swap PostgreSQL for DynamoDB by writing a new `DynamoUserRepository` and changing one line in the composition root. The domain service never changes.

---

### Q5: How would you implement a self-registering factory in Python without using `if/elif`?

**Model Answer**: Use `__init_subclass__` to auto-register subclasses into a class-level dictionary when they are defined. Each subclass declares its key via a class keyword argument, and the base class stores the mapping. The factory method looks up the registry by key and instantiates the matching class. New product types are added by defining a new subclass with a new key — the factory class never changes. This is exactly how SQLAlchemy dialects work (`create_engine("postgresql://...")` dispatches to `PostgreSQLDialect`), and how pytest plugins and flake8 extensions are discovered via Python entry points. The registry pattern is OCP-compliant: extending the factory is purely additive.

---

### Q6: Describe the GoF Structural Decorator vs. Python's `@decorator` syntax — are they the same thing?

**Model Answer**: They share the name "decorator" but are different patterns with different purposes. GoF Structural Decorator wraps an object that implements the same interface (Protocol), adding behavior at the object level — you can stack multiple wrappers, swap them at runtime, and each preserves the original interface contract. Example: `LoggingService(CachingService(RealService()))` — all three implement `Service(Protocol)`. Python's `@decorator` syntax wraps a callable (function or class) at definition time — it's a syntactic shorthand for `func = decorator(func)`. Python decorators work at the function level (retry, timing, caching function results), while GoF structural decorators work at the object/service level (adding logging or caching to a service). The two are complementary: use `@decorator` for function-level cross-cutting concerns; use GoF Structural Decorator when you need runtime composability of object behaviors behind a shared interface.

---

## Tier 2: Staff Engineer (L6)

### Q7: A payment service handles Stripe, PayPal, and Braintree with `if/elif provider ==` throughout. How do you refactor it to Strategy + Factory without breaking production?

**Model Answer**: Strangler fig approach — never do a big-bang refactor. Step 1: define `PaymentProcessor(Protocol)` with the methods currently scattered across the `if/elif` branches. Step 2: extract the Stripe branch into `StripeProcessor` (easiest first — usually the most-tested path). Step 3: add a `PaymentProcessorFactory` with a registry, register `StripeProcessor` for `"stripe"`. Step 4: replace the Stripe branch in the original service with `factory.create("stripe").charge(...)` — no behavior change, just redirection. Step 5: write characterization tests against the factory path before touching other providers. Step 6: extract Braintree and PayPal the same way. Step 7: delete the original `if/elif` block. Each step is a separate PR, each provably non-breaking. The migration is complete when the `if/elif` is gone and coverage over `PaymentProcessorFactory` is at 100%.

---

### Q8: How would you design an event system for a microservice where some events must be handled synchronously (audit log) and others asynchronously (email notification)?

**Model Answer**: Separate the two into distinct buses or routing tiers within one bus. Define a `Synchronous` and `Asynchronous` marker in the event type, or have two bus methods: `emit_sync(event)` and `emit_async(event)`. Alternatively, use a single bus where each handler is registered with a `mode` parameter: `bus.subscribe(OrderPlaced, AuditLogHandler(), mode="sync")` and `bus.subscribe(OrderPlaced, EmailHandler(), mode="async")`. In the `emit` implementation: run sync handlers in the request context first (block until complete, exceptions propagate and can roll back), then fire async handlers via `asyncio.create_task` or enqueue to a Celery/SQS queue (non-blocking, isolated from request outcome). The audit log handler's failure must roll back the transaction — so it runs synchronously inside the Unit of Work. The email handler's failure must not roll back the order — so it runs asynchronously after commit. This distinction is a business rule, not a technical preference, and should be explicit in the design.

---

### Q9: Walk through how `functools.lru_cache` is both a GoF Decorator and a Python decorator simultaneously.

**Model Answer**: `@functools.lru_cache(maxsize=128)` is a Python decorator because it uses the `@` syntax to wrap a function at definition time — `func = lru_cache(maxsize=128)(func)`. It's also a GoF Structural Decorator because the returned wrapper has the same callable signature as the original function (it satisfies the same `Callable[[Args], Return]` interface), adds behavior (memoization), and delegates to the original for cache misses. The wrapper maintains state (the cache dict and hit/miss counters, accessible via `func.cache_info()`). The `@functools.wraps` call inside `lru_cache` ensures the wrapper preserves the original's `__name__`, `__doc__`, and `__module__`. One subtlety: `lru_cache` doesn't work correctly with `unhashable` arguments (lists, dicts) — it raises `TypeError`. For memoizing functions that take unhashable args, use `joblib.Memory` or `cachetools.TTLCache` with a custom key function.

---

### Q10: Design a plugin system where external packages can contribute new data transformers to an ETL pipeline using Python entry points.

**Model Answer**: Three layers. First, define the interface: `Transformer(Protocol)` with `name: str`, `transform(df: pd.DataFrame) -> pd.DataFrame`, and `describe() -> str`. Second, define the discovery mechanism: use Python's `importlib.metadata.entry_points(group="myetl.transformers")` at pipeline startup to discover all registered transformers. Third, the registration contract: any external package that wants to contribute a transformer adds this to its `pyproject.toml`: `[project.entry-points."myetl.transformers"] normalize = "mypackage.transformers:NormalizeTransformer"`. The pipeline discovers and registers all entry points at startup, making them available in its registry. This is the OCP pattern at the packaging level — the core pipeline never changes when external teams add transformers. The same mechanism is used by pytest (plugins), Sphinx (extensions), Babel (localizations), and Airflow (operators). The key gotcha: entry point loading is lazy by default — call `entry_point.load()` explicitly and catch `ImportError` gracefully for packages with missing dependencies.

---

### Q11: A Repository's `find_active_users_with_premium_tier_and_recent_order` method is getting unwieldy. How do you design a more principled query interface?

**Model Answer**: Two approaches depending on complexity. First, the Specification pattern: define a `Specification(Protocol)` with `is_satisfied_by(entity) -> bool` and compose them with `AND`, `OR`, `NOT` operators. `repo.find(ActiveSpec() & PremiumTierSpec() & RecentOrderSpec())`. The SQL translation is done by a `SqlSpecificationVisitor` that converts spec composition to WHERE clauses. This scales well but adds significant complexity. Second (simpler, usually sufficient): a query object pattern. `repo.find(UserQuery(tier="premium", is_active=True, last_order_after=datetime(2025, 1, 1)))` — a `dataclass` that bundles filter criteria, with `None` meaning "no filter on this field". The repository translates each non-None field to a WHERE condition. The practical choice for most teams: query objects up to 5-7 filters; Specification pattern when filter combinations are driven by end-user input (dynamic query builders in analytics tools). Never encode business logic in repository method names — `find_users_eligible_for_re_engagement` belongs in the domain service, not the repository.

---

### Q12: The Observer event bus in production is causing cascading failures — one slow handler is delaying all other handlers. How do you fix it?

**Model Answer**: The root cause is synchronous sequential handler execution. Fix in three layers. Immediate: switch to `asyncio.gather(*handlers, return_exceptions=True)` so all handlers run concurrently and no single handler blocks others. Medium-term: add per-handler timeouts — `asyncio.wait_for(handler.handle(event), timeout=5.0)` — so a slow external call can't hold the bus indefinitely. Long-term: for handlers that call external systems (email, SMS, analytics), move them out of the in-process event bus entirely and into a durable message queue (SQS, RabbitMQ). The in-process bus handles fast, critical handlers (audit log, cache invalidation); the queue handles slow, fault-tolerant handlers (email, analytics). This separation means handler failure no longer propagates to the request, retries are durable (not lost on process restart), and you get built-in backpressure. The transition: publish to queue instead of calling handler directly; the queue consumer calls the same handler interface — Observer pattern at a different scope.

---

## Tier 3: Principal Engineer (L7+)

### Q13: You're designing a new Python microservice that will be maintained by 3 teams over 5 years. Walk through which of the 5 patterns you'd apply, where, and why — and which you'd explicitly defer.

**Model Answer**: Apply immediately: **Repository** for all data access — the service will outlive any specific ORM or DB choice, and testability is non-negotiable from day one. **Strategy** for any external integration (payment, notification, AI inference) — these providers will change over 5 years and across environments (test, staging, prod). **Factory** for creating the right Strategy implementation based on config — wires the env-specific concretion to the abstract Strategy. **Decorator** (functional) for cross-cutting concerns: retry on all external calls, structured logging, metrics emission — never duplicated in business logic. Apply reactively: **Observer** — only when the second or third independent subscriber to a domain event appears. Premature event bus adds indirection without benefit; wire directly on first subscriber. Defer entirely: Abstract Factory — only if the service grows to need multiple coordinated object families (e.g., full test/prod environment switching with 5+ components). The meta-principle: every pattern adds indirection; indirection is only valuable when it reduces the cost of a real change. Start with concrete, refactor to abstract when the change actually happens.

---

### Q14: Design a Python-based plugin architecture for an AI agent framework where external teams can contribute new tools (web search, code execution, DB query) without modifying the core agent loop.

**Model Answer**: Four-part design. First, the **Tool Protocol**: `class AgentTool(Protocol): name: str; description: str; def execute(self, input: str) -> ToolResult: ...`. The agent loop depends only on `list[AgentTool]` — it never knows concrete tool types. Second, **OCP-compliant registration** via both `__init_subclass__` (for tools in the same package) and Python entry points (`importlib.metadata.entry_points(group="agentfw.tools")`) for external packages. The agent framework discovers external tools at startup, instantiates them, and registers them in its tool registry. Third, **Factory for tool instantiation**: each tool may need configuration (API keys, DB URLs). The factory reads these from a config layer and injects them — tool classes declare their config needs, the factory resolves them. The agent loop just gets a list of ready-to-use tools. Fourth, **Observer for tool execution events**: the agent loop emits `ToolExecuted(tool_name, input, output, latency_ms)` events after each tool call — without knowing about logging, tracing, or cost tracking systems. External observability plugins subscribe to these events via the same entry point mechanism. The full design is OCP at three layers: new tools (Strategy + Factory), new event handlers (Observer), new configuration providers (Strategy). The agent loop itself never changes.

---

### Q15: When would you argue against using the Repository pattern in a Python service, and what would you use instead?

**Model Answer**: Three scenarios where Repository adds net cost. First, **CRUD-heavy services with no domain logic**: a User Management service that's 90% create-read-update-delete has no "domain" to separate from persistence. Django's Active Record (`User.objects.create`, `User.objects.filter`) is faster to write, easier to read, and the coupling is acceptable because there's no complex domain logic to protect. Adding a Repository layer here is indirection without benefit — it's abstraction for abstraction's sake. Second, **high-performance query services**: a reporting or analytics service where 80% of value is in complex, database-specific queries (window functions, CTEs, materialized views). A `ReportRepository.get_cohort_retention(...)` method would need to expose so many database-specific capabilities that the abstraction becomes hollow — you end up passing raw SQL through the interface. Use SQLAlchemy Core or an ORM directly; the persistence is the point. Third, **event-sourced systems**: if state is derived from an event log (Kafka, EventStoreDB) rather than rows in a table, the Repository abstraction doesn't map cleanly — you're not "storing and retrieving objects" but "appending and replaying events". Use an `EventStore(Protocol)` and `Projector` pattern instead. The general rule: Repository earns its keep when (a) business logic exists that must be testable in isolation and (b) the persistence mechanism is genuinely likely to change or be mocked in tests. Absent both, it's overhead.

---

### Q16: The codebase has 50 event types, 30 handlers, and the event bus is becoming a coupling magnet. How do you re-architect it?

**Model Answer**: A 50-event, 30-handler event bus in a single service is a sign that the service has too many responsibilities — the event bus is obscuring a missing bounded context split, not solving a design problem. The first step is a dependency graph: draw which aggregates produce which events and which handlers consume them. Clusters of tightly coupled producer-consumer pairs that rarely cross-communicate are candidates for extraction into separate services or at least separate bounded contexts within the monolith. For the events that remain in-process, apply three improvements. First, **typed event dispatch**: replace the `dict[type, list[Handler]]` bus with a `singledispatch`-based bus where handlers are registered per event type via `@bus.handler(OrderPlaced)` — makes handler-event coupling explicit and mypy-checkable. Second, **handler categorization**: tag handlers as synchronous (must complete in request) or asynchronous (fire-and-forget, enqueue) — currently likely all treated the same. Third, **event schema registry**: define all 50 event types in a single `domain/events.py` module with `@dataclass(frozen=True)` — this becomes the bounded context's published language, and changes here are auditable. If after this cleanup the bus is still complex, the problem is the monolith's boundaries, not the Observer pattern.
