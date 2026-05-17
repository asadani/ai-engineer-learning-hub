# Interview Questions & Scenarios

## Tier 1: Senior Engineer (L5)

### Q1: Explain the Single Responsibility Principle with a concrete Python example of a violation and how you'd fix it.

**Model Answer**: SRP says a class should have one reason to change, where "reason to change" maps to one stakeholder or concern. A common violation is a `UserService` that handles DB persistence, email sending, and CSV export — if marketing changes the email template, the DB team changes the schema, or reporting changes the format, all three touch the same class. The fix is to split into `UserRepository` (data access), `WelcomeEmailSender` (email), and `UserExporter` (reporting), each independently changeable and testable. In Python, the smell is easy to spot: a class whose name ends in "Manager", "Handler", or "Service" and has unrelated private methods that could stand alone as separate classes.

---

### Q2: What's the difference between `typing.Protocol` and `abc.ABC` in Python, and when would you use each?

**Model Answer**: `ABC` uses nominal subtyping — a class must explicitly inherit from the ABC to satisfy its contract, and the contract is enforced at instantiation time (you can't instantiate an ABC with unimplemented abstract methods). `Protocol` uses structural subtyping — any class with the right methods satisfies the Protocol without declaring intent, and checking is done by mypy at type-check time (not at runtime, unless you add `@runtime_checkable`). For dependency inversion boundaries, `Protocol` is more Pythonic — you can make a `boto3` S3 client satisfy an `ObjectStorage` Protocol without wrapping it. Use `ABC` when you want explicit "this is a subtype" declaration in the class hierarchy and runtime enforcement; use `Protocol` for port definitions in hexagonal architecture.

---

### Q3: Give an example of an LSP violation that would pass a type checker but fail at runtime.

**Model Answer**: The canonical example is `Square extends Rectangle`. If `Rectangle` guarantees that `set_width(5); set_height(10); area() == 50`, `Square` breaks this because setting height also sets width — it honors the interface signature but violates the behavioral postcondition. mypy won't catch this because both methods have the correct signatures. Only a behavioral test (`assert rect.area() == 50` after setting width and height independently) catches it. The lesson: LSP requires behavioral compatibility, not just signature compatibility. Property-based testing with Hypothesis, where you generate random inputs and assert that all subtypes satisfy the same postconditions, is the most systematic way to catch LSP violations.

---

### Q4: What does "depend on abstractions, not concretions" mean in Python's FastAPI context?

**Model Answer**: In FastAPI, the concretion is the concrete implementation class (e.g., `PostgresUserRepository`); the abstraction is the `Protocol` or `ABC` it satisfies (`UserRepository`). The DIP-violating version has the route handler directly importing and instantiating `PostgresUserRepository`. The DIP-compliant version uses `Depends()` to inject an abstract `UserRepository` dependency, where the dependency resolver provides the concrete implementation. This means in tests, you swap the `Depends()` override to inject `InMemoryUserRepository` — no mocking of `psycopg2`, no test database, no Docker. The tell that DIP is working: your domain tests have zero infrastructure imports.

---

### Q5: How does the Open/Closed Principle apply to a notification system that needs to support email, SMS, and Slack?

**Model Answer**: An OCP violation is a `NotificationService` with `if channel == "email": ... elif channel == "slack": ...` — every new channel requires modifying tested code. The OCP-compliant design defines `Notifier(Protocol)` with a `send(recipient, message)` method, then `EmailNotifier`, `SmsNotifier`, `SlackNotifier` each implement it. `NotificationService` takes a `list[Notifier]` and calls each. Adding push notifications means writing `PushNotifier` and registering it — the service never changes. A further improvement: use a registry pattern with `__init_subclass__` so new `Notifier` subclasses auto-register, turning extension into a pure addition operation.

---

### Q6: What is Interface Segregation in Python when there are no formal interfaces?

**Model Answer**: ISP in Python means designing `Protocol`s and function signatures to be as narrow as possible — callers only depend on what they use. The practical smell is a function that takes a large object but only reads one or two attributes: `def send_email(user: User)` when you only need `user.email` — change `User.email` field name and this breaks unnecessarily. The fix: `def send_email(recipient: str)`. At the class level: a fat `StorageClient` with upload, download, delete, list, and presign methods forces every consumer to depend on all five. Segregate into `ObjectUploader(Protocol)`, `ObjectDownloader(Protocol)`, `PresignedUrlGenerator(Protocol)` — each consumer depends only on its slice.

---

## Tier 2: Staff Engineer (L6)

### Q7: You're reviewing a PR where a new team introduced a service layer, but all tests use `unittest.mock.patch` to mock database calls directly. What architectural problem does this reveal, and how would you address it?

**Model Answer**: Patching `psycopg2.connect` or `sqlalchemy.orm.Session` directly means the service layer is instantiating its own database connections internally — a DIP violation. The service is tightly coupled to a specific ORM and database library. The fix is constructor injection: the service should accept a `UserRepository(Protocol)` through its `__init__`, so tests pass an `InMemoryUserRepository` without any patching. The migration path: refactor the service to take an injected repository, write a `PostgresUserRepository` that wraps the current DB code, and replace all the `patch` mocks with simple fakes. I'd also add an `import-linter` rule that prevents domain layer files from importing SQLAlchemy or psycopg2 directly — enforces DIP at the CI level so the violation can't regress.

---

### Q8: Design a plugin system for a data pipeline where external teams can register their own transformation steps without modifying core pipeline code.

**Model Answer**: Define a `Transformer(Protocol)` with `transform(data: pd.DataFrame) -> pd.DataFrame` and a `name: str` attribute. The core pipeline maintains a `TransformerRegistry` that maps names to implementations. Use `__init_subclass__` to auto-register: any subclass of a base `Transformer` class that declares `name = "my_transform"` is automatically added to the registry at import time. External teams ship a Python package with their transformer, register it as a `[project.entry-points."pipeline.transformers"]` entry point in their `pyproject.toml`, and the core pipeline discovers it at startup via `importlib.metadata.entry_points`. This is exactly how pytest plugins, flake8 extensions, and Sphinx themes work. The core pipeline code never changes when new transformers are added — strict OCP compliance.

---

### Q9: A `PaymentService` class has 400 lines and 25 methods covering authorization, charging, refunds, fraud detection, and reporting. Walk through how you'd refactor it step by step without breaking production.

**Model Answer**: This is a classic SRP violation — five distinct responsibilities in one class. Step 1: identify the cohesion clusters by running LCOM4 analysis (or manually: which methods share instance variables?). Step 2: extract interfaces first — define `PaymentAuthorizer(Protocol)`, `ChargeProcessor(Protocol)`, `RefundHandler(Protocol)`, `FraudDetector(Protocol)`, `PaymentReporter(Protocol)`. Step 3: extract one class at a time, starting with the most isolated (usually `FraudDetector` — typically it only reads, never writes). Step 4: keep the original `PaymentService` as a thin facade that delegates to the new classes — this preserves the existing API contract and requires no external call-site changes. Step 5: once all classes are extracted and tested independently, deprecate and remove the facade. Each extraction is a separate PR, each with targeted tests. The risk profile is low because at no point is existing behavior removed, only delegated.

---

### Q10: Explain the Stable Abstractions Principle and how it relates to SOLID, with a concrete Python package structure example.

**Model Answer**: The Stable Abstractions Principle (SAP, Robert C. Martin) says stable packages (those many others depend on) should be abstract; unstable packages (those that depend on many others) should be concrete. This maps directly to DIP: the `Abstractness` of a package (ratio of abstract classes/Protocols to total classes) should increase with its `Stability` (inverse of efferent coupling). In Python, concretely: your `myapp.domain.ports` package contains only `Protocol` definitions — it's maximally abstract (A=1) and stable (nothing depends on infrastructure; many things depend on it). Your `myapp.infrastructure.postgres` package contains only concrete implementations — it's maximally concrete (A=0) and unstable (it depends on SQLAlchemy, psycopg2, and the domain ports). The "main sequence" is `A + I ≈ 1`. Violation: a stable package that is also concrete (`A=0, I=0`) — the "zone of pain". This is what happens when you put concrete DB calls inside a module that 10 other modules import.

---

### Q11: How would you apply LSP when designing a hierarchy of AWS storage backends (S3, EFS, EBS) behind a common `StorageBackend` abstraction?

**Model Answer**: First, identify the behavioral contract precisely — not just method signatures but invariants: `write(path, data)` must guarantee the data is durably persisted (not just buffered); `read(path)` must return exactly what was written; `delete(path)` after `write(path)` must make subsequent `read(path)` raise `FileNotFoundError`. S3 is eventually consistent after a delete (historically — though strong consistency was added in 2020). EBS is synchronous. EFS has distributed consistency semantics. If the base contract says "after `delete`, `read` raises `FileNotFoundError` immediately", EFS under network partition might violate this. The LSP-correct design either: (a) weakens the contract to allow eventual consistency and documents it explicitly, or (b) creates separate `EventualStorageBackend` and `StrongConsistencyStorageBackend` hierarchies. Critically, any code that uses `StorageBackend` must be written to tolerate the weakest guarantee in the contract, not assume the strongest implementation.

---

### Q12: When does following SOLID principles conflict with Pythonic idioms, and how do you resolve the tension?

**Model Answer**: Several real tensions. First, DIP vs. Python convention: Python code often passes functions as arguments (`sorted(items, key=lambda x: x.price)`) — this is DIP via higher-order functions, not via Protocol injection. Forcing a `SortKey(Protocol)` abstraction here is un-Pythonic overengineering. Accept duck typing for simple callables; use Protocol for complex, multi-method dependencies. Second, SRP vs. Python modules: Python idiom is to have utility functions as module-level functions rather than static methods or utility classes. A `utils.py` with 10 functions isn't a SRP violation if those functions all serve the same concern. Third, OCP vs. Python's preference for simplicity: don't abstract a `if format == "json"` to a `Formatter` hierarchy if there are only two formats and they'll never change — YAGNI wins. The resolution: apply SOLID at boundaries that change and are tested; use Pythonic simplicity everywhere else.

---

## Tier 3: Principal Engineer (L7+)

### Q13: A monolith is being decomposed into microservices. How do SOLID principles, specifically DIP and OCP, guide the boundary decisions?

**Model Answer**: DIP applied at the service boundary level means services should depend on contracts (API schemas, message schemas), not on each other's implementation details. The `OrderService` microservice doesn't import from the `InventoryService` codebase — it depends on an `InventoryReservationEvent` Avro schema (an abstraction). This mirrors DIP: both services depend on the shared schema definition (the abstraction), not on each other's internals. OCP guides where boundaries should be: if two capabilities change together for the same reason, they belong in the same service — splitting them creates shotgun surgery across service boundaries, which is far more expensive than within a monolith. If two capabilities change independently for different reasons (different teams, different deployment cadences), split them. The heuristic is Conway's Law inverted: design service boundaries around team boundaries, and the SOLID principles enforce that those boundaries are stable abstractions, not leaky implementation exposures. Practical litmus: can `OrderService` be deployed independently without coordinating with `InventoryService`? If yes, the interface is a proper abstraction. If no, the boundary is in the wrong place.

---

### Q14: How would you set up an architecture review process that systematically catches SOLID violations before they become technical debt?

**Model Answer**: Four-layer defense. First, automated gates in CI: mypy strict (catches DIP/ISP/LSP at type level), import-linter (enforces no domain imports of infrastructure), radon CC gate (catches SRP via complexity), pylint design checks (too-many-methods, too-many-arguments). These run on every PR and are zero-tolerance — no exceptions without documented justification. Second, PR template with a SOLID checklist (the 12-item checklist per principle) — reviewers explicitly answer "does this PR introduce any `isinstance` checks in polymorphic paths?" Third, quarterly architecture review using `wily` trend reports and `pydeps` graphs: which modules are gaining coupling? Which files have the highest churn? These are the SRP/DIP erosion signals that daily PRs miss. Fourth, fitness functions (from "Building Evolutionary Architectures"): automated tests that assert architectural properties — e.g., `test_domain_has_no_infra_imports()` as an actual pytest test that inspects the import graph. These live in the test suite and fail the build if violated, making architecture constraints self-enforcing. The most important cultural element: architects don't just review design docs — they review code, and their review comments are structured ("this is a DIP violation because...") not vague ("I don't like this").

---

### Q15: How do SOLID principles apply to a Python-based AI/ML service that serves LLM inference with RAG, where the business logic interacts with vector stores, LLMs, and rerankers?

**Model Answer**: This is exactly where SOLID is most valuable — because all three components (vector store, LLM, reranker) will change: you'll swap embedding models, try different LLMs, evaluate different rerankers. DIP: define `VectorStore(Protocol)` with `search(query_vector, k, filter)`, `LLMClient(Protocol)` with `generate(messages, max_tokens)`, `Reranker(Protocol)` with `rerank(query, candidates)`. The `RAGPipeline` class depends only on these protocols — it never imports `pinecone`, `anthropic`, or `cohere` directly. Concrete implementations live in `infrastructure/`: `PineconeVectorStore`, `AnthropicClient`, `CohereReranker`. SRP: the pipeline is responsible only for orchestration — chunking, embedding, and indexing are separate classes. OCP: adding a new retrieval strategy (e.g., HyDE) means adding a `QueryTransformer(Protocol)` and implementing `HyDEQueryTransformer`, not modifying the pipeline. LSP: all `LLMClient` implementations must honor the contract — if `generate()` is expected to be synchronous and return a `str`, an async implementation that returns a coroutine violates LSP (Python type system allows this mistake; explicit `async def` in Protocol prevents it). ISP: the evaluation harness only needs `LLMClient.generate()` — pass a narrow `Generator(Protocol)` rather than the full `LLMClient`. The result: you can swap Anthropic for Bedrock in one line, run the entire pipeline in tests with `FakeLLMClient` returning fixtures, and benchmark retrieval strategies independently of generation.

---

### Q16: What are the limits of SOLID, and where have you seen its application cause more harm than good?

**Model Answer**: Three real failure modes. First, abstraction-driven indirection hell: a codebase where every single collaboration is mediated by a Protocol leads to 40-class systems where understanding a simple feature requires tracing 8 files. The fix: apply SOLID to high-change, high-stakes boundaries; use direct calls within a bounded context where the code is stable. Second, premature ISP: splitting interfaces before you understand the actual usage patterns creates fragmented Protocols that constantly need to be combined. Start with one cohesive interface, split when you observe a concrete class forced to implement irrelevant methods. Third, DI container overuse: a `dependency-injector` container with 200 bindings adds a configuration management burden that outweighs the testability benefit for small teams. In Python, constructor injection without a container handles 90% of cases. The meta-lesson: SOLID principles are tools for managing the cost of change, not ends in themselves. The question is never "does this code follow SOLID?" but "does this code have the changeability and testability we need for our context?". Apply aggressively where the answer is "no"; leave alone where the answer is "yes, and SOLID would add unnecessary indirection".
