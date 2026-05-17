# Key Technical Concepts

## 1. LoRA — Low-Rank Adaptation

The most widely deployed PEFT method. Introduced by Hu et al. (2021), now the default for production fine-tuning.

**Core idea**: For each weight matrix W in the model, instead of updating W directly, inject a parallel low-rank decomposition and train only that. The weight update ΔW is constrained to be the product of two small matrices: ΔW = BA, where B ∈ R^{d×r} and A ∈ R^{r×d}, with r << min(d, d).

**Why rank constrains expressiveness**: The rank r controls the "capacity" of the adapter. A higher rank can represent more complex weight updates but requires more parameters:
```
Parameters in one LoRA adapter = d_in × r + r × d_out
For LLaMA-3-8B: d=4096, r=16 → 4096×16 + 16×4096 = 131,072 params per layer
8B model has ~32 attention layers × 4 matrices = ~128 LoRA modules
Total LoRA params: 128 × 131,072 ≈ 16.8M = 0.21% of 8B
```

**The alpha/r scaling**: LoRA outputs are scaled by `alpha/r`. If alpha=32 and r=16, the effective learning rate for the adapter is 2×. This decouples the scaling from the rank choice. Standard practice: set `alpha = 2 × r`.

**Which layers to target**: By default, target query and value projection matrices (`q_proj`, `v_proj`). In practice, targeting all attention matrices + MLP layers improves quality:

```python
from peft import LoraConfig, get_peft_model, TaskType

lora_config = LoraConfig(
    r=16,                       # rank — start here, increase if underfit
    lora_alpha=32,              # alpha = 2×r is standard
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",  # attention
        "gate_proj", "up_proj", "down_proj",       # MLP
    ],
    lora_dropout=0.05,
    bias="none",                # "none" = don't train biases (faster)
    task_type=TaskType.CAUSAL_LM,
)
model = get_peft_model(base_model, lora_config)
model.print_trainable_parameters()
# trainable params: 41,943,040 || all params: 8,030,261,248 || trainable%: 0.5223
```

**Merging LoRA into base model** (for zero-overhead inference):
```python
from peft import PeftModel

# Load base + adapter
model = AutoModelForCausalLM.from_pretrained(base_model_id, torch_dtype=torch.bfloat16)
model = PeftModel.from_pretrained(model, adapter_path)

# Merge: W_merged = W_base + BA
model = model.merge_and_unload()
model.save_pretrained("merged_model")
```

After merging, inference is identical to the base model — no adapter overhead. This is the standard deployment path.

---

## 2. QLoRA — Quantized LoRA

Dettmers et al. (2023). Makes 70B fine-tuning accessible on consumer/single-node hardware by quantizing the frozen base model to 4-bit (NF4) while training LoRA adapters in bf16.

**Three key innovations:**
1. **NF4 (NormalFloat4)**: A 4-bit data type whose 16 quantization points are placed at equal probability intervals of a normal distribution — matching the actual weight distribution of neural networks. Better than uniform int4 by design.
2. **Double quantization**: Quantize the quantization constants themselves (saving ~0.37 bits/parameter extra).
3. **Paged optimizers**: Use NVIDIA's unified memory to swap optimizer states to CPU when GPU memory is tight.

```python
from transformers import AutoModelForCausalLM, BitsAndBytesConfig
from peft import prepare_model_for_kbit_training, LoraConfig, get_peft_model
import torch

# Step 1: Load base model in 4-bit
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_compute_dtype=torch.bfloat16,   # compute in bf16, store in nf4
    bnb_4bit_use_double_quant=True,           # double quantization
    bnb_4bit_quant_type="nf4",               # NormalFloat4
)
model = AutoModelForCausalLM.from_pretrained(
    "meta-llama/Meta-Llama-3.1-70B-Instruct",
    quantization_config=bnb_config,
    device_map="auto",
)

# Step 2: Prepare model for k-bit training (enables gradient checkpointing)
model = prepare_model_for_kbit_training(model)

# Step 3: Add LoRA adapters (these train in bf16)
config = LoraConfig(r=64, lora_alpha=16, target_modules=["q_proj","v_proj","k_proj","o_proj"],
                    lora_dropout=0.05, bias="none", task_type="CAUSAL_LM")
model = get_peft_model(model, config)
```

