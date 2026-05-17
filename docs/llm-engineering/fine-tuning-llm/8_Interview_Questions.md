# Interview Questions & Model Answers

## L5 (Senior Engineer) — Fundamentals

---

### Q1: Explain LoRA. Why is it effective despite modifying < 1% of parameters?

**Model Answer:**

LoRA (Low-Rank Adaptation) is based on the empirical observation that the weight updates needed for task adaptation are low-rank — they lie in a low-dimensional subspace of the full weight matrix space. This was observed in GPT-3 fine-tuning experiments showing that effective fine-tuning updates have intrinsic dimensionality much lower than the parameter count.

**Mechanism**: For a weight matrix W ∈ R^{d×k}, instead of computing the full update ΔW ∈ R^{d×k} (d×k parameters), LoRA constrains ΔW = BA where B ∈ R^{d×r} and A ∈ R^{r×k}, with r << min(d,k). For Llama-3-8B with d=4096, k=4096, r=16: ΔW has 4096×4096 = 16.7M parameters; BA has 4096×16 + 16×4096 = 131K parameters — a 127× compression.

**Why it works**: Transformers are heavily over-parameterized for any specific task. The gradient updates during fine-tuning don't explore all of weight space — they concentrate in directions most relevant to the task. The low-rank decomposition captures these principal directions. For most task-specific adaptations (format, style, domain vocabulary), rank-4 through rank-64 is sufficient.

**The frozen base model benefit**: By keeping the base model weights frozen and only training the adapters, LoRA prevents catastrophic forgetting. The base model's general capabilities are preserved by construction — only the adapter's capacity can be "specialized away." This is fundamentally why LoRA outperforms full fine-tuning at low dataset sizes: full FT has too many degrees of freedom to constrain from a small dataset.

**Initialization**: B is initialized to zero (so ΔW = BA = 0 at the start — training begins from the base model). A is initialized with random Gaussian values to break symmetry. This is important: if A were also zero-initialized, there would be no gradient signal for the first step.

---

### Q2: What is QLoRA and when should you use it vs standard LoRA?

**Model Answer:**

QLoRA adds quantization of the base model to LoRA, enabling fine-tuning of very large models on severely memory-constrained hardware.

**The key insight**: During inference, quantizing weights to 4-bit (NF4) is stable. But backpropagation through a quantized model is problematic — quantization is non-differentiable. QLoRA's solution: freeze the quantized base model (no gradients through it), add LoRA adapters that are trained in full precision (bf16), and use "dequantize as needed" — weights are dequantized to bf16 for each forward pass, gradients flow only through the adapters.

**Comparison:**

Standard LoRA (bf16 base):
- 7B model: ~16GB base + ~0.5GB adapters + gradient/optimizer ~2GB = ~18.5GB total
- Faster forward/backward pass (no dequantize step)
- Preferred when memory allows

QLoRA (NF4 base):
- 7B model: ~4GB base (NF4) + ~0.5GB adapters + ~2GB optimizer = ~6.5GB total
- Slightly slower due to dequantize step in each forward pass
- Enables 70B fine-tuning on 2× A100 80GB

**When to use QLoRA**: When GPU memory is the constraint and you can't fit the base model in bf16. The quality difference between LoRA and QLoRA at the same rank is small (< 1% on most benchmarks) — QLoRA is not a significant quality trade-off, just a memory trade-off.

**Practical rule**: If you have an A100 80GB, use bf16 LoRA for 7B and QLoRA for 70B. If you have an RTX 4090 (24GB), use QLoRA for 7B. If you have 2× A100 80GB, use QLoRA for 70B. The NF4 data type is designed for neural network weights (which are near-normally distributed) and is slightly better than uniform int4.

---

### Q3: Why does training only on assistant tokens matter? What happens if you train on all tokens?

**Model Answer:**

In a chat-formatted training example, there are three types of tokens:
1. **System prompt tokens**: Define the model's persona
2. **User turn tokens**: The questions/requests
3. **Assistant tokens**: What the model should learn to generate

If you compute cross-entropy loss over ALL tokens, you're teaching the model to predict the user's questions given the context — including predicting "what would a user ask next?" This is not what you want for a fine-tuned assistant. Worse, the model sees user turns as things to predict, which can cause it to confuse the user and assistant roles.

