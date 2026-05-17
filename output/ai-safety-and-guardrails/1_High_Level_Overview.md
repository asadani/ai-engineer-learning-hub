# High-Level Overview

## What It Is

**AI safety & guardrails** for production LLMs is the discipline of constraining model inputs, behavior, and outputs so the system is secure, policy-compliant, and bounded in blast radius — even under adversarial use. It spans application security (prompt injection, data exfiltration), content safety (toxicity, self-harm, illegal content), and operational safety (an agent doing something irreversible).

## Why LLM Security Is Different

Traditional appsec assumes a clear code/data separation. LLMs erase it: **instructions and data share one channel — natural language**. Any text the model reads — user input, a retrieved document, a tool result, another agent's message — can be interpreted as an instruction. This is why prompt injection has no clean fix and why classic input-sanitization intuitions are insufficient.

## The OWASP Top 10 for LLM Applications (2025)

The authoritative threat model interviewers expect you to know. Headline items:

- **LLM01 Prompt Injection** — #1 for the second consecutive edition. Attacker input is interpreted as instructions.
- **LLM02 Sensitive Information Disclosure** — leaking PII/secrets/system prompt.
- **LLM03 Supply Chain** — compromised models, datasets, plugins.
- **LLM04 Data & Model Poisoning** — tampered training/fine-tune/RAG data.
- **LLM05 Improper Output Handling** — unsanitized model output reaching downstream systems (XSS, SQLi, command exec).
- **LLM06 Excessive Agency** — agent has more tool capability/autonomy than the task needs.
- **LLM07 System Prompt Leakage** — secrets/logic embedded in the system prompt exposed.
- **LLM08 Vector & Embedding Weaknesses** — RAG-specific injection/poisoning/retrieval attacks.
- **LLM09 Misinformation** — confident, unsupported output relied upon.
- **LLM10 Unbounded Consumption** — cost/DoS via uncontrolled inference (token/wallet drain).

## The Core Principle: Defense-in-Depth

No single control stops prompt injection. OWASP's own guidance: treat any one mechanism as *one layer*, not a replacement for the others. The layered design:

```
1. Input    : validation, structure/fencing, injection classifier (Prompt Guard)
2. Policy   : system-prompt hardening, least-privilege tool scopes
3. Model    : safety-tuned model + guardrail model on I/O (Llama Guard / NeMo)
4. Action   : human-in-the-loop on irreversible/destructive tools, dry-run
5. Output   : output filtering, schema/grounding checks, downstream sanitization
6. Monitor  : red-team evals, online detection, audit, rate/cost limits
```

## Where It Sits

Safety wraps the whole stack: it constrains prompt engineering (system-prompt leakage), RAG (vector/embedding + indirect injection), agents/protocols (excessive agency, confused deputy), and cost (unbounded consumption). It is a cross-cutting requirement, not a feature — and in regulated domains it is a launch gate.
