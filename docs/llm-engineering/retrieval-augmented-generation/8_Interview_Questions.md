# Interview Questions & Scenarios

## Tier 1: Senior Engineer (L5)

### Q1: Explain the difference between a bi-encoder and a cross-encoder, and where each is used in a RAG pipeline.

**Model Answer**: A bi-encoder independently encodes the query and each document into vectors, then computes similarity via dot product or cosine — this is O(1) at query time once vectors are pre-computed, making it suitable for ANN retrieval over millions of documents. A cross-encoder jointly encodes the query and document as a single sequence, producing a scalar relevance score — higher quality but O(n) at query time, so it can only score a small candidate set. In a production RAG pipeline, the bi-encoder retrieves the top-20 candidates from the index, and the cross-encoder reranks them to top-5 before context assembly.

---

### Q2: You're getting low faithfulness scores (< 0.6) in RAGAS evaluation. What are your first three debugging steps?

**Model Answer**: First, check whether the retrieved context actually contains the answer — low faithfulness often means the retriever is returning tangentially related chunks and the LLM is hallucinating to fill the gap. Second, examine context token density: if you're retrieving 20 chunks with a total of 15K tokens but the answer is in one specific sentence, dilution is causing the model to lose the signal. Third, check if the LLM's generation prompt has explicit grounding instructions ("Answer only based on the provided context; if the context doesn't contain the answer, say 'I don't know'") — models without this instruction will confabulate freely.

---

### Q3: What is Reciprocal Rank Fusion (RRF) and why is it preferred over score-based fusion for combining dense and sparse retrieval results?

**Model Answer**: RRF computes a combined score as the sum of `1/(k + rank)` for each retrieval system's ranking, where k is typically 60. It's preferred over raw score fusion because embedding similarity scores and BM25 scores live in incomparable ranges — a cosine similarity of 0.85 and a BM25 score of 12.3 cannot be directly added. RRF only uses rank position, which is invariant to the underlying score scale. It also naturally handles the case where one system has no result for a query (infinite rank → 0 contribution) without requiring score normalization.

---

### Q4: What chunking strategy would you use for a corpus of legal contracts, and why?

**Model Answer**: Hierarchical chunking with structure-aware splitting. Legal contracts have clause/section boundaries that are semantically meaningful — splitting mid-clause destroys the legal meaning. I'd parse the document structure (section headers, numbered clauses) using a tool like Unstructured.io or LlamaParse, create small chunks at the clause level (200-300 tokens) for high-precision retrieval, and store the parent section (1000-2000 tokens) as context to return to the LLM. Additionally, I'd embed metadata — party names, governing law, effective date, clause type (indemnification, limitation of liability, etc.) — and use metadata filtering before vector search to scope retrieval to relevant document types.

---

### Q5: How does HyDE (Hypothetical Document Embeddings) work, and when would you use it?

**Model Answer**: HyDE generates a hypothetical answer to the user's question using the LLM, then embeds that hypothetical answer rather than the original question. The intuition is that the embedding space learned from documents maps question-like text far from document-like text, so searching with a document-like hypothesis closes the distribution gap. It works well when user queries are short and telegraphic ("quantum computing advantages") but the corpus is dense prose. The tradeoff is an added LLM call latency (200-500ms) and the risk that a confidently wrong hypothesis retrieves confidently wrong documents. I'd use it in async pipelines, complex factual queries, and batch evaluation — not in real-time conversational flows.

---

### Q6: What is the "lost in the middle" problem, and how do you mitigate it?

**Model Answer**: Liu et al. (2023) showed empirically that LLMs reliably recall information placed at the beginning and end of a long context, but recall degrades significantly for information in the middle — regardless of context window size. In a RAG context, stuffing 20 chunks in rank order means the most important chunk (rank 3-7) is exactly where recall is weakest. Mitigation: (1) place the highest-scored chunks at the beginning and end of the context block, not in rank order; (2) limit retrieved chunks to 3-7 rather than 20, trading recall for precision; (3) use contextual compression to distill each chunk to only the sentences relevant to the query before assembling the context.

---

## Tier 2: Staff Engineer (L6)

### Q7: Design a multi-tenant RAG system where each tenant has strict data isolation. What are the failure modes if isolation is implemented incorrectly?

**Model Answer**: Correct multi-tenant RAG isolation requires enforcement at the vector store level, not just at application layer. Options: (1) namespace-per-tenant in Pinecone or Weaviate — each tenant's vectors live in a separate namespace, and all queries are scoped to that namespace; (2) metadata field `tenant_id` as a mandatory pre-filter before ANN search (supported by Qdrant's payload-indexed filtering during graph traversal). Application-layer filtering (retrieve globally, then post-filter by tenant) is a critical mistake: it exposes one tenant's data to the LLM context of another during the retrieval stage, even if the final answer is filtered. Failure modes include cross-tenant data leakage in the context window (security incident), degraded retrieval quality (tenant A's vectors polluting tenant B's results), and incorrect billing/attribution.

---

