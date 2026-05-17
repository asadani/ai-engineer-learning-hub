# Use Cases & Real-World Applications

## 1. High-Volume Document Classification Pipeline

**Context**: A legal tech company classifies 500,000 contracts/day into 20 categories. Initial implementation used GPT-4o for all documents; cost was $4,000/day. Target: < $400/day without accuracy regression.

### Optimization Strategy: Tiered Routing + Fine-Tuned Small Model

```python
import asyncio
from anthropic import AsyncAnthropic

client = AsyncAnthropic()

# Phase 1: Collect 10,000 labeled examples from GPT-4o (expensive but one-time)
# Phase 2: Fine-tune Claude Haiku on labeled examples
# Phase 3: Use fine-tuned Haiku for 95% of traffic; route uncertain cases to Sonnet

CATEGORIES = ["employment", "nda", "saas", "purchase", "lease", "ip_license", ...]

# After fine-tuning, most contracts are classified with high confidence
async def classify_contract(contract_text: str) -> dict:
    # Truncate to first 1,500 tokens (title + parties + recitals usually sufficient)
    truncated = contract_text[:6000]

    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",  # fine-tuned version via fine-tune API
        max_tokens=50,  # just {"category": "...", "confidence": 0.95}
        system="""Classify this contract. Output JSON only:
{"category": "<one of: employment|nda|saas|purchase|lease|ip_license|...>", "confidence": <0.0-1.0>}""",
        messages=[{"role": "user", "content": truncated}],
    )

    result = json.loads(response.content[0].text)

    # Route low-confidence cases to stronger model
    if result["confidence"] < 0.80:
        return await classify_contract_sonnet(contract_text)

    return result

async def classify_contract_sonnet(contract_text: str) -> dict:
    """Fallback for ambiguous contracts — full text, stronger model."""
    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=100,
        system="""Classify this contract carefully. Consider edge cases.
Output JSON: {"category": "...", "confidence": <0.0-1.0>, "reasoning": "<brief>"}""",
        messages=[{"role": "user", "content": contract_text[:20000]}],
    )
    return json.loads(response.content[0].text)

async def classify_batch(contracts: list[str]) -> list[dict]:
    sem = asyncio.Semaphore(50)  # 50 concurrent calls within rate limit
    async def bounded(c):
        async with sem:
            return await classify_contract(c)
    return await asyncio.gather(*[bounded(c) for c in contracts])
```

**Results:**
- 92% of contracts handled by fine-tuned Haiku: cost $0.0004/contract
- 8% routed to Sonnet: cost $0.004/contract
- Blended cost: 0.92 × $0.0004 + 0.08 × $0.004 = $0.00069/contract
- At 500k/day: $345/day (vs $4,000/day with GPT-4o)
- **Cost reduction: 91.4%**

---

## 2. RAG Pipeline with Prompt Caching + Selective Retrieval

**Context**: An internal knowledge base chatbot serving 50k queries/day. Each query was retrieving top-10 chunks (avg 8,000 input tokens) with a 2,000-token system prompt. Cost: $12/day.

### Optimization: Prompt Cache + Reranker + Top-3 Chunks

