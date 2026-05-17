# Products & Tools

## Proprietary VLMs (frontier)

| Model | Strengths |
|---|---|
| **Gemini 3** | Built ground-up for text/vision/tools/UI; document, screen-agent, video reasoning |
| **GPT-class (4.x/5-tier)** | Strong visual QA and reasoning |
| **Claude 4 (Opus/Sonnet)** | Improved vision; image→code; document understanding |

## Open VLMs

| Model | Notes |
|---|---|
| **Qwen3-VL** (incl. 235B-A22B) | Rivals top proprietary on many multimodal benchmarks; GUI operation via tool use; 2D/3D grounding, OCR, video, docs |
| **GLM-4.5V / 4.6V** | Native multimodal tool use; 128K context; strong visual reasoning |
| **Pixtral (12B)** (Mistral) | Efficient; beats prior open VLMs on instruction following |
| **Molmo** (AI2, 1B/7B/72B) | 72B competitive with earlier proprietary on academic benchmarks |

## Multimodal Embeddings / Retrieval

| Tool | Role |
|---|---|
| Native multimodal embedding models (e.g., Gemini multimodal embedding) | One vector space across text/image/video/audio/docs |
| **ColPali / ColQwen** | Late-interaction retrieval over document *page images* (layout-heavy doc RAG) |
| CLIP/SigLIP-family | Image–text embeddings (older but ubiquitous baseline) |

## Serving

| Concern | Tool |
|---|---|
| Open VLM serving | **vLLM / SGLang / TGI** (multimodal support) |
| Image-token cost/latency | resolution/tiling policy; routing — see *Cost Optimization* |
| Long visual decode at scale | disaggregated serving (Dynamo) — see *LLM Serving & Inference* |

## Evaluation

| Tool | Role |
|---|---|
| MMMU / DocVQA / ChartQA / MMBench-style suites | Standard VLM capability benchmarks |
| **RAGAS** | Multimodal RAG faithfulness/grounding (see *Evals in AI*) |
| Task-specific golden sets | Required — public benchmarks are often saturated/contaminated |

## Selection Guidance

- Frontier multimodal reasoning, hosted OK → **Gemini 3 / GPT / Claude 4**.
- On-prem / cost-tiered / open weights → **Qwen3-VL** or **GLM-4.x V**; **Pixtral/Molmo** for efficiency.
- Layout-heavy document RAG → **ColPali/ColQwen** visual retrieval, not OCR pipelines.
- Cross-modal search → **native multimodal embeddings**, one space.
- Always: build a **task-specific eval set**; don't trust saturated public leaderboards.
