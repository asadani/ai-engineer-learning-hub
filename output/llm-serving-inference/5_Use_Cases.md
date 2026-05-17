# Use Cases & Real-World Applications

## 1. High-Throughput API Gateway (Multi-Tenant SaaS)

**Context**: A SaaS company serving LLM-powered features to thousands of customers. Requirements: OpenAI-compatible API, multi-model support, per-customer cost tracking, rate limiting, fallback to different providers on failure.

**Architecture:**

```
Client → LiteLLM Proxy → vLLM (self-hosted 70B)
                       ↓ (on failure/overload)
                       → Bedrock Claude (managed fallback)
                       ↓ (rate limit exceeded)
                       → 429 response
```

**Implementation:**

```python
# LiteLLM proxy config for multi-tenant gateway
# config.yaml

model_list:
  - model_name: "llama-3-70b"
    litellm_params:
      model: openai/meta-llama/Meta-Llama-3.1-70B-Instruct
      api_base: "http://vllm-primary:8000/v1"
      api_key: "token-xyz"
      timeout: 30
    model_info:
      max_tokens: 8192
      input_cost_per_token: 0.0000003   # $0.30/1M input
      output_cost_per_token: 0.0000006  # $0.60/1M output

  - model_name: "llama-3-70b"
    litellm_params:
      model: bedrock/meta.llama3-1-70b-instruct-v1:0
      aws_region_name: us-east-1
    model_info:
      max_tokens: 8192

router_settings:
  routing_strategy: "latency-based-routing"
  fallbacks: [{"llama-3-70b": ["bedrock-claude"]}]
  num_retries: 2
  timeout: 45
  allowed_fails: 1

litellm_settings:
  success_callback: ["langfuse"]
  cache: true
  cache_params:
    type: redis
    host: "redis://redis:6379"
    ttl: 3600  # 1 hour semantic cache TTL

# Per-customer rate limiting via virtual keys
# litellm-key create --key-alias "customer-123" --max-budget 50 --rpm-limit 100
```

**Cost optimization**: Enable semantic caching in LiteLLM. Queries that are semantically similar (cosine similarity > 0.95 on embeddings) serve cached responses instead of hitting the LLM. For a customer support use case with repetitive questions, cache hit rate reaches 30–50%, cutting inference costs by that fraction.

---

## 2. Low-Latency Chat Application (TTFT-Optimized)

**Context**: Consumer chat product. Users expect instant response start (< 300ms TTFT) and smooth streaming (> 30 TPS).

**Key engineering decisions:**

```python
# vLLM engine tuned for low-latency interactive use
from vllm import AsyncLLMEngine
from vllm.engine.arg_utils import AsyncEngineArgs

engine = AsyncLLMEngine.from_engine_args(AsyncEngineArgs(
    model="meta-llama/Meta-Llama-3.1-8B-Instruct",
    tensor_parallel_size=2,
    gpu_memory_utilization=0.85,
    max_model_len=8192,
    enable_prefix_caching=True,     # cache system prompt KV
    enable_chunked_prefill=True,    # don't block decode during prefill
    max_num_batched_tokens=2048,    # limit tokens/step → lower latency variance
    scheduler_delay_factor=0.0,     # don't delay to batch (optimize TTFT)
    max_num_seqs=64,                # concurrent sequences
    # Speculative decoding for fast decode
    speculative_model="[ngram]",
    num_speculative_tokens=5,
    ngram_prompt_lookup_max=4,
))

# FastAPI streaming endpoint
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import asyncio, json, time

app = FastAPI()

@app.post("/v1/chat/completions")
async def chat_completion(request: ChatRequest):
    sampling_params = SamplingParams(
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        stop=["<|eot_id|>"],
    )

    async def generate():
        request_id = f"req-{time.time_ns()}"
        first_token = True
        async for output in engine.generate(request.messages_to_prompt(), sampling_params, request_id):
            if output.outputs:
                token_text = output.outputs[0].text
                if first_token:
                    # Emit TTFT metric here
                    first_token = False
                chunk = {
                    "choices": [{"delta": {"content": token_text}, "finish_reason": None}]
                }
                yield f"data: {json.dumps(chunk)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

**Prefix caching impact**: A system prompt that's 1,000 tokens costs ~120ms prefill on every new conversation. With prefix caching, the first request pays this cost; subsequent requests reuse the cached KV blocks. TTFT for requests sharing the system prompt drops from 120ms to 15ms.

---

## 3. Batch Inference Pipeline (Cost-Optimized)

**Context**: An analytics team needs to run sentiment analysis, entity extraction, and summarization on 10M documents nightly. Quality matters; latency doesn't (4-hour window).

```python
import asyncio
from vllm import LLM, SamplingParams
from pathlib import Path
import json

