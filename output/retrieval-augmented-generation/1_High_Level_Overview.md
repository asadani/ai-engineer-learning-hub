# High-Level Overview

## What It Is

Retrieval-Augmented Generation (RAG) is an inference-time architecture that grounds LLM responses in external knowledge by retrieving relevant documents before generation. Rather than relying solely on parametric memory baked into model weights, RAG injects retrieved context into the prompt, making the model's response verifiable, updatable, and domain-specific — without retraining.

Origin: Lewis et al. (Facebook AI Research, 2020) — "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks" — first formalized RAG as a trainable end-to-end architecture combining a DPR retriever with a seq2seq generator. In production, the paradigm has evolved significantly: retriever and generator are typically not jointly trained, and the retriever is usually an ANN (approximate nearest neighbor) search over a pre-built vector index.

## The Core Problem It Solves

LLMs have three structural limitations that RAG directly addresses:

1. **Knowledge cutoff**: Weights freeze at training time. RAG decouples knowledge from model weights — swap the index, not the model.
2. **Hallucination under knowledge gaps**: A model without relevant context will confabulate. With retrieved context, the model can answer "I don't know" grounded in the retrieved set.
3. **Domain specificity at scale**: Fine-tuning a 70B model on enterprise documents is expensive, slow, and brittle when docs change. RAG indexes update in minutes; fine-tunes take hours to days.

## Where It Sits in the GenAI Stack (2025-2026)

RAG is not a monolith — it spans two distinct pipelines:

```
INDEXING (offline)
  Raw docs → Chunking → Embedding → Vector Store
                                         ↓
QUERY (online)
  User query → Embed query → ANN Search → Rerank → Prompt Assembly → LLM → Response
```

In production enterprise GenAI deployments as of 2026, RAG dominates over pure fine-tuning for knowledge tasks. The rationale: knowledge changes frequently, governance requires traceability (what was retrieved?), and the cost delta between fine-tuning and index maintenance favors RAG for most CRUD-like knowledge workloads.

## Key Insight

The power of RAG is not in retrieval accuracy per se — it's in the **precision-recall tradeoff at the context window boundary**. A 128K context window doesn't mean you stuff 128K of documents; LLMs suffer "lost in the middle" degradation for evidence buried mid-context. The real engineering challenge is retrieving the 3-10 most relevant chunks with high precision, not retrieving 100 chunks with high recall.

## Variants (as of 2026)

| Variant | Key Idea | When to Use |
|---------|----------|-------------|
| Naive RAG | Fixed chunks → embedding → ANN → generate | Baseline; low-complexity corpora |
| Advanced RAG | Query rewriting, re-ranking, hybrid search | Production default |
| Modular RAG | Swap-in components (retrievers, rerankers, generators) | Research / multi-domain |
| Self-RAG | LLM decides whether to retrieve and critiques output | High-quality but slow |
| GraphRAG (Microsoft, 2024) | Knowledge graph extraction + community summaries | Multi-hop reasoning over large corpora |
| Agentic RAG | Retrieval as a tool call in an agent loop | Complex multi-step Q&A |
| Corrective RAG (CRAG) | Evaluates retrieval quality, falls back to web search | When index staleness is a risk |

## Production Reality

- Most production RAG systems underperform benchmarks because chunking strategy and index quality are treated as afterthoughts. The retriever quality, not the LLM, is typically the bottleneck.
- Hybrid search (dense + sparse BM25) consistently outperforms pure embedding search on out-of-distribution queries, especially for domain-specific terminology.
- Reranking is the single highest-ROI addition to a baseline RAG system. Adding a cross-encoder reranker (Cohere Rerank, BGE-Reranker-v2) typically lifts answer quality by 10-25% relative with a p99 latency cost of 50-150ms.
