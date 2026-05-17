# High-Level Overview

## What It Is

**Multimodal AI** systems process and/or generate more than one modality — text, image, audio, video, documents. A **Vision-Language Model (VLM)** is the dominant subclass: an LLM extended to accept images (and often video/documents) alongside text and reason jointly over them. **Any-to-any** models additionally *generate* multiple modalities. A **multimodal embedding model** maps multiple modalities into one shared vector space for cross-modal retrieval.

## The 2026 Landscape

Writing in 2026: **multimodal capability is no longer a differentiating feature — it is table stakes.** If 2023–2025 were the model arms race, 2026 is the year of integration.

- **Proprietary**: GPT-class, **Gemini 3** (built ground-up for text/vision/tools/UI; strong document/screen/video), **Claude 4** (improved vision + image-to-code) lead frontier multimodal reasoning. Gemini's native multimodal embedding maps text/image/video/audio/documents into one space.
- **Open**: **Qwen3-VL** (flagship rivals top proprietary on many multimodal benchmarks; can operate PC/mobile UIs via tool use), **GLM-4.5V/4.6V** (native multimodal tool use, 128K context), **Pixtral** (Mistral, efficient), **Molmo** (AI2; 72B beats some prior proprietary). The open/proprietary gap has narrowed sharply.

## Why It Matters

Most real enterprise data is not clean text — it's PDFs with tables and figures, screenshots, scanned forms, diagrams, charts, product images, and video. Text-only models can't use it. VLMs unlock document AI, UI/screen agents, visual QA, and multimodal search over the data organizations actually have.

## The Core Problem It Solves

Two specific shifts:
1. **Document understanding without brittle pipelines.** The legacy OCR→layout-detection→parse stack fails on complex, visually-rich, non-linear documents. A capable VLM (or visual late-interaction retrieval like ColPali) reads the page *as a page*.
2. **Cross-modal retrieval.** Native multimodal embeddings let "find the slide that shows X" or "retrieve the diagram for this question" work without per-modality silos.

## The Catch (principal-level nuance)

- **Cost**: images consume many tokens; high-resolution/video inputs are a real, often-underestimated cost driver.
- **Visual hallucination**: VLMs confidently misread charts, miscount, and invent text not present — the dominant failure mode.
- **Grounding**: "where in the image" (bounding boxes / region grounding) is weaker and more variable than text reasoning.
- **Eval**: many public multimodal benchmarks are saturated/contaminated; task-specific evals are essential.

## Where It Sits

A model capability cutting across the stack: it extends RAG (multimodal RAG — see *Retrieval-Augmented Generation*), agents (screen/UI agents — see *Agentic Design Patterns*), serving (image-token cost/latency — see *LLM Serving & Inference*, *Cost Optimization*), safety (image-based injection, unsafe visual content — see *AI Safety & Guardrails*), and evals (see *Evals in AI*).
