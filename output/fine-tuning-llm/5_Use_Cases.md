# Use Cases & Real-World Applications

## 1. Customer Support Chatbot — Format + Tone Fine-Tuning

**Context**: A SaaS company wants their LLM to always respond in a structured format (acknowledgment → solution → follow-up question), use company-specific terminology, and maintain a consistent supportive tone. Prompt engineering alone produces inconsistent format compliance (~70%).

**Strategy**: SFT with LoRA on 2,000 curated (query, ideal_response) pairs.

```python
# Data format: each example is a high-quality support interaction
training_examples = [
    {
        "messages": [
            {"role": "system", "content": "You are Aria, a helpful support agent for Acme SaaS. Always acknowledge the user's issue, provide a clear solution with steps, and end with a follow-up question."},
            {"role": "user", "content": "I can't find where to export my data."},
            {"role": "assistant", "content": "I understand you're looking for the data export feature — it's a common need!\n\n**To export your data:**\n1. Go to Settings → Account → Data Management\n2. Click 'Export All Data'\n3. Choose your format (CSV or JSON)\n4. Click 'Generate Export' — you'll receive an email when it's ready (usually 5–10 minutes)\n\nIs there a specific type of data you're trying to export, like contacts or activity logs?"}
        ]
    },
    # ... 1999 more examples
]

# Training setup — 2K examples, single A100 (~30 min)
from trl import SFTTrainer, SFTConfig
from peft import LoraConfig

sft_config = SFTConfig(
    num_train_epochs=5,          # more epochs for small dataset
    per_device_train_batch_size=4,
    gradient_accumulation_steps=4,
    learning_rate=2e-4,
    warmup_ratio=0.1,
    lr_scheduler_type="cosine",
    bf16=True,
    gradient_checkpointing=True,
    packing=True,
    max_seq_length=2048,
    output_dir="./support-bot-v1",
)

# Evaluation: format compliance rate (does response have all 3 sections?)
def eval_format_compliance(model, tokenizer, test_queries):
    compliant = 0
    for query in test_queries:
        response = generate(model, tokenizer, query)
        sections = ["acknowledge", "solution", "follow-up"]
        # Simplified check — use LLM-judge in practice
        if all(has_section(response, s) for s in sections):
            compliant += 1
    return compliant / len(test_queries)
```

**Result**: Format compliance from 70% (prompted 70B) to 97% (fine-tuned 8B). 8B model now outperforms prompted 70B at 1/8th the inference cost.

---

## 2. Code Generation Fine-Tuning

**Context**: An internal tooling team wants a model that generates code in their proprietary framework's API (not in the base model's training data) and follows internal coding standards.

**Strategy**: Two-stage: (1) Continued pre-training on API documentation + codebase, (2) SFT on (specification, correct_implementation) pairs.

```python
# Stage 1: Continued pre-training on internal API docs
# Format: raw text, not instruction format
internal_docs_dataset = load_from_disk("s3://bucket/internal-api-docs/")

# Very low LR for continued pre-training to avoid forgetting
continued_pt_config = SFTConfig(
    num_train_epochs=1,         # 1 epoch over corpus — just language modeling
    per_device_train_batch_size=4,
    gradient_accumulation_steps=8,
    learning_rate=5e-6,         # much lower than SFT
    lr_scheduler_type="cosine",
    packing=True,
    max_seq_length=4096,
    output_dir="./continued-pt",
)

# Stage 2: SFT on (spec, implementation) pairs
code_sft_examples = [
    {
        "messages": [
            {"role": "system", "content": "You are a Python developer using the AcmeFramework v3 API."},
            {"role": "user", "content": "Create a data pipeline that reads from AcmeSource, transforms with AcmeTransform, and writes to AcmeSink with error handling."},
            {"role": "assistant", "content": """```python
from acme.v3 import Pipeline, AcmeSource, AcmeTransform, AcmeSink
from acme.v3.errors import AcmeConnectionError, AcmeTransformError

def build_pipeline(config: dict) -> Pipeline:
    pipeline = Pipeline(name="data-pipeline", version="1.0")

    source = AcmeSource(
        connection_string=config["source_connection"],
        batch_size=config.get("batch_size", 1000),
    )

    transform = AcmeTransform(
        schema=config["schema"],
        on_error="log_and_skip",  # internal standard: never fail silently
    )

    sink = AcmeSink(
        destination=config["sink_destination"],
        write_mode="append",
    )

    pipeline.connect(source >> transform >> sink)
    return pipeline

if __name__ == "__main__":
    pipeline = build_pipeline(load_config("pipeline.yaml"))
    result = pipeline.run()
    print(f"Processed {result.rows_written:,} rows, {result.errors} errors")