### Q8: Your RAG system's context_recall score is 0.92 but faithfulness is 0.61. What does this tell you, and what would you do?

**Model Answer**: High recall means the retriever is successfully surfacing the documents that contain the answer — the information is available in the context. Low faithfulness means the LLM is not staying grounded in that context — it's generating claims not supported by what was retrieved. This disconnect points to a generation problem, not a retrieval problem. I'd investigate in this order: check if the LLM generation prompt has strong grounding instructions; check if the context window is large enough that the model is "reading past" the relevant chunks (lost in the middle); check whether the relevant information requires multi-hop reasoning across multiple chunks that the LLM is synthesizing incorrectly; and consider switching to a model with better instruction-following (Claude over GPT-3.5 for grounding-heavy tasks). Fine-tuning on grounded answers is a last resort if the above don't resolve it.

---

### Q9: How would you build an index update pipeline that keeps a RAG system's index fresh within 15 minutes of document changes?

**Model Answer**: Event-driven incremental indexing. For each document store (S3, Confluence, SharePoint): set up change event hooks (S3 EventBridge, Confluence webhooks, SharePoint webhooks) → route to an SQS queue → Lambda or ECS task consumer that: (1) fetches the changed document, (2) re-chunks it, (3) re-embeds the new chunks, (4) deletes the old chunk vectors for that document from the vector store (by document ID metadata filter), (5) upserts the new chunk vectors. The deletion step is critical and often missed — without it, stale chunks accumulate. For high-volume corpora, use DynamoDB to track `doc_id → chunk_ids` mapping to enable efficient targeted deletion. Monitor `index_freshness_lag_seconds` as an SLO.

---

### Q10: Explain GraphRAG (Microsoft, 2024) and when it outperforms standard vector RAG.

**Model Answer**: GraphRAG extracts a knowledge graph (entities and relationships) from the corpus during indexing, then organizes entities into communities using the Leiden algorithm, and generates community summaries at multiple granularities. At query time, it searches over community summaries (for global, synthesized questions) as well as local entity neighborhoods (for specific factual questions). Standard vector RAG struggles with "global" queries that require synthesizing information across many documents (e.g., "what are the main themes across all customer complaints?") because no single chunk contains that synthesis. GraphRAG handles these by pre-computing community-level summaries. The tradeoffs: indexing costs 10-100x more (LLM calls for entity extraction and summarization), and the pipeline is significantly more complex. Use GraphRAG when queries are inherently multi-hop, comparative, or require corpus-wide synthesis; use standard RAG for point lookups and factual Q&A.

---

### Q11: How do you handle the evaluation of a RAG system when you don't have a labeled ground-truth dataset?

**Model Answer**: Two approaches. First, synthetic dataset generation: use the LLM to generate question-answer pairs from the corpus itself (`QuestionGenerator` in RAGAS or LlamaIndex), then use those synthetic pairs as the evaluation set. The coverage of the synthetic set matters — ensure questions are generated from chunks across the full corpus, not just the first 10 documents. Second, reference-free metrics: RAGAS faithfulness and answer relevance don't require ground truth — faithfulness checks whether the answer is grounded in retrieved context, and answer relevance checks whether the answer addresses the question. These can be computed on production traffic without labels. The third option is implicit signals: user thumbs down rate, escalation rate (query forwarded to human), session abandonment after the answer — these are weak but real-world feedback signals. Build toward labeled data by having human reviewers annotate a random sample of 100-200 queries/week.

---

### Q12: Your embedding model was just upgraded from `text-embedding-ada-002` to `text-embedding-3-large`. What is your migration plan?

**Model Answer**: You cannot mix vectors from different models in the same index — the embedding spaces are incompatible, and cosine similarity across models is meaningless. Full re-index is required. Plan: (1) provision a new vector store index (or namespace) for the new model; (2) run the full re-embedding pipeline on the new index while keeping the old index live and serving traffic; (3) run parallel shadow evaluation: for a sample of production queries, retrieve from both old and new indexes, run RAGAS on both, compare metrics; (4) once new index metrics are equal or better, shift 10% → 50% → 100% of traffic via feature flag; (5) decommission old index after 1 week of stable operation. Total re-embedding cost for 1M chunks at 512 tokens each: `1M × 512 / 1000 × $0.13/1K tokens ≈ $66` for `text-embedding-3-large`. Scheduling: at 100 requests/second throughput to the embeddings API, 1M chunks takes ~3 hours.

---

## Tier 3: Principal Engineer (L7+)

### Q13: A senior engineer proposes using a single 128K context LLM to avoid building RAG infrastructure. How do you evaluate this proposal?

