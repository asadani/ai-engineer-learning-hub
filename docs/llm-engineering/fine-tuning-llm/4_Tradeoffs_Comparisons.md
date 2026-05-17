# Tradeoffs & Comparisons

## Fine-Tuning vs RAG vs Prompt Engineering

| Approach | Best For | Not Good For | Cost | Latency Impact | Knowledge Currency |
|----------|---------|-------------|------|---------------|-------------------|
| **Prompt Engineering** | Format guidance, few-shot examples, role framing | Deeply domain-specific behavior, cost-sensitive high-volume | Low | Higher TTFT (long prompts) | Always current |
| **RAG** | Factual grounding, fresh information, source citation | Output format/style control, reasoning patterns | Medium (retrieval infra) | +100–500ms retrieval | Always current |
| **Fine-Tuning** | Output format, style, domain reasoning, small model specialization | Up-to-date world knowledge, rare/few-shot tasks | High (training) | None (merged adapters) | Frozen at training time |
| **FT + RAG** | Specialized + grounded (best quality) | Simple use cases | Highest | +retrieval latency | Current facts |

**The rule of thumb**: Try prompt engineering first (hours), then RAG (days), then fine-tuning (weeks). Escalate only when the cheaper option demonstrably fails on the eval set.

---

## Full Fine-Tuning vs LoRA vs QLoRA

| Dimension | Full FT | LoRA | QLoRA |
|-----------|---------|------|-------|
| **Quality ceiling** | Highest | Near-full (gap < 2% at r=64) | Slightly below LoRA |
| **GPU memory (7B)** | ~60GB | ~20GB | ~8GB |
| **GPU memory (70B)** | >400GB | ~120GB | ~40GB |
| **Training speed** | Slowest | ~1.5× faster than FT | ~2× faster than FT |
| **Forgetting risk** | Highest | Low (frozen base) | Low |
| **Adapter merge?** | N/A | Yes — zero inference overhead | Yes, dequantize first |
| **Multiple adapters?** | No | Yes (LoRA multiplexing) | Limited |
| **When to use** | Domain-specific pretraining, large dataset, max quality | Production default | Single consumer GPU |

**The quality gap between full FT and LoRA at r=64 is < 2% on most benchmarks.** For 95% of production use cases, LoRA with adequate rank is indistinguishable from full FT in production metrics.

---

## DPO vs PPO vs ORPO vs GRPO

| Method | Requires Reward Model | Requires SFT Base | Complexity | Use Case |
|--------|----------------------|------------------|-----------|----------|
| **SFT only** | No | No | Low | Format, style, domain knowledge |
| **DPO** | No | Yes | Medium | Preference alignment (chosen/rejected pairs) |
| **ORPO** | No | No (single-stage) | Low | Preference alignment, simpler than DPO |
| **SimPO** | No | Yes | Low | Reference-free DPO variant, very simple |
| **PPO (RLHF)** | Yes (separate) | Yes | High | Complex reward shaping, fine-grained control |
| **GRPO** | Verifiable reward fn | Yes | Medium | Math/code reasoning, verifiable tasks |

**PPO vs DPO in practice**: PPO was the RLHF approach used by OpenAI for ChatGPT. DPO achieves comparable alignment results with 3× less complexity (no reward model, no separate critic, no rollout buffer). The 2026 consensus: use DPO or ORPO unless you have a specific reason to need PPO's flexibility. GRPO is the right choice when rewards are verifiable (math, code execution).

---

## LoRA Rank Selection

| Rank | Trainable Params (8B) | Use Case | Risk |
|------|----------------------|----------|------|
| r=4 | ~5M (0.06%) | Quick style/format adaptation | Underfit for complex tasks |
| r=8 | ~10M (0.12%) | Simple domain adaptation | Often underfit |
| r=16 | ~21M (0.26%) | General-purpose SFT | Good starting point |
| r=32 | ~42M (0.52%) | Specialized domain, harder tasks | Acceptable |
| r=64 | ~84M (1.05%) | Near-full FT quality | Slightly more forgetting |
| r=128 | ~168M (2.1%) | Maximum adapter capacity | Significant forgetting risk |
| r=256 | ~335M (4.2%) | Almost never needed | Wasteful |

**Starting recommendation**: r=16, alpha=32. If eval loss plateaus early (underfitting), increase to r=32 or r=64. If validation loss diverges from train loss (overfitting), reduce or add dropout.

**RSLoRA (Rank-Stabilized LoRA)**: Scales the LoRA output by `1/√r` instead of `alpha/r`. Allows higher ranks without instability — useful at r=64+.

```python
lora_config = LoraConfig(r=64, lora_alpha=64, use_rslora=True, ...)
```

---

## Learning Rate Selection

