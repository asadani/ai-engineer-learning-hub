# Products & Tools

## RAG & Pipeline Evaluation Frameworks

### RAGAS
- **What**: Open-source Python library for automated RAG evaluation using LLM-as-judge
- **Metrics**: `faithfulness`, `answer_relevance`, `context_precision`, `context_recall`, `answer_correctness`, `context_entity_recall`
- **How it works**: Each metric decomposes the evaluation into atomic LLM calls — faithfulness extracts claims then checks each against context
- **Integration**: Works with LangChain, LlamaIndex, raw data via `Dataset`; exports to W&B, LangSmith
- **2025 update**: RAGAS v0.2 introduced `testset_generator` (synthetic Q&A generation from docs) and `EvaluationDataset` class for structured eval pipelines
- **Cost**: ~4–8 LLM calls per query-response pair; at Claude Haiku pricing, ~$0.001/eval; 1000-query eval costs ~$1
- **Limitation**: LLM-as-judge variance; scores can fluctuate 3–5% between runs; run twice and average

```python
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevance, context_precision
from datasets import Dataset

data = Dataset.from_dict({
    "question": questions,
    "answer": answers,
    "contexts": contexts,         # List[List[str]]
    "ground_truth": references,   # optional, for correctness metrics
})
results = evaluate(data, metrics=[faithfulness, answer_relevance, context_precision])
df = results.to_pandas()
print(df[["question", "faithfulness", "answer_relevance"]].describe())
```

### DeepEval
- **What**: pytest-style LLM testing framework; run evals as unit tests in CI/CD
- **Metrics**: `GEval`, `FaithfulnessMetric`, `AnswerRelevancyMetric`, `HallucinationMetric`, `ToxicityMetric`, `BiasMetric`, `SummarizationMetric`
- **Key feature**: `@pytest.mark.parametrize` style test cases with `assert_test()` — integrates directly into CI pipelines
- **Integration**: Confident AI dashboard for result tracking; works with any LLM framework

```python
from deepeval import assert_test
from deepeval.metrics import GEval, FaithfulnessMetric
from deepeval.test_case import LLMTestCase, LLMTestCaseParams

def test_rag_faithfulness():
    test_case = LLMTestCase(
        input="What is the refund policy?",
        actual_output=rag_pipeline.query("What is the refund policy?"),
        retrieval_context=["Refunds are processed within 30 days of purchase..."],
    )
    metric = FaithfulnessMetric(threshold=0.8, model="gpt-4o")
    assert_test(test_case, [metric])
```