**Model Answer**: It's a legitimate approach for specific problem shapes, and I'd evaluate it along five dimensions. First, corpus size: 128K tokens handles ~200-400 dense pages — enough for small, stable document sets but not enterprise corpora in the millions of documents. Second, query type: if questions require holistic synthesis across the full corpus, long-context wins; if questions are point lookups ("what does Section 4.2 say"), retrieval precision wins. Third, cost at scale: `gpt-4o` at $5/1M input tokens, 100K token context, 100 queries/hour = $50/hour just in input costs — vs. a RAG system where context averages 3K tokens at $0.15/hour. Fourth, freshness: long-context doesn't solve the knowledge cutoff problem — you still need to inject updated documents. Fifth, latency: 100K token prefill is 2-5 seconds TTFB; a well-tuned RAG pipeline with 3K context runs in under 1 second. My recommendation: use long-context for small, infrequently updated corpora with synthesis queries; RAG for everything else at production scale. They're not mutually exclusive — a RAG system can retrieve the top-3 most relevant documents and stuff them fully into context, getting both.

---

### Q14: Design the architecture for a RAG system that must serve 10,000 queries per second with < 500ms p99 end-to-end latency. Walk through every bottleneck.

**Model Answer**: At 10K QPS, each stage needs horizontal scaling. Breaking down the latency budget: target 500ms total — allocation: 20ms embedding, 15ms ANN search, 50ms reranker (can skip for latency), 400ms LLM generation, 15ms overhead.

**Embedding (20ms target)**: Self-host a small embedding model (Cohere embed-english-v3 or bge-m3) on GPU fleet behind a load balancer. At 10K QPS, batch size 1 on an A10G GPU handles ~2K requests/second — need 5+ GPU replicas. Alternatively, distill to a smaller model (100-200M params) that fits on CPU — viable if quality tradeoff is acceptable.

**Vector search (15ms target)**: HNSW with ef_search=50 on a purpose-built vector DB cluster. At 10K QPS, Qdrant or Weaviate on a 16-core instance handles ~2-3K QPS — need 4-5 nodes behind a load balancer. Sharding strategy: shard by document type or date range to keep each node's index small and search fast.

**LLM (400ms target)**: This is the hardest constraint. At 10K QPS with 3K token context + 300 token output on `claude-sonnet`, you need massive API throughput or self-hosted inference. Options: (1) Bedrock on-demand with auto-scaling; (2) provisioned throughput on Bedrock for guaranteed capacity; (3) self-hosted Llama-3-8B-Instruct on vLLM with continuous batching on A100s — at 10K QPS, need ~50 A100s for this model. (4) Caching layer: semantic query cache (embed query, search cache index) to serve repeat/similar queries without LLM call — typical cache hit rate 20-40% in production, effectively reducing LLM load.

**Operational concerns**: Circuit breakers on each stage (especially LLM), graceful degradation (return cached answer or "please try again" if LLM latency spikes), separate SLO tracking per stage to identify bottlenecks in real-time.

---

### Q15: How would you set up a continuous evaluation system that automatically catches retrieval quality regressions before they reach production?

**Model Answer**: A regression gate in CI/CD. The system has three layers. First, an offline golden dataset: a curated set of 500-1000 question → (expected_answer, expected_chunk_ids) pairs maintained as a git-versioned YAML file. Cover all query intents and edge cases; update when new document types are added. Second, an evaluation pipeline triggered on any PR that modifies chunking logic, embedding model, retrieval parameters, or reranker: (a) build the index on a staging environment using the PR's changes; (b) run the golden dataset through the full RAG pipeline; (c) compute context_precision, context_recall, hit_rate@5, faithfulness; (d) compare against a baseline (last release's metrics stored in a metrics store like MLflow or DynamoDB). Third, a gating policy: block merge if any metric regresses by >3% relative. The subtle gotcha is that evaluation metrics have variance (LLM-as-judge is non-deterministic) — run evaluation twice and average, and set the regression threshold above the noise floor. Additionally, run a weekly shadow evaluation on 1% of production traffic (log queries + pipeline outputs without user data) to catch distribution shift that the golden dataset misses.

---

### Q16: Describe three architectural decisions that distinguish a principal-level RAG design from a senior-level one.

**Model Answer**: First, **separation of indexing and serving concerns**: senior engineers often build a monolithic pipeline where the same service indexes and serves queries. At principal level, these are separate services with separate scaling properties — indexing is bursty and CPU/GPU-intensive; serving is latency-sensitive and needs predictable capacity. Decoupling them with an async queue (SQS) and separate compute allows independent scaling and failure isolation.

Second, **metadata schema design as a first-class concern**: a senior engineer picks whatever metadata seems useful at the time; a principal engineer designs the metadata schema upfront as a core architectural decision, because it determines what filtering is possible forever (you cannot retroactively add a metadata field without re-indexing). The schema should cover: document lineage (source system, doc ID, version), temporal properties (created_at, updated_at), access control (owner, ACL groups), and domain-specific dimensions (document type, language, topic) — all indexed in the vector store for pre-filter use.

Third, **evaluation-driven iteration**: senior engineers optimize RAG by intuition ("let me try a larger chunk size"). Principal engineers define metrics baselines first, instrument the pipeline to emit those metrics from day one, and make every parameter decision (chunk size, top-K, embedding model) as an A/B test measured against those baselines. The pipeline configuration (chunk size, overlap, model, top-K) should be data-driven and version-controlled, not hardcoded.