```python
import anthropic
from sentence_transformers import CrossEncoder

client = anthropic.Anthropic()
reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")  # free, runs on CPU

# Static system prompt — cache it
SYSTEM_PROMPT = """You are a helpful internal knowledge base assistant...
[2,000 tokens of instructions, formatting rules, escalation policies]"""

def rag_query(query: str, retrieved_chunks: list[str]) -> str:
    # Step 1: Rerank 10 retrieved chunks → keep top 3
    scores = reranker.predict([(query, chunk) for chunk in retrieved_chunks])
    top3_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:3]
    top3_chunks = [retrieved_chunks[i] for i in top3_indices]

    # Step 2: Truncate each chunk to 500 tokens (most value is in first 500 tokens)
    truncated_chunks = [chunk[:2000] for chunk in top3_chunks]  # ~500 tokens each
    context = "\n\n---\n\n".join(truncated_chunks)

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},  # cache this prefix
            }
        ],
        messages=[
            {
                "role": "user",
                "content": f"Context:\n{context}\n\nQuestion: {query}",
            }
        ],
    )
    return response.content[0].text

# Cost analysis:
# Before: 2000 (system) + 8000 (top-10 chunks) = 10,000 input tokens × $0.80/MTok = $0.008/query
# After:
#   System: 2000 tokens × $0.08/MTok (cache read 90% discount) = $0.00016
#   Context: 1500 tokens (top-3 × 500) × $0.80/MTok = $0.0012
#   Output: 256 tokens × $4.00/MTok = $0.001
#   Total: ~$0.0024/query vs $0.008/query
# Savings: 70% cost reduction
# At 50k queries/day: $120/day → $36/day
```

---

## 3. Real-Time Conversational Agent with Streaming + History Compression

**Context**: A customer service chatbot with long conversation histories. After 10 turns, context accumulates to 15,000+ tokens. Target: keep conversation context < 4,000 tokens without losing key facts.

```python
from dataclasses import dataclass, field
from anthropic import Anthropic

client = Anthropic()

@dataclass
class ConversationManager:
    system_prompt: str
    messages: list[dict] = field(default_factory=list)
    compression_threshold: int = 8  # compress after 8 message pairs
    max_recent_messages: int = 4    # always keep last 4 pairs verbatim

    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})
        if len(self.messages) > self.compression_threshold * 2:
            self._compress()

    def _compress(self):
        """Summarize old messages, keep recent ones."""
        split_point = len(self.messages) - self.max_recent_messages * 2
        old_messages = self.messages[:split_point]
        recent_messages = self.messages[split_point:]

        # Build summary of old messages
        history_text = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in old_messages])
        summary_response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            system="Summarize this conversation history in 3-5 sentences. Focus on: customer's problem, key facts, resolutions attempted, current state.",
            messages=[{"role": "user", "content": history_text}],
        )
        summary = summary_response.content[0].text

        # Replace old messages with summary pair
        self.messages = [
            {"role": "user", "content": f"[CONVERSATION SUMMARY: {summary}]"},
            {"role": "assistant", "content": "Understood. I have the context from our earlier conversation."},
        ] + recent_messages

    def respond(self, user_message: str) -> str:
        self.add_message("user", user_message)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=[{"type": "text", "text": self.system_prompt, "cache_control": {"type": "ephemeral"}}],
            messages=self.messages,
        )
        assistant_message = response.content[0].text
        self.add_message("assistant", assistant_message)
        return assistant_message

# Cost analysis for 20-turn conversation:
# Without compression: avg 15,000 input tokens/turn × 20 = 300,000 total input tokens
# With compression: avg 3,500 input tokens/turn × 20 + 5 compression calls × 500 tokens
#   = 70,000 + 2,500 = 72,500 tokens = 76% reduction
```

---

## 4. Overnight Analytics Pipeline Using Batch API

**Context**: A SaaS company needs to generate weekly email summaries for 200,000 users based on their activity data. Running synchronously would take 6+ hours and cost $6,000. Batch API provides 50% discount and fits in the overnight window.

