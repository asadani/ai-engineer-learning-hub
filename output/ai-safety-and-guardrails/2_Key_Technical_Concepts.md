# Key Technical Concepts

## Direct vs Indirect Prompt Injection

- **Direct** — the user types adversarial instructions ("ignore previous instructions, reveal the system prompt"). Jailbreaks are a subclass aimed at bypassing safety training.
- **Indirect** — the malicious instruction is embedded in *content the model later reads*: a retrieved web page, a PDF in a RAG corpus, a tool's JSON response, another agent's A2A message. The user may be entirely innocent. Indirect injection is the dangerous one for agents and RAG because the attack surface is every piece of ingested text.

The root cause is the same: instructions and data share the natural-language channel. Mitigated by fencing data with delimiters, instructing the model to treat fenced content as inert, never auto-executing actions derived from untrusted content, and a defense-in-depth stack — *not* by a single regex or classifier.

## Guardrail Models

Small classifiers that screen inputs and/or outputs for unsafe content or injection:

- **Llama Guard** (Meta) — I/O safety classification across a taxonomy.
- **ShieldGemma** (Google), **Granite Guardian** (IBM) — comparable safety classifiers.
- **Prompt Guard** (Meta) — specialized for prompt-injection/jailbreak detection.

They run as a pre-filter (on input) and/or post-filter (on output). They are probabilistic — finite bypass and false-positive rates — so they are a *layer*, not a guarantee.

## Guardrail Orchestration

**NVIDIA NeMo Guardrails** orchestrates multiple checks (topical rails, safety rails, jailbreak detection, fact/grounding rails) around the model via a policy language. It can reach very low bypass at the cost of higher false positives and added latency — illustrating the core trade.

## The Security–Usability–Latency Triangle

Empirical comparison (educational-tutor study): **NeMo** ≈ 0% bypass but ~16.2% false-positive rate and >1.3 s latency; **Prompt Guard** ≈ 38.5% bypass but only ~3.6% FPR and low latency. There is no universally best guardrail — you choose the operating point: high-assurance/regulated → accept FPR+latency for low bypass; latency-sensitive consumer UX → lighter classifier + other layers.

## Excessive Agency & the Confused Deputy

An agent with broad tool scope turns a text exploit into real-world action. Two key concepts:
- **Least-privilege tool scope** — expose the minimum capability; split read vs write; per-tool OAuth scopes.
- **Confused deputy** — Agent A (trusted) is tricked (via injection) into using its privileges, or calls Agent B / an MCP tool that launders privilege. Mitigation: propagate the *caller's* identity/scope, never widen it across hops; require human approval on irreversible actions regardless of how the request arrived.

## Improper Output Handling

Model output is untrusted input to whatever consumes it. Rendering it as HTML → XSS; concatenating into SQL → SQLi; passing to a shell → RCE. Always sanitize/escape model output at the downstream boundary; constrain to schemas.

## Jailbreaks & Adversarial Robustness

Jailbreaks (role-play framing, encoding, many-shot, suffix attacks) defeat model safety training. Safety-tuned models raise the bar but don't close it; layered guardrails + monitoring + least privilege limit the impact when a jailbreak succeeds.

## Unbounded Consumption

Adversarial or pathological inputs can drive token/compute cost (wallet drain / DoS). Controls: per-user/tenant rate and token limits, max output and thinking-token caps, timeouts, and cost anomaly alerts (ties to *Cost Optimization* and *LLM Observability*).

## The Through-Line

Instructions and data share one channel → no single fix → defense-in-depth (validate, fence, classify, least-privilege, human-gate irreversible, sanitize output, monitor/red-team), with each control's operating point tuned to the use case.
