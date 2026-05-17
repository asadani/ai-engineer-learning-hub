# Key Technical Concepts

## 1. Prompt Caching

### Anthropic Prompt Caching
Anthropic's cache_control feature stores a KV cache checkpoint at a marked boundary. Subsequent requests that share the prefix up to that boundary pay 90% less on input tokens (and zero on re-encoding).

```python
import anthropic

client = anthropic.Anthropic()

# Cache the system prompt + static context (tool definitions, knowledge base excerpts)
response = client.messages.create(
    model="claude-opus-4-6",
    max_tokens=1024,
    system=[
        {
            "type": "text",
            "text": LARGE_SYSTEM_PROMPT,  # 2,000 tokens of instructions
            "cache_control": {"type": "ephemeral"},  # mark this for caching
        }
    ],
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": STATIC_KNOWLEDGE_BASE,  # 10,000 tokens of docs
                    "cache_control": {"type": "ephemeral"},  # second cache point
                },
                {"type": "text", "text": user_query},
            ],
        }
    ],
)

# Inspect cache performance
usage = response.usage
print(f"Cache read tokens: {usage.cache_read_input_tokens}")   # 90% discount
print(f"Cache write tokens: {usage.cache_creation_input_tokens}")  # 25% surcharge (amortized)
print(f"Regular input tokens: {usage.input_tokens}")
```

**Economics:**
- Cache write: 25% surcharge over base input price (paid once per 5-minute TTL)
- Cache read: 10% of base input price (paid every hit)
- Break-even: If you call the API > 1.25× in the cache TTL window, you save money
- At 100 requests/5min: 99 reads × 0.1 + 1 write × 1.25 = 11.25 units vs 100 units = 89% savings