```"""},
        ]
    }
]

# Evaluation: Pass@1 on internal test suite
def evaluate_code_generation(model, tokenizer, test_problems):
    pass_count = 0
    for problem in test_problems:
        generated = generate(model, tokenizer, problem["prompt"])
        code = extract_code_block(generated)
        try:
            exec_result = run_in_sandbox(code, problem["test_cases"])
            if exec_result["passed"]:
                pass_count += 1
        except Exception:
            pass  # treat execution errors as failures
    return pass_count / len(test_problems)
```

**Key insight**: Pass@1 on internal API tests is the only metric that matters. Perplexity and loss are poor proxies for code correctness. Always evaluate with execution.

---

## 3. Structured Extraction Fine-Tuning

**Context**: A legal tech company processes contracts and needs to extract specific fields (parties, effective date, termination clause, governing law) in a consistent JSON format. Base model gets the schema right ~85% of the time; they need > 99%.

```python
from pydantic import BaseModel
from typing import Optional

class ContractExtraction(BaseModel):
    parties: list[str]
    effective_date: Optional[str]
    termination_clause: Optional[str]
    governing_law: Optional[str]
    contract_value: Optional[str]

# Training data: 5,000 contracts with expert-annotated extractions
training_data = [
    {
        "messages": [
            {"role": "system", "content": "Extract contract metadata as JSON matching this schema exactly."},
            {"role": "user", "content": f"Extract from: {contract_text}"},
            {"role": "assistant", "content": json.dumps(extraction.model_dump(), indent=2)}
        ]
    }
    for contract_text, extraction in load_labeled_contracts()
]

# Fine-tune with temperature=0 generation target (deterministic extraction)
# Use guided decoding at inference time (vLLM + outlines) for schema compliance
```

**Post fine-tuning**: Schema compliance from 85% → 99.8%. The remaining 0.2% failures are genuinely ambiguous contracts — acceptable. Combine with guided decoding (`vllm` + `outlines` JSON schema enforcement) to guarantee format validity even for edge cases.

---

## 4. Multi-Task Fine-Tuning with LoRA Mixture

**Context**: A platform that serves 3 distinct document tasks — summarization, classification, and named entity recognition — from the same base model. Instead of 3 separate fine-tuned models, maintain one base + 3 LoRA adapters.

```python
from peft import PeftModel

base_model = AutoModelForCausalLM.from_pretrained("meta-llama/Meta-Llama-3.1-8B-Instruct")

# Load adapter at request time based on task
def get_model_for_task(task: str) -> PeftModel:
    adapter_map = {
        "summarize": "./adapters/summarize-lora",
        "classify": "./adapters/classify-lora",
        "ner": "./adapters/ner-lora",
    }
    # Hot-swappable with vLLM's LoRA support
    return PeftModel.from_pretrained(base_model, adapter_map[task])

# In vLLM production serving:
# Each request specifies which adapter via LoRARequest
# vLLM holds base model + up to 8 adapters in GPU memory simultaneously
# LRU eviction for the 9th+ adapter
```

**Training each adapter independently**: Train summarization adapter on summarization data (2K examples), classification adapter on classification data (10K examples), NER adapter on NER data (5K examples). Total training time: ~3× a single-task run. Storage: base model (16GB) + 3 adapters (3 × 40MB) = 16.12GB vs. 3 × full models = 48GB.

---

## 5. DPO Alignment for Safety and Quality

**Context**: An AI writing assistant generates high-quality content but occasionally produces verbose, tangential, or mildly inappropriate responses. After SFT, apply DPO to refine tone, conciseness, and safety boundaries.

```python
from trl import DPOTrainer, DPOConfig
from datasets import Dataset

# Preference data: same prompt, two responses
# chosen = more concise, on-topic, appropriate
# rejected = verbose, tangential, or borderline
dpo_dataset = Dataset.from_list([
    {
        "prompt": "Write a professional email declining a meeting invitation",
        "chosen": "Subject: Re: Meeting Invitation — [Date]\n\nHi [Name],\n\nThank you for the invitation. Unfortunately, I have a prior commitment and won't be able to attend. I hope the meeting goes well, and please feel free to share any key outcomes.\n\nBest regards,\n[Your Name]",
        "rejected": "Subject: Meeting Decline\n\nDear [Name],\n\nI hope this email finds you well! I wanted to reach out to let you know that unfortunately, due to a variety of scheduling conflicts and prior commitments that have arisen on my calendar for that particular date and time, I find myself unable to attend the meeting that you have so kindly invited me to. I want to assure you that this is no reflection on the importance of the meeting or your invitation, which I genuinely appreciate...",
    },
    # ... preference pairs on safety, conciseness, accuracy
])

dpo_config = DPOConfig(
    beta=0.1,
    learning_rate=5e-7,           # very low — subtle alignment
    per_device_train_batch_size=1,
    gradient_accumulation_steps=16,
    max_length=2048,
    max_prompt_length=512,
    num_train_epochs=1,           # DPO rarely needs more than 1 epoch
    bf16=True,
    output_dir="./dpo_aligned",
)

trainer = DPOTrainer(
    model=sft_model,
    ref_model=sft_model_copy,     # frozen reference
    args=dpo_config,
    train_dataset=dpo_dataset,
    tokenizer=tokenizer,
)
trainer.train()
```

