# Key Technical Concepts

## VLM Architecture (the standard pattern)

Most 2026 VLMs follow: **vision encoder → projector/connector → LLM**.

1. **Vision encoder** (typically a ViT, often CLIP/SigLIP-style) turns an image into patch embeddings.
2. **Projector / connector** (an MLP or cross-attention "resampler"/Q-Former) maps visual features into the LLM's token embedding space.
3. **LLM backbone** consumes projected visual tokens interleaved with text tokens and reasons jointly.

You should be able to draw this and name where the modality "fuses."

## Fusion Strategies

- **Early/deep fusion** — visual tokens enter the LLM token stream directly (most modern VLMs). Strong joint reasoning; image-token cost.
- **Cross-attention fusion** — LLM attends to visual features via added cross-attention layers (e.g., Flamingo-style). Decouples sequence length from image detail.
- **Late fusion** — separate encoders, combined at the end. Simple, weaker joint reasoning.

## Image Tokenization & the Cost Driver

Images are converted to tokens; **higher resolution and tiling = more tokens**. A single high-res image or a video (many frames) can dwarf the text prompt in token cost and latency. Resolution/tiling policy is an explicit cost/quality knob — not a default to ignore. (See *Cost Optimization*.)

## Multimodal Embeddings

A single model maps multiple modalities into **one shared vector space**, so a text query can retrieve images/video and vice versa. 2026 brought native multimodal embedding models (text/image/video/audio/documents in one space), enabling true cross-modal retrieval without per-modality bridges. Contrast with older "CLIP for image, separate model for text" setups.

## Multimodal RAG

RAG over non-text corpora. Two main approaches:
- **Caption-then-text-RAG** — describe images with a VLM, index the text. Simple; loses visual detail.
- **Native multimodal retrieval** — embed images/pages directly (multimodal embeddings or **late-interaction visual retrieval like ColPali/ColQwen**, which embeds document *page images* and matches at patch level). Stronger on visually-rich, layout-heavy documents; this is the 2026 best practice for document RAG. (See *Retrieval-Augmented Generation*.)

## Visual Grounding & Region Reference

Tasks needing "where" — bounding boxes, point/region grounding, UI element localization. 2026 models (Qwen3-VL, GLM-4.x V) do 2D/3D grounding and can drive GUIs by recognizing UI elements. Grounding is weaker/higher-variance than text reasoning — evaluate it explicitly for agent/screen use.

## Visual Hallucination

The dominant failure mode: confidently misreading charts/tables, miscounting objects, "reading" text not present, or describing plausible-but-absent content. Mitigations: ask for verbatim transcription before interpretation, request uncertainty/abstention, ground answers to detected regions, and verify against structured extraction where possible.

## OCR Pipeline vs VLM

Legacy: OCR → layout detection → rule/ML parse. Brittle on non-linear, visually-rich, multi-column, handwritten, or chart-heavy documents. A capable VLM (or ColPali-style visual retrieval) reads the page holistically and is now preferred for many document-AI tasks — at higher per-call cost.

## The Through-Line

Encoder → projector → LLM, fused early; images become (many) tokens (the cost lever); one shared embedding space enables cross-modal retrieval and multimodal RAG; the failure mode to design against is visual hallucination/weak grounding — so evaluate modality-specifically.
