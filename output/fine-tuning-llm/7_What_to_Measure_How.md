# What to Measure & How

## Universal Fine-Tuning Metrics Checklist

### Training Health Metrics

| Metric | Type | Target | Collection Method |
|--------|------|--------|-------------------|
| **Train loss** | Gauge | Monotonically decreasing | `trainer.log_metrics()` / W&B |
| **Eval loss** | Gauge | Decreasing then plateau | `trainer.evaluate()` every N steps |
| **Train/eval gap** | Gauge | < 0.3 absolute | Computed from above |
| **Grad norm** | Gauge | 0.1 – 2.0 for LoRA | `trainer.log_metrics()` |
| **Learning rate** | Gauge | Follows cosine schedule | `trainer.log_metrics()` |
| **GPU memory (MB)** | Gauge | < 90% of available | `nvidia-smi` / W&B system metrics |
| **Tokens/sec (throughput)** | Gauge | Maximize | Computed: tokens_in_batch / step_time |
| **Step time (ms)** | Histogram | < 1s per step (typical) | W&B / Trainer timing |

### Post-Training Quality Metrics

| Metric | Type | Typical Target | Collection Method |
|--------|------|---------------|-------------------|
| **Task F1 / Accuracy** | Gauge | Domain-specific | Custom eval script on hold-out set |
| **Format compliance rate** | Gauge | > 98% | Schema validator on generated outputs |
| **Format failure rate** | Gauge | < 2% | Inverse of above |
| **Perplexity (domain)** | Gauge | < base model (lower = better) | `evaluate_perplexity()` on domain text |
| **BERTScore F1** | Gauge | > 0.88 | `bert_score` library |
| **ROUGE-L** | Gauge | Benchmark-dependent | `evaluate.load("rouge")` |
| **Pass@1** | Gauge | > 0.70 (code tasks) | Code execution in sandbox |

### Capability Regression Metrics

| Benchmark | When to Run | Acceptable Delta | Tool |
|-----------|-------------|-----------------|------|
| **MMLU** | After every training run | < −2pp | lm-evaluation-harness |
| **HellaSwag** | After every training run | < −2pp | lm-evaluation-harness |
| **ARC Challenge** | After every training run | < −2pp | lm-evaluation-harness |
| **TruthfulQA** | Pre-deploy gate | < −2pp | lm-evaluation-harness |
| **GSM8K** | Pre-deploy (if math matters) | < −3pp | lm-evaluation-harness |
| **HumanEval** | Pre-deploy (if code matters) | < −3pp | bigcode/bigcode-evaluation-harness |

### Alignment Quality Metrics (DPO/RLHF)

| Metric | Type | Target | Collection Method |
|--------|------|--------|-------------------|
| **Preference accuracy** | Gauge | > 0.75 | DPO reward margin on held-out preference pairs |
| **Mean reward margin** | Gauge | > 0 | `policy_logp(chosen) − ref_logp(chosen) > rejected` |
| **KL divergence vs. reference** | Gauge | < 3.0 nats | Compute during DPO training |
| **Refusal accuracy** | Gauge | > 99% | Red team test suite |
| **False positive refusal rate** | Gauge | < 5% | Benign queries that should NOT be refused |
| **Human preference rate (A/B)** | Gauge | > 60% vs. SFT | Human evaluation (50–100 examples) |

---

## Data Quality Metrics

Before training, measure dataset quality:

```python
import json
from collections import Counter
from anthropic import Anthropic

def audit_training_data(dataset_path: str) -> dict:
    """Automated data quality audit before fine-tuning."""
    examples = [json.loads(l) for l in open(dataset_path)]

    # 1. Length distribution
    response_lengths = [
        len(ex["messages"][-1]["content"].split())
        for ex in examples
    ]

    # 2. Deduplication check (exact match on last response)
    responses = [ex["messages"][-1]["content"] for ex in examples]
    duplicate_rate = 1 - len(set(responses)) / len(responses)

    # 3. LLM-judge quality scoring (sample 10%)
    client = Anthropic()
    sample_idx = random.sample(range(len(examples)), len(examples) // 10)
    quality_scores = []
    for i in sample_idx:
        ex = examples[i]
        prompt_text = ex["messages"][-2]["content"]
        response_text = ex["messages"][-1]["content"]

        judge_response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=100,
            messages=[{
                "role": "user",
                "content": f"""Rate this (instruction, response) pair on a scale of 1-5.
Instruction: {prompt_text[:500]}
Response: {response_text[:500]}
Output only a single integer (1-5) and nothing else."""
            }]
        )
        try:
            score = int(judge_response.content[0].text.strip())
            quality_scores.append(score)
        except ValueError:
            pass

    return {
        "n_examples": len(examples),
        "duplicate_rate": duplicate_rate,
        "response_length_p50": int(np.percentile(response_lengths, 50)),
        "response_length_p99": int(np.percentile(response_lengths, 99)),
        "quality_score_mean": np.mean(quality_scores),
        "quality_score_p25": np.percentile(quality_scores, 25),
        "low_quality_rate": sum(1 for s in quality_scores if s <= 2) / len(quality_scores),
    }
```

