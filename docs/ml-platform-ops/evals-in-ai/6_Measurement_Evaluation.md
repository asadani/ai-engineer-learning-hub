# Measurement & Evaluation

## Evaluating the Evaluators (Meta-Evaluation)

The eval system itself must be evaluated. An LLM judge that is poorly calibrated, biased, or inconsistent produces false confidence. Meta-evaluation is the process of validating the eval pipeline.

---

## Inter-Annotator Agreement (IAA)

Before relying on human annotations as ground truth, measure how consistently humans agree with each other. Low agreement means the task definition is ambiguous, not that the model is bad.

```python
from sklearn.metrics import cohen_kappa_score
from scipy.stats import spearmanr
import numpy as np

def inter_annotator_agreement(
    annotator_a: list[int],
    annotator_b: list[int],
    scale: str = "ordinal",  # "nominal" or "ordinal"
) -> dict:
    """Compute agreement between two annotators."""
    if scale == "nominal":
        kappa = cohen_kappa_score(annotator_a, annotator_b)
        return {"cohen_kappa": kappa, "interpretation": interpret_kappa(kappa)}
    else:
        # Weighted kappa for ordinal scales (1-5 rating)
        kappa = cohen_kappa_score(annotator_a, annotator_b, weights="quadratic")
        spearman, _ = spearmanr(annotator_a, annotator_b)
        return {
            "weighted_kappa": kappa,
            "spearman_r": spearman,
            "interpretation": interpret_kappa(kappa),
            "mean_a": np.mean(annotator_a),
            "mean_b": np.mean(annotator_b),
        }

def interpret_kappa(k: float) -> str:
    if k < 0.20: return "slight"
    if k < 0.40: return "fair"
    if k < 0.60: return "moderate"
    if k < 0.80: return "substantial"
    return "almost perfect"

# Target: kappa >= 0.60 before accepting annotations
# If kappa < 0.40, revise annotation guidelines before proceeding
```

**IAA thresholds for eval work**:
- Factoid Q&A correctness: expect kappa 0.8–0.9 (fairly objective)
- Response helpfulness: expect kappa 0.5–0.7 (subjective, context-dependent)
- Toxicity detection: expect kappa 0.7–0.85 (guidelines matter hugely)
- Style/tone: expect kappa 0.4–0.6 (highly subjective)

---

## LLM Judge Calibration (Judge vs. Human Agreement)

Before deploying an LLM judge in production, validate it against human labels on a calibration set of 100–200 samples.

```python
from scipy.stats import pearsonr, spearmanr
import numpy as np

def calibrate_llm_judge(
    judge_fn,
    calibration_set: list[dict],  # [{question, response, human_score_1..n}]
) -> dict:
    """Measure judge-human agreement. Target: pearson_r >= 0.80."""
    judge_scores = []
    human_avg_scores = []

    for item in calibration_set:
        result = judge_fn(item["question"], item["response"])
        judge_scores.append(result["score"])
        human_avg = np.mean(item["human_scores"])  # average of multiple annotators
        human_avg_scores.append(human_avg)

    pearson_r, p_pearson = pearsonr(judge_scores, human_avg_scores)
    spearman_r, p_spearman = spearmanr(judge_scores, human_avg_scores)
    mae = np.mean(np.abs(np.array(judge_scores) - np.array(human_avg_scores)))

    # Bias analysis
    verbosity_bias = compute_verbosity_correlation(judge_scores, calibration_set)
    position_bias = compute_position_bias(judge_fn, calibration_set)

    return {
        "pearson_r": pearson_r,
        "spearman_r": spearman_r,
        "mae": mae,
        "calibrated": pearson_r >= 0.80,
        "verbosity_bias": verbosity_bias,  # correlation between score and response length
        "position_bias": position_bias,    # preference for first vs. second in pairwise
        "n_samples": len(calibration_set),
        "recommendation": "Use in production" if pearson_r >= 0.80 else f"Recalibrate (r={pearson_r:.2f})",
    }
```

**Common calibration failures and fixes**:

| Failure | Symptom | Fix |
|---------|---------|-----|
| Verbosity bias | Score correlates with response length (r > 0.3) | Add to prompt: "Do not be influenced by response length" |
| Leniency bias | Judge mean 4.2, human mean 3.1 | Add score anchors with concrete examples per level |
| Self-preference | Model X judged by Model X scores 20% higher | Use a third-party judge model |
| Position bias | First response wins 65% of pairwise | Swap positions, take average |

---

## Eval Dataset Quality Metrics

The golden dataset is the foundation of all evals. Measure its quality explicitly.

