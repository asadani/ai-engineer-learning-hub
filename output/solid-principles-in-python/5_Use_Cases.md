# Use Cases & Real-World Applications

## 1. Hexagonal Architecture (Ports & Adapters) in a FastAPI Service

**Principles encoded**: DIP, SRP, OCP

The most architecturally significant application of SOLID in Python backend services. The domain core depends on abstract `Protocol` ports; infrastructure adapters implement those ports.

```
┌──────────────────────────────────────────────────┐
│                  DOMAIN CORE                      │
│  OrderService, Order, User (business logic)       │
│  depends only on: OrderRepo(Protocol),            │
│                   Notifier(Protocol)              │
└────────────────────┬─────────────────────────────┘
                     │ depends on
         ┌───────────┼───────────┐
         ▼           ▼           ▼
   PostgresRepo  DynamoRepo  InMemoryRepo   ← adapters (infra)
   SmtpNotifier  SlackNotif  FakeNotifier   ← adapters (infra)
```

```python
# domain/ports.py
from typing import Protocol
from .models import Order

class OrderRepository(Protocol):
    def save(self, order: Order) -> None: ...
    def find_by_id(self, order_id: str) -> Order | None: ...

class Notifier(Protocol):
    def send(self, recipient: str, subject: str, body: str) -> None: ...

# domain/service.py
class OrderService:
    def __init__(self, repo: OrderRepository, notifier: Notifier) -> None:
        self._repo = repo
        self._notifier = notifier

    def place_order(self, order: Order) -> None:
        if order.total < 0:
            raise ValueError("Order total cannot be negative")
        self._repo.save(order)
        self._notifier.send(order.customer_email, "Order Confirmed", f"Order {order.id} placed")

# infrastructure/postgres_repo.py
class PostgresOrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def save(self, order: Order) -> None:
        self._session.add(order.to_orm())

# tests/test_order_service.py — zero infrastructure
def test_places_order_and_notifies():
    repo = InMemoryOrderRepository()
    notifier = CapturingNotifier()
    svc = OrderService(repo, notifier)

    order = Order(id="o1", customer_email="x@y.com", total=Decimal("99.00"))
    svc.place_order(order)

    assert repo.find_by_id("o1") == order
    assert len(notifier.sent) == 1
```

---

## 2. Plugin System (OCP in Action)

**Principles encoded**: OCP, DIP, SRP

A plugin/extension system where new behavior is added by registering new classes, never modifying the dispatcher.

```python
from typing import Protocol
from dataclasses import dataclass

class EventHandler(Protocol):
    event_type: str
    def handle(self, payload: dict) -> None: ...

class HandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = {}

    def register(self, handler: EventHandler) -> None:
        self._handlers.setdefault(handler.event_type, []).append(handler)

    def dispatch(self, event_type: str, payload: dict) -> None:
        for handler in self._handlers.get(event_type, []):
            handler.handle(payload)

# Adding new behavior: write a new class, register it
@dataclass
class OrderShippedEmailHandler:
    event_type: str = "order.shipped"

    def handle(self, payload: dict) -> None:
        send_email(payload["customer_email"], "Your order shipped!")

@dataclass
class OrderShippedAnalyticsHandler:
    event_type: str = "order.shipped"

    def handle(self, payload: dict) -> None:
        analytics.track("order_shipped", payload)

registry = HandlerRegistry()
registry.register(OrderShippedEmailHandler())
registry.register(OrderShippedAnalyticsHandler())
# dispatch never changes
registry.dispatch("order.shipped", {"customer_email": "x@y.com", "order_id": "123"})
```

This is the exact pattern used in Django signals, Celery task routing, and FastAPI's event hooks.

---

## 3. ML Pipeline with Swappable Components (DIP + OCP)

**Principles encoded**: DIP, OCP, SRP

ML pipelines need to swap models, feature extractors, and data loaders without rewriting orchestration code.

