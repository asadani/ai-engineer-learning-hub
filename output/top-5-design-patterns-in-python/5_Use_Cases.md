# Use Cases & Real-World Applications

## 1. Strategy: ML Model Serving with Swappable Inference Backends

**Context**: An inference API must support multiple model backends (SageMaker, Bedrock, self-hosted vLLM, mock for testing) without changing the serving logic.

```python
from typing import Protocol
from dataclasses import dataclass

@dataclass
class InferenceRequest:
    prompt: str
    max_tokens: int = 512
    temperature: float = 0.7

@dataclass
class InferenceResponse:
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: float

class InferenceBackend(Protocol):
    def complete(self, request: InferenceRequest) -> InferenceResponse: ...

class BedrockBackend:
    def __init__(self, model_id: str, region: str = "us-east-1") -> None:
        import boto3
        self._client = boto3.client("bedrock-runtime", region_name=region)
        self._model_id = model_id

    def complete(self, request: InferenceRequest) -> InferenceResponse:
        import time, json
        body = json.dumps({"prompt": request.prompt, "max_tokens": request.max_tokens})
        start = time.perf_counter()
        response = self._client.invoke_model(modelId=self._model_id, body=body)
        result = json.loads(response["body"].read())
        return InferenceResponse(
            text=result["completion"],
            input_tokens=result["usage"]["input_tokens"],
            output_tokens=result["usage"]["output_tokens"],
            latency_ms=(time.perf_counter() - start) * 1000,
        )

class VllmBackend:
    def __init__(self, base_url: str) -> None:
        import httpx
        self._client = httpx.Client(base_url=base_url)

    def complete(self, request: InferenceRequest) -> InferenceResponse: ...

class FixtureBackend:  # for tests — no infrastructure
    def __init__(self, response_text: str = "mocked response") -> None:
        self._text = response_text

    def complete(self, request: InferenceRequest) -> InferenceResponse:
        return InferenceResponse(text=self._text, input_tokens=10, output_tokens=5, latency_ms=1.0)

class InferenceService:
    def __init__(self, backend: InferenceBackend) -> None:
        self._backend = backend

    def answer(self, question: str) -> str:
        response = self._backend.complete(InferenceRequest(prompt=question))
        return response.text
```

Swapping from Bedrock to vLLM: one line change in the composition root. Tests run with `FixtureBackend` — no AWS credentials, no network.

---

## 2. Factory + Strategy: Multi-Provider Payment Processing

**Context**: An e-commerce platform supports Stripe, Braintree, and PayPal. The correct provider is selected at runtime based on the customer's region and payment method.

```python
from typing import Protocol
from decimal import Decimal
from dataclasses import dataclass

@dataclass
class PaymentRequest:
    amount: Decimal
    currency: str
    customer_id: str
    payment_method_token: str

@dataclass
class PaymentResult:
    transaction_id: str
    status: str

class PaymentProcessor(Protocol):
    def charge(self, request: PaymentRequest) -> PaymentResult: ...
    def refund(self, transaction_id: str, amount: Decimal) -> PaymentResult: ...

class StripeProcessor:
    def charge(self, request: PaymentRequest) -> PaymentResult: ...
    def refund(self, transaction_id: str, amount: Decimal) -> PaymentResult: ...

class BraintreeProcessor:
    def charge(self, request: PaymentRequest) -> PaymentResult: ...
    def refund(self, transaction_id: str, amount: Decimal) -> PaymentResult: ...

# Factory: creates the right Strategy based on runtime context
class PaymentProcessorFactory:
    _providers: dict[str, type] = {}

    def __init_subclass__(cls, provider: str, **kwargs):
        super().__init_subclass__(**kwargs)
        PaymentProcessorFactory._providers[provider] = cls

    @classmethod
    def create(cls, provider: str, **config) -> PaymentProcessor:
        if provider not in cls._providers:
            raise ValueError(f"Unknown provider: {provider!r}")
        return cls._providers[provider](**config)

# Service: uses Strategy (processor) created by Factory
class CheckoutService:
    def __init__(self, processor_factory: type[PaymentProcessorFactory]) -> None:
        self._factory = processor_factory

    def process_payment(self, request: PaymentRequest, provider: str) -> PaymentResult:
        processor = self._factory.create(provider)
        return processor.charge(request)
```

---

## 3. Decorator: Cross-Cutting Concerns in a FastAPI Microservice

**Context**: API handlers need consistent logging, timing, retry on transient errors, and rate limiting — without embedding these in business logic.

```python
import functools, time, logging
from typing import Callable, TypeVar
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

# Composable decorators for cross-cutting concerns
def log_call(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        logger.info("Calling %s args=%s kwargs=%s", func.__qualname__, args, kwargs)
        result = await func(*args, **kwargs)
        logger.info("%s returned successfully", func.__qualname__)
        return result
    return wrapper

def emit_metric(metric_name: str):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                latency = (time.perf_counter() - start) * 1000
                metrics.record(metric_name, latency, status="success")
                return result
            except Exception as e:
                metrics.record(metric_name, 0, status="error")
                raise
        return wrapper
    return decorator

# Applied to a service method — business logic is uncontaminated
class EmbeddingService:
    @log_call
    @emit_metric("embedding.generate")
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=0.5, max=5),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
    )
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await self._client.embed(texts)  # pure business logic
```

**GoF Structural Decorator for service wrapping**:

