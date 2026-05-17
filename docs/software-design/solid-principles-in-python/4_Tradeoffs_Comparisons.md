# Tradeoffs & Comparisons

## SOLID vs. YAGNI vs. DRY

The three most cited design principles often pull in opposite directions in Python codebases.

| Principle | Core Directive | Tension With SOLID |
|-----------|---------------|-------------------|
| **YAGNI** (You Aren't Gonna Need It) | Don't build for hypothetical future requirements | OCP says design for extension; YAGNI says don't until you need it |
| **DRY** (Don't Repeat Yourself) | Eliminate duplication | SRP says classes should have one reason to change — forcing DRY can couple classes that should be independent |
| **KISS** (Keep It Simple) | Prefer simple over clever | DIP adds abstraction layers; KISS resists them |

**Resolution in practice**:
- Apply OCP retroactively — when you've extended the same logic twice, abstract the variation point. Don't design for extension on first implementation (YAGNI).
- Apply DRY within a single responsibility, not across responsibilities. Two classes that both format dates may legitimately have their own formatters if their reasons to change are different — shared utility couples them unnecessarily.
- Apply DIP when you have evidence you'll swap the implementation (tests, multiple environments, future provider changes). Don't abstract a dependency that will never change.

---

## SOLID vs. Functional Approaches

Python supports both OOP and functional styles. SOLID is OOP-oriented, but the underlying concerns translate:

| SOLID Principle | OOP Expression | Functional Equivalent |
|-----------------|---------------|----------------------|
| SRP | One class, one responsibility | Pure functions with no side effects; one function does one thing |
| OCP | Polymorphism via Protocol/ABC | Higher-order functions; pass behavior as arguments |
| LSP | Subtype behavioral consistency | Function composition consistency; Functor laws in `returns` |
| ISP | Small, focused Protocols | Narrow function signatures; take only what you need |
| DIP | Inject abstract dependencies | Pass functions/callables as parameters; Reader monad |

```python
# OCP in functional style: pass behavior, don't branch
def process_data(data: list, transform: Callable[[dict], dict]) -> list:
    return [transform(item) for item in data]

# extend by passing new transform, never modify process_data
result = process_data(data, add_timestamp)
result = process_data(data, normalize_currency)
```

For pure data pipelines (ETL, ML preprocessing), functional style with narrow functions often achieves the same goals as SOLID OOP with less boilerplate.

---

## Abstract Base Classes (ABC) vs. Protocol

This is the most practically important Python-specific tradeoff in SOLID.

| Dimension | `abc.ABC` + `@abstractmethod` | `typing.Protocol` |
|-----------|------------------------------|-------------------|
| **Subtyping** | Nominal (must `class Foo(ABC)`) | Structural (duck typing checked by mypy) |
| **Enforcement** | Runtime (`TypeError` on instantiation) | Static (mypy only, no runtime check unless `@runtime_checkable`) |
| **Third-party compatibility** | Cannot retroactively make external class comply | External class satisfies Protocol without modification |
| **Explicitness** | Inheritance makes intent explicit in `class` declaration | Implicit — discoverable only via type annotations |
| **Multiple compliance** | Explicit multiple inheritance | Object satisfies multiple Protocols naturally |
| **Best for** | Internal hierarchies; when runtime enforcement is needed | Dependency boundaries; decoupling from third-party libs |

```python
# ABC: explicit, runtime-enforced
class PaymentProvider(ABC):
    @abstractmethod
    def charge(self, amount: Decimal) -> Receipt: ...

class StripeProvider(PaymentProvider):  # must declare intent
    def charge(self, amount: Decimal) -> Receipt: ...

# Protocol: structural, flexible
class PaymentProvider(Protocol):
    def charge(self, amount: Decimal) -> Receipt: ...

class StripeProvider:  # no inheritance required
    def charge(self, amount: Decimal) -> Receipt: ...

# Both work — Protocol is more Pythonic for DIP boundaries
```

**Recommendation**: Use `Protocol` for dependency inversion boundaries (ports in hexagonal architecture). Use `ABC` for internal class hierarchies where you want explicit "this is a subtype" declaration and runtime enforcement.

---

## SOLID Overhead: When Not to Apply

| Context | SOLID Worth It? | Reasoning |
|---------|----------------|-----------|
| Script < 200 LOC | No | No collaboration, no tests needed, throw-away |
| Jupyter notebook analysis | No | Exploratory; SRP would kill iteration speed |
| Single-developer microservice with stable requirements | Maybe SRP, DIP only | DIP for testability; SRP for clarity |
| Shared library used by 5+ teams | Yes, fully | Interface stability is critical; OCP and DIP protect callers |
| Prototype / spike | No | Apply SOLID when productionizing, not spiking |
| Long-lived domain core (orders, payments, identity) | Yes, fully | These change most; SOLID pays off most here |

**The tell**: if you can't write a unit test without spinning up a database, message broker, or HTTP server, DIP is missing. That's the clearest signal that SOLID investment has ROI.

---

## Inheritance vs. Composition (Practical LSP Consequence)

LSP problems most commonly arise from deep inheritance hierarchies. The standard resolution is **composition over inheritance**:

| | Inheritance | Composition |
|---|-------------|-------------|
| **Coupling** | Tight (subclass depends on all of parent) | Loose (composed object exposes narrow interface) |
| **Reuse** | Reuse via extending | Reuse via delegating |
| **LSP risk** | High (fragile base class problem) | Low (composed objects are independently testable) |
| **Flexibility** | Fixed at class definition time | Swappable at runtime |

```python
# Inheritance (LSP risk)
class EnhancedList(list):
    def add(self, item): self.append(item)  # violates list contract subtly

# Composition (safe)
class EnhancedList:
    def __init__(self): self._items = []
    def add(self, item): self._items.append(item)
    def __len__(self): return len(self._items)
```

**Rule of thumb**: Prefer composition when the relationship is "has-a" or "uses-a". Use inheritance only for true "is-a" relationships where LSP can be verified.

---

## Comparing SOLID Implementations Across Languages

Python's dynamic type system creates tradeoffs vs. statically-typed languages:

| Dimension | Java / C# | Python |
|-----------|-----------|--------|
| Interface mechanism | `interface` keyword | `Protocol` (structural) or `ABC` (nominal) |
| DI containers | Spring, Guice, .NET DI | `dependency-injector`, `lagom`, or manual |
| OCP extension mechanism | Generics + interfaces | `Protocol` + duck typing + `functools.singledispatch` |
| LSP enforcement | Compiler catches signature mismatches | mypy + `@override` (Python 3.12+) |
| ISP enforcement | Interface narrowing at compile time | `Protocol` + mypy |
| Boilerplate | High (Java: lots of interface files) | Low (`Protocol` is 2 lines) |

Python's lower boilerplate means SOLID is cheaper to apply but also easier to violate implicitly. The discipline must be compensated by strong type annotation culture and mypy enforcement in CI.