```python
from typing import Protocol
import numpy as np

class FeatureExtractor(Protocol):
    def extract(self, text: str) -> np.ndarray: ...

class Classifier(Protocol):
    def predict(self, features: np.ndarray) -> str: ...

class DataLoader(Protocol):
    def load(self) -> list[dict]: ...

class InferencePipeline:
    def __init__(
        self,
        loader: DataLoader,
        extractor: FeatureExtractor,
        classifier: Classifier,
    ) -> None:
        self._loader = loader
        self._extractor = extractor
        self._classifier = classifier

    def run(self) -> list[str]:
        records = self._loader.load()
        return [
            self._classifier.predict(self._extractor.extract(r["text"]))
            for r in records
        ]

# Production wiring
pipeline = InferencePipeline(
    loader=S3DataLoader(bucket="prod-data", prefix="2026/03/"),
    extractor=BedrockTitanEmbedder(model_id="amazon.titan-embed-text-v2:0"),
    classifier=SageMakerEndpointClassifier(endpoint="sentiment-v3"),
)

# Testing wiring — no AWS required
test_pipeline = InferencePipeline(
    loader=InMemoryDataLoader(records=[{"text": "great product"}]),
    extractor=FakeEmbedder(dim=1024),
    classifier=AlwaysPositiveClassifier(),
)
```

Adding a new extractor (e.g., switching from Titan to Cohere): implement `CoherEmbedder`, pass it in. `InferencePipeline` never changes.

---

## 4. Strategy Pattern for Pricing Rules (OCP + SRP)

**Principles encoded**: OCP, SRP

E-commerce pricing with multiple discount strategies, each independently testable and addable.

```python
from typing import Protocol
from decimal import Decimal

class DiscountStrategy(Protocol):
    def apply(self, price: Decimal, customer: Customer) -> Decimal: ...

class NoDiscount:
    def apply(self, price: Decimal, customer: Customer) -> Decimal:
        return price

class PremiumMemberDiscount:
    RATE = Decimal("0.15")
    def apply(self, price: Decimal, customer: Customer) -> Decimal:
        if customer.tier == "premium":
            return price * (1 - self.RATE)
        return price

class VolumeDiscount:
    def apply(self, price: Decimal, customer: Customer) -> Decimal:
        if customer.annual_spend > Decimal("10000"):
            return price * Decimal("0.90")
        return price

class PricingEngine:
    def __init__(self, strategies: list[DiscountStrategy]) -> None:
        self._strategies = strategies

    def calculate(self, base_price: Decimal, customer: Customer) -> Decimal:
        price = base_price
        for strategy in self._strategies:
            price = strategy.apply(price, customer)
        return price

# Adding Black Friday discount: new class, no changes to PricingEngine
engine = PricingEngine([PremiumMemberDiscount(), VolumeDiscount(), BlackFridayDiscount()])
```

---

## 5. ISP in API Client Design

**Principles encoded**: ISP, SRP

A fat client class forces all consumers to depend on methods they don't use. Split by consumer need.

```python
# Violation: fat client
class S3Client:
    def upload(self, key: str, data: bytes) -> None: ...
    def download(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def list_objects(self, prefix: str) -> list[str]: ...
    def generate_presigned_url(self, key: str, expiry: int) -> str: ...

# The report generator only needs upload; it's forced to depend on a type with delete/list
class ReportGenerator:
    def __init__(self, storage: S3Client) -> None: ...  # ISP violation

# Compliant: segregated protocols
class ObjectUploader(Protocol):
    def upload(self, key: str, data: bytes) -> None: ...

class PresignedUrlGenerator(Protocol):
    def generate_presigned_url(self, key: str, expiry: int) -> str: ...

class ReportGenerator:
    def __init__(self, storage: ObjectUploader) -> None: ...  # depends only on what it needs

class DownloadHandler:
    def __init__(self, storage: PresignedUrlGenerator) -> None: ...
```

Real-world: boto3's S3 client satisfies both `ObjectUploader` and `PresignedUrlGenerator` structurally — no wrapper needed. Tests use `FakeUploader` with 3 lines.

---

## 6. Django Application with SOLID Service Layer

**Principles encoded**: SRP, DIP, OCP

Typical Django anti-pattern: fat views and fat models. SOLID-compliant pattern: thin views, service layer, repository pattern.

```python
# anti-pattern: fat view does everything
class OrderCreateView(View):
    def post(self, request):
        order = Order.objects.create(...)  # DB
        send_mail("Order placed", ..., [request.user.email])  # email
        analytics.track("order_created", ...)  # analytics
        return JsonResponse({"id": order.id})

# SOLID-compliant
class OrderCreateView(View):
    def post(self, request):
        svc = OrderService(
            repo=DjangoOrderRepository(),
            notifier=DjangoEmailNotifier(),
        )
        order = svc.place_order(OrderRequest.from_request(request))
        return JsonResponse({"id": order.id})

# OrderService is pure Python, tested without Django test client
# DjangoOrderRepository can be swapped for InMemoryOrderRepository in tests
```
