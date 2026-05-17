# What to Measure & How

## Operational Metrics for Code Quality (SOLID as a Design Discipline)

Unlike runtime systems, SOLID compliance is measured at development time and in CI/CD. The "SLOs" here are quality gates that prevent architectural degradation over time.

---

## Metrics Checklist

| Metric Name | Type (counter/gauge/ratio) | Target SLO | Collection Method |
|-------------|--------------------------|------------|-------------------|
| **Cyclomatic complexity (CC) per function** | Gauge | Max CC ≤ 10 per function | `radon cc src/ -n C` in CI |
| **Average CC per module** | Gauge | Average CC < 5 | `radon cc src/ --total-average` |
| **Maintainability Index (MI)** | Gauge (0-100) | MI > 65 per file | `radon mi src/ -s` |
| **Type error count** | Counter | 0 errors under `mypy --strict` | `mypy src/ --strict` in CI |
| **`isinstance` in domain layer** | Counter | 0 | `grep -rn "isinstance(" src/domain/` |
| **Concrete imports in domain** | Counter | 0 | `lint-imports` (import-linter) |
| **`raise NotImplementedError` stubs** | Counter | 0 in non-abstract code | `grep -rn "raise NotImplementedError"` |
| **Lines of code per class** | Gauge | < 300 LOC | `wily` or `radon raw` |
| **Methods per class** | Gauge | < 20 public methods | `pylint too-many-public-methods` |
| **Parameters per function** | Gauge | ≤ 7 | `pylint too-many-arguments` |
| **Test coverage %** | Ratio | ≥ 85% (domain layer ≥ 95%) | `pytest --cov` |
| **Test file to source ratio** | Ratio | ≥ 1:1 | File count comparison |
| **Mocks per test** | Gauge (sampled) | ≤ 3 mocks per test | Manual review / `pytest-mock` usage grep |
| **Circular import count** | Counter | 0 | `pydeps --show-cycles` |
| **PR size (lines changed)** | Gauge | < 400 lines per PR | GitHub/GitLab PR analytics |
| **File churn (commits per file/month)** | Gauge | Flag files > 20 commits/month | `git log --oneline -- file.py | wc -l` |

---

## Setting Up the Measurement Toolchain

### Step 1: radon in CI

```bash
# Install
pip install radon wily

# Check complexity (fail if any function is grade C or worse)
radon cc src/ -n C --total-average

# Maintainability index
radon mi src/ -s --min B

# Raw metrics (LOC, SLOC per file)
radon raw src/ -s
```

### Step 2: mypy strict mode

```toml
# pyproject.toml
[tool.mypy]
strict = true
ignore_missing_imports = false
disallow_untyped_defs = true
disallow_any_generics = true
warn_return_any = true
warn_unused_ignores = true
```

```bash
mypy src/ 2>&1 | tee mypy_report.txt
# Gate: fail CI if exit code != 0
```

### Step 3: import-linter for architectural boundaries

```toml
# .importlinter
[importlinter]
root_package = myapp
include_external_packages = True

[importlinter:contract:domain-purity]
name = Domain layer must not import infrastructure
type = forbidden
source_modules = myapp.domain
forbidden_modules =
    myapp.infrastructure
    sqlalchemy
    boto3
    redis
    celery
```

```bash
pip install import-linter
lint-imports  # fails CI on boundary violations
```

### Step 4: wily for trend tracking

```bash
# Build history (run once per release or weekly)
wily build src/

# Show metric changes since last version
wily diff src/ -r HEAD~10

# Report on a specific file's complexity over time
wily report src/domain/order_service.py cyclomatic
```

### Step 5: pydeps for dependency visualization

```bash
pip install pydeps
pydeps src/myapp --max-bacon 3 --cluster --rankdir BT -o deps.svg
# Review the SVG — domain should have arrows pointing at it (depended on)
# not pointing away (depending on infra)
```

---

## File Churn Analysis (SRP Violation Detector)

Files that change frequently for many different reasons are SRP violations waiting to be named.

```bash
# Files changed most frequently in last 90 days
git log --since="90 days ago" --format="%H" | xargs -I{} git diff-tree --no-commit-id -r --name-only {} \
  | sort | uniq -c | sort -rn | head -20
```

A file appearing 40+ times in 90 days warrants investigation: is it changing for one reason, or many? Cross-reference with PR titles — if the same file appears in "fix email", "update pricing", "change notifications", it's doing too much (SRP violation).

---

## Test Quality Signals

### Mocking density (DIP signal)

```bash
# Count mock usage per test file — high counts signal DIP violations
grep -rn "mock\|Mock\|patch" tests/ | awk -F: '{print $1}' | sort | uniq -c | sort -rn | head -10
```

More than 3-4 mocks per test is a yellow flag. If you're mocking `smtplib.SMTP`, `psycopg2.connect`, and `requests.post` directly in the same test, you're testing the infrastructure wiring, not the business logic — DIP is missing.

### Test setup size (SRP signal)

```bash
# Find tests with large setup blocks (> 20 lines of setup before first assertion)
grep -n "def test_" tests/ -A 30 | grep -E "assert|# THEN" | awk '{if ($0 ~ /assert/) print NR}'
```

A test requiring 20 lines of setup to exercise one behavior means the class under test has too many responsibilities.

---

## Practical Enforcement: Pre-commit Hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.3.0
    hooks:
      - id: ruff
        args: [--fix]

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.9.0
    hooks:
      - id: mypy
        args: [--strict]

  - repo: local
    hooks:
      - id: radon-complexity
        name: Check cyclomatic complexity
        entry: radon cc src/ -n C
        language: python
        pass_filenames: false

      - id: import-linter
        name: Check import boundaries
        entry: lint-imports
        language: python
        pass_filenames: false
```

---

## Design Review Checklist (Manual SOLID Audit)

Use this when reviewing PRs for architectural quality:

**SRP**
- [ ] Does each class have a single clear name that describes one thing?
- [ ] Would this class need to change for more than one category of reason?
- [ ] Are there private methods that seem unrelated to the class's primary purpose?

**OCP**
- [ ] Are there `if/elif` chains that switch on type or string identifiers? (OCP smell)
- [ ] If we add a new variant of X, how many files change? More than 1 = OCP violation.

**LSP**
- [ ] Do any subclass methods `raise NotImplementedError`?
- [ ] Are there `isinstance` checks in code that should be polymorphic?
- [ ] Would all subtypes pass the same set of behavioral tests as the parent?

**ISP**
- [ ] Do any functions take a large object but only use 1-2 fields from it?
- [ ] Are there abstract methods that some implementors leave as stubs?

**DIP**
- [ ] Are concrete classes instantiated inside domain/service layer methods?
- [ ] Can the class be tested without any external infrastructure?
- [ ] Are dependencies injectable via constructor?
