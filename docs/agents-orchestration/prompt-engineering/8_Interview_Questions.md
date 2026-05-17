# Interview Questions & Scenarios

## L5 — Foundations

**Q1. Is prompt engineering still relevant in 2026, or did better models / context engineering kill it?**
Still core. Better models raise the floor but don't remove the need to specify a task unambiguously — variance from under-specification persists. Context engineering is the system that assembles context; the instruction part of that context *is* prompt engineering. It's the cheapest, fastest, lowest-risk lever and the substrate beneath every agent (system + tool prompts).

**Q2. How do you make a prompt reliable rather than clever?**
Remove ambiguity: explicit role, explicit task, explicit constraints, fenced/delimited inputs, representative few-shot only where needed, and a guaranteed output schema via constrained decoding. Then prove it on a held-out labeled set and protect it with a CI regression gate. Reliability is specification + evaluation, not magic phrases.

**Q3. Zero-shot vs few-shot — how do you decide?**
Default zero-shot on capable 2026 models. Add few-shot only when evals show a format/convention/edge-case gap the instruction can't convey. Examples must be representative and diverse; unrepresentative examples teach the wrong distribution, and they cost tokens and risk lost-in-the-middle.

## L6 — Design & Tradeoffs

**Q4. A production prompt is flaky. Walk me through fixing it.**
Don't tweak wording blindly. Build/extend a labeled eval set from real failing inputs. Inspect failures for a pattern: is it under-specified (add constraints), fused (decompose into extract→reason→format), format-fragile (constrained output), or example-poisoned (fix few-shot)? Iterate against the held-out set, sensitivity-sweep, then gate the fix in CI with rollback. Escalate to RAG/fine-tune only if measured insufficient.

**Q5. When do you decompose vs keep one prompt?**
Decompose when one prompt fuses multiple tasks or when failures aren't attributable. Decomposition gives reliability and localizable errors at the cost of more calls/orchestration. Keep a single prompt when the task is genuinely atomic and a single call meets quality — don't pay orchestration cost for nothing.

**Q6. How does prompting differ for reasoning models vs standard models?**
Standard models benefit from explicit chain-of-thought and step scaffolding. Reasoning/extended-thinking models reason internally (often in a hidden trace); hand-authored CoT and heavy few-shot can constrain or derail them and waste thinking tokens. For reasoning models: state goal, hard constraints, and output format; omit step scaffolding; budget thinking tokens. Knowing the target model class is essential.

## L7+ — Principal

**Q7. Make prompts a governed, safe part of the SDLC for 50 engineers.**
Prompts as code: versioned in git/prompt-manager, code-reviewed, each bound to a labeled eval dataset. CI runs the suite on any prompt PR and blocks below threshold. Deploy by label/alias for instant rollback. Bind production traces to prompt version (OTel) and sample outputs into an offline judge for drift detection. Treat a prompt change exactly like a code deploy — auditable, testable, reversible.

**Q8. How do you prove a new prompt is better and won't regress something else?**
A held-out labeled suite with hard/edge/adversarial cases and a task-appropriate metric; require regression delta ≥ 0 vs baseline before ship, plus a sensitivity sweep (paraphrases, example order, input shift) reporting variance not just mean. Gate in CI. A single playground "looks better" is not evidence; an unstable high score is a fail.

**Q9. Where does prompt engineering stop and RAG/fine-tuning begin?**
Prompt engineering fixes ambiguity, behavior, and format. If the gap is *missing or changing knowledge*, that's RAG. If it's a *latent skill, style, or format the model can't be instructed into* after solid prompting + RAG, that's fine-tuning. The discipline is to climb the ladder only on *measured* insufficiency — most teams over-escalate and pay infra/training cost for a prompt+eval problem.

## Rapid-Fire

- *Prompts are…?* Code — versioned, reviewed, regression-tested.
- *Guarantee parseable output how?* Constrained/structured decoding, not prose-parsing.
- *CoT on a reasoning model?* Usually counterproductive.
- *Cheapest lever in the stack?* A well-engineered, evaluated prompt.
- *"It works" means?* A measured pass rate on a held-out set.
