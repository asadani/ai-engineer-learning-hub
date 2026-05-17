# Products & Tools

## LiteLLM — Unified API Gateway with Cost Tracking

LiteLLM provides a single OpenAI-compatible interface across 100+ LLM providers with built-in cost tracking, rate limiting, and model routing.

```python
# pip install litellm
from litellm import completion, acompletion
import litellm

# Enable cost tracking globally
litellm.success_callback = ["langfuse"]  # or custom callback
litellm.set_verbose = False

# Transparent cost logging
response = completion(
    model="anthropic/claude-haiku-4-5-20251001",
    messages=[{"role": "user", "content": "Summarize this text: " + text}],
    max_tokens=256,
)
print(f"Cost: ${response._hidden_params['response_cost']:.6f}")
print(f"Tokens: {response.usage.total_tokens}")

# Model routing with fallback
response = completion(
    model="anthropic/claude-sonnet-4-6",
    messages=[{"role": "user", "content": query}],
    fallbacks=["anthropic/claude-haiku-4-5-20251001", "openai/gpt-4o-mini"],  # cheaper fallbacks on error
    num_retries=2,
    timeout=30,
)
```

**LiteLLM Proxy (production deployment):**
```yaml
# litellm_config.yaml — deploy as a gateway service
model_list:
  - model_name: claude-fast        # internal alias
    litellm_params:
      model: anthropic/claude-haiku-4-5-20251001
      api_key: os.environ/ANTHROPIC_API_KEY
      rpm: 1000

  - model_name: claude-smart
    litellm_params:
      model: anthropic/claude-sonnet-4-6
      api_key: os.environ/ANTHROPIC_API_KEY
      rpm: 200

router_settings:
  routing_strategy: cost-based-routing  # auto-route to cheapest available
  allowed_fails: 3
  cooldown_time: 300

general_settings:
  max_budget: 100.0     # hard stop at $100 budget
  budget_duration: "1d"
  alerting: ["slack"]
  alerting_threshold: 0.8  # alert at 80% budget consumed
```

---

## LangFuse — LLM Observability with Cost Attribution

LangFuse provides per-request, per-user, and per-feature cost attribution with session tracing.

```python
from langfuse import Langfuse
from langfuse.decorators import observe, langfuse_context
import anthropic

langfuse = Langfuse(
    public_key="pk-...",
    secret_key="sk-...",
    host="https://cloud.langfuse.com",
)
client = anthropic.Anthropic()

@observe(name="rag-pipeline")
def rag_query(user_id: str, query: str, feature: str = "search") -> str:
    langfuse_context.update_current_trace(
        user_id=user_id,
        tags=[feature],
        metadata={"query_length": len(query)},
    )

    # Embedding call
    with langfuse_context.observe_llm(
        name="embed",
        model="amazon.titan-embed-text-v2:0",
        input=query,
    ):
        embedding = embed(query)

    # Generation call — Langfuse auto-captures tokens + cost
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{"role": "user", "content": f"Context: {context}\n\nQuery: {query}"}],
    )
    return response.content[0].text

# Query cost per user/feature in Langfuse dashboard:
# SELECT user_id, sum(cost_usd), count(*) FROM traces GROUP BY user_id ORDER BY sum(cost_usd) DESC
```

**What LangFuse gives you:**
- Per-session, per-user cost breakdown
- Cost trend over time (spot regressions after prompt changes)
- Latency × cost scatter (identify outlier expensive requests)
- Evaluation scores alongside cost (quality/cost Pareto)

---

## AWS Bedrock — Managed Inference with Cost Controls