**The correct approach**: Set `labels[i] = -100` for all non-assistant token positions. PyTorch's `CrossEntropyLoss` ignores positions with label -100. Loss is computed only where the model should generate.

```python
# TRL's SFTTrainer with DataCollatorForCompletionOnlyLM
from trl import DataCollatorForCompletionOnlyLM

collator = DataCollatorForCompletionOnlyLM(
    response_template="<|start_header_id|>assistant<|end_header_id|>",
    tokenizer=tokenizer,
)
# This automatically masks everything before the assistant response
```

**What happens if you train on all tokens:**
- Model learns to predict user queries as well as responses
- Results in a model that is slightly more likely to generate user-like continuations mid-response
- Can cause "role confusion" where the model sometimes acts as the user instead of the assistant
- Generally lower quality on instruction-following benchmarks
- More subtle: the model wastes gradient updates learning the user turn distribution, reducing effective sample efficiency

This is one of the most common implementation bugs in beginner fine-tuning projects and a good interview filter for whether someone has actually trained models.

---

### Q4: Explain DPO. What problem does it solve vs RLHF with PPO, and what are its failure modes?

**Model Answer:**

**The RLHF with PPO pipeline** requires:
1. Train a reward model on human preference pairs (chosen, rejected)
2. Initialize a policy from the SFT model
3. Run PPO: sample rollouts from policy, score with reward model, update policy to maximize reward while staying close to reference (KL penalty)

This requires training and maintaining two separate models (reward model + policy), generating rollouts at training time (expensive), and carefully tuning PPO's many hyperparameters (clip ratio, GAE, entropy bonus). It's complex, unstable, and expensive.

**DPO observes**: The optimal policy for RLHF can be expressed in closed form as a function of the reference model's probabilities. This means you can skip the reward model entirely — the reward is implicitly encoded in the log-probability ratio between the policy and the reference. The DPO loss directly optimizes for preferring the chosen response over the rejected response:

```
L_DPO(θ) = -E[log σ(β(log P_θ(y_w|x) - log P_ref(y_w|x)) - β(log P_θ(y_l|x) - log P_ref(y_l|x)))]
```

**DPO advantages**: No reward model training, no rollout generation during training, no PPO instability, dramatically simpler implementation.

**DPO failure modes:**

1. **Distribution shift**: DPO computes log-probabilities of the chosen and rejected responses. If the SFT model's probability of these responses is very low (out-of-distribution for the model), the gradient signal is unreliable. Fix: use on-policy data — generate chosen/rejected pairs from the SFT model rather than from a stronger model.

2. **Reward hacking / length bias**: The model finds that generating longer responses increases chosen probability (because humans often label verbose responses as better). This leads to verbosity. Fix: length-normalize the preference labels, use conciseness as an explicit evaluation criterion.

3. **Forgetting SFT capabilities**: DPO training can degrade the model's instruction-following quality if β is too low (policy deviates too far from reference). Fix: use β = 0.1–0.3 for moderate alignment, not β = 0.01.

4. **Data quality sensitivity**: DPO is sensitive to the quality of preference labels. Noisy labels (human annotators who disagree) can push the model in contradictory directions. Fix: filter preference pairs where annotators strongly disagree; use multi-annotator consensus.

---

### Q5: What are the hyperparameters you tune for LoRA fine-tuning and how would you approach a new problem?

**Model Answer:**

The core LoRA hyperparameters, in order of importance:

**1. Rank (r)**: Start at r=16 for most tasks. Increase to r=32 or r=64 if:
- Training loss decreases but domain task metrics plateau early (underfitting)
- The task involves complex reasoning rather than just style/format changes
- You have > 10K high-quality examples

**2. Learning rate**: Start at 2e-4 for LoRA adapters on an instruct model. Reduce to 5e-5 if:
- Train loss decreases smoothly but then diverges (instability)
- The model produces repetitive outputs after training (collapse symptom)

**3. Epochs**: 3 epochs for datasets of 5K–50K. For smaller datasets (< 2K), 5–10 epochs. Watch the eval loss curve — stop when it plateaus (early stopping with patience=3 evaluations).

**4. Alpha**: Set to 2× r. This scales the LoRA output to compensate for the initialization scale. Don't tune this — it's a convention.

**5. Target modules**: Start with attention + MLP (all six matrices: q,k,v,o, gate, up, down). If memory-constrained, drop k and gate first — v and q carry more task-specific signal.

