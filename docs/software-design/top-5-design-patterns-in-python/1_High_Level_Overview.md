# High-Level Overview

## What Design Patterns Are

Design patterns are named, reusable solutions to recurring software design problems. They are not code libraries — they are structural templates that capture proven approaches to organizing collaborations between objects. The GoF book (Gang of Four — Gamma, Helm, Johnson, Vlissides, 1994) catalogued 23 patterns across three categories: **Creational**, **Structural**, and **Behavioral**.

| Category | Concern | Examples |
|----------|---------|---------|
| **Creational** | How objects are created | Factory Method, Abstract Factory, Singleton, Builder, Prototype |
| **Structural** | How objects are composed | Decorator, Adapter, Facade, Proxy, Composite |
| **Behavioral** | How objects communicate | Strategy, Observer, Command, Iterator, Template Method |

## The Top 5 for Python Engineers

The five patterns covered in this guide were selected based on:
- Frequency in production Python codebases (microservices, ML pipelines, web backends)
- Interview prevalence at senior/principal level
- Python-specific nuances that distinguish them from Java/C++ implementations

| # | Pattern | Category | Core Problem Solved |
|---|---------|----------|---------------------|
| 1 | **Strategy** | Behavioral | Swap algorithms/behaviors at runtime without branching |
| 2 | **Factory Method & Abstract Factory** | Creational | Decouple object creation from usage |
| 3 | **Decorator** | Structural | Extend behavior without subclassing or modifying |
| 4 | **Observer** | Behavioral | Notify dependents of state changes without tight coupling |
| 5 | **Repository** | Architectural | Decouple domain logic from data access |

Note: Repository is not a GoF pattern — it originates from Domain-Driven Design (Evans, 2003). It's included because it's the most practically impactful pattern in Python backend services and the one most frequently tested at staff/principal level.

## Why They Matter in Python

Python's dynamic type system, first-class functions, and decorators make several GoF patterns either trivial, redundant, or implemented differently than in Java:

- **Iterator**: Built into the language (`__iter__`, `__next__`, generators). Never implement manually.
- **Singleton**: Python modules are singletons by default. The pattern is mostly implemented via metaclass or module-level instance.
- **Command**: Python's first-class functions often replace command objects — `queue.put(functools.partial(handler, args))` is a command.
- **Template Method**: Usually replaced by higher-order functions or `Protocol` injection rather than abstract base class inheritance.

The five selected patterns remain distinct and valuable in Python because they involve structural choices — how components are composed and communicate — that Python's syntax doesn't automatically resolve.

## Pattern Relationships

```
Strategy ──── "how to do it" varies ──────── Factory creates the right Strategy
   │                                                │
   │ strategies are registered in                  │ abstract factories create
   ▼                                               ▼
Observer ── "when it happens" varies ─── Decorator adds behavior to both

                    Repository
                    "where data lives" varies
                    (implemented as a Strategy for data access)
```

These five patterns commonly appear together in production:
- A `PaymentService` uses **Strategy** to select the payment processor
- A **Factory** creates the right processor based on the provider name
- A **Decorator** wraps the processor with logging and retry logic
- An **Observer** fires domain events after payment succeeds
- A **Repository** abstracts the persistence of payment records

## Python-Specific Advantages

1. **Protocols over ABC**: Python's structural typing makes pattern implementations lighter — no `implements PaymentStrategy` boilerplate.
2. **First-class functions**: Many behavioral patterns can be implemented as callables rather than full classes. This is Pythonic and appropriate for simple cases.
3. **Metaclasses and decorators**: Python's `@decorator` syntax and metaclass system enable pattern implementation at the class definition level, not just at instantiation.
4. **`__init_subclass__`**: Enables auto-registration patterns (key for Observer and Factory) that require explicit registration code in other languages.
5. **Context managers**: A Python-native pattern (`__enter__`/`__exit__`) that implements RAII, not covered in GoF but as important as any of the five listed.
