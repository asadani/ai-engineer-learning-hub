# Products & Tools

## Core Training Libraries

### HuggingFace TRL (Transformer Reinforcement Learning)

The primary library for SFT, DPO, PPO, GRPO, and other alignment training. Provides `SFTTrainer`, `DPOTrainer`, `PPOTrainer`, `ORPOTrainer`, `GRPOTrainer`, and `RewardTrainer` — all built on top of HuggingFace `Trainer`.

```python
from trl import SFTTrainer, SFTConfig
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer
from datasets import load_dataset

model = AutoModelForCausalLM.from_pretrained(
    "meta-llama/Meta-Llama-3.1-8B-Instruct",
    torch_dtype=torch.bfloat16,
    device_map="auto",
    attn_implementation="flash_attention_2",
)
tokenizer = AutoTokenizer.from_pretrained("meta-llama/Meta-Llama-3.1-8B-Instruct")
tokenizer.pad_token = tokenizer.eos_token
tokenizer.padding_side = "right"  # critical for causal LMs

dataset = load_dataset("json", data_files="train.jsonl", split="train")

lora_config = LoraConfig(
    r=16, lora_alpha=32,
    target_modules=["q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"],
    lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
)

sft_config = SFTConfig(
    output_dir="./sft_output",
    num_train_epochs=3,
    per_device_train_batch_size=2,
    gradient_accumulation_steps=8,    # effective batch = 2 × 8 × num_gpus
    learning_rate=2e-4,
    lr_scheduler_type="cosine",
    warmup_ratio=0.05,
    bf16=True,
    gradient_checkpointing=True,
    gradient_checkpointing_kwargs={"use_reentrant": False},
    packing=True,
    max_seq_length=4096,
    logging_steps=10,
    save_strategy="steps",
    save_steps=200,
    eval_strategy="steps",
    eval_steps=200,
    load_best_model_at_end=True,
    metric_for_best_model="eval_loss",
    report_to="wandb",
)

trainer = SFTTrainer(
    model=model,
    args=sft_config,
    train_dataset=dataset["train"],
    eval_dataset=dataset["validation"],
    peft_config=lora_config,
    tokenizer=tokenizer,
)
trainer.train()
trainer.save_model()
```

---

### Unsloth

Performance-optimized fine-tuning library. Custom CUDA kernels, patched Flash Attention, and memory-efficient LoRA kernels. **2–5× faster training and 40–70% less memory than standard TRL/PEFT** on the same hardware. Drop-in replacement for most workflows.

```python
from unsloth import FastLanguageModel
import torch

# Load with Unsloth optimizations
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="unsloth/Meta-Llama-3.1-8B-Instruct",
    max_seq_length=4096,
    dtype=None,              # auto-detect bf16/fp16
    load_in_4bit=True,
    token=os.environ["HF_TOKEN"],
)

# Apply LoRA with Unsloth's optimized kernels
model = FastLanguageModel.get_peft_model(
    model,
    r=16,
    target_modules=["q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"],
    lora_alpha=16,
    lora_dropout=0,         # Unsloth supports 0 dropout for max speed
    bias="none",
    use_gradient_checkpointing="unsloth",  # uses Unsloth's custom GC implementation
    random_state=42,
    use_rslora=False,       # rank-stabilized LoRA — try True for higher ranks
    loftq_config=None,
)

# Standard TRL trainer from here
from trl import SFTTrainer, SFTConfig
trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    args=SFTConfig(
        per_device_train_batch_size=4,
        gradient_accumulation_steps=4,
        warmup_steps=5,
        num_train_epochs=3,
        learning_rate=2e-4,
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        optim="adamw_8bit",     # 8-bit AdamW: 4× less optimizer memory
        weight_decay=0.01,
        lr_scheduler_type="linear",
        output_dir="outputs",
        report_to="wandb",
    ),
)
trainer.train()
```

**When to use Unsloth**: If you're budget-constrained or training on a single GPU. The speedup is real and documented (they publish reproducible benchmarks). The trade-off: Unsloth patches model internals — less stable with very new model architectures until they add support.

---

### Axolotl

YAML-driven fine-tuning framework. Wraps TRL/PEFT/DeepSpeed with a configuration-first approach. Popular in the open-source fine-tuning community for its ease of experimentation.

