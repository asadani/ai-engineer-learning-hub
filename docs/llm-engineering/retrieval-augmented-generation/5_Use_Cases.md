# Use Cases & Real-World Applications

## 1. Enterprise Knowledge Base / Internal Q&A

**Canonical use case.** Replace SharePoint/Confluence keyword search with conversational Q&A over internal documentation, policies, runbooks, and wikis.

**Architecture**:
```
Confluence/SharePoint/S3 → Ingestion pipeline → Chunker → Embedder
                                                               ↓
Employee query → Embed → Hybrid search (OpenSearch) → Rerank → LLM
                                                                 ↓
                                                    Answer + cited doc links
```

**Production signals**:
- Morgan Stanley's internal advisor platform (built on OpenAI) retrieves across 100K+ research documents; reported 20% advisor productivity gain
- Typical enterprise deployment: 500K-5M document chunks, OpenSearch or Pinecone backend, Bedrock or Azure OpenAI as generator

**Critical requirements**: Access control (ACL per document — a user should only retrieve documents they can read), audit logging (what was retrieved for every answer), freshness SLA (how stale can the index be?)

**Gotcha**: Without ACL enforcement at retrieval time, RAG becomes a privilege escalation vector. Metadata filtering on user role/department must happen before vector search, not after.

---

## 2. Customer Support / Ticket Deflection

**Use case**: Route support queries to AI-generated answers grounded in product documentation, FAQs, and past resolved tickets.

**Architecture**:
```
Product docs + KB articles + resolved tickets → Index
                                                   ↓
Customer query → Intent classification → RAG retrieval → Answer generation
                       ↓
              (escalate to human if confidence low)
```

**Integration pattern**: Typically sits in front of Zendesk, Intercom, Freshdesk. When RAG answer confidence is low (RAGAS faithfulness < 0.7 or answer relevance < 0.8), route to human agent with pre-fetched context.

**Real-world**: Intercom Fin, Zendesk AI, Salesforce Einstein Copilot all implement this pattern. Typical reported deflection rates: 30-50% of Tier-1 tickets.

**Scaling concern**: Support corpora change frequently (product updates, policy changes). Index freshness pipeline must trigger on document update events (S3 event → Lambda → re-embed + upsert), not nightly batch.

---

## 3. Code Search & Developer Copilot

**Use case**: Retrieve relevant code snippets, API docs, internal library examples, and error resolutions to ground code generation.

**Unique requirements**:
- Code requires **syntax-aware chunking** (split at function/class/module boundaries, not fixed tokens)
- Hybrid retrieval is especially important: developers search with exact function names, import paths, error messages (BM25 handles these better than embeddings)
- Multi-language embedding models perform inconsistently; code-specific models (UniXcoder, CodeBERT, `text-embedding-3-large` fine-tuned on code) outperform general models

**Architecture at a monorepo scale**:
```
GitHub repo → AST-based chunker (function/class level) → code embedder
                                                               ↓
Developer query / IDE context → BM25 + dense hybrid → top-5 snippets
                                                               ↓
                                          Code generation LLM (Claude/GPT-4o/Gemini)
```

**Real-world**: GitHub Copilot uses retrieval over the open file, related files, and GitHub repositories. JetBrains AI Assistant, Cursor, and Codeium all implement RAG over the local codebase.

---

## 4. Medical & Clinical Decision Support

**Unique constraints**: Regulatory (FDA, HIPAA), hallucination risk is patient-safety relevant, evidence grading (RCT > observational study), citation required.

**Architecture additions over standard RAG**:
- Metadata must include publication date, study type, evidence level
- Reranker should be fine-tuned on medical literature (BioLinkBERT, PubMedBERT-based)
- Answer generation prompt explicitly requires citation and confidence caveat
- Human-in-the-loop override for high-stakes queries

**Use cases**: Clinical trial matching (retrieve matching criteria → check patient eligibility), drug interaction lookup, differential diagnosis support (Epic Systems' AI models, Nuance DAX)

---

## 5. Financial Analysis & Research

**Use case**: Q&A over earnings transcripts, SEC filings (10-K, 10-Q), analyst reports, market research.

**Unique requirements**:
- Structured + unstructured data fusion: numbers from tables (chunked as structured rows) + narrative from text
- Temporal awareness: "Q3 2024 revenue" requires date-aware retrieval and filtering
- Multi-document synthesis: "compare margin trends across the last 4 quarters" requires multi-hop retrieval

**Architecture addition**: Table extraction (Textract or Unstructured.io) with row-level chunking; metadata fields for fiscal period, company ticker, document type.

**Real-world**: Bloomberg's AI assistant, Morgan Stanley Research Copilot, JPMorgan Chase IndexGPT — all RAG-based over proprietary financial corpora.

---

## 6. Legal Document Review & Contract Analysis

**Use case**: Retrieve precedent clauses, flag non-standard language, answer questions about contract terms.

**Challenges**:
- Legal documents have complex cross-references ("as defined in Section 4.2(b)") — standard chunking severs these
- Semantic similarity is insufficient: legally similar sentences can have opposite force ("shall" vs. "may")

**Architecture considerations**:
- Hierarchical chunking: section-level for retrieval, full document available as parent context
- GraphRAG for cross-reference resolution
- Clause-level embedding with contract metadata (governing law, effective date, party names) for filtered retrieval

---

## 7. Agentic RAG: Multi-Step Research Pipelines

**Pattern**: RAG retrieval is a tool in an agent loop, not a one-shot pipeline. The agent decides when to retrieve, what to retrieve, and whether results are sufficient.

```python
# Simplified LangGraph agentic RAG
tools = [retriever_tool, web_search_tool, calculator_tool]
agent = create_react_agent(llm, tools)

# Agent flow:
# 1. Plan: "I need to find X, then compute Y based on X"
# 2. Retrieve X from index
# 3. If retrieved context is insufficient: trigger web search
# 4. Compute Y using calculator
# 5. Synthesize final answer with citations
```

**When to use over standard RAG**:
- Questions requiring multiple retrieval hops ("what is the impact of policy X on metric Y given context Z")
- Dynamic corpora (agent can decide to trigger a fresh web search vs. use stale index)
- Complex reasoning with tool use (RAG answer feeds into a calculation, not just text generation)

**Production tools**: LangGraph (most mature for production agentic RAG), LlamaIndex `AgentRunner`, AWS Bedrock Agents with Knowledge Bases integration.
