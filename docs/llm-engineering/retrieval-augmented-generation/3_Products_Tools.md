# Products & Tools

## Orchestration Frameworks

### LangChain
- **Positioning**: General-purpose LLM application framework; de facto standard for prototyping
- **RAG primitives**: `DocumentLoader`, `TextSplitter`, `VectorStore`, `Retriever`, `RetrievalQA`, `RAGChain`
- **Strengths**: Huge ecosystem, integrations with 100+ vector stores and LLMs, LangGraph for agentic RAG
- **Weaknesses**: Abstraction leaks at scale; debugging multi-step chains is painful; callback system is convoluted; version instability historically (v0.1 → v0.2 → v0.3 broke APIs repeatedly)
- **When to use**: Rapid prototyping, teams already in the ecosystem, when LangSmith tracing is valuable

### LlamaIndex
- **Positioning**: Purpose-built for RAG and data-augmented LLM workflows
- **RAG primitives**: `SimpleDirectoryReader`, `SentenceSplitter`, `VectorStoreIndex`, `QueryEngine`, `RetrieverQueryEngine`, `SubQuestionQueryEngine`
- **Strengths**: More principled RAG abstractions than LangChain, better support for hierarchical retrieval, structured data query, multi-modal
- **Weaknesses**: Smaller ecosystem than LangChain; agentic capabilities catching up to LangGraph
- **When to use**: Production RAG pipelines where correctness and retrieval quality matter more than feature breadth

### Haystack (deepset)
- **Positioning**: Production-focused NLP/RAG framework with strong document processing pipeline
- **Strengths**: Well-engineered pipeline DAG, strong BM25/hybrid search support, good for enterprise document processing
- **When to use**: Teams doing heavy document ingestion with complex preprocessing (PDFs, tables, OCR)

### DSPy (Stanford)
- **Positioning**: Programmatic LLM pipeline optimization — compiles prompts and retrieval strategies rather than hand-crafting them
- **Unique value**: Optimizes the full RAG pipeline (retrieval + prompting) against a labeled dataset; replaces manual prompt engineering
- **When to use**: When you have labeled Q&A pairs and want to systematically optimize retrieval + generation together

---

## Vector Databases

### Pinecone
- **Type**: Managed, serverless vector database (SaaS only)
- **Architecture**: Proprietary; pods or serverless (recommended 2024+)
- **Strengths**: Zero ops, auto-scaling, fast startup, native hybrid search (sparse-dense)
- **Limits (2026)**: Serverless ~100ms p99 first query (cold); pod-based ~10ms; metadata filtering can be slow at scale
- **Cost**: ~$0.033/1M read units; serverless pricing is query-volume-based, not storage-based
- **When to use**: Teams that don't want to operate infrastructure; early-stage products

### Weaviate
- **Type**: Open-source + managed cloud (Weaviate Cloud Services)
- **Architecture**: HNSW + optional BM25 natively; multi-tenant with tenant isolation
- **Strengths**: Native hybrid search, GraphQL API, multi-modal (vectors + data objects in one schema), strong multi-tenancy
- **When to use**: Multi-tenant SaaS applications, hybrid search requirements, teams comfortable self-hosting

### Qdrant
- **Type**: Open-source + managed cloud
- **Architecture**: HNSW; written in Rust; strong payload (metadata) filtering during ANN search
- **Strengths**: Best-in-class filtered search (filter applied during HNSW graph traversal, not post-filter), quantization support, sparse vectors natively, excellent Rust performance
- **When to use**: Production deployments with complex metadata filtering; performance-critical self-hosted setups

### pgvector (PostgreSQL extension)
- **Type**: Open-source PostgreSQL extension
- **Architecture**: IVFFlat and HNSW index types; lives in Postgres
- **Strengths**: Zero new infrastructure if already on Postgres/Aurora; joins with relational data; ACID transactions; familiar ops model
- **Weaknesses**: Not purpose-built for ANN; at >10M vectors, pure pgvector lags dedicated stores; recall degrades without careful tuning
- **When to use**: Teams already on RDS/Aurora Postgres who need vector search without a new service; < 5M vectors; when joining vector results with relational filters is common

