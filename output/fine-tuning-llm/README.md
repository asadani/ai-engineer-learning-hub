# Fine-Tuning an LLM

**Principal-level interview prep notes** — covering LoRA, QLoRA, DoRA, AdaLoRA, SFT, DPO, ORPO, GRPO, catastrophic forgetting, distributed training (DeepSpeed ZeRO, FSDP), data pipeline, Unsloth, Axolotl, TRL, AWS SageMaker, and evaluation.

Generated: 2026-03-22

---

## Contents

| # | File | Words | Focus |
|---|------|-------|-------|
| 1 | [High-Level Overview](1_High_Level_Overview.md) | 1,018 | FT decision triangle, method hierarchy (FFT/LoRA/QLoRA/alignment), catastrophic forgetting, cost reality check, overfitting guardrails |
| 2 | [Key Technical Concepts](2_Key_Technical_Concepts.md) | 2,040 | LoRA math + initialization, QLoRA (NF4 + double quant + paged optimizers), DoRA, AdaLoRA, instruction tuning + chat templates, DPO objective, ORPO, GRPO, DeepSpeed ZeRO, FSDP, gradient checkpointing, sequence packing |
| 3 | [Products & Tools](3_Products_Tools.md) | 1,163 | TRL (SFTTrainer, DPOTrainer), Unsloth (2–5× speedup), Axolotl (YAML-driven), LLaMA-Factory (web UI), Distilabel (synthetic data), deduplication, AWS SageMaker training jobs + checkpointing, Bedrock FT, W&B experiment tracking |
| 4 | [Tradeoffs & Comparisons](4_Tradeoffs_Comparisons.md) | 1,399 | FT vs RAG vs prompting, full FT vs LoRA vs QLoRA, DPO vs PPO vs ORPO vs GRPO, rank selection table, LR selection guide, dataset size vs method, optimizer comparison, chat template formats, instruction tuning vs DAPT |
| 5 | [Use Cases](5_Use_Cases.md) | 1,701 | Customer support format fine-tuning, code generation (2-stage), structured extraction, multi-task LoRA multiplexing, DPO alignment, GRPO for math reasoning, end-to-end production pipeline |
| 6 | [Measurement & Evaluation](6_Measurement_Evaluation.md) | 1,185 | During-training monitoring (loss curves, grad norm), post-training (task metrics, capability regression, format compliance, safety), DPO alignment evaluation, human evaluation protocol, evaluation stage table |
| 7 | [What to Measure & How](7_What_to_Measure_How.md) | 1,104 | Metric tables (training health, quality, regression, alignment, data quality), W&B config, evaluation automation script, domain-specific targets |
| 8 | [Interview Questions](8_Interview_Questions.md) | 4,763 | 12 tiered Q&As: L5 (LoRA mechanism, QLoRA, assistant-token masking, DPO failure modes, hyperparameter tuning), L6 (70B setup, production/test mismatch, GRPO vs PPO), L7+ (company knowledge assistant architecture, catastrophic forgetting deep dive, synthetic data pipeline, reasoning preservation) |

**Total: ~14,373 words**

---

## Key Themes

### The Decision Hierarchy
```
Prompt Engineering → RAG → SFT → SFT + DPO
```
Each step adds capability but also cost and complexity. Escalate only when the prior step measurably fails.

### LoRA Mental Model
- ΔW = BA (low-rank decomposition of weight update)
- Only BA is trained; W_base is frozen → catastrophic forgetting is structurally prevented
- r=16, alpha=32 is the universal starting point
- Merge for zero inference overhead: `model.merge_and_unload()`
- Multiply adapters serve multiple tasks from one base model

### Alignment Ladder
| Stage | Tool | Requirement |
|-------|------|-------------|
| Format/style/domain | SFT (LoRA) | (instruction, response) pairs |
| Preference alignment | DPO or ORPO | (prompt, chosen, rejected) pairs |
| Verifiable reasoning | GRPO | Programmatic reward function |
| Complex reward shaping | PPO | Separate reward model |

### Critical Implementation Details
- **Train only on assistant tokens** — mask user/system turns with `-100`; this is the #1 implementation bug
- **B initialized to zero** — ensures ΔW = 0 at training start (warm start from base)
- **Use the model's native chat template** — wrong template = wrong token boundaries = degraded quality
- **Enable gradient checkpointing** for any model > 7B: `model.gradient_checkpointing_enable()`
- **Sequence packing**: 2–5× throughput improvement for short-example datasets
- **AdamW 8-bit** (`adamw_bnb_8bit`): 4× less optimizer memory, same quality

### Production Pipeline
```
Data → LLM-judge quality filter → Dedup → SFT (LoRA) → Eval gate
      → DPO preference data (generate 2× + auto-label) → DPO fine-tune
      → Capability regression check → Merge + quantize → A/B deploy
```

---

## Quick Reference: Hardware Requirements

| Model | Method | Minimum GPU | Recommended |
|-------|--------|------------|-------------|
| 7B | QLoRA | 1× RTX 4090 (24GB) | 1× A100 40GB |
| 7B | LoRA bf16 | 1× A100 40GB | 2× A100 40GB |
| 13B | QLoRA | 1× A100 40GB | 1× A100 80GB |
| 70B | QLoRA | 2× A100 80GB | 4× A100 80GB |
| 70B | LoRA bf16 | 4× A100 80GB | 8× A100 80GB |
| 70B | Full FT | 16× A100 80GB | 32+ A100 80GB |
