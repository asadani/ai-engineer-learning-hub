# Fine-Tuning an LLM — High-Level Overview

## What It Is

Fine-tuning is the process of continuing to train a pre-trained LLM on a smaller, task-specific dataset to adjust its weights — shifting the model's behavior, knowledge, or output style toward a target distribution. It's the bridge between a general foundation model and a specialized production system.

The term "fine-tuning" covers a spectrum: from updating all 70 billion parameters to modifying < 0.1% of them via parameter-efficient adapters. The choice of method determines compute cost, storage overhead, risk of catastrophic forgetting, and quality ceiling.

---

## The Fine-Tuning Decision Triangle

Before writing a training loop, answer three questions:

```
                        Can prompt engineering solve it?
                          (few-shot, chain-of-thought, careful instruction)
                              ↓ No
                        Does RAG cover the knowledge gap?
                          (retrieval can inject missing facts)
                              ↓ No / not sufficient
                        Fine-tune — but which method?
```

**When fine-tuning is the right answer:**
- The model consistently fails at a specific output format/schema despite good prompting
- You need specialized domain vocabulary or reasoning patterns the base model lacks
- Latency/cost budget prohibits long prompts (system prompt of 3,000 tokens × 100M requests = very expensive)
- You need behavior customization that can't be expressed in a prompt (safety constraints, persona consistency, citation style)
- You're building a small model (3B–8B) to replace a large one (70B+) for a narrow task

**When fine-tuning is the wrong answer:**
- You haven't first optimized your prompt (fine-tuning a poorly-prompted model → fine-tuned poorly-prompted model)
- Your task distribution changes frequently (fine-tuned model is "frozen" at training-time distribution)
- You have < 100 quality examples (too little data for meaningful fine-tuning signal)
- The task requires up-to-date world knowledge (fine-tuning doesn't update knowledge well; RAG does)

---

## The Fine-Tuning Method Hierarchy

```
Full Fine-Tuning (FFT)
├── Update all N parameters
├── Best quality ceiling
├── Cost: GPU-months, full weight storage
└── Risk: catastrophic forgetting

Parameter-Efficient Fine-Tuning (PEFT)
├── LoRA / QLoRA / AdaLoRA / DoRA
│   ├── Add low-rank adapter matrices (< 1% of params)
│   ├── Cost: 2–10× cheaper than FFT
│   └── Can merge into base model for zero-overhead inference
├── Prompt Tuning / Prefix Tuning
│   ├── Add trainable tokens to the context
│   └── Minimal parameters; lower quality ceiling than LoRA
└── (IA)³
    └── Multiply activations/attention by learned vectors; very few params

Alignment Fine-Tuning
├── SFT (Supervised Fine-Tuning) — teaches instruction-following format
├── RLHF (PPO) — optimizes for human preference via reward model
├── DPO (Direct Preference Optimization) — preference learning without RL
├── ORPO / SimPO — single-stage SFT + preference learning
└── GRPO (Group Relative Policy Optimization — DeepSeek) — reasoning alignment
```

---

## The Two-Stage Mental Model

Most production fine-tuning uses a two-stage pipeline:

**Stage 1 — SFT (Supervised Fine-Tuning):**
Train on curated (instruction, response) pairs to teach the model the format, style, and domain knowledge you need. This is the workhorse. ~80% of production fine-tuning stops here.

**Stage 2 — Alignment (optional but increasingly standard):**
After SFT, run DPO or PPO on (chosen, rejected) preference pairs to align the model's outputs with human preferences: correct over incorrect, safe over unsafe, concise over verbose. Required for public-facing models; optional for internal tooling.

---

## What Gets Modified: A Weight-Level View

```python
# The fine-tuning target determines what changes
model = AutoModelForCausalLM.from_pretrained("meta-llama/Meta-Llama-3.1-8B")

# Full fine-tuning: ALL parameters are trainable
# ~8B parameters × 2 bytes/param (bf16) = ~16GB just for gradients
# With optimizer states (AdamW): 4× model size = ~64GB GPU memory for training

# LoRA: only adapter matrices are trainable
# rank=16, alpha=32 → ~4M new parameters = 0.05% of 8B
# Training memory: ~16GB (base model in fp16/int4) + ~1GB adapters

# The adapter structure:
# For each attention layer weight W (d×d):
#   W' = W + BA  where B ∈ R^{d×r}, A ∈ R^{r×d}, r << d
#   Only B and A are trained; W is frozen
```

---

## The Catastrophic Forgetting Problem

Fine-tuning on task-specific data causes the model to partially overwrite general capabilities. A model fine-tuned heavily on medical literature forgets how to write poetry. This is the fundamental tension of fine-tuning.

**Severity correlates with:**
- Number of training steps (more steps = more forgetting)
- Learning rate (higher LR = faster forgetting)
- Domain distance from pre-training data
- Proportion of parameters updated (full FT > LoRA > prefix tuning)

**Mitigations:**
- **Replay buffer**: Mix a small fraction (5–10%) of general-purpose data into every fine-tuning batch
- **Low learning rates**: 1e-5 to 5e-6 for full FT; 2e-4 is reasonable for LoRA adapters
- **LoRA rank selection**: Lower rank = less forgetting, but also lower capacity; r=8–32 is the practical range
- **Evaluate on capabilities you care about preserving** throughout training (not just at the end)

---

## Cost Reality Check

| Method | 7B Model | 70B Model | GPU Required | Time |
|--------|----------|-----------|--------------|------|
| Full FT (bf16) | ~4× A100 80GB | ~32× A100 | NVLink cluster | 12–72h |
| LoRA (bf16 base) | ~2× A100 | ~4× A100 | Single node | 4–24h |
| QLoRA (int4 base) | ~1× A100 40GB | ~2× A100 80GB | Single GPU | 4–16h |
| QLoRA (int4 base) | ~1× RTX 4090 | ~2× A100 | Consumer GPU | 8–24h |

**Rule of thumb**: QLoRA makes 7B fine-tuning accessible on a single A100 ($3/hr on Lambda Labs) for ~$15–50 for a small dataset run. 70B LoRA on 2× A100s costs $50–200 for a production run.

---

## The Overfitting Trap

Fine-tuning datasets are small (1K–100K examples). Models this large can memorize a small dataset in very few steps. Signs of overfitting:
- Training loss continues decreasing; validation loss plateaus or increases
- Model reproduces training examples verbatim
- Performance on held-out test set degrades after an early peak

**Standard guardrails:**
- Validation split: 5–10% of data, evaluate every 100–200 steps
- Early stopping: stop when validation loss hasn't improved for 3–5 evaluations
- Regularization: weight decay (0.01–0.1), dropout on adapter layers (0.05–0.1)
- Dataset diversity: ensure training set covers all variations of inputs you'll see in production
