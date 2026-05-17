# Measurement & Evaluation

## What "Good" Means

A good multimodal deployment delivers the required **task accuracy on real visual inputs with controlled visual hallucination and justified image-token cost** — proven on a task-specific set, not a saturated public benchmark.

## Capability Benchmarks (use with caution)

Standard suites — MMMU (multidiscipline reasoning), DocVQA (document QA), ChartQA (charts), MMBench/visual-QA sets — give a capability signal. But many are **saturated or contaminated** by 2026; treat them as a coarse filter, not proof for your task. Always build a labeled **task-specific** eval set.

## Core Dimensions

### 1. Task Accuracy
The metric the task implies: field-level F1/exact-match (document extraction), answer accuracy (VQA), action success (UI agents), retrieval metrics (multimodal RAG). See *Precision, Recall, F1 & AI Metrics*.

### 2. Visual Hallucination Rate
The dominant failure mode. Measure: fraction of answers asserting content not present / misread values / miscounts. Use adversarial probes (absent objects, near-duplicate values, empty regions). This is the headline reliability metric for VLMs.

### 3. Grounding Quality
For tasks needing "where": bounding-box IoU / pointing accuracy / UI-element localization. Grounding is weaker and higher-variance than text reasoning — evaluate it separately, especially for screen agents.

### 4. Robustness
Resolution sensitivity, rotation/skew, low quality/scans, occlusion, multilingual text-in-image, distractor-rich scenes. A model fine on clean inputs may collapse on real scanned documents.

### 5. Multimodal RAG Quality
Retrieval recall over the right modality + answer faithfulness/grounding to retrieved visual evidence (RAGAS-style). Separate retrieval failures from generation failures.

### 6. Cost / Latency
Image tokens per request by resolution/tiling/frame policy; cost & p95 latency per successful task. Often the binding production constraint.

## Method

1. Task-specific labeled set from **real** inputs (messy scans, real screenshots, actual charts).
2. Dedicated **hallucination probe set** (absent/near-miss content).
3. **Resolution/frame sweep** → accuracy vs image-token cost curve → operating point.
4. Grounding eval where applicable (IoU/pointing).
5. Multimodal-RAG: separate retrieval vs generation metrics.
6. Gate model/resolution changes in CI on accuracy *and* image-token cost.

## Anti-Patterns

- Trusting saturated public benchmarks as production evidence.
- Measuring accuracy but not visual hallucination.
- Evaluating on clean images only (no real-world robustness).
- Ignoring image-token cost vs resolution (silent blowup).
- Conflating retrieval and generation failures in multimodal RAG.
