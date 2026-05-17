# Use Cases & Real-World Applications

## 1. Structured Extraction

Pull fields from messy documents. Pattern: system role + explicit JSON Schema + constrained/structured output + rule "if a field is absent, return `null`, never guess" + 2–3 representative few-shot examples covering edge cases. Eval on a labeled set with exact-match/field-F1. Outcome: parseable, low-hallucination extraction without prose-parsing.

## 2. Classification / Routing

Route tickets or queries to categories. Pattern: enumerate categories with crisp definitions and boundary examples, force a single-label structured output, add an explicit "ambiguous → `needs_human`" escape. Eval with precision/recall/F1 per class. Outcome: stable routing with a safe abstain path.

## 3. Agent System & Tool Prompts

An agent's reliability is largely its system prompt and tool descriptions. Pattern: precise role, explicit tool-use policy (when to call, when to stop, irreversibility gating), fenced tool outputs, decomposition of plan vs act. Tool descriptions are prompt engineering *and* an injection surface — keep them tight and untrusting of returned content.

## 4. RAG Answer Synthesis

The generation half of RAG is a prompt problem. Pattern: instruct strict grounding ("answer only from the provided context; if unsupported, say so"), cite sources, place the question at the end (recency), fence retrieved context. Eval faithfulness/groundedness (RAGAS). Outcome: reduced hallucination on retrieved content.

## 5. LLM-as-Judge / Eval Prompts

Evaluation itself runs on prompts. Pattern: a rubric with explicit criteria and scales, few-shot calibrated exemplars, structured score output, and bias controls (position-swap, blind to source). A poorly engineered judge prompt silently corrupts every metric downstream.

## 6. Reasoning-Model Task Prompt

Hard analytical task on an extended-thinking model. Pattern: state the objective, hard constraints, and required output format; *omit* "think step by step" and hand-written reasoning scaffolds; set/observe a thinking budget. Outcome: better accuracy and controlled thinking-token cost vs over-scaffolded prompts.

## Pattern Summary

| Need | Prompt pattern |
|---|---|
| Parseable fields | Schema + constrained output + null rule |
| Safe routing | Defined classes + abstain path |
| Reliable agent | Tight system/tool prompts + decomposition |
| Grounded RAG answers | Strict-grounding + cite + question-last |
| Trustworthy evals | Rubric + calibrated judge + bias controls |
| Reasoning tasks | Goal/constraints/output, no CoT scaffolding |