```python
def evaluate_dataset_quality(dataset: list[dict]) -> dict:
    """Assess quality of an eval dataset."""
    questions = [item["question"] for item in dataset]
    answers = [item.get("ground_truth", "") for item in dataset]

    # 1. Diversity: are questions semantically diverse?
    from sentence_transformers import SentenceTransformer
    import numpy as np
    model = SentenceTransformer("all-MiniLM-L6-v2")
    embeddings = model.encode(questions)
    # Average pairwise cosine distance — higher = more diverse
    from sklearn.metrics.pairwise import cosine_distances
    dist_matrix = cosine_distances(embeddings)
    avg_diversity = dist_matrix[np.triu_indices_from(dist_matrix, k=1)].mean()

    # 2. Coverage: distribution across intent categories
    from collections import Counter
    categories = Counter(item.get("category", "unknown") for item in dataset)
    category_entropy = compute_entropy(list(categories.values()))

    # 3. Difficulty: fraction of questions where baseline model fails
    # (run separately)

    # 4. Freshness: age of dataset
    import datetime
    dates = [item.get("created_at") for item in dataset if item.get("created_at")]
    if dates:
        oldest = min(dates)
        staleness_days = (datetime.date.today() - oldest).days
    else:
        staleness_days = None

    return {
        "size": len(dataset),
        "diversity_score": float(avg_diversity),  # target > 0.4
        "category_entropy": category_entropy,      # target > 2.0 nats
        "staleness_days": staleness_days,          # alert if > 180 days
        "category_distribution": dict(categories),
        "has_ground_truth": sum(1 for item in dataset if item.get("ground_truth")) / len(dataset),
    }
```

**Dataset maintenance signals**:
- Staleness > 180 days: re-sample from production logs
- Diversity score < 0.3: dataset has clusters of near-duplicate questions
- Single category > 40% of dataset: coverage gap in other categories

---

## Tracking Eval Results Over Time

Evals are only useful if tracked as a time series. A single point-in-time score is not actionable.

```python
import json
from pathlib import Path
from datetime import datetime

def record_eval_result(
    run_name: str,
    metrics: dict,
    metadata: dict,
    results_dir: str = "eval_results/",
) -> Path:
    """Persist eval results with version context for trend analysis."""
    import subprocess
    record = {
        "run_name": run_name,
        "timestamp": datetime.utcnow().isoformat(),
        "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip(),
        "git_branch": subprocess.check_output(["git", "branch", "--show-current"]).decode().strip(),
        "metrics": metrics,
        "metadata": {
            "model": metadata.get("model"),
            "prompt_version": metadata.get("prompt_version"),
            "retriever": metadata.get("retriever"),
            "eval_dataset_version": metadata.get("eval_dataset_version"),
            "n_samples": metadata.get("n_samples"),
        },
    }
    path = Path(results_dir) / f"{run_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(record, indent=2))
    return path

# Query for trend analysis
def compute_metric_trend(
    results_dir: str,
    metric: str,
    last_n_runs: int = 20,
) -> list[dict]:
    records = sorted(
        [json.loads(p.read_text()) for p in Path(results_dir).glob("*.json")],
        key=lambda r: r["timestamp"],
    )[-last_n_runs:]
    return [
        {"timestamp": r["timestamp"], "value": r["metrics"].get(metric), "git_sha": r["git_sha"]}
        for r in records if metric in r.get("metrics", {})
    ]
```

---

## Statistical Power Analysis for Eval Sample Sizing

A common mistake is running evals on too few samples and drawing conclusions from noise.

```python
from statsmodels.stats.power import TTestIndPower

def required_sample_size(
    effect_size: float = 0.3,    # minimum detectable difference (e.g., 0.03 on a 0-1 scale with std=0.1)
    alpha: float = 0.05,         # false positive rate
    power: float = 0.80,         # probability of detecting true effect
) -> int:
    """How many samples needed to detect a given effect size?"""
    analysis = TTestIndPower()
    n = analysis.solve_power(
        effect_size=effect_size,
        alpha=alpha,
        power=power,
        alternative="two-sided",
    )
    return int(np.ceil(n))

# Examples:
# Detect 3% change (effect_size = 0.03/0.10 = 0.3): n=177 per group
# Detect 1% change (effect_size = 0.01/0.10 = 0.1): n=1571 per group
# This is why 50-sample eval sets can't detect small regressions reliably
```

**Practical sample sizing guide**:
- CI / PR gate eval: 200–500 samples (detects 3–5% regression reliably)
- Weekly regression eval: 1000 samples (detects 1–2% regression)
- Quarterly major eval: 2000+ samples with human review on failure cases
