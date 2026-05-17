# Measurement & Evaluation

## The Two Phases of Fine-Tuning Evaluation

Fine-tuning evaluation has two distinct phases that require different metrics:
1. **During training**: Monitor convergence, detect overfitting, catch instability early
2. **Post-training**: Measure task performance, capability regression, and deployment readiness

---

## During-Training Monitoring

### Loss Curves

```python
# What healthy training looks like
# - Train loss: smooth, monotonically decreasing
# - Eval loss: decreases then plateaus (good) or starts increasing (overfit)
# - Gap between train/eval: small gap = good generalization

# Overfitting signatures:
#   - Eval loss increasing while train loss decreasing → reduce epochs or increase dropout
#   - Eval loss flat from step 1 → LR too high, model not learning
#   - Loss NaN/exploding → LR too high, check grad_norm

# Healthy grad_norm range for LoRA: 0.1 – 2.0
# If consistently > 5.0: lower LR or add gradient clipping (already default at 1.0 in Trainer)

import wandb

class LossMonitorCallback(TrainerCallback):
    def on_log(self, args, state, control, logs=None, **kwargs):
        if logs and "eval_loss" in logs and "loss" in logs:
            gap = logs["eval_loss"] - logs["loss"]
            if gap > 0.5:
                print(f"WARNING: Train/eval gap = {gap:.3f} — possible overfitting at step {state.global_step}")
            wandb.log({"train_eval_gap": gap, "step": state.global_step})
```

### Learning Rate Finder (optional but useful for new dataset/model combos)

```python
from torch.optim import AdamW
from torch.optim.lr_scheduler import OneCycleLR

# Quick LR range test: train for 100 steps, sweep LR from 1e-7 to 1e-3
# Plot loss vs LR — pick LR just before loss starts increasing
# Typically 10× below the steepest descent point

# In practice for LoRA: 1e-4 to 3e-4 works for most 7B models
# Trust the defaults before doing a full range test
```

---

## Post-Training Evaluation Framework

### 1. Task-Specific Metrics

The most important evaluation. Your fine-tuning target should have a measurable metric:

```python
from sklearn.metrics import f1_score, classification_report

def evaluate_classification_ft(model, tokenizer, test_examples, label_map):
    predictions, labels = [], []
    format_failures = 0

    for ex in test_examples:
        output = generate(model, tokenizer, ex["prompt"], max_tokens=10, temperature=0.0)
        parsed = parse_label(output, label_map)

        if parsed is None:
            format_failures += 1
            continue
        predictions.append(parsed)
        labels.append(ex["label"])

    return {
        "f1_macro": f1_score(labels, predictions, average="macro"),
        "f1_weighted": f1_score(labels, predictions, average="weighted"),
        "format_failure_rate": format_failures / len(test_examples),
        "classification_report": classification_report(labels, predictions),
        "n": len(test_examples),
    }


def evaluate_extraction_ft(model, tokenizer, test_examples):
    """Evaluate structured extraction: exact match + field-level accuracy."""
    field_correct = defaultdict(int)
    field_total = defaultdict(int)
    schema_valid = 0

    for ex in test_examples:
        output = generate(model, tokenizer, ex["prompt"], max_tokens=512, temperature=0.0)
        try:
            predicted = json.loads(output)
            schema_valid += 1
            for field, expected_value in ex["ground_truth"].items():
                field_total[field] += 1
                if normalize(predicted.get(field)) == normalize(expected_value):
                    field_correct[field] += 1
        except json.JSONDecodeError:
            pass

    return {
        "schema_validity_rate": schema_valid / len(test_examples),
        "field_accuracy": {f: field_correct[f] / field_total[f] for f in field_total},
        "overall_accuracy": sum(field_correct.values()) / sum(field_total.values()),
    }
```

### 2. Capability Regression Testing

Fine-tuning should not destroy general capabilities:

```python
# Run standard benchmarks before and after fine-tuning
# Report deltas, not absolutes

BENCHMARK_BASELINES = {
    "llama-3.1-8b-base": {
        "mmlu": 0.642,
        "hellaswag": 0.812,
        "arc_challenge": 0.591,
        "truthfulqa": 0.431,
    }
}

def run_regression_suite(model_path: str, base_model_id: str) -> dict:
    """Run lm-evaluation-harness benchmarks and compute deltas."""
    from lm_eval import simple_evaluate

    results = simple_evaluate(
        model="hf",
        model_args=f"pretrained={model_path}",
        tasks=["mmlu", "hellaswag", "arc_challenge", "truthfulqa_mc2"],
        num_fewshot=5,
        device="cuda",
    )

    baseline = BENCHMARK_BASELINES[base_model_id]
    deltas = {}
    for task, result in results["results"].items():
        score = result.get("acc_norm,none") or result.get("acc,none")
        deltas[task] = {
            "score": score,
            "delta": score - baseline.get(task, 0),
            "regression": score < baseline.get(task, 0) - 0.02,  # > 2pp drop = regression
        }

    return deltas

# Run with lm-eval-harness CLI
# lm_eval --model hf --model_args pretrained=./fine_tuned_model \
#   --tasks mmlu,hellaswag --num_fewshot 5 --output_path ./eval_results.json
```

### 3. Format and Safety Evaluation