```yaml
# axolotl_config.yml
base_model: meta-llama/Meta-Llama-3.1-8B-Instruct
model_type: LlamaForCausalLM
tokenizer_type: AutoTokenizer

load_in_4bit: true
strict: false

datasets:
  - path: ./data/train.jsonl
    type: chat_template  # or: alpaca, sharegpt, completion, etc.
    chat_template: llama3

val_set_size: 0.05
output_dir: ./outputs/qlora-llama3-8b

sequence_len: 4096
sample_packing: true

adapter: qlora
lora_r: 64
lora_alpha: 16
lora_dropout: 0.05
lora_target_modules:
  - q_proj
  - v_proj
  - k_proj
  - o_proj
  - gate_proj
  - up_proj
  - down_proj

gradient_accumulation_steps: 4
micro_batch_size: 2
num_epochs: 3
optimizer: adamw_bnb_8bit
lr_scheduler: cosine
learning_rate: 0.0002
train_on_inputs: false  # only train on assistant responses
group_by_length: false
bf16: auto
tf32: false
gradient_checkpointing: true
flash_attention: true
logging_steps: 10
eval_steps: 200
save_steps: 200
warmup_steps: 10
```

```bash
# Launch
accelerate launch -m axolotl.cli.train axolotl_config.yml

# Multi-GPU
accelerate launch --config_file fsdp_config.yaml -m axolotl.cli.train config.yml
```

**Why Axolotl over raw TRL**: Axolotl handles the boilerplate of dataset formatting (supports 20+ data formats including alpaca, ShareGPT, chatml, completion, instruction), multi-dataset mixing, deepspeed/FSDP integration, and checkpoint resume. Reduces a 300-line training script to a 50-line YAML.

---

### LLaMA-Factory

Web UI + CLI for fine-tuning. Supports LoRA, QLoRA, full FT, DPO, PPO across all major model families (Llama, Qwen, Mistral, Yi, Gemma). Good for teams that want a GUI workflow.

```bash
# Install
pip install llamafactory

# Web UI
llamafactory-cli webui

# CLI training
llamafactory-cli train \
  --model_name_or_path meta-llama/Meta-Llama-3.1-8B-Instruct \
  --method lora \
  --dataset_dir ./data \
  --dataset my_dataset \
  --template llama3 \
  --output_dir ./saves/llama3-8b-lora \
  --num_train_epochs 3 \
  --per_device_train_batch_size 2 \
  --gradient_accumulation_steps 8 \
  --learning_rate 2e-4 \
  --lora_rank 16 \
  --lora_alpha 32 \
  --fp16
```

---

## Data Preparation Tools

### LLM Data Pipelines

```python
# Distilabel: synthetic data generation pipeline
from distilabel.pipeline import Pipeline
from distilabel.steps import LoadDataFromHub, KeepColumns
from distilabel.steps.tasks import TextGeneration, UltraFeedback

pipeline = Pipeline(
    name="generate-sft-data",
    steps=[
        LoadDataFromHub(
            repo_id="HuggingFaceH4/instruction-dataset",
            split="train",
            batch_size=64,
        ),
        TextGeneration(
            llm=InferenceEndpointsLLM(
                model_id="meta-llama/Meta-Llama-3.1-70B-Instruct",
            ),
            system_prompt="You are an expert assistant. Answer concisely and accurately.",
        ),
        UltraFeedback(
            llm=InferenceEndpointsLLM(
                model_id="meta-llama/Meta-Llama-3.1-70B-Instruct",
            ),
        ),
    ],
)
distiset = pipeline.run()
```

### Dataset Deduplication (crucial for quality)

```python
# MinHash LSH deduplication
from datasets import load_dataset
from datasketch import MinHash, MinHashLSH

def get_minhash(text: str, num_perm: int = 128) -> MinHash:
    m = MinHash(num_perm=num_perm)
    for shingle in {text[i:i+5] for i in range(len(text) - 4)}:
        m.update(shingle.encode("utf8"))
    return m

# Remove near-duplicates with Jaccard similarity > 0.8
lsh = MinHashLSH(threshold=0.8, num_perm=128)
unique_indices = []
for i, example in enumerate(dataset):
    mh = get_minhash(example["text"])
    if not lsh.query(mh):
        lsh.insert(str(i), mh)
        unique_indices.append(i)

deduped_dataset = dataset.select(unique_indices)
print(f"Removed {len(dataset) - len(deduped_dataset)} duplicates")
```

---

## AWS Fine-Tuning Infrastructure

### AWS SageMaker Training Jobs

Managed compute for distributed fine-tuning. Handles instance provisioning, distributed setup (NCCL), and S3 checkpointing automatically.