**Memory comparison (70B model):**
- Full FT bf16: ~560GB GPU memory (70B × 2B weight + 2B grad + 8B optimizer)
- LoRA bf16: ~150GB (70B × 2B frozen + 4B LoRA grad + 16B LoRA optimizer)
- QLoRA NF4: ~40GB (70B × 0.5B frozen NF4 + small LoRA in bf16)

QLoRA enables 70B fine-tuning on 2× A100 80GB or even a single A100 with `--gradient_checkpointing`.

---

## 3. DoRA — Weight-Decomposed Low-Rank Adaptation

Liu et al. (2024). Decomposes the pre-trained weight into magnitude and direction components, then applies LoRA only to the direction. Bridges the gap between LoRA and full fine-tuning in learning capacity.

```python
# DoRA in peft (built-in support from v0.9+)
lora_config = LoraConfig(
    r=16,
    lora_alpha=32,
    target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
    use_dora=True,   # ← enables DoRA instead of standard LoRA
    task_type=TaskType.CAUSAL_LM,
)
```

Quality improvement over LoRA at the same rank is typically 1–3% on instruction-following benchmarks. Marginal overhead vs LoRA. Use DoRA when maximizing quality at a given rank budget.

---

## 4. AdaLoRA — Adaptive Budget Allocation

Zhang et al. (2023). Allocates the rank budget adaptively across weight matrices based on their importance. More important matrices (e.g., attention layers in deep parts of the network) get higher rank; less important ones get lower rank or are pruned entirely.

```python
from peft import AdaLoraConfig

adalora_config = AdaLoraConfig(
    init_r=12,        # initial rank
    target_r=8,       # target rank after pruning
    beta1=0.85,
    beta2=0.85,
    tinit=200,        # warmup steps before pruning
    tfinal=1000,      # total pruning duration
    deltaT=10,        # pruning frequency
    lora_alpha=32,
    target_modules=["q_proj", "v_proj"],
    task_type=TaskType.CAUSAL_LM,
)
```

Useful when you have a fixed parameter budget and want to maximize quality. In practice, for most production fine-tuning, standard LoRA with r=16–64 is sufficient.

---

## 5. Instruction Tuning — Data Format

The format of training data is as critical as the model architecture. Foundation models must be taught to follow instructions via SFT on (instruction, response) pairs.

**Chat template for Llama-3:**
```python
from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("meta-llama/Meta-Llama-3.1-8B")

# The tokenizer handles template formatting
messages = [
    {"role": "system", "content": "You are a helpful legal assistant."},
    {"role": "user", "content": "What does 'force majeure' mean?"},
    {"role": "assistant", "content": "Force majeure refers to unforeseeable circumstances..."},
]

# Format with chat template — this is what the model sees during training
formatted = tokenizer.apply_chat_template(
    messages,
    tokenize=False,
    add_generation_prompt=False,
)
# <|begin_of_text|><|start_header_id|>system<|end_header_id|>
# You are a helpful legal assistant.<|eot_id|>
# <|start_header_id|>user<|end_header_id|>
# What does 'force majeure' mean?<|eot_id|>
# <|start_header_id|>assistant<|end_header_id|>
# Force majeure refers to...<|eot_id|>
```

**Critical: train only on assistant tokens, not on user/system tokens.** Compute loss only where the model should generate — mask everything else with -100 in labels:

```python
def tokenize_and_mask(example, tokenizer, max_length=2048):
    """Tokenize and mask non-assistant portions for SFT."""
    full_text = tokenizer.apply_chat_template(
        example["messages"], tokenize=False, add_generation_prompt=False
    )
    tokenized = tokenizer(full_text, max_length=max_length, truncation=True)

    labels = tokenized["input_ids"].copy()

    # Find assistant start/end positions and mask everything else
    # (Implementation depends on tokenizer; TRL's DataCollatorForCompletionOnlyLM handles this automatically)
    assistant_start = tokenizer.encode("<|start_header_id|>assistant<|end_header_id|>", add_special_tokens=False)
    eot_id = tokenizer.encode("<|eot_id|>", add_special_tokens=False)

    # Mask all tokens not in assistant response blocks
    in_assistant = False
    for i, token_id in enumerate(labels):
        if not in_assistant:
            labels[i] = -100  # mask: don't compute loss here

    return {"input_ids": tokenized["input_ids"], "labels": labels, "attention_mask": tokenized["attention_mask"]}
```

---

