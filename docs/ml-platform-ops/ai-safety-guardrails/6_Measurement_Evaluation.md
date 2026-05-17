# Measurement & Evaluation

## What "Good" Means

A safe system has an **acceptably low bypass rate at an acceptable false-positive rate and latency for its surface**, demonstrated by red-teaming against the OWASP LLM Top 10 — and bounded blast radius when a control does fail.

## Core Metrics

- **Bypass / attack success rate (ASR)** — fraction of adversarial prompts that defeat the guardrails and elicit unsafe behavior. The primary security metric. Lower = safer.
- **False-positive rate (FPR)** — fraction of *legitimate* requests wrongly blocked/refused. The usability cost. Over-refusal is a real failure, not "safe by default."
- **Latency overhead** — added time from guardrail/classifier passes. The UX cost.
- **Blast radius** — what an attacker can actually *do* on success (read-only vs irreversible action vs data exfiltration). Least privilege shrinks this independently of ASR.

These trade off (the security–usability–latency triangle); report them together, never ASR alone.

## Red-Teaming Method

1. **Map to OWASP LLM Top 10** — direct + indirect injection, jailbreaks, sensitive-info disclosure, improper output handling, excessive agency, unbounded consumption.
2. **Curated + automated attack suites** — known jailbreak families, encoding/role-play/many-shot, indirect payloads in documents/tool outputs/agent messages; tools like garak/DeepTeam.
3. **Per-surface evaluation** — each tool/endpoint at its chosen operating point (strict vs permissive).
4. **Action-level tests** — confirm irreversible tools require HITL even when the model is jailbroken (blast-radius verification).
5. **CI gate** — red-team suite runs on model/prompt/guardrail changes; regressions block deploy.
6. **Online detection** — sample production traffic for injection/jailbreak signatures and refusal anomalies (ties to *LLM Observability*).

## Evaluation of Trade-offs

Plot ASR vs FPR vs latency for candidate guardrail configurations on a representative attack+benign set; choose the operating point per surface. A config that "blocks everything" with 16% FPR is a *measured* decision, not a default.

## Anti-Patterns

- Reporting ASR without FPR/latency (hides over-refusal and UX cost).
- Testing only direct injection (misses indirect — the agent/RAG killer).
- Red-teaming once at launch, never in CI.
- Measuring detection but not blast radius (a contained breach ≠ no breach if the agent could act).
- One operating point across all surfaces.
