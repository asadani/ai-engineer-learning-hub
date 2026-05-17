# Products & Tools

## Prompt Management / Versioning

| Tool | Role |
|---|---|
| **Langfuse Prompt Management** | Versioned prompts, deploy labels, link prompts to traces/evals |
| **LangSmith** | Prompt hub, versioning, dataset-backed evals |
| **PromptLayer / Helicone** | Prompt registry, A/B, request logging |
| Git + templates | Prompts as files, code review, CI — the baseline discipline |

## Programmatic Optimization

| Tool | Role |
|---|---|
| **DSPy** | Declarative "programs"; optimizes instructions + few-shot against a metric |
| TextGrad / optimizer libs | Gradient-style textual optimization of prompts |

## Structured Output

| Tool | Role |
|---|---|
| Provider structured outputs / tool calling (Anthropic, OpenAI, Google) | Schema-guaranteed JSON |
| **Pydantic / Instructor / Outlines** | Typed parsing + constrained/grammar decoding |

## Evaluation & Playgrounds

| Tool | Role |
|---|---|
| **Arize Phoenix, Langfuse, LangSmith** | Prompt eval datasets, LLM-as-judge, regression runs |
| **OpenAI Evals / UK AISI Inspect** | Reusable eval harnesses for prompt suites |
| Provider playgrounds / workbench | Fast manual iteration before formalizing into evals |

## Selection Guidance

- Production prompt → store in a **versioned prompt manager** (or git), link to an eval set, gate changes in CI.
- Output must be machine-parsed → **constrained/structured output**, never prose-parsing.
- High-stakes prompt, plateaued by hand → **DSPy**-style optimization against a metric.
- Proving a change → **eval platform with a labeled dataset + LLM-judge**, not a playground glance.
- Don't adopt heavy tooling first; the non-negotiable baseline is *prompt-in-git + a labeled eval set in CI*.