| Scenario | Recommended LR | Rationale |
|----------|---------------|-----------|
| LoRA on instruct model | 1e-4 to 3e-4 | Fast learning on adapters only |
| LoRA on base model | 5e-5 to 2e-4 | Base model needs more careful adaptation |
| Full FT (small dataset) | 1e-5 to 5e-5 | Prevent catastrophic forgetting |
| Full FT (large dataset) | 5e-5 to 2e-4 | More data = more tolerance |
| DPO | 5e-7 to 5e-6 | Very small adjustments to SFT base |
| GRPO | 1e-7 to 5e-7 | Tiny policy updates to prevent collapse |

**Learning rate schedule**: Cosine decay with 5–10% warmup is standard. For very small datasets (< 1K examples), linear warmup to avoid early instability. Never use constant LR for fine-tuning — the model diverges without decay.

**The LR × batch size relationship**: Effective LR scales with `sqrt(batch_size)` (linear scaling rule sometimes used, sqrt more commonly for fine-tuning). If you increase effective batch size 4×, increase LR by 2×.

---

## Dataset Size vs Method vs Outcome

| Dataset Size | Recommended Method | Expected Outcome |
|-------------|-------------------|-----------------|
| 100–500 examples | LoRA r=8, 1–3 epochs, low LR | Subtle style/format adaptation |
| 500–5K examples | LoRA r=16, 2–5 epochs | Reliable task-specific behavior |
| 5K–50K examples | LoRA r=32–64, 3–5 epochs | Strong domain specialization |
| 50K–500K examples | LoRA r=64 or Full FT | Publication-grade specialization |
| 500K+ examples | Full FT with replay buffer | Essentially a new model |

**Data quality >> quantity**: A carefully curated 1,000-example dataset outperforms a noisy 50,000-example dataset. The single most impactful investment in any fine-tuning project is data quality review. Use GPT-4/Claude to score every example before training.

---

## Optimizer Comparison for Fine-Tuning

| Optimizer | Memory | Speed | Quality | Notes |
|-----------|--------|-------|---------|-------|
| **AdamW (fp32)** | Highest (4× params) | Baseline | Best | Standard; too expensive for large models |
| **AdamW 8-bit (bnb)** | 4× reduction | ~Same | Near-identical | Use with LoRA; saves ~20GB on 70B |
| **Paged AdamW 8-bit** | Same as 8-bit | Same | Same | Spills optimizer states to CPU RAM on OOM |
| **Lion** | 2× reduction vs AdamW | Slightly faster | Comparable | Simpler math; less tuned for LLMs |
| **SGD + momentum** | 2× reduction | Fastest | Lower | Rarely used for LLM FT |
| **Adafactor** | 1× (no 2nd moment) | Medium | Slightly lower | Good for very constrained memory |

**Practical default**: `adamw_bnb_8bit` (bitsandbytes AdamW in 8-bit) for LoRA fine-tuning. Cuts optimizer memory in half with no quality cost. Use `paged_adamw_8bit` only if you're hitting OOM due to optimizer states.

---

## Chat Template Format Comparison

| Format | System Prompt | Turn Separator | Used By |
|--------|-------------|----------------|---------|
| **ChatML** | `<|im_start|>system\n...<|im_end|>` | `<|im_start|>role\n...<|im_end|>` | Qwen, OpenAI, many fine-tuned models |
| **Llama-3** | `<|start_header_id|>system<|end_header_id|>` | `<|start_header_id|>role<|end_header_id|>` | Meta Llama-3+ |
| **Alpaca** | No system message | `### Instruction:\n...\n### Response:` | Legacy, avoid |
| **ShareGPT** | `system` field | `human`/`gpt` role names | Dataset format standard |
| **Mistral** | No system message | `[INST]...[/INST]` | Mistral v0.1–0.2 |

**Use the model's native chat template** for fine-tuning. Using the wrong template causes the model to generate the wrong delimiters and confuses inference. Always:
```python
tokenizer.apply_chat_template(messages, tokenize=False)
# Returns the correct format for the specific model
```

---

## Instruction Tuning vs Continued Pre-Training vs Domain-Adaptive Pre-Training

| Technique | What It Changes | Data Type | Cost | Use Case |
|-----------|----------------|-----------|------|----------|
| **Instruction tuning (SFT)** | Behavior / format | (instruction, response) pairs | Low | Make model follow instructions, output specific format |
| **Continued pre-training** | Knowledge + capabilities | Raw text (no labels) | High | Inject domain knowledge at scale |
| **Domain-adaptive pre-training (DAPT)** | Domain vocabulary + concepts | Domain raw text, then SFT | Very high | Build domain expert from scratch |

**When to use continued pre-training**: The domain vocabulary is so specialized that the base model consistently fails at tokenization/understanding (e.g., genomics sequences, legal clause parsing, rare languages). For most cases, instruction tuning on curated examples is sufficient — the base model already has the vocabulary.
