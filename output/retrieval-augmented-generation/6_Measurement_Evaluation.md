# Measurement & Evaluation

## The RAG Evaluation Stack

RAG evaluation is layered: component-level metrics (retrieval quality, generation quality) and end-to-end metrics (answer correctness, user satisfaction). Conflating these is a common mistake — a perfectly faithful answer to a wrongly retrieved context is still a wrong answer.

```
┌─────────────────────────────────────────────────────┐
│            END-TO-END EVALUATION                     │
│  answer_correctness, user_satisfaction, task_success │
├─────────────────────────────────────────────────────┤
│          GENERATION QUALITY                          │
│  faithfulness, answer_relevance, groundedness        │
├─────────────────────────────────────────────────────┤
│          RETRIEVAL QUALITY                           │
│  context_precision, context_recall, hit_rate, MRR   │
└─────────────────────────────────────────────────────┘
```

---

## RAGAS Metrics (Primary Framework)

RAGAS (Retrieval-Augmented Generation Assessment, Es et al., 2023) is the standard framework for automated RAG evaluation using LLM-as-judge. Each metric is independently interpretable.

### Faithfulness
- **What**: Does the generated answer contain only claims that are supported by the retrieved context?
- **How computed**: LLM extracts atomic claims from answer → for each claim, LLM checks if it can be inferred from context → score = supported_claims / total_claims
- **Range**: 0–1; production target > 0.85
- **Failure mode**: Low faithfulness = hallucination. Most common cause: retrieved context doesn't contain the answer, so LLM makes up a plausible-sounding answer.

### Answer Relevance
- **What**: Does the answer address the question asked? (Not a retrieval metric — measures generation quality)
- **How computed**: LLM generates N candidate questions from the answer → cosine similarity between generated questions and original question → mean similarity
- **Range**: 0–1; production target > 0.80
- **Failure mode**: Model answers a related but different question. Common with broad/ambiguous queries.

### Context Precision
- **What**: Of the retrieved chunks, what fraction were actually relevant to answering the question?
- **How computed**: LLM judges each chunk: is it useful for answering this question? → relevant_chunks / total_retrieved_chunks
- **Range**: 0–1; production target > 0.70
- **Failure mode**: Low precision = noisy context retrieved, diluting the useful signal. Fix: tighten chunk retrieval, improve embedding model, add metadata filtering.

### Context Recall
- **What**: Of the relevant information needed to answer the question, what fraction was retrieved?
- **How computed**: Requires ground-truth answer. LLM checks: for each sentence in ground truth, can it be attributed to retrieved context?
- **Range**: 0–1; production target > 0.80
- **Failure mode**: Low recall = the retriever is missing relevant documents. Fix: hybrid search, query expansion, increase top-K.

### Answer Correctness (requires ground truth)
- **What**: How correct is the answer compared to the ground truth answer?
- **How computed**: Combination of factual similarity (F1 over extracted facts) + semantic similarity (embedding cosine)
- **Range**: 0–1; most demanding metric; requires a labeled dataset

---

## Retrieval-Level Metrics (IR Classics)

These don't require LLM calls and are fast to compute over a labeled dataset.

| Metric | Formula | What It Measures |
|--------|---------|-----------------|
| **Hit Rate @ K** | Fraction of queries where at least one relevant doc is in top-K | Whether the relevant doc is retrieved at all |
| **MRR @ K** | Mean of 1/rank of first relevant doc | How high the first relevant doc ranks |
| **NDCG @ K** | Normalized Discounted Cumulative Gain | Quality of full top-K ranking |
| **Precision @ K** | Relevant docs in top-K / K | Fraction of retrieved docs that are relevant |
| **Recall @ K** | Relevant docs in top-K / total relevant docs | Coverage of relevant docs |

**Practical use**: Hit Rate @ 5 and MRR @ 5 are the most actionable metrics for RAG because they reflect whether the right doc is available to the generator at all.

---

## Benchmarks & Leaderboards

### BEIR (Benchmarking IR)
- Standard heterogeneous IR benchmark: 18 datasets across 9 domains (biomedical, financial, Wikipedia, argument retrieval, etc.)
- Used to compare embedding models and retrieval strategies
- Strong BEIR performance correlates with production retrieval quality on diverse corpora
- Reference scores (nDCG@10): BM25 ~0.43, `text-embedding-3-large` ~0.55, `voyage-3` ~0.58

### MTEB (Massive Text Embedding Benchmark)
- 56 tasks across 8 categories; the most comprehensive embedding model leaderboard
- `Retrieval` subtask on MTEB is most relevant for RAG
- 2026 SOTA: `GTE-Qwen2-7B-instruct`, `voyage-3`, `text-embedding-3-large` all clustered at top

### RGB (RAG Benchmark, Chen et al.)
- 4 RAG-specific tasks: noise robustness, negative rejection, information integration, counterfactual robustness
- Tests whether the LLM correctly uses or ignores retrieved context
- Useful for measuring generator quality independently of retrieval

### RAGAS Benchmark Datasets
- `fiqa` (financial Q&A), `hotpotqa` (multi-hop reasoning), `nq` (natural questions) are standard evaluation sets shipped with RAGAS library

---

## Evaluation Pipeline Architecture

```python
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevance, context_precision, context_recall
from datasets import Dataset

# Build evaluation dataset
eval_data = {
    "question": questions,          # user queries
    "answer": generated_answers,    # RAG pipeline outputs
    "contexts": retrieved_chunks,   # List[List[str]] per query
    "ground_truth": reference_answers  # required for context_recall, answer_correctness
}

dataset = Dataset.from_dict(eval_data)
results = evaluate(dataset, metrics=[
    faithfulness, answer_relevance, context_precision, context_recall
])
print(results.to_pandas())
```

**Cost note**: RAGAS uses LLM-as-judge internally. At 4 metrics × N test questions, budget ~4N LLM calls. At $0.003/call with claude-haiku, 1000-question eval set costs ~$12. Automate this in CI/CD gated on PRs that change chunking/embedding/retrieval logic.

---

## A/B Testing Retrieval Strategies

In production, don't evaluate RAG in isolation — run shadow mode A/B:

1. Route 10% of production traffic to new retrieval strategy
2. Log retrieved contexts + answers for both variants
3. Sample 200 query-answer pairs per variant
4. Run RAGAS evaluation + human spot-check
5. Promote if faithfulness, context precision, and answer relevance all improve or hold steady

**Shadow logging minimum**: question, retrieved chunk IDs + scores, final answer, latency, user feedback signal (thumbs up/down if available).