```python
def evaluate_format_compliance(model, tokenizer, format_test_cases):
    """Measures how reliably the model outputs the required format."""
    import json, re

    results = []
    for case in format_test_cases:
        output = generate(model, tokenizer, case["prompt"], max_tokens=512, temperature=0.0)
        result = {
            "prompt": case["prompt"],
            "output": output,
            "checks": {},
        }
        for check_name, check_fn in case["checks"].items():
            result["checks"][check_name] = check_fn(output)
        results.append(result)

    compliance_by_check = defaultdict(list)
    for r in results:
        for check_name, passed in r["checks"].items():
            compliance_by_check[check_name].append(passed)

    return {
        check: sum(vals) / len(vals)
        for check, vals in compliance_by_check.items()
    }


def run_safety_red_team(model, tokenizer, red_team_prompts: list[str]) -> dict:
    """Test model on curated adversarial/safety prompts."""
    refusal_count = 0
    for prompt in red_team_prompts:
        output = generate(model, tokenizer, prompt, max_tokens=200, temperature=0.0)
        # LLM-as-judge: did the model refuse appropriately?
        is_refusal = judge_is_refusal(output)
        if is_refusal:
            refusal_count += 1

    return {
        "refusal_rate": refusal_count / len(red_team_prompts),
        "n_tested": len(red_team_prompts),
    }
```

---

## Evaluating DPO Alignment Quality

DPO alignment is harder to evaluate than SFT — the goal is subtle preference alignment:

```python
def evaluate_dpo_alignment(
    model, ref_model, tokenizer, preference_test_set
) -> dict:
    """
    Measure how often the DPO-aligned model prefers chosen over rejected.
    Expected outcome: aligned model should assign higher probability to chosen.
    """
    model_prefers_chosen = 0
    reward_margins = []

    for example in preference_test_set:
        prompt = example["prompt"]
        chosen = example["chosen"]
        rejected = example["rejected"]

        # Compute log probabilities
        def get_log_prob(text):
            inputs = tokenizer(prompt + text, return_tensors="pt")
            with torch.no_grad():
                outputs = model(**inputs, labels=inputs["input_ids"])
            return -outputs.loss.item()

        policy_chosen_logp = get_log_prob(chosen)
        policy_rejected_logp = get_log_prob(rejected)
        ref_chosen_logp = ref_model_log_prob(ref_model, prompt, chosen)
        ref_rejected_logp = ref_model_log_prob(ref_model, prompt, rejected)

        # DPO implicit reward
        chosen_reward = policy_chosen_logp - ref_chosen_logp
        rejected_reward = policy_rejected_logp - ref_rejected_logp
        margin = chosen_reward - rejected_reward

        reward_margins.append(margin)
        if margin > 0:
            model_prefers_chosen += 1

    return {
        "preference_accuracy": model_prefers_chosen / len(preference_test_set),
        "mean_reward_margin": np.mean(reward_margins),
        "reward_margin_p25": np.percentile(reward_margins, 25),
    }
```

A well-aligned DPO model should show `preference_accuracy > 0.75` (prefers chosen over rejected in 75%+ of cases) and positive mean reward margin.

---

## Human Evaluation Protocol

Automated metrics tell you only part of the story. For high-stakes deployments, run human evaluation:

```python
# Side-by-side evaluation form
evaluation_protocol = {
    "evaluators": 3,       # minimum 3 per example for reliability
    "examples_per_eval": 50,  # 50 examples × 3 evaluators = 150 judgments
    "dimensions": [
        {
            "name": "Instruction following",
            "question": "Did the response fully address what was asked?",
            "scale": "1-5",
        },
        {
            "name": "Factual accuracy",
            "question": "Are all factual claims in the response accurate?",
            "scale": "1-5",
        },
        {
            "name": "Conciseness",
            "question": "Was the response appropriately concise (not too verbose)?",
            "scale": "1-5",
        },
        {
            "name": "Overall preference",
            "question": "Which response do you prefer overall? [Model A / Model B / Tie]",
            "scale": "A/B/Tie",
        }
    ],
    "inter_rater_metric": "Krippendorff's alpha",
    "minimum_agreement": 0.6,  # below this, re-evaluate the rubric or re-train evaluators
}

# Tooling: LabelStudio, Argilla, Scale AI, or a custom internal UI
```

---

## Evaluation at Each Stage of the Pipeline

| Stage | Primary Metric | Secondary Metrics | Pass Threshold |
|-------|---------------|------------------|----------------|
| **Data curation** | LLM-judge quality score | Dedup rate, length distribution | Avg quality > 3.5/5 |
| **SFT (during training)** | Eval loss | Train/eval gap, grad_norm | Eval loss decreasing, gap < 0.3 |
| **SFT (post)** | Domain task F1 / accuracy | Format compliance rate | Task metric > target |
| **Capability regression** | MMLU delta | HellaSwag, ARC delta | < -2pp delta per benchmark |
| **DPO (during)** | Reward margin | Preference accuracy | Margin positive, trending up |
| **DPO (post)** | Human preference rate | Safety red team pass rate | Human pref > 65% vs SFT |
| **Pre-deploy** | Full eval suite | Latency SLO, cost/token | All thresholds pass |
| **A/B test (production)** | Session success rate | User satisfaction | Non-inferior at 95% CI |
