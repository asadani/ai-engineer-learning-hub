# Key Technical Concepts

## Pipeline Architecture

RAG consists of two distinct pipelines with very different operational characteristics:

```
╔══════════════════════════════════════════════════════╗
║  INDEXING PIPELINE  (offline / async)                ║
║                                                       ║
║  Documents → [Loader] → [Chunker] → [Embedder]       ║
║                                          ↓            ║
║                                    [Vector Store]     ║
╚══════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════╗
║  QUERY PIPELINE  (online / latency-sensitive)         ║
║                                                       ║
║  Query → [Query Transform] → [Embed] → [ANN Search]  ║
║              ↓                              ↓         ║
║         [BM25 Search] ──── [Fusion/RRF] ───┘         ║
║                                  ↓                    ║
║                            [Reranker]                  ║
║                                  ↓                    ║
║                        [Context Assembly]              ║
║                                  ↓                    ║
║                          [LLM Generation]              ║
╚══════════════════════════════════════════════════════╝
```

---

## Chunking Strategies

Chunking is where most production RAG systems lose quality. The wrong chunking strategy is unteachable by a better model downstream.

### Fixed-Size (Token/Character)
- 512 or 1024 tokens with 10-20% overlap
- Fast, deterministic, works as baseline
- Problem: cuts across sentence/paragraph boundaries, breaking semantic coherence

### Recursive Character Splitting
- Tries `\n\n` → `\n` → `. ` → ` ` → character-level in sequence
- Better coherence than pure fixed-size; default in LangChain/LlamaIndex

### Semantic Chunking
- Embed each sentence, compute cosine distance between adjacent sentences, split where similarity drops
- Produces semantically coherent chunks of variable size
- ~2-3x slower to index; chunk sizes vary widely (harder to optimize embedding batching)

### Document-Aware / Structural
- Parse document structure (headers, sections, tables, code blocks) and chunk at structural boundaries
- Best for PDFs, HTML, Markdown, code repositories
- Requires document-type-specific parsers (Unstructured.io, LlamaParse)

### Hierarchical (Parent-Child)
- Index small chunks (128 tokens) for retrieval precision; return parent chunk (512 tokens) for context
- Solves the precision vs. context-size tradeoff directly
- LlamaIndex calls this "Small-to-Big Retrieval"

**Rule of thumb**: Chunk size should reflect the granularity of questions. FAQ-style Q&A → small chunks. Synthesis over long documents → larger chunks with summaries.

---

## Embedding Models

Embeddings map text to dense vectors in a high-dimensional semantic space (typically 768-3072 dims). Model choice drives retrieval quality more than any other single variable.

| Model | Dims | Max Tokens | Notes |
|-------|------|------------|-------|
| `text-embedding-3-large` (OpenAI) | 3072 (reducible) | 8192 | Top MTEB scores; supports dimension reduction via Matryoshka |
| `embed-english-v3.0` (Cohere) | 1024 | 512 | Excellent for retrieval; supports `input_type` (query vs. doc) |
| `amazon.titan-embed-text-v2:0` (AWS) | 1024 | 8192 | Native Bedrock; supports dimension reduction (256/512/1024) |
| `voyage-3` (Voyage AI) | 1024 | 32000 | State-of-art on MTEB; good for long docs |
| `GTE-Qwen2-7B-instruct` | 3584 | 131072 | Open-source SOTA; 7B params, expensive but strong |
| `bge-m3` (BAAI) | 1024 | 8192 | Strong multilingual; also does sparse (SPLADE) retrieval |

**Critical detail**: Cohere and Voyage require separate embeddings for queries vs. documents (`input_type="search_query"` vs `"search_document"`). Conflating them silently degrades retrieval. OpenAI's models don't distinguish, which is one reason they're popular for quick integrations.

---

## Vector Search & ANN Algorithms