| Metric | Target | Alert Threshold |
|--------|--------|----------------|
| **Exact duplicate rate** | < 1% | > 5% |
| **Near-duplicate rate (MinHash)** | < 5% | > 15% |
| **LLM-judge quality mean (1-5)** | > 3.5 | < 3.0 |
| **Low-quality examples (score ≤ 2)** | < 5% | > 15% |
| **Response length p50** | 100–500 words | < 20 or > 2000 |
| **Response length CV** | < 1.5 | > 2.5 (highly variable) |

---

## Training Configuration Tracking

Every training run should log:

```python
# Minimum run metadata for reproducibility
run_metadata = {
    # Data
    "dataset_path": "s3://bucket/data/training-v3.jsonl",
    "dataset_sha256": hashlib.sha256(open(dataset_path, "rb").read()).hexdigest(),
    "n_examples_train": len(train_dataset),
    "n_examples_eval": len(eval_dataset),

    # Model
    "base_model": "meta-llama/Meta-Llama-3.1-8B-Instruct",
    "base_model_sha": model.config._commit_hash,

    # LoRA config
    "lora_r": 16,
    "lora_alpha": 32,
    "target_modules": ["q_proj", "v_proj", "k_proj", "o_proj"],
    "lora_dropout": 0.05,

    # Training config
    "learning_rate": 2e-4,
    "lr_scheduler": "cosine",
    "warmup_ratio": 0.05,
    "effective_batch_size": 64,  # per_device × accumulation × num_gpus
    "num_epochs": 3,
    "max_seq_length": 4096,
    "packing": True,

    # Hardware
    "num_gpus": 2,
    "gpu_type": "A100-80GB",
    "training_framework": "TRL 0.11.4 + PEFT 0.13.0 + Unsloth 2025.3",
}
```

---

## Evaluation Automation Script

```bash
#!/bin/bash
# evaluate_checkpoint.sh — run full eval suite on a checkpoint

MODEL_PATH=$1
BASE_MODEL="meta-llama/Meta-Llama-3.1-8B-Instruct"
OUTPUT_DIR="./eval_results/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUTPUT_DIR"

echo "=== Domain Task Evaluation ==="
python eval_task.py \
  --model_path "$MODEL_PATH" \
  --test_set data/test.jsonl \
  --output "$OUTPUT_DIR/task_eval.json"

echo "=== Capability Regression (lm-evaluation-harness) ==="
lm_eval \
  --model hf \
  --model_args "pretrained=$MODEL_PATH,dtype=bfloat16" \
  --tasks mmlu,hellaswag,arc_challenge \
  --num_fewshot 5 \
  --output_path "$OUTPUT_DIR/benchmarks.json" \
  --device cuda

echo "=== Format Compliance ==="
python eval_format.py \
  --model_path "$MODEL_PATH" \
  --test_cases data/format_tests.jsonl \
  --output "$OUTPUT_DIR/format_eval.json"

echo "=== Safety Red Team ==="
python eval_safety.py \
  --model_path "$MODEL_PATH" \
  --probes data/safety_probes.jsonl \
  --output "$OUTPUT_DIR/safety_eval.json"

echo "=== Generating Report ==="
python generate_eval_report.py \
  --eval_dir "$OUTPUT_DIR" \
  --base_model "$BASE_MODEL" \
  --output "$OUTPUT_DIR/report.md"

echo "Evaluation complete. Results in $OUTPUT_DIR"
```

---

## Domain-Specific Evaluation Targets

| Domain | Primary Metric | Minimum Target | Notes |
|--------|---------------|----------------|-------|
| **Customer support** | Format compliance rate | > 98% | Must follow template |
| **Code generation** | Pass@1 on test suite | > 70% | Execute in sandboxed env |
| **Legal extraction** | Field-level accuracy | > 95% | Per-field evaluation, not overall |
| **Medical QA** | Recall on clinical questions | > 95% | Precision secondary |
| **Classification** | F1 macro (per class) | > 85% macro | Check minority class F1 |
| **Summarization** | BERTScore F1 + SummaC | > 0.88 + > 0.75 | Both required |
| **SQL generation** | Execution accuracy | > 80% | Run queries, check output |
| **Math/reasoning** | Pass@1 on problem set | > 75% | Verifiable final answer |
| **RAG answer** | Faithfulness | > 90% | No hallucination on source |
