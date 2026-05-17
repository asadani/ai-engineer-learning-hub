# What to Measure & How

## Observability Architecture

Production RAG requires distributed tracing across the full pipeline. Each stage is independently measurable and independently failure-prone.

```
User Query
    │
    ▼
[Query Transform]  ← trace span: duration, query_in, query_out
    │
    ▼
[Embedding]        ← trace span: duration, model, token_count, cost
    │
    ▼
[Vector Search]    ← trace span: duration, index, top_k, scores, filter
    │
    ▼
[BM25 Search]      ← trace span: duration, term_hits
    │
    ▼
[RRF Fusion]       ← trace span: final_ranked_chunks, scores
    │
    ▼
[Reranker]         ← trace span: duration, model, input_count, output_scores
    │
    ▼
[Context Assembly] ← trace span: token_count, chunk_ids_used
    │
    ▼
[LLM Generation]   ← trace span: duration, model, input_tokens, output_tokens, cost
    │
    ▼
Response
```

Use OpenTelemetry traces → Grafana Tempo or AWS X-Ray. Every stage should emit a span with stage-specific attributes.

---

## Metrics Checklist

| Metric Name | Type | Target SLO | Collection Method |
|-------------|------|------------|-------------------|
| **e2e_latency_ms** | Histogram | p50 < 1000ms, p99 < 3000ms | OTel span duration (root) |
| **embedding_latency_ms** | Histogram | p99 < 150ms | OTel span (embed stage) |
| **vector_search_latency_ms** | Histogram | p99 < 50ms | OTel span (ANN search) |
| **reranker_latency_ms** | Histogram | p99 < 200ms | OTel span (reranker) |
| **llm_ttfb_ms** (time to first byte) | Histogram | p99 < 1500ms | OTel span start → first token |
| **llm_generation_latency_ms** | Histogram | p99 < 2500ms | OTel span (LLM call) |
| **retrieval_top_k_score** | Gauge | top-1 score > 0.75 | Log score from vector DB |
| **retrieval_score_gap** | Gauge | gap(rank1, rank2) > 0.05 | Computed from search results |
| **chunks_retrieved** | Counter | — | Log count per query |
| **context_token_count** | Histogram | < 60% of context window | Tokenizer output |
| **llm_input_tokens** | Counter | — | LLM response metadata |
| **llm_output_tokens** | Counter | — | LLM response metadata |
| **estimated_cost_usd** | Counter | < budget threshold | tokens × price/token |
| **rag_request_total** | Counter | — | Increment per query |
| **rag_error_rate** | Gauge | < 0.5% | errors / total requests |
| **index_document_count** | Gauge | — | Vector DB admin API |
| **index_freshness_lag_seconds** | Gauge | < 3600s (1 hour) | now() - last_indexed_at |
| **faithfulness_score** | Gauge (sampled) | > 0.85 | RAGAS eval on 5% sample |
| **context_precision_score** | Gauge (sampled) | > 0.70 | RAGAS eval on 5% sample |
| **user_thumbs_down_rate** | Gauge | < 5% | Product feedback event |
| **retrieval_null_rate** | Gauge | < 2% | Queries returning 0 chunks |

---

## Alerting Thresholds

```yaml
# Example Grafana/CloudWatch alerts

- alert: RAGHighLatency
  expr: histogram_quantile(0.99, rag_e2e_latency_ms) > 3000
  for: 5m
  severity: warning

- alert: RAGHighErrorRate
  expr: rate(rag_errors_total[5m]) / rate(rag_requests_total[5m]) > 0.005
  for: 2m
  severity: critical

- alert: RAGIndexStaleness
  expr: rag_index_freshness_lag_seconds > 7200
  for: 10m
  severity: warning

- alert: RAGRetrievalNullRate
  expr: rate(rag_null_retrieval_total[10m]) / rate(rag_requests_total[10m]) > 0.02
  for: 5m
  severity: warning

- alert: RAGFaithfulnessLow
  expr: rag_faithfulness_score_avg < 0.80
  for: 30m
  severity: warning
```

---

## Logging Strategy

Every RAG query should emit a structured log record with enough information to reproduce and debug the answer:

```json
{
  "trace_id": "abc123",
  "timestamp": "2026-03-21T10:23:45Z",
  "user_id": "u_789",
  "query": "What is our refund policy for enterprise subscriptions?",
  "query_transformed": "enterprise subscription refund policy terms",
  "retrieved_chunks": [
    {"chunk_id": "doc42_chunk3", "score": 0.91, "source": "policy_v3.pdf"},
    {"chunk_id": "doc17_chunk8", "score": 0.84, "source": "faq.md"}
  ],
  "reranked_chunks": ["doc42_chunk3", "doc17_chunk8"],
  "context_token_count": 1847,
  "llm_model": "claude-sonnet-4-5",
  "llm_input_tokens": 2103,
  "llm_output_tokens": 287,
  "e2e_latency_ms": 1243,
  "embedding_latency_ms": 87,
  "vector_search_latency_ms": 12,
  "reranker_latency_ms": 134,
  "llm_latency_ms": 987,
  "estimated_cost_usd": 0.00089
}
```

Ship these logs to OpenSearch/Kibana or CloudWatch Logs Insights. Index `chunk_id` and `user_id` for fast lookup. Retain for minimum 30 days for debugging and evaluation dataset construction.

---

## Dashboards

### Operational Dashboard (Grafana)
- **Top panels**: e2e p50/p95/p99 latency (time-series), error rate, request volume
- **Stage breakdown**: latency by stage (embedding, search, reranker, LLM) as stacked bar chart
- **Cost tracking**: daily/hourly spend by model (embedding API + generation API)
- **Index health**: document count, last indexed timestamp, freshness lag

### Quality Dashboard (sampled evaluation)
- **RAGAS scores** (faithfulness, context precision, answer relevance) as time-series — run evaluation daily on a 50-query sample
- **Retrieval score distribution**: histogram of top-1 retrieved chunk scores — bimodal distribution (very high + very low) suggests query distribution shift
- **Null retrieval rate**: queries that returned 0 chunks — spikes indicate index corruption or out-of-domain query surge
- **Feedback signals**: user thumbs up/down rate, escalation rate (queries routed to human)

---

## Index Health Monitoring

The index is a first-class operational asset, not a one-time artifact.

```python
# Periodic health check (run every 15 min)
async def check_index_health(vector_store):
    # 1. Document count (detect unexpected drops)
    count = await vector_store.count()
    metrics.gauge("rag_index_document_count", count)

    # 2. Freshness (time since last successful upsert)
    lag = time.time() - get_last_indexed_timestamp()
    metrics.gauge("rag_index_freshness_lag_seconds", lag)

    # 3. Canary query (known-answer probe)
    result = await vector_store.search("canary query text", k=1)
    expected_doc_id = "canary_doc_001"
    hit = result[0].id == expected_doc_id if result else False
    metrics.gauge("rag_canary_hit", int(hit))

    if not hit:
        alert("RAG canary query miss — index may be corrupted or empty")
```

The canary query pattern is the most reliable early warning system for index degradation.
