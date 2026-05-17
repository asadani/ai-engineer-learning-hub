# Interview Questions & Scenarios

## L5 — Foundations

**Q1. Sketch a typical VLM architecture.**
Vision encoder (ViT, CLIP/SigLIP-style) → projector/connector (MLP or cross-attention resampler/Q-Former) that maps visual features into the LLM's embedding space → LLM backbone reasons over interleaved visual + text tokens. Modern VLMs mostly use deep fusion (visual tokens in the LLM stream). Naming where fusion happens is the key concept.

**Q2. Why are images a cost concern?**
Images are converted to tokens; higher resolution and tiling produce many more tokens, and video multiplies by frames. A single high-res image or a short video can dwarf the text prompt in token cost and latency. Resolution/tiling/frame policy is an explicit cost/quality knob, not a default.

**Q3. What's the dominant VLM failure mode?**
Visual hallucination: confidently misreading charts/tables, miscounting, "reading" absent text, or describing plausible-but-absent content. It's the headline reliability metric and must be evaluated with adversarial probes (absent/near-miss content), not just accuracy.

## L6 — Design & Tradeoffs

**Q4. VLM vs OCR pipeline for document processing — how do you choose?**
Clean, linear, high-volume text → OCR pipeline is cheap and adequate. Visually-rich, non-linear, multi-column, chart-heavy, or handwritten documents → a VLM (or ColPali-style visual retrieval) reads the page holistically and avoids the brittle, template-bound OCR→layout→parse stack, at higher per-page token cost. Decide by document complexity and maintenance burden, not novelty.

**Q5. Design RAG over a corpus of slide decks and scanned reports.**
Don't caption-then-text-RAG (lossy on layout/charts). Use late-interaction visual retrieval (ColPali/ColQwen) or native multimodal embeddings to index page images; retrieve relevant pages; a VLM answers grounded in those page images with verbatim value reading and region grounding. Evaluate retrieval recall and answer faithfulness separately (RAGAS).

**Q6. How do you control multimodal cost without tanking quality?**
Treat resolution/tiling/frame-rate as a tuned knob: build an accuracy-vs-image-token curve per use case and operate at the knee (low-res for gist, high-res only for dense text/forms). Route simple visual tasks to smaller/open VLMs; reserve frontier models for hard reasoning. Break out image tokens in telemetry so the driver is visible and alertable.

## L7+ — Principal

**Q7. A team trusts an open VLM because it "beats GPT on MMMU." Respond.**
Public multimodal benchmarks (MMMU/DocVQA/ChartQA) are largely saturated/contaminated by 2026 and don't predict your task. Require a task-specific labeled eval on *real* messy inputs (actual scans/screenshots/charts), a dedicated visual-hallucination probe set, robustness on degraded inputs, and cost at the chosen resolution. The open/proprietary gap has genuinely narrowed, so open may well win — but on *your* eval, not a leaderboard.

**Q8. Safety considerations unique to multimodal?**
Adversarial text embedded in an image can carry prompt-injection that bypasses text-only input filters (image-based indirect injection); unsafe visual content needs visual moderation; PII appears in images/screenshots (redaction must be visual-aware); screen agents can take irreversible UI actions. Apply defense-in-depth from *AI Safety & Guardrails* with modality-aware controls: scan image-derived text, visual content classifiers, HITL on irreversible UI actions, least privilege.

**Q9. Why is "multimodal is table stakes in 2026" a strategy statement, not a feature note?**
Because the differentiator moved from *having* vision to *integrating* it well: retrieval over real document corpora, screen/agent grounding, cost-controlled resolution policy, visual-hallucination evaluation, and modality-aware safety. Frontier and strong open models all do vision; competitive advantage is now the surrounding system (multimodal RAG, evals, cost, guardrails) — exactly the same engineering discipline as text, applied to pixels.

## Rapid-Fire

- *VLM stack?* Vision encoder → projector → LLM.
- *Image cost lever?* Resolution/tiling/frames → tokens.
- *Top failure mode?* Visual hallucination.
- *Layout-heavy doc RAG?* ColPali/native multimodal retrieval, not caption-then-text.
- *Public VLM benchmarks in 2026?* Often saturated/contaminated — use task evals.
- *Cross-modal search?* One shared multimodal embedding space.
