# Products & Tools

## Frontier / Hosted Reasoning Models

| Model family | Notes |
|---|---|
| **OpenAI o-series (o1, o3, …)** | Frontier reasoning; opaque trace; effort levels; strong ARC-AGI/math/code |
| **DeepSeek-R1 (+ 0528)** | Open-weight (MIT); visible `<think>` CoT; o1-level; RLVR-trained |
| **Extended-thinking models (Claude 3.7-style)** | Hybrid instant/deep; developer-set thinking budget |
| **Gemini reasoning tiers** | Reasoning-capable frontier tier for math/science/agents |

## Open / Distilled Reasoners

| Model | Notes |
|---|---|
| **DeepSeek-R1-Distill-Qwen / -Llama** (1.5B–70B) | Reasoning distilled into small models; commodity-GPU friendly |
| Other open reasoning models (Qwen/QwQ, GLM-thinking, etc.) | Growing open ecosystem of test-time-compute models |

## Training / RL Stacks

| Tool | Role |
|---|---|
| **Hugging Face TRL** | GRPO, RLVR, SFT, DPO (see *Fine-Tuning LLMs*) |
| verl / OpenRLHF / TRL-style RL frameworks | Scalable RLVR training |
| Distillation pipelines (trace generation + SFT) | The cheap path to small reasoners |

## Serving & Ops

| Concern | Tool / approach |
|---|---|
| Long decode (reasoning = long output) | **vLLM / SGLang / TensorRT-LLM**, disaggregated serving (NVIDIA Dynamo) — see *LLM Serving & Inference* |
| Thinking-token cost control | Budget/effort caps; routing — see *Cost Optimization* |
| Trace/cost visibility | OTel GenAI spans incl. reasoning tokens — see *LLM Observability & LLMOps* |
| Reasoning evals | Contamination-resistant benchmarks (ARC-AGI, fresh sets) — see *Evals in AI* |

## Selection Guidance

- Need open-weight, inspectable reasoning / on-prem → **DeepSeek-R1** (or a distill for cost).
- Frontier accuracy, opacity acceptable → **o-series**.
- Want one model for instant *and* deep, with a cost dial → **extended-thinking** model.
- Reasoning at scale on a budget → **distilled small reasoner**, not RL-from-scratch.
- Always: route simple tasks to standard models; reserve reasoning models for tasks that measurably need them.
