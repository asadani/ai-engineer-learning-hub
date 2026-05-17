# Key Technical Concepts

## Roles & Structure

Separate **system** (durable role, rules, format contract), **user** (the task + inputs), and, where supported, **developer** instructions. Fence untrusted inputs in explicit delimiters (XML/JSON/markdown) so the model distinguishes *instructions* from *data*. Structure is both a quality and a security control (indirect prompt-injection mitigation).

## Zero-shot vs Few-shot

- **Zero-shot**: instruction only. Default for capable 2026 models on common tasks.
- **Few-shot**: include worked input→output examples. Use when the task has a specific format, a non-obvious convention, or edge cases the instruction can't fully convey. Examples must be representative and diverse; bad examples teach bad behavior. Mind token cost and lost-in-the-middle (place pivotal examples at edges).

## Chain-of-Thought (CoT) and Its 2026 Caveat

CoT ("reason step by step") improves multi-step accuracy on **standard** models. But for **reasoning models** (extended-thinking / o-series style), explicit CoT scaffolding is often *counterproductive* — the model already reasons internally (sometimes in a hidden trace). Modern guidance: for reasoning models, state the goal, constraints, and output format clearly and *don't* hand-author the reasoning steps. Knowing which model class you're targeting is the key 2026 distinction.

## Structured / Constrained Output

Specify an exact schema (JSON Schema) and use the provider's structured-output / tool-calling / grammar-constrained decoding to *guarantee* parseable output rather than asking politely and parsing prose. Constrained decoding removes a whole class of "the model wrapped JSON in apology text" failures.

## Decomposition

Split a fused task into focused steps (e.g., extract → validate → reason → format), each with its own small prompt and eval. Decomposition beats wording-tweaking for flaky mega-prompts and makes failures localizable. Trade-off: more calls (cost/latency) and orchestration — escalate only when a single step genuinely can't hold the task.

## Self-Consistency & Sampling

For hard reasoning where a verifier exists or majority voting is valid: sample multiple completions (temperature > 0) and aggregate (majority / best-by-check). Improves accuracy at a compute cost; only worthwhile when the task is hard and the aggregation rule is sound.

## Output Steering Techniques

- **Explicit constraints** ("if unknown, return `null` — do not guess") to control hallucination and refusals.
- **Prefilling** the assistant turn (where supported) to lock format/role.
- **Negative instructions sparingly** — prefer stating the desired behavior over listing prohibitions.
- **Stop conditions / max tokens** aligned to the output contract.

## Prompt Sensitivity & Robustness

Models are sensitive to phrasing, ordering, and example selection. A "good" prompt is one whose pass rate is *stable* across paraphrases and input distribution shifts — measure sensitivity, don't assume it.

## Prompt Optimization (programmatic)

Frameworks like **DSPy** treat prompts as parameters: you specify the task signature and metric, and the framework searches/optimizes instructions and few-shot exemplars against an eval set. This shifts prompt engineering from manual wording to *optimizing against a metric* — the principal-level direction for high-stakes prompts.

## The Through-Line

Reliability = remove ambiguity (role, constraints, fenced inputs) + guarantee format (constrained output) + decompose when fused + match technique to model class (CoT vs reasoning model) + prove it with evals. Everything else is folklore.