### Amazon OpenSearch (k-NN plugin)
- **Type**: Managed (Amazon OpenSearch Service) or self-hosted
- **Architecture**: HNSW (via nmslib / Lucene) + BM25 natively
- **Strengths**: Native hybrid search (BM25 + k-NN), strong observability, integrates with AWS Bedrock Knowledge Bases natively, existing OpenSearch expertise reusable
- **When to use**: AWS-centric teams, hybrid search requirements, existing OpenSearch investment

### Chroma
- **Type**: Open-source; SQLite-backed for dev, self-hosted for prod
- **Positioning**: Developer-focused, minimal setup; embedding stored alongside metadata
- **When to use**: Local development, notebooks, proof-of-concept; not recommended for production at scale

---

## AWS Native Services

### Amazon Bedrock Knowledge Bases
- **What it is**: Fully managed RAG-as-a-service on AWS
- **Architecture**: Ingest documents → auto-chunk + embed (Titan Embeddings or Cohere) → store in OpenSearch Serverless or Aurora pgvector → query via `RetrieveAndGenerate` API
- **Supported data sources**: S3, Confluence, SharePoint, Salesforce, web crawl
- **Strengths**: Zero infrastructure for embedding + indexing pipeline; native IAM/KMS; CloudTrail auditable; integrates with Bedrock Guardrails
- **Limitations**: Limited chunking control (fixed-size only as of mid-2025); no custom rerankers; limited to OpenSearch or pgvector backends
- **When to use**: Enterprise AWS shops where ops simplicity and compliance are priorities over retrieval quality tuning

### Amazon Kendra
- **Positioning**: Enterprise search powered by ML (pre-dates Bedrock, not purely vector-based)
- **Differentiation**: Understands document structure (FAQs, tables), has ACL-based access control, document-type-aware ranking
- **When to use**: Regulated industries needing document-level access control, SharePoint/Confluence indexing, traditional enterprise search with GenAI Q&A on top

---

## Evaluation Tooling

### RAGAS
- **What**: Python library for automated RAG evaluation using LLM-as-judge
- **Metrics**: `faithfulness`, `answer_relevance`, `context_precision`, `context_recall`, `answer_correctness`
- **Integration**: Works with LangChain, LlamaIndex; outputs to pandas DataFrames, Weights & Biases, LangSmith
- **Limitation**: LLM-as-judge has its own biases; expensive to run at scale (each eval is an LLM call)

### TruLens
- **What**: Open-source evaluation + observability for LLM apps
- **Strengths**: Real-time instrumentation (trace every pipeline call), feedback functions (RAG triad: groundedness, relevance, coherence), integrates with Snowflake

### DeepEval
- **What**: Open-source pytest-like framework for LLM evaluation
- **Strengths**: Unit-test style assertions on LLM outputs, CI/CD integrable, 10+ built-in metrics for RAG

### Weights & Biases Weave
- **What**: Tracing + evaluation platform; tracks every LLM call with inputs/outputs/latency
- **When to use**: Teams already using W&B for ML experiments; good for A/B testing retrieval strategies

---

## Document Parsing & Ingestion

| Tool | Strengths | Use Case |
|------|-----------|----------|
| **Unstructured.io** | Best-in-class PDF/HTML/DOCX parsing; table extraction | Complex enterprise docs |
| **LlamaParse** (LlamaIndex) | PDF → Markdown with table/image handling | LlamaIndex pipelines |
| **Apache Tika** | 1000+ file formats; Java-based | Broad format support in Java shops |
| **Docling** (IBM, 2024) | Strong PDF layout understanding; open-source | Research-grade PDF parsing |
| **AWS Textract** | OCR + form/table extraction; native AWS | Scanned docs, AWS-native stacks |
