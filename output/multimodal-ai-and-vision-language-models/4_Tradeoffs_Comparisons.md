# Tradeoffs & Comparisons

## Proprietary vs Open VLMs (2026)

| | Proprietary (Gemini 3 / GPT / Claude 4) | Open (Qwen3-VL / GLM-4.x V / Pixtral) |
|---|---|---|
| Peak capability | Frontier | Competitive on many benchmarks |
| On-prem / data control | No | Yes |
| Cost control | API tiers | Full control; size-tiered |
| Drift | Provider updates silently | You pin weights |
| 2026 reality | Best for hardest visual reasoning | Strong default for cost/control |

The gap narrowed sharply — open is now a credible default for many workloads.

## VLM vs OCR Pipeline (document AI)

| | OCR → layout → parse | VLM / ColPali |
|---|---|---|
| Clean, linear docs | Cheap, fine | Overkill |
| Visually-rich / non-linear / charts / handwriting | Brittle, fails | Robust |
| Cost per page | Low | Higher (image tokens) |
| Maintenance | High (rules per template) | Low |

Use OCR for simple high-volume linear text; VLM/visual-retrieval for complex layout-heavy documents.

## Native Multimodal Embedding vs Caption-then-Text

| | Caption → text RAG | Native multimodal embedding / ColPali |
|---|---|---|
| Visual detail retained | Low (lossy captions) | High |
| Build complexity | Low | Moderate |
| Layout/chart retrieval | Weak | Strong |
| 2026 best practice (rich docs) | — | ✅ |

## Resolution / Tiling: Quality vs Cost

Higher resolution and more tiles → better fine-detail reading (small text, dense tables) but linearly more image tokens (cost + latency). It's an explicit per-use-case knob: low-res for thumbnails/scene gist, high-res for forms/charts. Defaulting to max resolution is a silent cost blowup.

## Early/Deep Fusion vs Cross-Attention

| | Deep fusion (visual tokens in stream) | Cross-attention |
|---|---|---|
| Joint reasoning | Strong | Good |
| Sequence/token cost | High (image tokens in context) | Decoupled from image detail |
| Prevalence (2026) | Most VLMs | Some long-video/high-detail designs |

## Common Failure Modes

- **Trusting VLM chart/table reads** without verification → confident visual hallucination.
- **Max resolution by default** → image-token cost explosion.
- **OCR pipeline on complex docs** → brittle failures a VLM would handle.
- **Caption-then-text RAG for layout-heavy corpora** → lossy retrieval; use visual retrieval.
- **Public-benchmark trust** → saturated/contaminated scores; no task eval.
- **No image-based injection guardrail** → adversarial text-in-image bypasses text filters (see *AI Safety & Guardrails*).