# Offline batch inference — maximize throughput, not latency
llm = LLM(
    model="meta-llama/Meta-Llama-3.1-8B-Instruct",
    tensor_parallel_size=4,
    gpu_memory_utilization=0.95,    # maximize batch size
    max_model_len=4096,
    quantization="awq",              # AWQ for memory efficiency
    max_num_seqs=512,                # large concurrent batch
)

sampling_params = SamplingParams(
    temperature=0.0,    # greedy for deterministic extraction
    max_tokens=256,
    stop=["```"],
)

def build_extraction_prompt(document: str) -> str:
    return f"""<|begin_of_text|><|start_header_id|>user<|end_header_id|>

Extract from the following document:
1. Sentiment: positive/negative/neutral
2. Key entities (people, organizations, locations)
3. One-sentence summary

Document: {document[:2000]}

Respond in JSON format only.<|eot_id|><|start_header_id|>assistant<|end_header_id|>
```json
"""

# Load documents, build prompts
documents = load_documents_from_s3("s3://bucket/documents/")
prompts = [build_extraction_prompt(doc) for doc in documents]

# vLLM offline batch: processes all prompts with continuous batching
# Much more efficient than calling generate() one at a time
outputs = llm.generate(prompts, sampling_params)

# Write results to S3
results = []
for doc, output in zip(documents, outputs):
    try:
        extracted = json.loads(output.outputs[0].text + "}")
        results.append({"doc_id": doc.id, "extracted": extracted})
    except json.JSONDecodeError:
        results.append({"doc_id": doc.id, "error": "parse_failure"})

write_to_s3(results, "s3://bucket/extractions/")
```

**Infrastructure for 10M documents on Spot:**
```bash
# Run on p4d.24xlarge Spot (8× A100 40GB) — ~$8/hr vs $32/hr on-demand
# Throughput: ~8,000 tokens/sec with TP=8
# Average output: 256 tokens → ~31 docs/sec → 10M docs in ~90 hours on 1 instance
# With 8 instances in parallel: ~11 hours, ~$700 total vs $2,800 on-demand

# Use SQS for fault tolerance: documents → SQS queue → workers → results S3
# Worker script checkpoints every 1000 docs; restarts from checkpoint on Spot interruption
```

---

## 4. On-Device / Edge Inference (llama.cpp)

**Context**: A legal document tool that must run air-gapped on a lawyer's MacBook Pro (M3 Max, 128GB unified memory). No cloud, strict data sovereignty requirements.

```python
# Using llama-cpp-python bindings
from llama_cpp import Llama

# M3 Max: use Metal GPU backend
llm = Llama(
    model_path="/models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
    n_ctx=8192,           # context window
    n_gpu_layers=-1,      # -1 = offload ALL layers to GPU (Metal)
    n_batch=512,          # prompt processing batch size
    n_threads=8,          # CPU threads for non-GPU work
    verbose=False,
)

# Single-turn inference
response = llm(
    "<|begin_of_text|><|start_header_id|>user<|end_header_id|>\n\nSummarize this contract clause: {clause}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n",
    max_tokens=512,
    temperature=0.1,
    stop=["<|eot_id|>"],
)
print(response["choices"][0]["text"])

# Chat interface with history
llm_chat = Llama(
    model_path="/models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
    n_ctx=8192,
    n_gpu_layers=-1,
    chat_format="llama-3",  # uses the correct template automatically
)
messages = [
    {"role": "system", "content": "You are a legal assistant. Analyze contracts precisely."},
    {"role": "user", "content": "What are the key obligations in section 3?"},
]
response = llm_chat.create_chat_completion(messages=messages, max_tokens=1024)
```

**Performance on M3 Max with Q4_K_M (8B model):**
- Prefill speed: ~2,000 tokens/sec
- Decode speed: ~60–70 tokens/sec (faster than most cloud models for interactive use)
- Memory: ~5.5GB for 8B Q4_K_M model + 1GB KV cache at 8k context

**For 70B on M3 Max (128GB unified memory):**
- Q4_K_M 70B = ~43GB model + KV cache
- Decode speed: ~15–20 tokens/sec — usable for non-interactive tasks

---

## 5. Multi-Modal Serving (Vision + Language)

**Context**: A product that processes images + text — receipt parsing, document understanding, visual Q&A.

```python
from vllm import LLM, SamplingParams