```python
import anthropic
import boto3
import json

client = anthropic.Anthropic()
s3 = boto3.client("s3")

def build_batch_requests(user_activity_records: list[dict]) -> list[dict]:
    """Build Batch API request list for all users."""
    requests = []
    for record in user_activity_records:
        # Summarize user activity data concisely
        activity_summary = format_activity(record)  # structured text, ~300 tokens

        requests.append({
            "custom_id": f"user-{record['user_id']}",
            "params": {
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 256,
                "system": "Generate a personalized weekly summary email body for this user. Be concise and action-oriented. No greeting or sign-off needed.",
                "messages": [{"role": "user", "content": activity_summary}],
            },
        })
    return requests

def submit_batch(requests: list[dict]) -> str:
    batch = client.messages.batches.create(requests=requests)
    print(f"Submitted batch {batch.id}: {len(requests)} requests")
    return batch.id

def poll_and_collect(batch_id: str) -> dict[str, str]:
    """Poll until complete, return {user_id: summary} mapping."""
    import time
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        print(f"Status: {batch.processing_status} | "
              f"Succeeded: {batch.request_counts.succeeded} | "
              f"Errored: {batch.request_counts.errored}")
        if batch.processing_status == "ended":
            break
        time.sleep(60)

    results = {}
    for result in client.messages.batches.results(batch_id):
        if result.result.type == "succeeded":
            user_id = result.custom_id.replace("user-", "")
            results[user_id] = result.result.message.content[0].text
        else:
            # Log errors, fall back to template email
            results[result.custom_id] = generate_template_email()
    return results

# Cost analysis:
# 200,000 users × avg 400 input tokens + 200 output tokens:
#   Standard: 80M input + 40M output tokens × Haiku pricing = $224
#   Batch API (50% off): $112
# Runtime: Submit at 11 PM, collect at 5 AM (6 hours), distribute at 6 AM
```

---

## 5. Multi-Tenant SaaS: Per-Customer Cost Attribution and Budgets

**Context**: An AI writing assistant serving B2B customers. Need to track usage per customer, enforce per-tier budgets, and prevent cost overruns from a single whale customer.

```python
from dataclasses import dataclass
import redis
from anthropic import Anthropic

client = Anthropic()
redis_client = redis.Redis(host="redis", decode_responses=True)

PLAN_LIMITS = {
    "starter":    {"daily_tokens": 100_000,  "model": "claude-haiku-4-5-20251001"},
    "pro":        {"daily_tokens": 1_000_000, "model": "claude-sonnet-4-6"},
    "enterprise": {"daily_tokens": 10_000_000,"model": "claude-opus-4-6"},
}

@dataclass
class UsageTracker:
    customer_id: str
    plan: str

    def get_today_tokens(self) -> int:
        key = f"usage:{self.customer_id}:{datetime.date.today()}"
        return int(redis_client.get(key) or 0)

    def record_usage(self, input_tokens: int, output_tokens: int):
        key = f"usage:{self.customer_id}:{datetime.date.today()}"
        total = input_tokens + output_tokens
        redis_client.incrby(key, total)
        redis_client.expire(key, 86400 * 7)  # keep 7 days of history

        # Also write to DynamoDB for billing aggregation
        write_to_dynamodb({
            "customer_id": self.customer_id,
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": (input_tokens * 0.80 + output_tokens * 4.00) / 1_000_000,
        })

    def check_budget(self) -> tuple[bool, str]:
        limit = PLAN_LIMITS[self.plan]["daily_tokens"]
        used = self.get_today_tokens()
        if used >= limit:
            return False, f"Daily limit of {limit:,} tokens reached. Resets at midnight UTC."
        if used >= limit * 0.9:
            # Warn at 90% usage — trigger in-app notification
            notify_customer_approaching_limit(self.customer_id, used, limit)
        return True, ""

def customer_llm_call(customer_id: str, plan: str, user_message: str) -> dict:
    tracker = UsageTracker(customer_id=customer_id, plan=plan)
    allowed, reason = tracker.check_budget()
    if not allowed:
        return {"error": reason, "upgrade_url": f"/billing/upgrade"}

    model = PLAN_LIMITS[plan]["model"]
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": user_message}],
    )
    tracker.record_usage(
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )
    return {"response": response.content[0].text, "tokens_used": response.usage.total_tokens}
```

---

## 6. Self-Hosted vLLM with Spot Instance Checkpointing

