# Use Cases & Real-World Applications

## 1. Hard Math / Science / Code

The canonical fit: competition math, theorem-style reasoning, complex algorithmic coding, scientific analysis. A reasoning model with an adequate thinking budget materially outperforms a same-size standard model. Pattern: state the problem + constraints + answer format; let it think; verify with a checker where possible (pairs naturally with RLVR-style verification).

## 2. Agent Controller / Planner

Use a reasoning model as the *planner* of an agent (decompose, choose tools, reflect on results) while cheaper standard models handle routine sub-steps. Outcome: better plans and recovery on complex tasks without paying reasoning cost for every step. (See *Agentic Design Patterns*.)

## 3. Difficulty-Based Routing

A router classifies query difficulty: easy → standard model; hard → reasoning model (or escalate on low confidence / verifier failure). Outcome: reasoning-level accuracy on the hard tail at a fraction of the blended cost. The single highest-ROI deployment pattern. (See *Cost Optimization*.)

## 4. Verifiable-Reward Domains

Where outputs are checkable (unit tests, symbolic math, schema/constraint satisfaction), reasoning + an automated verifier (best-of-N, reject-and-retry) yields high reliability. The verifier also doubles as your eval signal.

## 5. Reasoning Distillation for Cost

Distill a frontier reasoner's traces into a small open model for a domain (e.g., support triage with multi-step policy logic). Outcome: most of the reasoning quality at commodity-GPU cost and latency, on-prem if needed.

## 6. When NOT to Use a Reasoning Model

Extraction, classification, summarization, retrieval-grounded Q&A, casual chat, anything latency-critical and not reasoning-bound. Here a reasoning model adds cost and latency for ≈0 quality gain — and overthinking can *reduce* quality. Knowing the non-use cases is a senior signal.

## Pattern Summary

| Need | Pattern |
|---|---|
| Hard math/code/science | Reasoning model + verifier, tuned budget |
| Complex agent plans | Reasoning planner + cheap workers |
| Cost-efficient quality | Difficulty routing standard↔reasoning |
| Checkable outputs | Reasoning + automated verifier (best-of-N) |
| Cheap reasoning at scale | Distilled small reasoner |
| Simple/latency-critical | **Standard model** (don't use reasoning) |