## 6. DPO — Direct Preference Optimization

Rafailov et al. (2023). Trains the model directly on (chosen, rejected) response pairs without a separate reward model. Mathematically equivalent to RLHF with PPO but vastly simpler.

**The objective**: Maximize the log-probability ratio of chosen over rejected, relative to the reference model, scaled by β (temperature):

```
L_DPO = -E[log σ(β × (log P_θ(y_w|x) - log P_ref(y_w|x)) - β × (log P_θ(y_l|x) - log P_ref(y_l|x)))]
```

Where y_w = preferred response, y_l = rejected response. The reference model (the SFT model) acts as a regularizer — prevents the policy from diverging too far.

```python
from trl import DPOTrainer, DPOConfig
from datasets import Dataset

# Dataset format for DPO
dpo_data = Dataset.from_list([
    {
        "prompt": "Explain quantum entanglement",
        "chosen": "Quantum entanglement is a phenomenon where two particles become correlated...",
        "rejected": "Quantum entanglement means particles are linked together and one affects the other instantly no matter how far apart they are — it's basically teleportation.",
    },
    # ... more examples
])

dpo_config = DPOConfig(
    beta=0.1,              # lower β = more deviation from reference allowed
    max_length=2048,
    max_prompt_length=512,
    learning_rate=5e-7,    # much lower than SFT — subtle preference shaping
    per_device_train_batch_size=2,
    gradient_accumulation_steps=8,
    num_train_epochs=1,    # DPO typically needs only 1 epoch
    bf16=True,
    output_dir="dpo_output",
)

trainer = DPOTrainer(
    model=sft_model,           # start from SFT checkpoint
    ref_model=ref_model,       # copy of SFT model, frozen
    args=dpo_config,
    train_dataset=dpo_data,
    tokenizer=tokenizer,
)
trainer.train()
```

**β tuning**: β controls how much the model deviates from the reference. Low β (0.05–0.1) = aggressive preference optimization (risk of reward hacking). High β (0.5+) = conservative, stays close to reference.

---

## 7. ORPO — Odds Ratio Preference Optimization

Hong et al. (2024). Eliminates the need for a reference model by embedding a penalty for rejected responses directly into the SFT loss. Single-stage training: SFT + preference alignment simultaneously.

```python
from trl import ORPOTrainer, ORPOConfig

orpo_config = ORPOConfig(
    lambda_=0.1,          # weight for the odds-ratio penalty
    learning_rate=8e-6,
    per_device_train_batch_size=2,
    gradient_accumulation_steps=4,
    max_length=2048,
    num_train_epochs=3,
    bf16=True,
    output_dir="orpo_output",
)

trainer = ORPOTrainer(
    model=base_model,   # start from base model directly — no SFT step
    args=orpo_config,
    train_dataset=dataset_with_chosen_rejected,
    tokenizer=tokenizer,
)
```

**ORPO vs DPO**: ORPO needs only (prompt, chosen, rejected) and trains in one stage. DPO requires a pre-trained SFT model as reference. ORPO is cheaper and simpler; DPO gives more control (can tune β and use different reference). For most production use cases, ORPO or the even simpler SimPO is the right default.

---

## 8. GRPO — Group Relative Policy Optimization (DeepSeek-R1)

Shao et al. (2024), used in DeepSeek-R1 to train reasoning models. Eliminates the critic network used in PPO by using group-relative rewards:

For each prompt, generate G completions. Compute the reward for each. Normalize rewards within the group (z-score). Use normalized rewards as advantages instead of a learned value function.

```python
from trl import GRPOTrainer, GRPOConfig

def reward_function(completions, **kwargs) -> list[float]:
    """Reward: +1 if final answer is correct, -0.5 if format wrong."""
    rewards = []
    for completion in completions:
        if has_correct_answer(completion):
            rewards.append(1.0)
        elif has_valid_format(completion):
            rewards.append(0.1)  # partial credit for correct format
        else:
            rewards.append(-0.5)
    return rewards

grpo_config = GRPOConfig(
    learning_rate=5e-7,
    num_generations=8,     # G: completions per prompt
    max_new_tokens=512,
    temperature=0.9,
    beta=0.01,             # KL penalty coefficient
    output_dir="grpo_output",
)

trainer = GRPOTrainer(
    model=sft_model,
    reward_funcs=reward_function,
    args=grpo_config,
    train_dataset=math_problems_dataset,
    tokenizer=tokenizer,
)
```

