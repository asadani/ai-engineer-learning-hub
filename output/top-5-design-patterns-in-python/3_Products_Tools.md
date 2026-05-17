# Products & Tools

## Frameworks That Embody These Patterns

### Strategy Pattern in the Wild

**Python `sorted()` / `list.sort()`**: The `key=` argument is a Strategy — callers inject the comparison behavior without modifying `sorted`. This is the most-used Strategy implementation in Python.

**`httpx` / `requests` Transport adapters**: Both libraries accept a custom transport object (a Strategy) that controls how HTTP requests are dispatched — used for mocking in tests, routing to mock servers, or adding custom retry logic.

**Scikit-learn Estimator API**: Every transformer (`StandardScaler`, `PCA`, `TfidfVectorizer`) implements `fit(X)`/`transform(X)` as a Strategy. `Pipeline` composes them without knowing concretely which transformer is active. This is the cleanest real-world Strategy implementation in the Python ecosystem.

```python
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression

# Each step is a Strategy; swap StandardScaler for MinMaxScaler without changing Pipeline
pipe = Pipeline([("scaler", StandardScaler()), ("clf", LogisticRegression())])
```

**Celery task routing**: The `task_routes` config maps task names to queue strategies — a Strategy for determining where work goes.

---

### Factory Pattern in the Wild

**`logging.getLogger(name)`**: A factory that returns the same `Logger` instance for the same name — combines Factory Method with Singleton registry. Callers never instantiate `Logger` directly.

**SQLAlchemy `create_engine(url)`**: A factory function that inspects the URL scheme (`postgresql+psycopg2://`, `sqlite:///`, `mysql+pymysql://`) and instantiates the appropriate engine dialect. Adding a new dialect doesn't modify `create_engine` — it registers a new entry point.

**`boto3.client("s3")` / `boto3.resource("dynamodb")`**: Factory methods that create the appropriate AWS service client based on the string identifier. The session manages credentials; callers never construct clients directly.

**`werkzeug.serving.make_server`**: Conditionally creates threaded, forking, or single-threaded WSGI servers based on configuration — classic Factory Method.

**Pydantic `model_validate` / `TypeAdapter`**: Factory-like construction from raw dicts/JSON — dispatches to the correct model subclass based on discriminator fields.

```python
from typing import Literal, Annotated, Union
from pydantic import BaseModel, Field

class Cat(BaseModel):
    pet_type: Literal["cat"]
    meows: int

class Dog(BaseModel):
    pet_type: Literal["dog"]
    barks: float

Pet = Annotated[Union[Cat, Dog], Field(discriminator="pet_type")]

# Factory dispatch via discriminator — Pydantic's Abstract Factory
pet = TypeAdapter(Pet).validate_python({"pet_type": "cat", "meows": 3})
```

---

### Decorator Pattern in the Wild

**Python standard library `functools`**:
- `@functools.lru_cache(maxsize=128)`: Structural Decorator — wraps a function with a memoization cache. One of the most commonly used decorators in Python.
- `@functools.cached_property`: Caches the result of a property computation on first access.
- `@functools.wraps`: Meta-decorator that preserves the wrapped function's metadata.

**FastAPI `@app.get()`, `@router.post()`**: Route decorators register handler functions with the router — a combination of Decorator and Observer (handler is registered as an observer for HTTP events on that path).

**`@pytest.fixture`, `@pytest.mark.parametrize`**: Decorator pattern for test infrastructure injection and parameterization.

**`tenacity` library**: Production-grade retry decorator with configurable stop conditions, wait strategies, and before/after hooks.

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((ConnectionError, TimeoutError)),
)
def call_external_api(payload: dict) -> dict: ...
```

**`wrapt` library**: Correct-by-default function wrapping that preserves introspection, `@property` behavior, and class method semantics — used when `functools.wraps` is insufficient (e.g., wrapping descriptors).

**AWS Lambda Powertools (Python)**:
- `@logger.inject_lambda_context`: Injects Lambda context into structured log records
- `@tracer.capture_method`: X-Ray tracing decorator
- `@metrics.log_metrics`: Flushes CloudWatch metrics on function exit

```python
from aws_lambda_powertools import Logger, Tracer, Metrics
logger = Logger(); tracer = Tracer(); metrics = Metrics()

