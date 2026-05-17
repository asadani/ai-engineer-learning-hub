# Measurement & Evaluation

## How to Measure SOLID Adherence

SOLID compliance is not directly measurable — it's a design quality, not a runtime metric. However, proxy metrics and automated tools provide signal on where violations are likely.

---

## Cyclomatic Complexity (SRP Proxy)

Cyclomatic complexity (CC) measures the number of linearly independent paths through code. High CC in a single function or class is a strong SRP smell — one unit is making too many decisions.

**Formula**: `CC = number_of_edges - number_of_nodes + 2` in the control flow graph. Equivalently: 1 + number of branches (if, for, while, except, case).

| CC Score | Risk | Action |
|----------|------|--------|
| 1–5 | Low | OK |
| 6–10 | Moderate | Consider refactoring |
| 11–15 | High | Refactor |
| > 15 | Very High | Mandatory refactor; likely SRP violation |

```bash
radon cc src/ -s -a --min B
# Output:
# src/order_service.py
#   F 45:4 process_order - D (15)  ← grade D, CC=15, refactor
#   F 82:4 validate_payment - B (8) ← acceptable

# Average complexity: B (6.2)
```

**Limitation**: A class with 20 simple methods has low CC per method but may still violate SRP. CC measures complexity of logic, not cohesion of responsibilities.

---

## Coupling Metrics (DIP Proxy)

### Afferent Coupling (Ca)
Number of classes outside a module that depend on it. High Ca = high responsibility; this module is a bottleneck. Changes here ripple widely.

### Efferent Coupling (Ce)
Number of classes a module depends on. High Ce = fragile; this module breaks when many other modules change.

### Instability (I)
`I = Ce / (Ca + Ce)` — ranges 0 (stable, depended on) to 1 (unstable, depends on others).

**DIP implication**: Your domain core should have low instability (I → 0); infrastructure adapters should have high instability (I → 1). If your domain core has I > 0.5, it depends on too many concretions — DIP is missing.

### Abstractness (A)
`A = abstract_classes / total_classes` in a module.

**Stable Abstractions Principle**: `I + A ≈ 1` (on the "main sequence"). Modules that are stable (low I) should be abstract (high A) — these are the stable Protocol/ABC definitions that domain and infra both depend on.

Tools: `radon`, `wily` (tracks metrics over time in git), SonarQube, `pydeps` (visualizes import dependencies as a graph).

```bash
pydeps src/myapp --max-bacon 3 --cluster --rankdir BT
# Generates a dependency graph image — visually identify circular dependencies and DIP violations
```

---

## Cohesion Metrics (SRP Proxy)

### Lack of Cohesion of Methods (LCOM)
Measures how related the methods of a class are by examining which instance variables they share. High LCOM = low cohesion = class should be split.

**LCOM4**: Number of connected components in the method-attribute graph. LCOM4 > 1 means the class has disconnected responsibility clusters — a direct SRP violation signal.

No standard Python tool computes LCOM natively; it can be computed via AST analysis. SonarQube computes it on Python codebases.

---

## Test Coverage as SRP Signal

Unit test coverage at high granularity reveals SRP compliance:

- If a "unit test" for `OrderService` requires mocking 5 dependencies → DIP violation (too many concretions) or SRP violation (too many responsibilities)
- If you can't test `process_payment` without also triggering email sending → SRP violation
- High coverage with small, focused tests → SRP compliance indicator

```bash
pytest --cov=src --cov-report=term-missing
# Look for files with < 80% coverage where missing lines are in deeply nested branches
# Those branches often indicate conditional logic that should be polymorphism (OCP violation)
```

**Mutation testing** (with `mutmut` or `cosmic-ray`) is a stronger signal: if killing a mutation in one class causes tests in an unrelated domain to fail, coupling exists that shouldn't.

```bash
mutmut run --paths-to-mutate src/domain/
mutmut results  # survived mutations = undertested code = potential SRP/DIP violations
```

---

## Type Coverage (ISP / DIP Signal)

```bash
mypy src/ --strict 2>&1 | grep -c "error"
# Zero mypy errors under --strict = Protocol contracts are honored
# Type: ignore comments = suppressed violations worth investigating

# Specific DIP check: count how many times concrete classes are used as type annotations
grep -rn ": Postgres\|: Smtp\|: S3Client" src/domain/  # should be zero
```

High counts of concrete class type annotations inside the domain layer = DIP violations. Domain should only reference `Protocol` types.

---

## Code Smell Signals per Principle

| SOLID Principle | Code Smell | Detection Method |
|-----------------|-----------|------------------|
| SRP | God class (> 300 LOC, > 20 methods) | `radon`, `pylint too-many-public-methods` |
| SRP | Long method (> 50 LOC) | `ruff C901`, `radon` |
| SRP | Divergent change (many unrelated PRs touch same file) | `git log --oneline -- file.py | wc -l` |
| OCP | Switch/if-elif chains on type fields | `pylint`, manual code review |
| OCP | Shotgun surgery (one feature change → many files) | PR diff analysis |
| LSP | `raise NotImplementedError` in subclass methods | `grep -rn "raise NotImplementedError" src/` |
| LSP | `isinstance` checks in polymorphic code | `grep -rn "isinstance(" src/domain/` |
| ISP | Unused abstract method stubs | mypy `--warn-unused-ignores`, manual |
| DIP | Concrete class instantiation inside business logic | `grep -rn "= Postgres\|= Smtp\|= boto3" src/domain/` |
| DIP | `import` of infrastructure modules in domain files | `pydeps` graph, `import-linter` |

### `import-linter` for architectural boundaries

```toml
# setup.cfg
[importlinter]
root_package = myapp

[importlinter:contract:domain-independence]
name = Domain must not import from infrastructure
type = forbidden
source_modules = myapp.domain
forbidden_modules = myapp.infrastructure
```

`lint-imports` will fail CI if any domain module imports from infrastructure — enforcing DIP at the import level.

---

## Continuous Measurement in CI/CD

```yaml
# .github/workflows/quality.yml
- name: Cyclomatic complexity gate
  run: radon cc src/ -n C --total-average
  # fails if any function has CC grade C or worse (> 10)

- name: Type check
  run: mypy src/ --strict

- name: Import architecture
  run: lint-imports

- name: Linting
  run: ruff check src/

- name: Test with coverage
  run: pytest --cov=src --cov-fail-under=85
```

Track `radon mi` (maintainability index) trend over time with `wily`:
```bash
wily build src/
wily diff src/ -r HEAD~5  # show metric changes over last 5 commits
```
