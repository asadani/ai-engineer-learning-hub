# Tradeoffs & Comparisons

## RAG vs. Fine-Tuning vs. Long-Context LLMs

This is the most common architectural decision in enterprise GenAI, and the answer is almost always "it depends" — but with concrete decision criteria.

| Dimension | RAG | Fine-Tuning | Long-Context (128K+) |
|-----------|-----|------------|----------------------|
| **Knowledge update latency** | Minutes (reindex) | Hours-days (retrain) | N/A (context at query time) |
| **Max knowledge size** | Practically unlimited (index scales) | ~100s of docs effectively | ~200-400 pages per query |
| **Retrieval precision required** | Yes (garbage in, garbage out) | N/A | No (stuff everything) |
| **Traceability / citation** | Native (returned chunks) | Opaque | Possible (highlight spans) |
| **Cost per query** | Low LLM tokens (< 4K context typical) | Same inference cost | High (128K tokens billed) |
| **Training data required** | No | Yes (high-quality Q&A pairs) | No |
| **Best for** | Frequently updated knowledge, large corpora | Tone/style/format adaptation, task specialization | Full-document analysis, small doc sets |
| **Fails at** | Low-recall retrieval, deeply implicit knowledge | Out-of-distribution, unseen facts | Cost at scale, many-doc comparison |

**Production reality (2026)**: Most enterprise deployments use RAG + light fine-tuning. Fine-tuning for behavior (tone, format, task structure), RAG for knowledge. Treating them as competing approaches is a false dichotomy.

---

## Dense Retrieval vs. Sparse (BM25) vs. Hybrid

| Dimension | Dense (Embeddings) | Sparse (BM25/TF-IDF) | Hybrid (RRF) |
|-----------|-------------------|----------------------|--------------|
| **Semantic similarity** | ✅ Strong | ❌ Keyword-only | ✅ Both |
| **Exact term match** | ❌ Poor (out-of-vocab) | ✅ Strong | ✅ Both |
| **New/rare terms** | ❌ Degrades | ✅ Handles naturally | ✅ Both |
| **Multilingual** | ✅ With right model | ❌ Language-specific | ✅ |
| **Index build time** | High (embedding calls) | Low | Medium |
| **Query latency** | 1-10ms (ANN) | 1-5ms | 2-15ms |
| **Infrastructure** | Vector DB required | Inverted index (ES/OS) | Both or unified store |

**Recommendation**: Use hybrid by default. The marginal infrastructure cost is low (OpenSearch, Qdrant, Weaviate all support it natively), and hybrid consistently wins on real-world queries where users mix semantic intent with specific terms, product names, or IDs.

---

## Chunking Strategy Tradeoffs

| Strategy | Retrieval Precision | Context Coherence | Index Cost | Complexity |
|----------|--------------------|--------------------|------------|------------|
| Fixed-size (512 tok) | Medium | Low | Low | Trivial |
| Recursive splitting | Medium | Medium | Low | Low |
| Semantic chunking | High | High | High (1 embed/sentence) | Medium |
| Document-structural | High | Highest | Medium | High (parser needed) |
| Hierarchical (parent-child) | High | High | 2x (two indexes) | Medium |

**Gotcha**: Larger chunks hurt precision (irrelevant context dilutes relevant); smaller chunks hurt coherence (answer span crosses chunk boundary). The sweet spot for most corpora: 256-512 tokens with 10% overlap for retrieval chunks, 1024-2048 for returned context (parent-child pattern).

---

## Reranker: Worth the Latency?

| Scenario | Add Reranker? | Reasoning |
|----------|---------------|-----------|
| p99 latency SLO < 500ms | Marginal; measure first | Cross-encoder adds 50-200ms |
| Corpus with domain jargon | Yes, strongly | BM25 + reranker handles terminology better than embeddings alone |
| Diverse document types | Yes | Reranker normalizes score across document types |
| Small corpus (< 10K docs) | No | ANN precision is already high; reranker adds cost without benefit |
| Async / batch pipeline | Always | Latency is irrelevant; reranker is free precision gain |

---

## When NOT to Use RAG

1. **Real-time data requirements**: If the answer requires data updated in the last 60 seconds (stock prices, live inventory), RAG with a static index fails. Use function calling / tool use against a live API instead.

2. **Highly implicit knowledge**: Knowledge that requires multi-hop reasoning across many documents (e.g., "compare the risk profiles of all 500 contracts") doesn't retrieve well into a prompt window. GraphRAG or agentic multi-step retrieval is more appropriate.

3. **Pure style/behavior tasks**: Summarization format, tone matching, code style enforcement → fine-tune, not RAG.

4. **Sub-10ms latency requirements**: End-to-end RAG (embed query + ANN search + LLM generation) floors at ~200ms. If you need sub-10ms, you need a different architecture entirely.

5. **< 100 documents total**: At this scale, stuff everything into a long-context LLM. The retrieval complexity isn't worth it when you can use `gpt-4o` with 128K context to process 300 pages per query.

---

## Embedding Model Tradeoffs

| Dimension | OpenAI `text-embedding-3-large` | Cohere `embed-v3` | Self-hosted (GTE-Qwen2-7B) |
|-----------|--------------------------------|-------------------|---------------------------|
| **Quality (MTEB)** | Top-tier | Top-tier | Top-tier (SOTA open-source) |
| **Latency (batch 32)** | ~100ms API | ~80ms API | ~20ms on A10G GPU |
| **Cost** | $0.13/1M tokens | $0.10/1M tokens | Infrastructure cost only |
| **Data residency** | Data leaves your VPC | Data leaves your VPC | Fully private |
| **Max tokens** | 8192 | 512 | 131072 |
| **Multilingual** | Good | Excellent | Excellent |

**Decision driver**: Regulated industries (healthcare, finance, government) that can't send data to third-party APIs → self-hosted. Everyone else → OpenAI or Cohere for simplicity.

---

## Vector DB Comparison (Production at Scale)

| Dimension | Pinecone Serverless | Qdrant (self-hosted) | pgvector (Aurora) | OpenSearch |
|-----------|--------------------|-----------------------|-------------------|------------|
| **Ops burden** | None | Medium | Low (managed RDS) | Medium-High |
| **Query latency (p99)** | 80-150ms | 5-20ms | 10-50ms | 20-80ms |
| **Filtered search** | Post-filter (degrades) | During-filter (strong) | Post-filter | Post-filter |
| **Hybrid search** | Yes (sparse-dense) | Yes | With workaround | Yes (native) |
| **Scale limit** | Practically unlimited | Depends on cluster | ~10M vectors practical | ~50M vectors |
| **Cost at 10M vectors** | ~$70/mo serverless | EC2 cost (~$150-300/mo) | RDS cost (~$200/mo) | ~$300-500/mo |
| **AWS-native** | No | No | Yes (Aurora) | Yes |

**Key insight**: Qdrant's payload-indexed filtering during graph traversal is a significant advantage for use cases with many metadata dimensions (date, department, user tier, language). Pinecone and pgvector apply filters post-retrieval, which degrades recall when filters are selective.