### TruLens (TruEra)
- **What**: Open-source eval + observability for LLM apps; real-time feedback instrumentation
- **Key concept**: "RAG Triad" — groundedness, context relevance, answer relevance — three metrics evaluated per query
- **Integration**: Snowflake native (TruLens is part of Snowflake's ML platform); works with LangChain, LlamaIndex, custom code
- **Strength**: Real-time leaderboard comparing different pipeline configurations side-by-side; good for A/B testing retrieval strategies

---

## Observability & Tracing Platforms

### LangSmith (LangChain)
- **What**: Tracing, evaluation, and dataset management platform for LLM apps
- **Key features**: Automatic trace capture for LangChain/LangGraph; dataset management with version history; human annotation workflows; evaluation runs against datasets
- **Eval workflow**: Log traces → create dataset from interesting traces → run evaluators (RAGAS, custom) → track scores over time → alert on regression
- **2025**: Added online evaluation — automatic scoring of production traces on configurable sampling rate
- **When to use**: Teams already using LangChain/LangGraph; excellent tracing UX; tight LangChain integration

### Weights & Biases Weave
- **What**: W&B's LLM-focused tracing and evaluation tool (separate from classic W&B)
- **Key features**: Automatic LLM call tracing, evaluation pipelines, leaderboard comparison, integration with W&B experiments
- **Strength**: Teams already using W&B for ML experiments — unified experiment tracking from training through inference eval
- **When to use**: ML-heavy teams with existing W&B investment; good for model comparison workflows

### Braintrust
- **What**: Commercial eval platform built specifically for AI products; founded by former OpenAI researchers
- **Key features**: Dataset management, experiment comparison, LLM-as-judge, human annotation, CI/CD integration via SDK and GitHub Actions
- **Differentiation**: Strong opinion on eval-as-code; every eval run is a versioned experiment; excellent UI for debugging individual failures
- **When to use**: Teams wanting a dedicated eval platform without the complexity of building one; good for product teams

### Promptfoo
- **What**: Open-source CLI and library for prompt testing and evaluation
- **Key features**: YAML-based test definitions, LLM-as-judge, red teaming, provider comparison (run same prompts against multiple models), CI/CD native
- **Strength**: Model comparison workflows — test the same prompt against Claude, GPT-4o, Gemini, and compare results side-by-side
- **When to use**: Evaluating prompt changes, model selection, red teaming before deployment

```yaml
# promptfoo.yaml
providers:
  - id: anthropic:claude-opus-4-5
  - id: openai:gpt-4o
  - id: bedrock:amazon.titan-text-premier-v1:0

prompts:
  - "Summarize this document: {{document}}"

tests:
  - vars:
      document: "{{file('test_docs/contract.txt')}}"
    assert:
      - type: llm-rubric
        value: "The summary captures the key parties, dates, and obligations"
      - type: contains
        value: "effective date"
      - type: not-contains
        value: "ERROR"
```

---

## Academic Benchmarks

### MMLU (Massive Multitask Language Understanding)
- 57 subjects from elementary to professional level (law, medicine, STEM, humanities)
- 5-shot multiple choice; measures breadth of world knowledge
- Score: 5-shot accuracy; GPT-4: 86.4%, Claude Opus: 86.8%, Llama-3-70B: 82.0%
- **Limitation**: Near-saturated at top models; contamination concerns (training data overlap)

### GPQA (Graduate-Level Google-Proof Q&A)
- 448 expert-level multiple choice questions (biology, chemistry, physics) that Google search can't answer
- Diamond set: 198 questions where domain experts achieve ~65% accuracy
- Frontier models (2026): Claude 3.5 Sonnet ~59%, GPT-4o ~53%
- **Value**: Much harder to contaminate; good signal for genuine reasoning

### HumanEval & MBPP (Code)
- **HumanEval**: 164 Python programming problems; measures functional correctness via unit tests (pass@k metric)
- **MBPP**: 374 crowd-sourced Python programming problems
- **LiveCodeBench** (2025): Dynamic benchmark with new problems monthly to prevent contamination

### HELM (Holistic Evaluation of Language Models)
- Stanford's multi-metric, multi-scenario benchmark; evaluates accuracy, calibration, robustness, fairness, efficiency simultaneously
- Most comprehensive but slowest to run; useful for model selection, not iteration

### MT-Bench & LMSYS Chatbot Arena
- **MT-Bench**: 80 multi-turn questions judged by GPT-4; measures instruction following and conversational ability
- **Chatbot Arena**: Human preference via pairwise comparison (Elo rating); most reliable signal for general capability ranking as of 2026

---

## AWS Native Tooling

### Amazon Bedrock Model Evaluation
- **What**: Managed eval service on Bedrock; run automatic and human evaluations against Bedrock models
- **Automatic eval tasks**: Summarization, Q&A, text classification, text generation — uses built-in metrics (ROUGE, BERTScore, accuracy)
- **Human eval**: Routes a sample to human reviewers via SageMaker Ground Truth
- **Limitation**: Limited to Bedrock-hosted models; doesn't support custom eval metrics yet
- **When to use**: AWS-native teams comparing Bedrock foundation models before selection

### SageMaker Clarify
- **What**: Bias detection, explainability, and model monitoring for SageMaker models
- **Relevance to LLM eval**: Measures text toxicity, stereotype detection, factual knowledge (via factual consistency checks)
- **Limitation**: More mature for traditional ML than LLMs; LLM-specific features added incrementally

---

## Specialized Eval Tools

| Tool | Specialization | Notes |
|------|---------------|-------|
| **EleutherAI lm-evaluation-harness** | Academic benchmarks (MMLU, HellaSwag, etc.) | Standard for open-source model evaluation |
| **OpenAI Evals** | Custom eval framework; open-source | Good for structured evals; requires JSONL datasets |
| **AgentBench** | Agent task evaluation across multiple environments | Multi-task agent benchmarking |
| **MT-Bench** | Multi-turn conversation quality | LLM-as-judge with GPT-4 |
| **HELMET** (2025) | Long-context evaluation | Tests 128K+ context tasks |
| **SimpleQA** (OpenAI) | Factual accuracy | Short, verifiable facts; high precision ground truth |
| **inspect_ai** (UK AISI) | Safety and capability evals | Used by UK AI Safety Institute |