**Approach for a new problem:**
1. **Sanity check**: Overfit a tiny batch (10 examples) to verify the training loop works — loss should go to near-zero.
2. **Baseline**: Evaluate the base model (no fine-tuning) on your test set first. If it scores > 85%, you may not need fine-tuning.
3. **First run**: r=16, LR=2e-4, 3 epochs. Evaluate on held-out set.
4. **If underfitting**: Increase r to 32, or check data quality (bad data → model can't learn from it regardless of rank).
5. **If overfitting**: Reduce epochs to where eval loss was at its minimum, or add lora_dropout=0.1.
6. **If instability** (loss spikes, NaN): Lower LR by 5×, increase warmup steps.

The most common mistake: spending time tuning hyperparameters before ensuring data quality. A 2× improvement in data quality beats any hyperparameter optimization.

---

## L6 (Staff Engineer) — System Design

---

### Q6: You need to fine-tune a 70B model on 50K proprietary examples. The team has 4× A100 80GB. Walk through the full training setup.

**Model Answer:**

**Memory budget with QLoRA on 4× A100 (320GB total):**
- Model in NF4: 70B × 0.5B/param = 35GB → fits comfortably in 1 GPU (keep it) or distribute with `device_map="auto"`
- LoRA adapters r=64: ~150M params × 2B/param = 300MB
- Optimizer states (AdamW 8-bit): ~600MB
- Activations with gradient checkpointing: ~8GB
- Total per GPU: ~44GB → fits in a single A100 80GB with headroom

With 4 GPUs: run LoRA (not QLoRA) in bf16 with tensor parallelism or data parallelism. At 50K examples, data parallelism is preferred:

```python
# accelerate config for 4-GPU data parallel training
# accelerate config → multi-GPU → DDP → 4 GPUs

from transformers import AutoModelForCausalLM
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTTrainer, SFTConfig
from accelerate import Accelerator

# Option A: QLoRA on single GPU (if worried about gradient sync overhead)
bnb_config = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16,
                                 bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True)
model = AutoModelForCausalLM.from_pretrained(
    "meta-llama/Meta-Llama-3.1-70B-Instruct",
    quantization_config=bnb_config,
    device_map="auto",  # spread layers across 4 GPUs for memory
)
model = prepare_model_for_kbit_training(model)

# Option B: bf16 LoRA with FSDP across 4 GPUs (faster for 50K examples)
# Use accelerate launch --config_file fsdp_config.yaml

lora_config = LoraConfig(
    r=64,                  # 50K examples: go higher rank
    lora_alpha=16,
    use_rslora=True,       # rank-stabilized for r=64
    target_modules=["q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"],
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
)
model = get_peft_model(model, lora_config)

sft_config = SFTConfig(
    output_dir="./70b-sft",
    num_train_epochs=2,            # 50K × 2 = 100K steps total
    per_device_train_batch_size=1, # 70B is memory-intensive even with QLoRA
    gradient_accumulation_steps=16, # effective batch = 64 with 4 GPUs
    learning_rate=1e-4,            # slightly lower than 8B default
    lr_scheduler_type="cosine",
    warmup_ratio=0.03,
    bf16=True,
    gradient_checkpointing=True,
    gradient_checkpointing_kwargs={"use_reentrant": False},
    packing=True,
    max_seq_length=4096,
    save_strategy="steps",
    save_steps=500,
    eval_strategy="steps",
    eval_steps=500,
    logging_steps=25,
    report_to="wandb",
    optim="adamw_bnb_8bit",
    weight_decay=0.01,
)
```

**Training cost estimate:**
- 50K examples, average 512 tokens/example, packed to 4096 → ~6,250 batches per epoch
- At 2 epochs: ~12,500 steps
- Per step with 4× A100: ~3–4 seconds → ~12–14 hours total
- Cost at $8/hr (4× A100 on Lambda Labs): ~$100–112 total

**S3 checkpointing strategy**: Save every 500 steps. If run fails, resume with `trainer.train(resume_from_checkpoint="./70b-sft/checkpoint-3000")`. Total checkpoint storage: ~600MB per checkpoint × 25 checkpoints = ~15GB (just the LoRA adapters, not full model).

**Post-training**: Merge LoRA into base model, quantize to AWQ int4 for deployment.

---

### Q7: Your fine-tuned model performs well on the held-out test set but poorly in production. What are the likely root causes and how would you diagnose them?

**Model Answer:**

This is train/serve distribution mismatch. Several canonical causes:

**1. Prompt format difference**

The most common and most embarrassing. Test set was formatted with the correct chat template; production code uses a slightly different format (wrong special tokens, missing newlines, different system prompt). The model is extremely sensitive to exact token sequences — even a single wrong token in the prompt format can cause degraded behavior.

Diagnosis: Log production requests verbatim (raw token IDs, not decoded text). Compare to training data format character-by-character.

Fix: Write a format validation test that verifies production prompts match the training format exactly.

**2. Input distribution shift**

The test set was sampled from the same distribution as training data. Production inputs come from real users who write differently than the data curators. Production queries may be shorter, more ambiguous, use different vocabulary, or cover edge cases not in training.

Diagnosis: Compare the n-gram distribution, average length, and topic distribution of training data vs. logged production inputs. Statistical tests: KS test on embedding distances.

Fix: Continuously log and sample production inputs → add to training data for next fine-tuning run. Build a feedback loop.

**3. Length/complexity distribution mismatch**

Test set had medium-length, well-specified queries. Production has very short queries ("summarize this" with a 10,000-word document) or very long ones. The model may not have seen these in training and handles them poorly.

Diagnosis: Segment production metrics by input length quartile. If the model degrades sharply above a certain length, training data coverage was insufficient.

**4. Truncation at max_seq_length**

Training used `max_seq_length=2048`. Production sends requests up to 8,000 tokens. Documents get silently truncated — the model is answering based on incomplete context. The model may not have been trained to handle truncated contexts gracefully.

Diagnosis: Log truncation events (requests where `len(tokenized) > max_seq_length`). Correlate truncation with poor outputs.

Fix: Increase `max_seq_length` in training, or implement explicit truncation handling (summarize → then answer, or chunk → then aggregate).

**5. Temperature/sampling parameter mismatch**

Training generated deterministic examples (consistent format). Production uses `temperature=0.8` for variety. At higher temperature, the model deviates from trained formats.

Fix: Use `temperature=0.1–0.3` for format-sensitive production tasks. Pair with structured output (constrained decoding) for zero-tolerance format requirements.

**6. System prompt drift**

The fine-tuning system prompt was "You are a helpful assistant." Production deployed with a longer, more specific system prompt. The model's behavior changes because the system prompt is conditioning all outputs. Fine-tuned models are sensitive to system prompt changes in ways the base model isn't (the SFT specifically learned to respond to the training system prompt).

Fix: Always fine-tune with the exact production system prompt. Treat system prompt as a locked hyperparameter, not a deployment-time variable.

---

### Q8: Compare GRPO to PPO. When would you choose GRPO for training a reasoning model?

**Model Answer:**

Both PPO and GRPO are policy optimization algorithms for LLM alignment. The key structural difference is how they estimate the advantage (the value of taking a specific action relative to baseline).

**PPO** uses a learned critic (value function) to estimate the advantage:
- Requires a separate value network (same size as the policy, typically frozen or smaller)
- The critic is learned jointly with the policy — training instability when critic lags the policy
- Credit assignment: the critic predicts V(s) for each token position, providing dense rewards throughout the sequence
- Well-tested but complex: clip ratio, GAE, entropy bonus, 4 hyperparameters to tune

**GRPO** (Group Relative Policy Optimization) removes the critic entirely:
- Generate G completions for each prompt (e.g., G=8)
- Compute reward for each completion (using an external reward function)
- Advantage for each completion = (reward − group_mean) / group_std (z-score)
- No learned value function — advantages are computed purely from the relative reward distribution

**Why GRPO is appealing for reasoning models:**

1. **Verifiable rewards**: Math and code have ground-truth correct answers. You can write `reward(completion) = 1 if final_answer_correct else 0`. This is objective and doesn't require human labelers or a reward model. GRPO works perfectly with this: just sample 8 solutions, run them through the verifier, use normalized scores as advantages.

2. **No reward model training**: Building a reliable reward model for nuanced reasoning quality is hard and expensive. If you can verify correctness programmatically (execute the code, check the math answer), GRPO skips this entirely.

3. **No credit assignment problem**: PPO needs to assign credit to individual tokens in a long chain-of-thought. For a multi-step math proof, which token was "responsible" for the final correct answer? GRPO sidesteps this by treating the entire completion as a unit, with advantage computed at the sequence level.

4. **Simpler stability**: Without a critic, there's one fewer source of training instability. GRPO is still sensitive to reward function design and β (KL penalty), but less so than PPO.

**When to use GRPO**: The reward is verifiable programmatically (correct/incorrect), not just preferentially (better/worse). Math, code, logic puzzles, structured extraction with ground truth. DeepSeek-R1 used GRPO with binary correctness rewards to train its reasoning chains.

**When PPO is still better**: When you need dense, nuanced reward shaping that a binary verifier can't provide — e.g., "this code is correct but inefficient" or "this answer is factually correct but not the most informative". Reward models (trained on human preferences) can capture these nuances; GRPO cannot.

---

## L7+ (Principal / Distinguished) — Strategy and Architecture

---

### Q9: A new team lead says "let's fine-tune Llama on all our company data to create an internal AI assistant." What questions would you ask, and what architecture would you propose?

**Model Answer:**

This is a very common proposal that conflates three distinct problems. My first response is to separate the goal from the method.

**Questions I'd ask:**

1. **What specific failure mode are you trying to fix?** "Internal AI assistant" is too broad. Is the base model failing at: output format (→ SFT), company-specific terminology (→ possibly fine-tuning, possibly just RAG), confidential internal knowledge (→ RAG), or consistent persona/tone (→ system prompt + SFT)?

2. **How often does your company data change?** Fine-tuning creates a model frozen at training time. If your internal documents, policies, or product info change monthly, you need RAG, not fine-tuning. A fine-tuned model trained on January's policy docs will answer incorrectly about March's policy changes.

3. **What does "all company data" include?** This is a data governance question, not a technical one. PII, customer data, trade secrets — what's the classification? Fine-tuning on unclassified company data and then serving the model to all employees creates a potential data leakage vector: the model may recall fine-tuning examples verbatim.

4. **Have you already tried a good system prompt + RAG?** In my experience, 80% of "we need fine-tuning" requests are solved by a well-engineered RAG system with a strong system prompt. Fine-tuning is the 20% case.

**Proposed architecture (after those answers):**

If the use case is primarily about answering questions from internal documents (most common):

```
RAG system (primary):
  - Indexing: chunk docs → embed (text-embedding-3-large) → store in pgvector on Aurora
  - Retrieval: hybrid BM25 + semantic, rerank with cross-encoder
  - Generation: Claude/GPT-4 with document context + company system prompt
  - Freshness: auto-re-index on document change (S3 event → Lambda → index update)

Fine-tuning (additive, if needed after RAG):
  - Only if the model consistently fails at output format despite good prompting
  - SFT on 200-500 examples of ideal (query, company-formatted response) pairs
  - LoRA r=8 → 16: subtle style/format adaptation
  - DO NOT train on internal knowledge directly
```

If the use case truly requires model capabilities that prompt/RAG can't address (specialized domain reasoning, consistent classification across many categories):

```
Fine-tuning scope: format + domain terminology only
  - Create 1K-5K high-quality (query, ideal_response) examples
  - SFT with LoRA r=16 on those examples
  - Keep base model's general capabilities via LoRA (not full FT)
  - Evaluate capability regression before deployment
  - Continue using RAG for knowledge retrieval — fine-tuning for behavior
```

The governance recommendation: version control your fine-tuned adapters (git-lfs or S3 versioning), log every training run (dataset hash, config, results), and maintain a rollback path to the base model.

---

### Q10: Explain catastrophic forgetting in the context of LLM fine-tuning. How does LoRA mitigate it, and what are the remaining risks?

**Model Answer:**

Catastrophic forgetting (McCloskey & Cohen, 1989) describes how neural networks trained on task B overwrite the weights that enabled task A, losing task A performance. For LLMs, this manifests as a fine-tuned model becoming highly competent at the target task while losing general capabilities (reasoning, factual recall, code generation) that weren't explicitly represented in the fine-tuning data.

**Mechanistically**: Gradient descent on a small, task-specific dataset pushes weights toward configurations that minimize loss on that data. The gradient signal for the task overwhelms the "implicit regularization" encoded in the original weights from pre-training. Weights drift from their pre-trained values, and the learned representations degrade.

**Severity factors:**
- **Dataset size**: More fine-tuning data relative to pre-training data = more forgetting
- **Learning rate**: Higher LR = faster, more severe forgetting
- **Training duration**: More epochs = more forgetting
- **Domain distance**: Fine-tuning on narrowly specialized data = more forgetting of unrelated domains
- **Parameter coverage**: Full FT of all layers = maximum forgetting; LoRA of 0.5% of params = minimal forgetting

**How LoRA mitigates it:**
LoRA's structural constraint is its primary anti-forgetting mechanism. By keeping W_base frozen and only training the adapter BA, the original weights are mathematically guaranteed to be preserved. Catastrophic forgetting requires the original weights to change. They don't.

The only forgetting risk with LoRA is the adapter's effect on the output: `h = Wx + BAx`. The BA contribution changes the model's behavior at every forward pass, but the W weights themselves are intact. If you remove the adapter (unload it), the model reverts exactly to the base model's behavior.

**Remaining risks even with LoRA:**

1. **Adapter-induced forgetting of base capabilities**: The adapter changes the output distribution. If trained on a narrow dataset, the adapter may cause the model to output narrowly even on queries outside the training distribution. This isn't weight forgetting — it's behavioral drift from the adapter always being active.

2. **LoRA targets the wrong layers**: If the adapter targets attention layers that encode general-purpose representations, the adapter can distort those representations even without changing the base weights. Behavior changes cascade through the model.

3. **High-rank adapters with extended training**: At r=128+, the adapter has significant capacity. With aggressive training (high LR, many epochs), the adapter can still push the model toward a specialized distribution even if base weights are frozen.

**Mitigation strategies:**
- **Replay buffer**: Mix 5–10% general instruction data into every fine-tuning batch. The adapter learns to serve both the task distribution and the general distribution.
- **LoRA rank selection**: Use the minimum rank that satisfies task performance. Lower rank = less adaptation capacity = less behavioral drift.
- **Capability evaluation throughout training**: Track MMLU/HellaSwag loss every 200 steps (not just at the end). If general benchmarks start degrading, stop or add replay data.
- **Separate adapters for separate tasks**: Don't combine drastically different tasks in one fine-tuning run. Train separate adapters and multiplex at serving time.

---

### Q11: How do you build a synthetic dataset pipeline for fine-tuning when you have no existing labeled data?

**Model Answer:**

Synthetic data generation has become one of the most important skills in LLM fine-tuning. The Phi-1, Phi-2, Phi-3, and Magpie families of models achieved disproportionate performance through high-quality synthetic data.

**The core insight**: A large, capable model (GPT-4, Claude-3.5-Sonnet) can generate training examples for a smaller model at much lower cost than human annotation. The small model learns from the large model's outputs — capability distillation through data.

**Pipeline architecture:**

```python
# Stage 1: Seed task collection
# Gather ~100 high-quality real examples manually. These seed the distribution.
seed_examples = load_manual_examples("seeds.jsonl")  # 100 curated examples

# Stage 2: Diversity expansion — generate prompts/instructions at scale
from anthropic import Anthropic
client = Anthropic()

def generate_diverse_instructions(seed: str, n: int = 20) -> list[str]:
    """Generate n variations of a seed instruction, covering different topics/styles."""
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": f"""Generate {n} diverse instructions similar in task type to this example, but covering different topics, difficulty levels, and phrasing styles. Return as a JSON list of strings.

Seed: {seed}"""
        }]
    )
    return json.loads(response.content[0].text)

# Generate 50K instruction variations from 100 seeds
all_instructions = []
for seed in seed_examples:
    all_instructions.extend(generate_diverse_instructions(seed["instruction"], n=500))

# Stage 3: Generate responses with quality scoring
def generate_and_score(instruction: str) -> dict | None:
    """Generate response and score quality. Return None if quality too low."""
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1024,
        system="You are an expert assistant. Provide thorough, accurate responses.",
        messages=[{"role": "user", "content": instruction}]
    )
    response_text = response.content[0].text

    # Self-score the response
    score_response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=10,
        messages=[{
            "role": "user",
            "content": f"Rate the quality of this response on a scale of 1-5. Respond with only the number.\n\nInstruction: {instruction}\n\nResponse: {response_text}"
        }]
    )
    score = int(score_response.content[0].text.strip())

    if score < 4:
        return None  # filter low-quality

    return {"instruction": instruction, "response": response_text, "quality_score": score}

# Stage 4: Deduplication + filtering
# MinHash LSH: remove near-duplicate instructions
# Filter: length, quality score, format validity

# Stage 5: Chat template formatting
dataset = [format_for_training(ex) for ex in generated_examples]
```

**Advanced techniques:**

**Magpie-style generation** (2024): Instead of prompting a model to generate instructions, use the model's chat template to auto-complete from the user turn start. The model generates natural, in-distribution instructions by predicting what a user would ask. More natural instruction distribution than explicit instruction generation prompts.

```python
# Magpie: let the model generate its own instructions
user_turn_start = tokenizer.apply_chat_template(
    [{"role": "user", "content": ""}],
    tokenize=False,
    add_generation_prompt=False,
)[:-len(tokenizer.eos_token)]  # everything up to the user content

# Generate: model fills in the user content naturally
generated_instruction = model.generate(tokenize(user_turn_start), max_new_tokens=200)
```

**Quality filters**: After generation, apply multi-step filtering:
1. Length filter: reject too short (< 20 words) or too long (> 800 words) responses
2. Format filter: reject responses that start with "As an AI language model..." (a known quality degrader)
3. LLM-judge quality score: keep only score ≥ 4/5
4. Deduplication: MinHash LSH at Jaccard similarity threshold 0.8
5. Domain relevance: embed and filter to target domain cluster

**The cost math**: For 50K examples at ~500 tokens each, using Claude-3-5-Haiku for generation: $0.25/M input, $1.25/M output. Total: ~$50–100 for the full dataset. Dramatically cheaper than human annotation (~$1–5 per example × 50K = $50K–250K).

---

### Q12: How do you approach fine-tuning when your task requires reasoning capabilities that the base model has but your fine-tuned model keeps losing?

**Model Answer:**

This is the "alignment tax" problem in a specific form: the fine-tuning distribution is narrower than the general reasoning distribution, causing the model to trade reasoning capacity for task-specific pattern matching.

**Diagnosing the root cause first:**

Is the reasoning degradation due to:
1. **Catastrophic forgetting via full FT** (rare if using LoRA): base weights changed
2. **Adapter-induced distribution narrowing**: the model has learned to "take shortcuts" on the task distribution
3. **Training data lacks reasoning demonstrations**: examples show correct answers without reasoning steps
4. **Temperature/sampling mismatch**: model needs higher temperature to reason but you're using T=0

**Mitigation strategies:**

**Include chain-of-thought in training data.** If your training examples show only (input → output) without intermediate reasoning steps, the model learns a shallow pattern. Including explicit reasoning:
```json
{
  "instruction": "Classify this complaint as High/Medium/Low severity",
  "response": "<think>The customer mentions data loss ('all my files are gone') which is irreversible and affects business operations. This is a High severity issue per our classification rubric.</think>\n\nHigh severity"
}
```
The model retains the ability to reason because it's trained to reason.

**Replay general reasoning data.** Add 10% of general instruction data (WizardLM, ShareGPT, FLAN) to your training batches. This provides gradient signal to preserve reasoning capabilities.

**Use a higher rank adapter.** Counterintuitively, a higher-rank LoRA with stronger regularization (weight decay, dropout) can preserve reasoning better than a low-rank adapter that forces the model to overly specialize. The higher rank provides capacity for both the task distribution and the reasoning distribution.

**Two-stage approach**: First, fine-tune on a mixed dataset (80% task + 20% reasoning examples like GSM8K chain-of-thought, FLAN reasoning tasks). Second, optionally fine-tune on task data only for 1 more epoch. The first stage preserves reasoning; the second specializes.

**Evaluate reasoning periodically during training.** Don't wait until the end to discover reasoning has degraded. Run a subset of GSM8K or multi-step reasoning tests every 200 training steps. If reasoning accuracy drops by > 5pp relative to the base model, add replay data immediately.

**The meta-lesson**: Fine-tuning is a distribution narrowing operation. If your target task can be accomplished via shallow pattern matching (and the model learns this shortcut), it will. Design your training data so that the shortcut path doesn't exist — include examples that require reasoning to get right, where pattern matching alone would fail.