```python
import sagemaker
from sagemaker.huggingface import HuggingFace

role = sagemaker.get_execution_role()

# Training script receives SM_* env vars for input/output paths
hyperparameters = {
    "model_id": "meta-llama/Meta-Llama-3.1-8B-Instruct",
    "dataset_path": "/opt/ml/input/data/training",
    "output_dir": "/opt/ml/model",
    "num_train_epochs": 3,
    "per_device_train_batch_size": 2,
    "gradient_accumulation_steps": 8,
    "learning_rate": 2e-4,
    "lora_r": 16,
    "lora_alpha": 32,
    "bf16": True,
    "packing": True,
}

huggingface_estimator = HuggingFace(
    entry_point="train.py",
    source_dir="./src",
    instance_type="ml.p4d.24xlarge",    # 8× A100 40GB
    instance_count=1,
    role=role,
    transformers_version="4.43.1",
    pytorch_version="2.1.0",
    py_version="py310",
    hyperparameters=hyperparameters,
    environment={
        "HF_TOKEN": os.environ["HF_TOKEN"],
        "WANDB_API_KEY": os.environ["WANDB_API_KEY"],
    },
    # Spot training — 60-70% cost reduction
    use_spot_instances=True,
    max_wait=86400,  # 24h max wait for Spot
    max_run=28800,   # 8h max training time
    checkpoint_s3_uri="s3://my-bucket/checkpoints/",
    checkpoint_local_path="/opt/ml/checkpoints",
)

# Define input channels
from sagemaker.inputs import TrainingInput
huggingface_estimator.fit({
    "training": TrainingInput("s3://my-bucket/training-data/", content_type="application/jsonlines"),
    "validation": TrainingInput("s3://my-bucket/validation-data/", content_type="application/jsonlines"),
})
```

**SageMaker checkpointing** (critical for Spot): SageMaker automatically syncs `/opt/ml/checkpoints` to S3 every 5 minutes and restores on restart. Your training script must resume from the latest checkpoint:

```python
import os, glob

checkpoint_dir = "/opt/ml/checkpoints"
output_dir = "/opt/ml/model"

# Find latest checkpoint
checkpoints = sorted(glob.glob(f"{checkpoint_dir}/checkpoint-*"), key=os.path.getmtime)
resume_from = checkpoints[-1] if checkpoints else None

training_args = SFTConfig(
    output_dir=output_dir,
    # ...
)
trainer = SFTTrainer(...)
trainer.train(resume_from_checkpoint=resume_from)
```

### AWS Bedrock Fine-Tuning (Managed)

For Titan and some Meta models, Bedrock offers managed fine-tuning without GPU management:

```python
import boto3, json

client = boto3.client("bedrock", region_name="us-east-1")

response = client.create_model_customization_job(
    jobName="llama3-ft-legal",
    customModelName="llama3-legal-v1",
    roleArn="arn:aws:iam::123456789:role/BedrockFinetuningRole",
    baseModelIdentifier="meta.llama3-1-8b-instruct-v1:0",
    customizationType="FINE_TUNING",
    trainingDataConfig={
        "s3Uri": "s3://my-bucket/training-data.jsonl"
    },
    validationDataConfig={
        "validators": [{"s3Uri": "s3://my-bucket/validation.jsonl"}]
    },
    outputDataConfig={"s3Uri": "s3://my-bucket/output/"},
    hyperParameters={
        "epochCount": "3",
        "batchSize": "4",
        "learningRate": "0.00005",
    },
)
```

**Bedrock FT limitations**: No LoRA control, limited hyperparameter access, only supported model families, and it's more expensive than self-managed on EC2. Useful for teams without MLOps capacity.

---

## Experiment Tracking

### Weights & Biases for Fine-Tuning

```python
import wandb
from transformers import TrainerCallback

# Auto-integration via SFTConfig
sft_config = SFTConfig(
    report_to="wandb",  # ← automatically logs loss, lr, gradients
    run_name="llama3-8b-legal-lora-r16",
    # ...
)

os.environ["WANDB_PROJECT"] = "llm-fine-tuning"
os.environ["WANDB_LOG_MODEL"] = "checkpoint"  # log model checkpoints as W&B artifacts

# Custom callback for domain metrics
class DomainEvalCallback(TrainerCallback):
    def on_evaluate(self, args, state, control, **kwargs):
        domain_metrics = run_domain_evaluation(model=kwargs["model"])
        wandb.log({
            "eval/format_compliance": domain_metrics["format_rate"],
            "eval/task_accuracy": domain_metrics["accuracy"],
            "step": state.global_step,
        })

trainer = SFTTrainer(..., callbacks=[DomainEvalCallback()])
```

**What to track during fine-tuning:**
- `train/loss` and `eval/loss` (primary signal for SFT convergence)
- `train/grad_norm` — exploding gradients (> 5.0) indicate LR too high
- `train/learning_rate` — verify cosine decay is behaving
- `eval/perplexity` — `exp(eval_loss)`, easier to interpret
- Domain-specific task metrics every N steps (not just loss)
- GPU memory utilization (catch OOM before it happens)