```python
import boto3
import json

bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")
bedrock_mgmt = boto3.client("bedrock", region_name="us-east-1")

# Invoke with cost-optimized model selection
def bedrock_invoke(prompt: str, tier: str = "standard") -> str:
    # Model ARNs by cost tier (Bedrock on-demand pricing)
    models = {
        "fast":     "anthropic.claude-haiku-4-5-20251001-v1:0",   # lowest cost
        "standard": "anthropic.claude-sonnet-4-6-v1:0",            # mid
        "powerful": "anthropic.claude-opus-4-6-v1:0",              # highest
    }
    response = bedrock.invoke_model(
        modelId=models[tier],
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 512,
            "messages": [{"role": "user", "content": prompt}],
        }),
    )
    return json.loads(response["body"].read())["content"][0]["text"]

# Bedrock Batch Inference — 50% discount for async workloads
def create_batch_job(input_s3_uri: str, output_s3_uri: str) -> str:
    response = bedrock_mgmt.create_model_invocation_job(
        roleArn="arn:aws:iam::123456789:role/BedrockBatchRole",
        clientRequestToken="unique-token-001",
        modelId="anthropic.claude-haiku-4-5-20251001-v1:0",
        inputDataConfig={"s3InputDataConfig": {"s3Uri": input_s3_uri}},
        outputDataConfig={"s3OutputDataConfig": {"s3Uri": output_s3_uri}},
    )
    return response["jobArn"]

# Bedrock Provisioned Throughput — predictable cost for high-volume
def purchase_provisioned_throughput(model_id: str, model_units: int) -> str:
    # 1 model unit = guaranteed throughput level
    # Pricing: ~$4/hour for 1 MU of Claude Haiku (vs variable on-demand)
    # Break-even: when on-demand cost exceeds provisioned at your volume
    response = bedrock_mgmt.create_provisioned_model_throughput(
        modelUnits=model_units,
        provisionedModelName=f"my-haiku-{model_units}mu",
        modelId=model_id,
        commitmentDuration="OneMonth",  # 1-month discount vs no commitment
    )
    return response["provisionedModelArn"]
```

**Bedrock cost optimization options:**

| Option | Discount | Tradeoff |
|--------|---------|----------|
| On-demand | Baseline | No commitment, pay per token |
| Batch inference | ~50% | Async only, results in < 24h |
| Provisioned throughput | 10–40% | Fixed monthly commitment, minimum usage |
| Cross-region inference | 0% | Latency increase, resilience benefit |

---

## AWS SageMaker — Self-Hosted Inference Economics

```python
import sagemaker
from sagemaker.huggingface import HuggingFaceModel
from sagemaker.serverless import ServerlessInferenceConfig

sess = sagemaker.Session()
role = "arn:aws:iam::123456789:role/SageMakerRole"

# Option A: Real-time endpoint (persistent, low latency)
# ml.g5.2xlarge = $1.52/hour (1× A10G 24GB) — runs Llama 8B quantized
hub = {
    "HF_MODEL_ID": "meta-llama/Llama-3.2-8B-Instruct",
    "HF_TASK": "text-generation",
    "SM_NUM_GPUS": json.dumps(1),
    "MAX_INPUT_LENGTH": json.dumps(2048),
    "MAX_TOTAL_TOKENS": json.dumps(4096),
}
model = HuggingFaceModel(
    env=hub,
    role=role,
    transformers_version="4.43",
    pytorch_version="2.1",
    py_version="py310",
    image_uri="763104351884.dkr.ecr.us-east-1.amazonaws.com/huggingface-pytorch-tgi-inference:...",
)
predictor = model.deploy(
    initial_instance_count=1,
    instance_type="ml.g5.2xlarge",
)

# Option B: Serverless (cost = 0 when idle, cold start ~3s)
serverless_config = ServerlessInferenceConfig(
    memory_size_in_mb=6144,   # up to 6GB RAM
    max_concurrency=10,
)
# Cost: $0.0000600 per GB-second compute (no idle cost)

# Option C: Spot instances for batch inference (60-80% discount)
# Set up checkpoint-based training job that tolerates interruption
```

