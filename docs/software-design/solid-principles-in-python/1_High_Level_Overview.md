# High-Level Overview

## What It Is

SOLID is a set of five object-oriented design principles coined by Robert C. Martin ("Uncle Bob") in the early 2000s, later synthesized by Michael Feathers into the acronym. They are prescriptive heuristics — not laws — for structuring code to maximize **changeability, testability, and understandability** over time.

| Letter | Principle | One-Line Summary |
|--------|-----------|-----------------|
| **S** | Single Responsibility Principle | A class should have one reason to change |
| **O** | Open/Closed Principle | Open for extension, closed for modification |
| **L** | Liskov Substitution Principle | Subtypes must be substitutable for their base types |
| **I** | Interface Segregation Principle | Clients shouldn't depend on interfaces they don't use |
| **D** | Dependency Inversion Principle | Depend on abstractions, not concretions |

## Why They Matter

The root problem SOLID solves is **code that is expensive to change**. In the absence of these principles, common failure modes are:

- **Shotgun surgery**: changing one behavior requires modifying 10 files
- **Fragile base class**: changing a parent class silently breaks unrelated subclasses
- **Tight coupling**: swapping a database or API client requires rewriting business logic
- **Untestable code**: business logic is entangled with I/O, making unit tests impossible without full infrastructure

These failure modes compound over time. SOLID principles address them structurally, at design time, not at debug time.

## Python-Specific Context

Python's dynamic type system makes SOLID both easier and more ambiguous to apply:

- **Duck typing** means "interface" doesn't require `ABC` or `Protocol` — any object with the right methods satisfies a contract. This makes ISP and DIP lighter-weight to implement but harder to enforce.
- **`typing.Protocol`** (PEP 544, Python 3.8+) enables structural subtyping — an object satisfies a `Protocol` without explicitly inheriting from it. This is the Pythonic way to express interfaces without the Java-style boilerplate.
- **`abc.ABC` and `@abstractmethod`** enforce nominal typing — subclasses must explicitly inherit and implement abstract methods. Use when you want inheritance hierarchy with enforced contracts.
- **Dataclasses and `attrs`** implement SRP cleanly for value objects without boilerplate.
- **Dependency injection in Python** is typically done through constructor arguments — no DI container is usually needed, though `dependency-injector` and `lagom` exist for complex applications.

## Common Misconceptions

1. **"SOLID means lots of small classes"** — Not inherently. SRP means one reason to change, not one method. A `UserRepository` with 15 CRUD methods is SRP-compliant.

2. **"SOLID is only for OOP"** — The principles translate to functional style: SRP → pure functions; OCP → higher-order functions and composition; DIP → passing functions as arguments.

3. **"Applying SOLID is always the right call"** — SOLID increases abstraction layers, which adds indirection and complexity. For scripts, simple utilities, or prototypes, SOLID is over-engineering. Apply SOLID proportionally to code that needs to change, scale, or be tested.

4. **"Python doesn't need explicit interfaces for SOLID"** — True for duck typing, but `Protocol` annotations make contracts explicit and enable mypy to catch violations at development time rather than at runtime.

## Relationship to Other Principles

- **DRY (Don't Repeat Yourself)** and SRP can conflict: eliminating duplication sometimes creates inappropriate coupling between modules that have different reasons to change.
- **YAGNI (You Aren't Gonna Need It)** is a corrective to over-applying OCP — don't design for extension points that don't exist yet.
- **Composition over Inheritance** is the practical implementation strategy for OCP and LSP — prefer building behavior by composing objects rather than extending class hierarchies.

## When SOLID Pays Off Most

- Long-lived codebases (> 6-month lifecycle)
- Team codebases where multiple engineers modify the same code
- Code that is unit-tested (SOLID makes code testable; testability makes SOLID visible)
- Domains with known extension points (plugin systems, payment providers, notification channels)
- Anywhere the cost of a wrong design is high (core domain logic, shared libraries)
