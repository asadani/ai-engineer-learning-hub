# Products & Tools

## Compression

| Tool | Role |
|---|---|
| **LLMLingua / LongLLMLingua** (Microsoft) | Token-level prompt/context compression via a small model |
| Provider summarization endpoints | Server-side history/document summarization |

## Context / Retrieval Engines

| Tool | Role |
|---|---|
| **LlamaIndex** | Retrieval, structure-aware chunking, query pipelines, response synthesis |
| **LangChain / LangGraph** | Context assembly, memory, state for agents |
| **Vector DBs** (pgvector, Pinecone, Weaviate, Qdrant, Milvus) | Long-term/retrieval store |
| Rerankers (Cohere Rerank, BGE-reranker, voyage-rerank) | Push relevant chunks to context edges |

## Memory

| Tool | Role |
|---|---|
| Framework memory modules (LangGraph checkpointers, LlamaIndex memory) | Short-term + summary memory |
| Dedicated memory layers (e.g., Mem0-style stores) | Long-term, cross-session facts/preferences |
| Object/blob store + DB | Context offloading targets (artifacts, large outputs) |

## Agent Runtimes with Built-in Context Management

| Runtime | Relevant capability |
|---|---|
| **Claude Code / agent runtimes** | Auto-compact at window threshold; sub-agent isolation |
| LangGraph | Explicit state graph, checkpointing, sub-graph isolation |
| CrewAI / AutoGen | Multi-agent context partitioning |

## Evaluation & Observability

| Tool | Role |
|---|---|
| **RAGAS** | Context precision/recall, faithfulness for retrieved context |
| **Arize Phoenix / Langfuse / LangSmith** | Trace token usage per context section, per turn |
| OTel GenAI conventions | Standard token/usage attributes for context accounting |

## Selection Guidance

- Bulky retrieved/few-shot blocks dominating tokens → **prompt compression** (LLMLingua).
- Quality loss from irrelevant chunks → **reranking + metadata filtering** before insertion.
- Agent fails at long horizons → **compaction + memory tiers + sub-agent isolation**.
- Need to prove a change helped → **RAGAS context metrics + token accounting** in tracing.
- Don't hand-build a memory layer before measuring; most wins come from selection and compaction, not storage tech.