```python
class CachingEmbeddingService:
    """Wraps EmbeddingService with a Redis cache — same interface."""
    def __init__(self, wrapped: EmbeddingService, cache: Redis, ttl: int = 3600) -> None:
        self._wrapped = wrapped
        self._cache = cache
        self._ttl = ttl

    async def embed(self, texts: list[str]) -> list[list[float]]:
        key = f"embed:{hash(tuple(texts))}"
        if cached := await self._cache.get(key):
            return json.loads(cached)
        result = await self._wrapped.embed(texts)
        await self._cache.setex(key, self._ttl, json.dumps(result))
        return result
```

---

## 4. Observer: Domain Events in a Order Management System

**Context**: When an order is placed, multiple subsystems must react: inventory reservation, email confirmation, analytics tracking, fraud scoring. These should be decoupled from the order placement logic.

```python
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Callable
import asyncio

# Domain events (immutable value objects)
@dataclass(frozen=True)
class OrderPlaced:
    order_id: str
    customer_id: str
    items: tuple
    total: float

@dataclass(frozen=True)
class PaymentConfirmed:
    order_id: str
    transaction_id: str

# Async event bus for I/O-bound handlers
class DomainEventBus:
    def __init__(self) -> None:
        self._handlers: dict[type, list[Callable]] = defaultdict(list)

    def on(self, event_type: type):
        """Decorator-style subscription."""
        def decorator(func: Callable) -> Callable:
            self._handlers[event_type].append(func)
            return func
        return decorator

    async def emit(self, event) -> None:
        handlers = self._handlers.get(type(event), [])
        results = await asyncio.gather(
            *(h(event) for h in handlers),
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, Exception):
                logger.error("Event handler failed: %s", r, exc_info=r)

bus = DomainEventBus()

@bus.on(OrderPlaced)
async def reserve_inventory(event: OrderPlaced) -> None:
    await inventory_service.reserve(event.order_id, event.items)

@bus.on(OrderPlaced)
async def send_confirmation_email(event: OrderPlaced) -> None:
    await email_service.send_order_confirmation(event.customer_id, event.order_id)

@bus.on(OrderPlaced)
async def track_analytics(event: OrderPlaced) -> None:
    await analytics.track("order_placed", {"order_id": event.order_id, "total": event.total})

# Order service — no knowledge of downstream side effects
class OrderService:
    def __init__(self, repo: OrderRepository, event_bus: DomainEventBus) -> None:
        self._repo = repo
        self._bus = event_bus

    async def place_order(self, customer_id: str, items: list) -> str:
        order = Order.create(customer_id=customer_id, items=items)
        await self._repo.save(order)
        await self._bus.emit(OrderPlaced(
            order_id=order.id,
            customer_id=customer_id,
            items=tuple(items),
            total=order.total,
        ))
        return order.id
```

**Key design**: handlers are independent — one failing (e.g., analytics outage) doesn't roll back the order. `return_exceptions=True` in `asyncio.gather` ensures all handlers run regardless of individual failures.

---

## 5. Repository + Unit of Work: Clean FastAPI Service

**Context**: A FastAPI service with multiple aggregates (User, Order, Payment) needs transactional consistency and full testability without a real database.

```python
# domain/ports.py
class UserRepository(Protocol):
    def save(self, user: User) -> None: ...
    def get(self, id: UUID) -> User | None: ...

class OrderRepository(Protocol):
    def save(self, order: Order) -> None: ...
    def list_by_user(self, user_id: UUID) -> list[Order]: ...

class UnitOfWork(Protocol):
    users: UserRepository
    orders: OrderRepository
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def __enter__(self) -> "UnitOfWork": ...
    def __exit__(self, *args) -> None: ...

# application/order_service.py
class OrderApplicationService:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def place_order(self, user_id: UUID, items: list[dict]) -> str:
        with self._uow_factory() as uow:
            user = uow.users.get(user_id)
            if not user:
                raise UserNotFoundError(user_id)
            order = Order.create(user_id=user.id, items=items)
            uow.orders.save(order)
            uow.commit()
            return order.id

# infrastructure/sqlalchemy_uow.py
class SqlAlchemyUoW:
    def __init__(self, session_factory) -> None:
        self._sf = session_factory

    def __enter__(self):
        self._session = self._sf()
        self.users = SqlAlchemyUserRepository(self._session)
        self.orders = SqlAlchemyOrderRepository(self._session)
        return self

    def __exit__(self, exc_type, *_):
        if exc_type: self.rollback()
        self._session.close()

    def commit(self): self._session.commit()
    def rollback(self): self._session.rollback()

# api/routes.py — thin, just wires DI
@router.post("/orders")
async def create_order(
    body: CreateOrderRequest,
    svc: OrderApplicationService = Depends(get_order_service),
    current_user: UUID = Depends(get_current_user),
):
    order_id = svc.place_order(current_user, body.items)
    return {"order_id": order_id}

# tests/test_order_service.py — zero infrastructure
def test_place_order_creates_order():
    uow = InMemoryUoW()
    uow.users.save(User(id=USER_ID, email="x@y.com", name="Alice", tier="standard"))
    svc = OrderApplicationService(uow_factory=lambda: uow)

    order_id = svc.place_order(USER_ID, [{"sku": "A", "qty": 2}])

    assert uow.orders.list_by_user(USER_ID)[0].id == order_id
```