**When to use GRPO**: Training reasoning / chain-of-thought models where correctness of a final answer can be verified programmatically (math, code, logic puzzles). The verifiable reward signal makes GRPO tractable where human preference data would be too expensive.

---

## 9. DeepSpeed ZeRO and FSDP for Distributed Fine-Tuning

For models > 7B on multiple GPUs:

**DeepSpeed ZeRO (Zero Redundancy Optimizer)**:
- ZeRO-1: Partition optimizer states across GPUs. Each GPU holds full params + grads, but only its shard of optimizer state.
- ZeRO-2: Partition optimizer states + gradients. Reduces memory proportional to world_size.
- ZeRO-3: Partition optimizer states + gradients + parameters. Each GPU holds 1/N of the model. Full model only exists in aggregate.

```python
# deepspeed_config.json for ZeRO-3
{
  "zero_optimization": {
    "stage": 3,
    "offload_optimizer": {"device": "cpu", "pin_memory": true},
    "offload_param": {"device": "cpu", "pin_memory": true},
    "overlap_comm": true,
    "contiguous_gradients": true,
    "sub_group_size": 1e9,
    "reduce_bucket_size": "auto",
    "stage3_prefetch_bucket_size": "auto",
    "stage3_param_persistence_threshold": "auto",
    "stage3_gather_16bit_weights_on_model_save": true
  },
  "gradient_accumulation_steps": 4,
  "gradient_clipping": 1.0,
  "bf16": {"enabled": true},
  "train_micro_batch_size_per_gpu": 2
}
```

```bash
# Launch with deepspeed
deepspeed --num_gpus=8 train.py \
  --deepspeed deepspeed_config.json \
  --model_name_or_path meta-llama/Meta-Llama-3.1-70B-Instruct \
  --output_dir ./fine_tuned_model
```

**PyTorch FSDP (Fully Sharded Data Parallel)**: Native PyTorch alternative to ZeRO-3. Integrated in Hugging Face `accelerate`. Generally preferred for simplicity:

```python
# accelerate config for FSDP
from accelerate import FullyShardedDataParallelPlugin
from torch.distributed.fsdp.fully_sharded_data_parallel import FullOptimStateDictConfig, FullStateDictConfig

fsdp_plugin = FullyShardedDataParallelPlugin(
    state_dict_config=FullStateDictConfig(offload_to_cpu=True, rank0_only=False),
    optim_state_dict_config=FullOptimStateDictConfig(offload_to_cpu=True, rank0_only=False),
)

# In accelerate config file:
# compute_environment: LOCAL_MACHINE
# distributed_type: FSDP
# fsdp_config:
#   fsdp_auto_wrap_policy: TRANSFORMER_BASED_WRAP
#   fsdp_backward_prefetch_policy: BACKWARD_PRE
#   fsdp_sharding_strategy: 1  # FULL_SHARD = ZeRO-3 equivalent
#   fsdp_state_dict_type: FULL_STATE_DICT
#   fsdp_offload_params: false
```

---

## 10. Gradient Checkpointing

Trading compute for memory: instead of storing all activations in the forward pass (needed for backprop), recompute them on demand during the backward pass. Reduces activation memory from O(L) to O(√L) where L = number of layers, at the cost of ~33% more compute.

```python
model.gradient_checkpointing_enable()

# In TrainingArguments:
training_args = TrainingArguments(
    gradient_checkpointing=True,
    gradient_checkpointing_kwargs={"use_reentrant": False},  # preferred for newer PyTorch
    # ...
)
```

Always enable gradient checkpointing for any model > 7B. The compute overhead is worth the memory savings — it's often the difference between fitting on available hardware or not.

---

## 11. Data Packing / Sequence Packing

Naive batching pads short sequences to the maximum length in the batch, wasting FLOPS on padding tokens. Sequence packing concatenates multiple short training examples into a single sequence (up to max_length), separated by EOS tokens, then masks cross-example attention.

```python
from trl import SFTTrainer, SFTConfig

sft_config = SFTConfig(
    packing=True,         # ← enables sequence packing
    max_seq_length=4096,  # pack examples to fill this length
    # ...
)
```

**Impact**: 2–5× throughput improvement for datasets with short average sequence lengths (< 512 tokens). Less helpful for long-document datasets where examples already fill the context window.