**What to cache:**
- System prompts (always — reused on every request)
- Tool definitions (heavy JSON schemas, called on every request)
- Static knowledge base excerpts (long documents that rarely change)
- Few-shot examples (don't change per request)

**What NOT to cache:**
- Conversation history (changes every turn)
- User queries (always unique)
- Retrieved context from vector DB (query-specific)

---

## 2. Semantic Caching

Exact caching misses paraphrased queries. Semantic caching stores (query_embedding, response) pairs and returns the cached response when a new query is within cosine similarity threshold.

```python
import numpy as np
from anthropic import Anthropic

client = Anthropic()

class SemanticCache:
    def __init__(self, threshold: float = 0.95, max_size: int = 10_000):
        self.threshold = threshold
        self.cache: list[dict] = []  # [{embedding, query, response, hits}]
        self.max_size = max_size
        self._embed_client = None

    def _embed(self, text: str) -> np.ndarray:
        # Use a cheap embedding model (Titan v2 on Bedrock: $0.00002/1k tokens)
        import boto3
        bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")
        response = bedrock.invoke_model(
            modelId="amazon.titan-embed-text-v2:0",
            body=json.dumps({"inputText": text, "dimensions": 256, "normalize": True}),
        )
        return np.array(json.loads(response["body"].read())["embedding"])

    def lookup(self, query: str) -> tuple[str | None, float]:
        if not self.cache:
            return None, 0.0
        q_emb = self._embed(query)
        # Vectorized cosine similarity over all cached embeddings
        cache_embs = np.stack([e["embedding"] for e in self.cache])
        sims = cache_embs @ q_emb  # already normalized → cosine similarity
        best_idx = int(np.argmax(sims))
        best_sim = float(sims[best_idx])
        if best_sim >= self.threshold:
            self.cache[best_idx]["hits"] += 1
            return self.cache[best_idx]["response"], best_sim
        return None, best_sim

    def store(self, query: str, response: str):
        embedding = self._embed(query)
        if len(self.cache) >= self.max_size:
            # Evict least-hit entry (LFU eviction)
            min_hits_idx = min(range(len(self.cache)), key=lambda i: self.cache[i]["hits"])
            self.cache.pop(min_hits_idx)
        self.cache.append({"embedding": embedding, "query": query, "response": response, "hits": 0})

semantic_cache = SemanticCache(threshold=0.95)

def cached_llm_call(query: str, system: str) -> tuple[str, bool]:
    cached_response, similarity = semantic_cache.lookup(query)
    if cached_response:
        return cached_response, True  # cache hit

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system=system,
        messages=[{"role": "user", "content": query}],
    )
    response_text = response.content[0].text
    semantic_cache.store(query, response_text)
    return response_text, False
```

**Threshold selection:**
- 0.98+: Extremely strict, only near-identical queries hit (safe but low hit rate)
- 0.95: Good default — paraphrases hit, topic shifts miss
- 0.90: Aggressive — may return responses for loosely related queries
- Always A/B test threshold against quality degradation on your query distribution

---

## 3. Model Routing

Route queries to the cheapest model that can handle them. The key is building a reliable router that doesn't degrade quality on hard queries.

```python
from anthropic import Anthropic
import re

client = Anthropic()

# Cost-ordered model tiers (Claude pricing as of 2025)
MODELS = {
    "haiku":  {"id": "claude-haiku-4-5-20251001",   "input": 0.80,  "output": 4.00},   # per MTok
    "sonnet": {"id": "claude-sonnet-4-6",             "input": 3.00,  "output": 15.00},
    "opus":   {"id": "claude-opus-4-6",               "input": 15.00, "output": 75.00},
}

ROUTER_SYSTEM = """Classify the complexity of this user query for routing to the appropriate AI model.

Output JSON: {"tier": "simple"|"moderate"|"complex", "reason": "<one sentence>"}

simple: factual lookup, yes/no, short summary, format conversion, direct extraction
moderate: multi-step reasoning, comparison, explanation requiring context synthesis
complex: research, code generation, analysis of tradeoffs, open-ended tasks requiring judgment"""

def route_query(query: str) -> str:
    """Returns model tier: simple | moderate | complex."""
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",  # always use cheapest model to route
        max_tokens=64,
        system=ROUTER_SYSTEM,
        messages=[{"role": "user", "content": f"Query: {query}"}],
    )
    try:
        result = json.loads(response.content[0].text)
        return result.get("tier", "moderate")
    except Exception:
        return "moderate"  # safe default

TIER_TO_MODEL = {"simple": "haiku", "moderate": "sonnet", "complex": "opus"}

def routed_call(query: str, system: str) -> dict:
    tier = route_query(query)
    model_key = TIER_TO_MODEL[tier]
    model = MODELS[model_key]

    response = client.messages.create(
        model=model["id"],
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": query}],
    )
    tokens_in = response.usage.input_tokens
    tokens_out = response.usage.output_tokens
    cost = (tokens_in * model["input"] + tokens_out * model["output"]) / 1_000_000

    return {
        "response": response.content[0].text,
        "tier": tier,
        "model": model_key,
        "cost_usd": cost,
    }
```

**Router design principles:**
- Use the cheapest model for the router itself (routing latency < 100ms, cost < $0.0001)
- Validate router accuracy on a labeled holdout set before deploying
- Add confidence scores — if router is uncertain, default to middle tier
- Monitor routing distribution in prod: if 80% is going to "complex", router may be miscalibrated

**Alternative: Rule-based routing** (zero cost, predictable)
```python
def rule_based_router(query: str, context_length: int) -> str:
    if context_length > 50_000:
        return "opus"  # long context needs most capable model
    if re.search(r"\b(calculate|compute|prove|debug|design|architect)\b", query, re.I):
        return "sonnet"
    if len(query.split()) < 15 and "?" in query:
        return "haiku"  # short factual questions
    return "sonnet"  # default to middle
```

---

## 4. Prompt Compression

Reduce input tokens without losing information the model needs.

### LLMLingua-style Token Pruning
```python
# LLMLingua uses a small LM to score token importance, prunes low-importance tokens
# pip install llmlingua
from llmlingua import PromptCompressor

compressor = PromptCompressor(
    model_name="microsoft/llmlingua-2-xlm-roberta-large-meetingbank",
    use_llmlingua2=True,
    device_map="cpu",
)

def compress_retrieved_context(chunks: list[str], compression_ratio: float = 0.5) -> str:
    """Compress retrieved context chunks by ~50% while preserving key information."""
    context = "\n\n".join(chunks)
    compressed = compressor.compress_prompt(
        context,
        rate=compression_ratio,
        force_tokens=["\n", ".", "?", "!"],  # never prune structural tokens
    )
    return compressed["compressed_prompt"]

# Typical result: 2,000 token context → 800 tokens, minimal quality loss on downstream tasks
```

### Selective Retrieval (Fewer Chunks)
```python
from anthropic import Anthropic

client = Anthropic()

def selective_retrieval_with_reranking(
    query: str,
    candidates: list[str],
    top_k: int = 3,  # send only top-3 to LLM instead of top-10
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
) -> list[str]:
    """Rerank candidates and return only the most relevant chunks."""
    from sentence_transformers import CrossEncoder
    model = CrossEncoder(reranker_model)
    pairs = [(query, chunk) for chunk in candidates]
    scores = model.predict(pairs)
    ranked = sorted(zip(scores, candidates), reverse=True)
    return [chunk for _, chunk in ranked[:top_k]]
```

### Conversation History Compression
```python
SUMMARIZER_SYSTEM = "Compress this conversation history into a brief summary capturing key facts, decisions made, and open questions. Be concise — 2-3 sentences max."

def compress_history(messages: list[dict], keep_last_n: int = 4) -> list[dict]:
    """Keep recent messages verbatim; summarize older messages."""
    if len(messages) <= keep_last_n * 2:
        return messages

    old_messages = messages[:-keep_last_n * 2]
    recent_messages = messages[-keep_last_n * 2:]

    history_text = "\n".join([f"{m['role']}: {m['content']}" for m in old_messages])
    summary_response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        system=SUMMARIZER_SYSTEM,
        messages=[{"role": "user", "content": history_text}],
    )
    summary = summary_response.content[0].text

    compressed_history = [
        {"role": "user", "content": f"[Conversation summary: {summary}]"},
        {"role": "assistant", "content": "Understood. I'll continue with that context in mind."},
    ] + recent_messages
    return compressed_history
```

---

## 5. Output Constraint and Structured Generation

Output tokens are 3–5× more expensive than input tokens. Reducing output length has outsized cost impact.

```python
def constrained_extraction(document: str, schema: dict) -> dict:
    """Force JSON output to avoid verbose prose."""
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,  # hard cap — structured extraction rarely needs more
        system=f"""Extract information as JSON matching this schema exactly:
{json.dumps(schema, indent=2)}
Output only valid JSON, no explanation, no markdown.""",
        messages=[{"role": "user", "content": document}],
    )
    return json.loads(response.content[0].text)

# vs. the verbose approach:
# "Please carefully analyze the document and extract the following fields,
#  explaining your reasoning for each..." → 3× more output tokens
```

**Output length by task type (calibrated targets):**

| Task | Typical Output Tokens | Constrained Target |
|------|----------------------|-------------------|
| Classification | 200–500 (explaining) | 10–50 (JSON label) |
| Field extraction | 500–1,000 | 50–200 (JSON schema) |
| Yes/No + reason | 100–300 | 20–50 |
| Summarization | Task-appropriate | Set `max_tokens` explicitly |
| Code generation | Full code needed | No constraint, but test pass rate > verbosity |

---

## 6. Batching

Batch inference costs less per token because fixed overhead (model loading, request handling) is amortized.

```python
import asyncio
from anthropic import AsyncAnthropic

async_client = AsyncAnthropic()

async def batch_classify(
    texts: list[str],
    batch_size: int = 20,
    max_concurrent: int = 5,
) -> list[str]:
    """Classify texts with controlled concurrency to maximize throughput within rate limits."""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def classify_one(text: str) -> str:
        async with semaphore:
            response = await async_client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=10,  # just the label
                system="Classify as: positive, negative, or neutral. Output one word only.",
                messages=[{"role": "user", "content": text[:500]}],  # truncate input
            )
            return response.content[0].text.strip().lower()

    tasks = [classify_one(text) for text in texts]
    return await asyncio.gather(*tasks)

# Anthropic Batch API: 50% discount, async (results in 1-24h)
async def anthropic_batch_api(requests: list[dict]) -> str:
    """Use Message Batches API for async workloads — 50% cost reduction."""
    batch = await async_client.messages.batches.create(
        requests=[
            {
                "custom_id": req["id"],
                "params": {
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": req.get("max_tokens", 256),
                    "messages": req["messages"],
                },
            }
            for req in requests
        ]
    )
    return batch.id  # poll batch.id for results

async def poll_batch(batch_id: str, poll_interval: int = 60) -> list[dict]:
    """Poll until batch completes."""
    while True:
        batch = await async_client.messages.batches.retrieve(batch_id)
        if batch.processing_status == "ended":
            results = []
            async for result in await async_client.messages.batches.results(batch_id):
                results.append({"id": result.custom_id, "response": result.result})
            return results
        await asyncio.sleep(poll_interval)
```

**When to use Batch API:**
- Analytics pipelines (classify/summarize documents overnight)
- Offline evaluation runs
- Dataset generation / synthetic data
- Any workload where results in < 24h is acceptable

---

## 7. KV Cache and Continuous Batching (Self-Hosted)

When running your own inference server (vLLM/TGI), these are the key efficiency levers:

```python
# vLLM server configuration for cost efficiency
from vllm import AsyncLLMEngine, SamplingParams
from vllm.engine.arg_utils import AsyncEngineArgs

engine_args = AsyncEngineArgs(
    model="meta-llama/Llama-3.1-8B-Instruct",
    quantization="awq",                   # 4-bit quantization: 4× memory reduction
    max_model_len=8192,                    # limit context to control KV cache size
    gpu_memory_utilization=0.90,          # leave 10% headroom
    max_num_seqs=256,                      # max concurrent sequences
    enable_prefix_caching=True,            # cache KV for shared prefixes (system prompt)
    # Continuous batching is automatic in vLLM — new requests slot into
    # freed positions as sequences complete (no padding waste)
)
engine = AsyncLLMEngine.from_engine_args(engine_args)
```

**The continuous batching win:** Traditional static batching: fill a batch, wait for the longest sequence to finish, then start next batch. Continuous batching: as each sequence finishes, immediately slot in a new request. Throughput improvement: 10–23× for mixed-length workloads.

**Prefix caching in self-hosted:**
- All requests sharing the same system prompt share KV cache blocks
- vLLM `enable_prefix_caching=True` → ~40% throughput improvement when system prompt is long
- Works automatically — no code changes needed in the application layer

---

## 8. Fine-Tuning for Cost Reduction (Not Just Quality)

A fine-tuned small model can match or beat a large model on a narrow task at 10× lower cost.

```python
# Cost comparison: Fine-tuned Haiku vs. GPT-4 on domain classification
#
# GPT-4o:           $5.00/MTok input, $15.00/MTok output → $0.012/request
# Fine-tuned Haiku: $1.00/MTok input,  $5.00/MTok output → $0.0015/request
# Fine-tuning cost: $0.008/1k tokens (amortized over 1M requests = negligible)
#
# If fine-tuned Haiku achieves 95% of GPT-4 accuracy on domain task:
# → 8× cost reduction for 5% quality delta
# → ROI positive at > ~5k requests/day

# Trigger for fine-tuning decision:
# 1. Narrow, well-defined task with stable distribution
# 2. Few-shot prompting with GPT-4 achieves acceptable quality
# 3. Scale justifies training cost (> 100k requests/month)
# 4. Have labeled data or can generate synthetic data at scale
```

---

## 9. Embedding Cost Optimization

Embeddings are called on every document upsert and every query. At scale, this matters.

```python
import boto3
import numpy as np
import hashlib, json

bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

# Model pricing comparison (per 1M tokens):
# OpenAI text-embedding-3-small: $0.020
# Amazon Titan Embed Text v2:    $0.020
# Cohere embed-english-v3.0:     $0.100
# BGE-M3 self-hosted on g4dn.xl: ~$0.001 (after amortization)

def embed_with_cache(texts: list[str], cache: dict) -> list[list[float]]:
    """Embed texts, using content hash as cache key."""
    results = []
    to_embed = []
    indices = []

    for i, text in enumerate(texts):
        key = hashlib.md5(text.encode()).hexdigest()
        if key in cache:
            results.append((i, cache[key]))
        else:
            to_embed.append(text)
            indices.append((i, key))

    # Batch embed uncached texts
    if to_embed:
        for j, text in enumerate(to_embed):
            response = bedrock.invoke_model(
                modelId="amazon.titan-embed-text-v2:0",
                body=json.dumps({"inputText": text[:8192], "dimensions": 256}),
            )
            embedding = json.loads(response["body"].read())["embedding"]
            i, key = indices[j]
            cache[key] = embedding
            results.append((i, embedding))

    results.sort(key=lambda x: x[0])
    return [emb for _, emb in results]

# Self-hosted option: sentence-transformers BAAI/bge-small-en-v1.5
# 33M params, runs on CPU, ~10ms/text, essentially free at scale
from sentence_transformers import SentenceTransformer
model = SentenceTransformer("BAAI/bge-small-en-v1.5")
embeddings = model.encode(texts, batch_size=64, show_progress_bar=False)
```