**Data collection for DPO**: Generate 2 responses for each prompt (using temperature diversity: T=0.3 for "chosen" candidate, T=1.0 for "rejected"). Have annotators pick the better response, or use LLM-as-judge to auto-label at scale. Rule of thumb: 500–5,000 preference pairs is sufficient for DPO alignment.

---

## 6. GRPO for Mathematical Reasoning (DeepSeek-R1 Style)

**Context**: A math tutoring app wants a model that shows its reasoning step-by-step and arrives at the correct final answer. The key: correct final answers can be automatically verified.

```python
from trl import GRPOTrainer, GRPOConfig
import re

def extract_answer(text: str) -> str | None:
    """Extract final answer from <answer>...</answer> tags."""
    match = re.search(r"<answer>(.*?)</answer>", text, re.DOTALL)
    return match.group(1).strip() if match else None

def compute_reward(completions: list[str], ground_truths: list[str], **kwargs) -> list[float]:
    """Multi-component reward: format + correctness."""
    rewards = []
    for completion, gt in zip(completions, ground_truths):
        reward = 0.0

        # Format reward: must have <think> and <answer> blocks
        if "<think>" in completion and "</think>" in completion:
            reward += 0.2
        if "<answer>" in completion and "</answer>" in completion:
            reward += 0.2

        # Correctness reward
        predicted = extract_answer(completion)
        if predicted and predicted.strip() == gt.strip():
            reward += 1.0
        elif predicted and is_approximately_equal(predicted, gt):
            reward += 0.5

        rewards.append(reward)
    return rewards

grpo_config = GRPOConfig(
    learning_rate=5e-7,
    num_generations=8,      # generate 8 completions per prompt → group relative
    max_new_tokens=1024,
    temperature=0.9,
    beta=0.01,              # KL divergence penalty
    per_device_train_batch_size=1,
    gradient_accumulation_steps=16,
    num_train_epochs=2,
    output_dir="./grpo_math",
)

trainer = GRPOTrainer(
    model=sft_model,
    reward_funcs=[compute_reward],
    args=grpo_config,
    train_dataset=math_dataset,
    tokenizer=tokenizer,
)
trainer.train()
```

**Why GRPO works for math**: The verifiable reward signal (is the final answer correct?) is ground truth — no preference labeling bias. The group-relative reward (how does this completion compare to the other 7?) provides dense signal even when all 8 completions fail, since you learn from relative ordering.

---

## 7. Production Pipeline: Data → SFT → DPO → Eval → Deploy

End-to-end production workflow on AWS:

```
Data Curation (S3)
    ↓
Quality Filtering (GPT-4-as-judge, deduplication)
    ↓
SFT Training (SageMaker ml.p4d.24xlarge, LoRA r=32)
    ↓
SFT Evaluation (domain metrics, format compliance, held-out test set)
    ↓
DPO Preference Data Generation (vLLM sampling × 2, LLM-judge labeling)
    ↓
DPO Training (SageMaker ml.g5.8xlarge, β=0.1)
    ↓
Alignment Evaluation (safety tests, human spot-check, benchmark regression)
    ↓
Adapter Merge (merge LoRA into base, optional quantization to AWQ int4)
    ↓
A/B Testing (vLLM canary: 5% traffic, champion: 95%)
    ↓
Full Rollout
```

```python
# Automated evaluation gate before deployment
def evaluate_before_deploy(model_path: str, config: EvalConfig) -> bool:
    results = {}

    # 1. Regression on general capabilities (don't break base model behavior)
    results["mmlu"] = run_mmlu(model_path, num_shots=5)
    results["hellaswag"] = run_hellaswag(model_path)

    # 2. Domain-specific task metrics
    results["task_f1"] = run_domain_eval(model_path, config.test_set)

    # 3. Format compliance
    results["format_rate"] = run_format_check(model_path, config.format_test_cases)

    # 4. Safety (red team checks)
    results["safety_pass_rate"] = run_safety_eval(model_path, config.safety_probes)

    # Gate: all thresholds must pass
    thresholds = {
        "mmlu": 0.58,          # don't regress more than 2pp from base
        "task_f1": 0.87,       # domain target
        "format_rate": 0.98,   # near-perfect format compliance
        "safety_pass_rate": 0.999,
    }
    passed = all(results[k] >= thresholds[k] for k in thresholds)
    log_eval_results(results)
    return passed
```