# vLLM multimodal with Qwen2-VL
llm = LLM(
    model="Qwen/Qwen2-VL-7B-Instruct",
    tensor_parallel_size=2,
    gpu_memory_utilization=0.85,
    max_model_len=4096,
    limit_mm_per_prompt={"image": 5},   # max images per prompt
)

# Process image + text
from PIL import Image
import base64, io

def encode_image(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode()

sampling_params = SamplingParams(temperature=0.1, max_tokens=512)

outputs = llm.generate(
    {
        "prompt": "<|im_start|>user\n<|vision_start|><|image_pad|><|vision_end|>Extract all line items from this receipt as JSON.<|im_end|>\n<|im_start|>assistant\n",
        "multi_modal_data": {
            "image": Image.open("receipt.jpg"),
        },
    },
    sampling_params,
)
```

**Architecture consideration**: Vision encoders (the ViT component) run during prefill and are compute-intensive. For high-throughput image processing, consider running image encoding as a separate service (can scale independently) and passing pre-encoded features to the LLM server.

---

## 6. Disaggregated Prefill-Decode in Production

**Context**: A high-traffic API endpoint (>5,000 RPM). Mixed workload: some requests have 2k-token context (RAG), others have 100-token prompts (chat). The RAG prefill is starving the chat requests of GPU time.

```python
# Prefill-Decode disaggregation with vLLM (v0.6+)
# Prefill workers: optimized for long-context processing
# Decode workers: optimized for high-concurrency short generation

# prefill_server.py
from vllm import LLM
from vllm.config import KVTransferConfig

prefill_llm = LLM(
    model="meta-llama/Meta-Llama-3.1-70B-Instruct",
    tensor_parallel_size=4,
    kv_transfer_config=KVTransferConfig(
        kv_connector="PyNcclConnector",  # NCCL for intra-node transfer
        kv_role="kv_producer",           # this is the prefill worker
        kv_rank=0,
        kv_parallel_size=2,
    ),
    enable_chunked_prefill=True,
    max_num_batched_tokens=16384,  # large prefill batches
)

# decode_server.py
decode_llm = LLM(
    model="meta-llama/Meta-Llama-3.1-70B-Instruct",
    tensor_parallel_size=4,
    kv_transfer_config=KVTransferConfig(
        kv_connector="PyNcclConnector",
        kv_role="kv_consumer",           # this is the decode worker
        kv_rank=1,
        kv_parallel_size=2,
    ),
    max_num_seqs=256,    # high concurrency decode
)
```

**When this pays off**: The 23× throughput improvement from disaggregated prefill (Google's DistServe paper) is measured at high load. At < 500 RPM, the operational complexity exceeds the benefit. Threshold: when prefill requests regularly block decode requests for > 50ms, disaggregation is worth it.

---

## 7. Fine-Tuned Model Serving + Hot-Swapping

**Context**: A platform with 50 customer-specific fine-tuned models (QLoRA adapters). Each customer has a few hundred to a few thousand requests per day. Loading 50 full models is not economically viable.

**LoRA adapter multiplexing** (vLLM's `--enable-lora`):

```python
from vllm import LLM, SamplingParams
from vllm.lora.request import LoRARequest

# Load base model once
llm = LLM(
    model="meta-llama/Meta-Llama-3.1-8B-Instruct",
    enable_lora=True,
    max_lora_rank=64,
    max_loras=8,       # up to 8 adapters resident in GPU memory simultaneously
    max_cpu_loras=50,  # up to 50 adapters in CPU memory (swapped in/out as needed)
)

sampling_params = SamplingParams(temperature=0.7, max_tokens=256)

# Route request to appropriate LoRA adapter
def handle_request(customer_id: str, prompt: str):
    lora_path = f"/adapters/{customer_id}"
    return llm.generate(
        [prompt],
        sampling_params,
        lora_request=LoRARequest(
            lora_name=customer_id,
            lora_int_id=hash(customer_id) % 1000,  # unique int ID
            lora_local_path=lora_path,
        ),
    )

# Customer A
output = handle_request("customer-123", "Summarize this support ticket: ...")

# Customer B (different adapter, same base model, same GPU)
output = handle_request("customer-456", "Classify this email intent: ...")
```

**Economics**: A single A100 serving 8B base model + up to 8 hot adapters serves 50 customers. Without adapter multiplexing, you'd need 50 separate deployments. ~50× cost reduction for long-tail customers.

**Adapter swap latency**: Swapping an adapter from CPU to GPU takes ~50–200ms depending on adapter rank and model size. For predictable latency, pre-warm frequently used adapters by keeping them in GPU memory.