Vector stores execute Approximate Nearest Neighbor (ANN) search — exact k-NN is O(n·d) and untenable at scale.

### HNSW (Hierarchical Navigable Small World)
- Graph-based: builds a multi-layer proximity graph at index time
- Search: enter at top layer, greedily navigate to approximate neighbors
- Parameters: `M` (graph connections per node, typically 16-64), `ef_construction` (index build quality), `ef_search` (query quality)
- **p99 latency**: 1-10ms for 1M vectors at ef=100
- **Recall tradeoff**: higher `ef_search` = better recall, more latency
- Used by: pgvector (HNSW option), Qdrant, Weaviate, Pinecone (internally)

### IVF (Inverted File Index) + PQ (Product Quantization)
- Cluster vectors into `nlist` Voronoi cells at index time; search only `nprobe` cells at query time
- PQ compresses vectors (e.g., 768 float32 → 96 uint8) — 8x storage reduction
- Used by: FAISS, pgvector (IVFFlat), Vespa
- Tradeoff: lower memory, slightly lower recall vs. HNSW; good for >100M vectors

### Hybrid Search (Dense + Sparse)
- BM25/TF-IDF for keyword relevance + embedding for semantic relevance
- Combine scores via Reciprocal Rank Fusion (RRF): `score = 1/(k + rank_dense) + 1/(k + rank_sparse)`, k=60 typical
- Consistently outperforms pure dense on queries with exact-match terminology, product codes, IDs
- Support: OpenSearch, Weaviate, Qdrant, pgvector (via `ts_rank`), Elasticsearch

---

## Re-ranking

Re-ranking is a second-pass scoring stage that uses a more expensive cross-encoder to re-score the top-K candidates from ANN retrieval.

**Bi-encoder** (used at retrieval): encode query and doc independently → fast, scalable, but lower precision
**Cross-encoder** (reranker): concatenate `[query, doc]` and score jointly → slower, but much higher precision

### Production rerankers (2025-2026)
- **Cohere Rerank 3.5**: managed API; strong multilingual; ~100ms added latency; SOTA on BEIR
- **BGE-Reranker-v2-m3**: open-source; deploy on SageMaker or ECS; same latency profile if self-hosted on GPU
- **Jina Reranker v2**: compact (278M), deployable on CPU; good for cost-sensitive deployments
- **FlashRank**: pure CPU, no GPU needed; good for < 10 docs reranking in latency-critical paths

**Typical setup**: retrieve top-20, rerank to top-5. Overkill to retrieve top-100 unless recall is measured to be low.

---

## Query Transformations

Raw user queries are often poor retrieval queries. Transform them before embedding:

- **HyDE (Hypothetical Document Embeddings)**: LLM generates a hypothetical answer, embed that instead of the question. Works because "answer-like" text is closer in embedding space to relevant docs than questions are.
- **Query decomposition**: multi-hop questions split into sub-queries, retrieved independently, answers fused
- **Step-back prompting**: abstract the query to a higher-level concept before retrieval
- **Multi-query**: generate N paraphrases of the query, retrieve for each, deduplicate

HyDE adds an LLM call latency (~200-500ms) but often lifts recall by 5-15% on complex queries. Worth the cost in async/batch pipelines; borderline for real-time.

---

## Context Window Management

Retrieval surfaces N chunks; not all should go into the prompt.

- **Lost in the middle**: Liu et al. (2023) showed LLMs recall information best at the beginning and end of context, not the middle. Place highest-scored chunks at edges.
- **Token budget allocation**: with a 128K context LLM, budget roughly: 20% system prompt, 50% retrieved context, 15% conversation history, 15% output headroom
- **Contextual compression**: before stuffing, pass each retrieved chunk through an LLM to extract only the sentences relevant to the query (LlamaIndex `ContextualCompressionRetriever`)
- **Metadata filtering**: pre-filter by document type, date, department before vector search — reduces search space and improves precision without sacrificing recall