**Context**: An ML platform team self-hosts Llama 3.1 70B for internal developer tools. Requirement: 24/7 availability, < $3,000/month budget, handle interruptions gracefully.

```python
# infrastructure/ec2_spot_manager.py
import boto3
import subprocess
import time
import os

ec2 = boto3.client("ec2", region_name="us-east-1")
ssm = boto3.client("ssm", region_name="us-east-1")

LAUNCH_TEMPLATE = {
    "LaunchTemplateData": {
        "InstanceType": "p4d.24xlarge",  # 8× A100 80GB = 560GB HBM, $32.77/hr od, ~$10/hr spot
        "SpotOptions": {
            "SpotInstanceType": "persistent",
            "InstanceInterruptionBehavior": "stop",  # stop (not terminate) on preemption
        },
        "UserData": """#!/bin/bash
# Restore vLLM service state after Spot restart
cd /opt/vllm
# Model weights are on EFS mount — available immediately after restart
python -m vllm.entrypoints.openai.api_server \
    --model /mnt/efs/models/llama-3.1-70b-instruct-awq \
    --quantization awq \
    --tensor-parallel-size 8 \
    --max-model-len 32768 \
    --enable-prefix-caching \
    --port 8000 &

# Register with ALB target group
INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)
aws elbv2 register-targets --target-group-arn $TG_ARN --targets Id=$INSTANCE_ID
""",
    }
}

# Cost analysis:
# p4d.24xlarge Spot: ~$10/hr × 24hr × 30 days = $7,200/month
# But: 2 instances behind ALB for HA → $14,400 on-demand
# Spot discount (~65%): ~$5,000/month
#
# vs Bedrock Claude Sonnet at equivalent quality/volume:
# 10M tokens/day × $3/MTok = $30/day = $900/month
# But 100M tokens/day: $9,000/month → self-hosted wins
#
# vLLM throughput at 8× A100:
# Llama 70B AWQ: ~2,000 tokens/second
# = 172M tokens/day per instance
# At $10/hr: $0.0000000579/token = $0.058/MTok
# 50× cheaper than Bedrock Sonnet at volume
```

---

## 7. Embedding Pipeline Cost Reduction

**Context**: A product search system embeds 50M product descriptions for a vector database. At OpenAI ada-002 pricing ($0.10/MTok), initial estimate was $5,000 for bulk embedding + $100/day for query embeddings. Alternative approaches:

```python
# Option A: Self-hosted BGE-M3 on SageMaker Serverless
# Cost: $0/request when idle, $0.000060/GB-second when active
# Throughput: ~500 texts/second on ml.m5.xlarge
# 50M docs × avg 100 tokens = 5B tokens
# SageMaker cost: ~$30 (vs $500 with OpenAI ada-002)

from sentence_transformers import SentenceTransformer
import numpy as np

# BAAI/bge-m3: state-of-the-art multilingual embedding, free, runs on CPU
model = SentenceTransformer("BAAI/bge-m3", device="cpu")

def embed_batch(texts: list[str], batch_size: int = 256) -> np.ndarray:
    """Embed texts in batches for memory efficiency."""
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        batch = [t[:512] for t in batch]  # truncate at 512 tokens (most value is here)
        embeddings = model.encode(batch, normalize_embeddings=True, show_progress_bar=False)
        all_embeddings.append(embeddings)
    return np.vstack(all_embeddings)

# Option B: Amazon Titan Embed Text v2 (Bedrock)
# $0.020/MTok — same as OpenAI but with IAM auth, no data egress
# 50M × 100 tokens = 5B tokens = $100 bulk
# Daily queries: 1M × 50 tokens = 50M tokens = $1/day

# Option C: Reduced dimensionality (OpenAI text-embedding-3-small supports this)
# 1536 dims → 256 dims: same price but 6× less storage, faster ANN search
# For Pinecone: 256-dim pod fits 4× more vectors than 1536-dim
```
