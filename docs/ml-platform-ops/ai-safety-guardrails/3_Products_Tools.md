# Products & Tools

## Guardrail Models (classifiers)

| Tool | Focus | Notes |
|---|---|---|
| **Llama Guard** (Meta) | Input/output safety taxonomy | Widely used open baseline |
| **Prompt Guard** (Meta) | Prompt-injection / jailbreak detection | Low latency; higher bypass alone |
| **ShieldGemma** (Google) | Content safety classification | Open weights |
| **Granite Guardian** (IBM) | Safety + hallucination/risk checks | Open weights |

## Orchestration / Policy

| Tool | Role |
|---|---|
| **NVIDIA NeMo Guardrails** | Orchestrate topical/safety/jailbreak/grounding rails via policy; ~0% bypass achievable at FPR+latency cost |
| **Guardrails AI** | Output schema/validation + correction rails |
| Provider safety systems | Built-in moderation/safety on frontier APIs (first layer, not sole layer) |

## Red-Teaming & Evaluation

| Tool | Role |
|---|---|
| **DeepTeam (Confident AI)** | LLM red-teaming mapped to OWASP LLM Top 10 |
| **garak** | LLM vulnerability scanner (injection, jailbreak, leakage) |
| **UK AISI Inspect** | Rigorous safety evaluations (see *Evals in AI*) |
| OWASP LLM Top 10 / Cheat Sheets | Threat model + prompt-injection-prevention checklist |

## Standards & References

- **OWASP Top 10 for LLM Applications (2025)** — canonical threat model.
- **OWASP LLM Prompt Injection Prevention Cheat Sheet** — concrete mitigations.
- MITRE ATLAS — adversarial ML threat knowledge base.

## Selection Guidance

- Baseline content safety on I/O → **Llama Guard** (or ShieldGemma/Granite Guardian).
- Injection/jailbreak specifically → **Prompt Guard** + structural/defense-in-depth (not alone).
- Need topical + grounding + jailbreak policy orchestration → **NeMo Guardrails** (accept FPR/latency).
- Output must be structurally valid → **Guardrails AI** + constrained decoding.
- Prove resistance → **DeepTeam/garak** red-team mapped to OWASP, in CI.
- Principle: layer provider safety + classifier + structure + least-privilege + HITL + monitoring — never ship a single control.
