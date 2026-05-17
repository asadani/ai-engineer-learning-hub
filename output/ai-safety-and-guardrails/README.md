# AI Safety & Guardrails

Principal-level interview prep notes on securing and constraining LLM applications — the **OWASP Top 10 for LLM Applications (2025)**, prompt-injection defense, guardrail models, and defense-in-depth for agents.

Generated: 2026-05-17 (web-grounded)

---

## Contents

| # | File | Focus |
|---|------|-------|
| 1 | [High-Level Overview](1_High_Level_Overview.md) | Threat model, why LLM security is different, OWASP LLM Top 10 |
| 2 | [Key Technical Concepts](2_Key_Technical_Concepts.md) | Direct vs indirect prompt injection, guardrail models, defense-in-depth, agent risk, jailbreaks |
| 3 | [Products & Tools](3_Products_Tools.md) | Llama Guard, ShieldGemma, Granite Guardian, Prompt Guard, NeMo Guardrails, red-team tooling |
| 4 | [Tradeoffs & Comparisons](4_Tradeoffs_Comparisons.md) | Security vs usability vs latency, guardrail comparison, prevention vs detection |
| 5 | [Use Cases](5_Use_Cases.md) | RAG injection, tool-using agents, content moderation, regulated domains |
| 6 | [Measurement & Evaluation](6_Measurement_Evaluation.md) | Bypass rate, FPR, latency, red-teaming |
| 7 | [What to Measure & How](7_What_to_Measure_How.md) | Metrics, instrumentation, alerting |
| 8 | [Interview Questions](8_Interview_Questions.md) | Tiered Q&As (L5/L6/L7+) with model answers |

---

## Key Themes

### 1. Prompt Injection Is the #1 Risk — Two Editions Running
Prompt injection holds the top spot in the OWASP Top 10 for LLM Applications **2025** (second consecutive edition). There is no single fix; it is mitigated, not solved.

### 2. Guardrails Are One Layer, Not the Answer
A guardrail model (Llama Guard, etc.) is one control in a defense-in-depth design — alongside input validation, structured/fenced prompts, least-privilege tool scopes, and human approval on destructive actions. Treating a guardrail as the whole solution is the classic failure.

### 3. Every Control Is a Security–Usability–Latency Trade
Empirically, NeMo Guardrails can reach ~0% bypass but at ~16% false-positive rate and >1.3 s latency; lighter classifiers are faster but leak more. There is no free guardrail — you tune the operating point to the use case.

### 4. Agents Multiply the Blast Radius
An LLM that can call tools turns a text exploit into action (data exfiltration, irreversible operations, confused-deputy via chained agents/MCP). Tool scope and human-in-the-loop on irreversible actions are the high-leverage controls.

### 5. Trust Boundaries Move Into the Prompt
Retrieved documents, tool outputs, and other agents' messages are *untrusted input the model reads as text*. Indirect prompt injection lives here. Fence data, never auto-trust returned content, propagate identity without widening scope.