**SageMaker vs Bedrock break-even analysis:**
```
SageMaker g5.2xlarge ($1.52/hr) running Llama 8B:
- Throughput: ~500 tokens/second with continuous batching
- Cost: $1.52 / (500 × 3600) = $0.000000844/token = $0.000844/MTok

Bedrock Claude Haiku:
- Cost: $0.80/MTok input, $4.00/MTok output

SageMaker is 1000× cheaper per token — but only if GPU is utilized
At 50% utilization: still 500× cheaper
Break-even utilization: > 0.08% (SageMaker wins at almost any load if you have ops)
```

---

## PromptLayer / Helicone — Lightweight Cost Proxies

```python
# Helicone: drop-in proxy, zero code changes needed
import anthropic

client = anthropic.Anthropic(
    api_key=ANTHROPIC_API_KEY,
    base_url="https://anthropic.helicone.ai",  # proxy URL
    default_headers={
        "Helicone-Auth": f"Bearer {HELICONE_API_KEY}",
        "Helicone-Property-Feature": "rag-search",  # tag for cost attribution
        "Helicone-Property-User-Id": user_id,
        "Helicone-Cache-Enabled": "true",   # enable Helicone semantic cache
        "Helicone-Cache-Bucket-Max-Size": "10",
    },
)
# All requests now tracked in Helicone dashboard with cost, latency, tokens
```

**Use Helicone/PromptLayer when:**
- Need cost attribution with zero engineering investment
- Debugging prompt changes in production
- Cost per feature/user reporting without custom infrastructure

**Use LangFuse when:**
- Multi-step pipelines where you need trace-level cost (embedding + retrieval + generation)
- Custom evaluation scores alongside cost
- Self-hosted observability (compliance requirements)

---

## GPUStack / Ollama — Local Inference for Development

```bash
# Ollama: near-zero cost for development and low-traffic production
ollama pull llama3.2:3b-instruct-q4_K_M  # 2GB, runs on MacBook M2

# Cost comparison:
# Claude Haiku API: $0.80/MTok = $0.0008/1k tokens
# Ollama on MacBook M2: electricity only = ~$0.000001/1k tokens
# Useful for: CI/CD eval runs, development, internal tools

# Production Ollama (small team, < 10 RPS):
# m7g.2xlarge (ARM Graviton): $0.32/hr → $230/month
# Can serve llama3.2:8b at ~100 tokens/second
# Cost at 10 RPS × 200 tokens: 10 × 200 × 60 × 60 = 7.2M tokens/hr
# API cost: $5.76/hr (Haiku) vs $0.32/hr (self-hosted) = 18× cheaper
```

---

## Weights & Biases / MLflow — Training Cost Tracking

```python
import wandb

# Track fine-tuning cost vs performance
with wandb.init(project="llm-finetuning", config={"model": "llama-3.2-8b", "method": "qlora"}):
    wandb.log({
        "training_cost_usd": gpu_hours * gpu_price_per_hour,
        "eval_loss": eval_loss,
        "task_accuracy": task_accuracy,
        "inference_cost_per_1k_tokens": calculate_inference_cost(),
        # The ROI metric: quality improvement / (training cost + inference savings)
        "cost_efficiency_ratio": task_accuracy / training_cost_usd,
    })
```

---

## Tool Selection Summary

| Tool | Best For | Cost | Self-Hostable |
|------|---------|------|--------------|
| **LiteLLM** | Multi-provider routing, fallbacks, cost cap | Free OSS / $49+/mo hosted | Yes |
| **LangFuse** | Trace-level cost attribution, quality×cost | Free tier / $59+/mo | Yes |
| **Helicone** | Zero-change proxy, semantic cache | Free tier / $100+/mo | Yes |
| **AWS Bedrock** | Managed API, AWS-native cost controls | Pay per token | No |
| **SageMaker** | Self-hosted, high volume, compliance | GPU hourly | AWS-managed |
| **vLLM** | Self-hosted, maximum throughput efficiency | Free OSS | Yes |
| **Ollama** | Dev/test, small-scale internal tools | Free | Yes |
| **W&B / MLflow** | Fine-tuning ROI tracking | Free / $50+/mo | Yes |