@logger.inject_lambda_context(log_event=True)
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def handler(event, context): ...
```

---

### Observer Pattern in the Wild

**Django Signals (`django.dispatch.Signal`)**: Classic Observer implementation. `post_save`, `pre_delete`, `m2m_changed` are built-in signals. Custom signals decouple apps.

```python
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=Order)
def send_order_confirmation(sender, instance, created, **kwargs):
    if created:
        send_email(instance.customer.email, "Order confirmed")
```

**Celery signals**: `task_success`, `task_failure`, `task_retry` — hooks into task lifecycle without modifying task code.

**SQLAlchemy event system**: `@event.listens_for(Session, "before_commit")` — hook into ORM lifecycle events. Powers audit logging, soft deletes, and cache invalidation.

```python
from sqlalchemy import event

@event.listens_for(Session, "before_commit")
def set_updated_at(session):
    for obj in session.dirty:
        if hasattr(obj, "updated_at"):
            obj.updated_at = datetime.utcnow()
```

**RxPY / ReactiveX**: Functional reactive programming — Observers subscribe to Observable streams. Used in event-driven ML pipelines and real-time data processing.

**`watchdog` library**: Filesystem Observer — watches directory/file changes and notifies registered handlers.

**`pyee` (Python EventEmitter)**: Lightweight Node.js-style EventEmitter for Python. Simpler than full Observer classes for event-driven scripts.

---

### Repository Pattern in the Wild

**Django ORM Manager**: `User.objects` is a repository-like interface — `User.objects.filter(tier="premium")` abstracts the SQL. Django makes it hard to implement clean Repository pattern due to the Active Record nature of models; `django-repository` and manual service layer patterns compensate.

**SQLAlchemy Session**: Not a repository itself, but the Session pattern is the Unit of Work; combine with repository classes for clean DDD implementation.

**`databases` library**: Async database access — can wrap in a repository for async FastAPI services.

**Spring Data (Java, for reference)**: The archetype repository implementation — `JpaRepository<User, UUID>` generates implementations automatically. Python equivalents are more explicit; there's no direct ORM-level code generation.

**`piccolo-orm`**: Python async ORM where table classes can be used as repositories directly; cleaner than Django for hexagonal architecture.

---

## Testing Tools That Enable Pattern Verification

| Tool | Pattern Relationship |
|------|---------------------|
| `pytest` fixtures | Implements DIP/Repository — inject fakes at test time |
| `pytest-mock` / `unittest.mock` | Replace concrete dependencies (use sparingly — prefer fakes) |
| `hypothesis` | Property-based testing for Strategy/Observer behavioral contracts |
| `factory_boy` | Creates test domain objects — a Factory pattern for test data |
| `freezegun` | Decorator pattern for freezing time in tests |
| `respx` / `responses` | Mock HTTP at transport level — Strategy for HTTP in tests |

---

## Libraries That Implement These Patterns Idiomatically

| Library | Pattern | How |
|---------|---------|-----|
| `attrs` | Strategy + SRP | Clean value objects; behavior via protocols |
| `returns` (dry-python) | Strategy + Decorator | `Result`, `Maybe` as strategy-like containers |
| `dependency-injector` | Factory + Strategy | Declarative wiring of strategy implementations |
| `structlog` | Decorator | Processors are decorators chained on log records |
| `celery` | Observer + Strategy | Tasks are observers; routing is a strategy |
| `pydantic` | Factory | `model_validate` is a discriminated factory |
| `tenacity` | Decorator | Retry strategies as composable decorators |
