# Products & Tools

## Inference Engines

### vLLM

The dominant open-source LLM serving engine for production. Originated at UC Berkeley (2023), now backed by vLLM team + Anyscale.

**Key capabilities:**
- PagedAttention + continuous batching (the original implementation)
- OpenAI-compatible REST API out of the box
- Multi-GPU tensor parallelism and pipeline parallelism
- AWQ, GPTQ, FP8, int8 quantization
- Speculative decoding (medusa, eagle, ngram)
- Guided generation (outlines, lm-format-enforcer)
- Multimodal support (LLaVA, Qwen-VL, etc.)
- Prefix caching: cache KV for shared system prompts across requests

```bash
# Install
pip install vllm

# Start OpenAI-compatible server
python -m vllm.entrypoints.openai.api_server \
  --model meta-llama/Meta-Llama-3.1-8B-Instruct \
  --tensor-parallel-size 2 \
  --gpu-memory-utilization 0.90 \
  --max-model-len 8192 \
  --enable-prefix-caching \
  --quantization awq \
  --port 8000
```

```python
# Python API
from vllm import LLM, SamplingParams

llm = LLM(
    model="meta-llama/Meta-Llama-3.1-8B-Instruct",
    tensor_parallel_size=2,
    gpu_memory_utilization=0.90,
    enable_prefix_caching=True,
    max_model_len=8192,
)

sampling_params = SamplingParams(
    temperature=0.7,
    top_p=0.9,
    max_tokens=512,
    stop=["</s>", "<|eot_id|>"],
)

outputs = llm.generate(["Explain tensor parallelism in LLM serving"], sampling_params)
for output in outputs:
    print(output.outputs[0].text)

# Async engine for production server
from vllm.engine.async_llm_engine import AsyncLLMEngine
from vllm.engine.arg_utils import AsyncEngineArgs

engine_args = AsyncEngineArgs(
    model="meta-llama/Meta-Llama-3.1-8B-Instruct",
    tensor_parallel_size=2,
    enable_chunked_prefill=True,
)
engine = AsyncLLMEngine.from_engine_args(engine_args)

async def generate_stream(prompt: str):
    from vllm import RequestOutput
    from vllm.sampling_params import SamplingParams
    sampling_params = SamplingParams(temperature=0.7, max_tokens=200)
    request_id = "req-001"
    async for output in engine.generate(prompt, sampling_params, request_id):
        if output.outputs:
            yield output.outputs[0].text
```

**vLLM on AWS**:
- Run on `p4d.24xlarge` (8× A100 40GB) or `p4de.24xlarge` (8× A100 80GB)
- Docker image: `vllm/vllm-openai:latest`
- EKS deployment with GPU node groups (instance type `p4d.24xlarge`, GPU plugin + device plugin)
- Use `--served-model-name` to present as `gpt-4` for drop-in OpenAI replacement

---

### Text Generation Inference (TGI) — Hugging Face

HuggingFace's production serving framework. Ships as the backend for the Inference API.

```python
# TGI Python client
from huggingface_hub import InferenceClient

client = InferenceClient("http://localhost:8080")

# Streaming generation
for token in client.text_generation(
    "What is Flash Attention?",
    max_new_tokens=200,
    stream=True,
    details=True,
):
    print(token.token.text, end="", flush=True)

# With messages API (chat)
response = client.chat_completion(
    messages=[{"role": "user", "content": "Explain PagedAttention"}],
    max_tokens=500,
    stream=False,
)
```

```bash
# TGI Docker
docker run --gpus all -p 8080:80 \
  -v $PWD/models:/data \
  ghcr.io/huggingface/text-generation-inference:2.3.1 \
  --model-id meta-llama/Meta-Llama-3.1-8B-Instruct \
  --num-shard 2 \
  --quantize bitsandbytes \
  --max-input-length 4096 \
  --max-total-tokens 8192
```

**TGI vs vLLM**: TGI is more battle-tested for Hugging Face model ecosystem (safetensors loading, token streaming edge cases). vLLM has better PagedAttention implementation and generally higher throughput benchmarks. Most new projects default to vLLM.

---

### TensorRT-LLM (NVIDIA)

NVIDIA's optimized inference library. The highest throughput option for NVIDIA GPUs, at the cost of significant compilation overhead.

**Key differentiators:**
- Custom CUDA/C++ kernels for every supported model architecture
- In-flight batching (NVIDIA's term for continuous batching)
- FP8 quantization on H100 (using hardware FP8 Tensor Cores)
- INT4 AWQ/GPTQ with custom dequantize-then-multiply kernels
- Inflight batching scheduler with chunked context

```python
# TensorRT-LLM: build engine first (one-time, hours)
import tensorrt_llm
from tensorrt_llm.models import LLaMAForCausalLM

# Convert HF weights → TRT-LLM checkpoint
# trtllm-build --checkpoint_dir ./llama-3-8b-trt-ckpt \
#              --output_dir ./llama-3-8b-engine \
#              --gemm_plugin bfloat16 \
#              --max_batch_size 64 \
#              --max_input_len 2048 \
#              --max_seq_len 4096

# Then serve via Triton Inference Server
# tritonserver --model-repository=/engines/
```

**When to choose TRT-LLM**: Maximum throughput on NVIDIA H100/A100 at the cost of multi-hour build time and locked model architecture. Production deployments at scale (>10k RPM) justify it. Not suitable for rapid iteration.

---

### llama.cpp

C++ inference for quantized GGUF models. The gold standard for CPU inference and consumer GPU (RTX 4090) inference.

```bash
# Build
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp && cmake -B build -DGGML_CUDA=ON && cmake --build build -j

# Run interactive
./build/bin/llama-cli \
  -m /models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf \
  --n-gpu-layers 35 \
  --ctx-size 8192 \
  --temp 0.7 \
  -p "You are a helpful assistant." \
  -i  # interactive mode

# Server (OpenAI-compatible)
./build/bin/llama-server \
  -m /models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf \
  --n-gpu-layers 35 \
  --ctx-size 8192 \
  --host 0.0.0.0 --port 8080 \
  --parallel 4 \
  --cont-batching
```

**Key params:**
- `--n-gpu-layers N`: offload first N layers to GPU (rest on CPU). Set to 99 for full GPU, adjust down for partial offload.
- `--ctx-size`: context window. KV cache scales with this.
- `--parallel`: simultaneous request slots for server mode.
- `--cont-batching`: continuous batching (enable for server use).

**Convert HF model → GGUF:**
```bash
python convert_hf_to_gguf.py /hf_model_path --outtype f16 --outfile model-f16.gguf
./build/bin/llama-quantize model-f16.gguf model-q4km.gguf Q4_K_M
```

---

## Gateway / Router Layer

### LiteLLM

Universal LLM API gateway. Single interface for 100+ LLM providers. Essential for multi-provider architectures, cost tracking, fallbacks.

```python
import litellm
from litellm import completion

# Unified interface: works with OpenAI, Anthropic, Bedrock, Vertex, Ollama, vLLM, TGI...
response = completion(
    model="anthropic/claude-3-5-sonnet-20241022",
    messages=[{"role": "user", "content": "Hello"}],
    max_tokens=100,
)

# Fallback chain: try claude, fall back to gpt-4, then local llama
response = completion(
    model="claude-3-5-sonnet-20241022",
    messages=[{"role": "user", "content": "Hello"}],
    fallbacks=["gpt-4o", "ollama/llama3.1"],
    num_retries=3,
)

# Async + streaming
import asyncio
from litellm import acompletion

async def stream_response():
    response = await acompletion(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Tell me about vLLM"}],
        stream=True,
    )
    async for chunk in response:
        if chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="")

asyncio.run(stream_response())
```

**LiteLLM Proxy Server** (for teams):
```yaml
# config.yaml
model_list:
  - model_name: gpt-4
    litellm_params:
      model: anthropic/claude-3-5-sonnet-20241022
      api_key: os.environ/ANTHROPIC_API_KEY

  - model_name: gpt-4
    litellm_params:
      model: bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0
      aws_region_name: us-east-1

  - model_name: llama-3
    litellm_params:
      model: openai/meta-llama/Meta-Llama-3.1-8B-Instruct
      api_base: http://vllm-server:8000/v1

router_settings:
  routing_strategy: least-busy  # or: latency-based-routing, cost-based-routing
  num_retries: 3
  timeout: 30

litellm_settings:
  success_callback: ["langfuse"]
  failure_callback: ["slack"]
  cache: true
  cache_params:
    type: redis
    host: redis-host
    port: 6379
```

```bash
litellm --config config.yaml --port 4000 --detailed_debug
```

---

### Ollama

Local model serving with a clean CLI and API. Manages model downloads, automatic GPU detection, memory-mapped GGUF.

```bash
# Install: curl -fsSL https://ollama.ai/install.sh | sh
ollama pull llama3.1:8b
ollama pull llama3.1:70b-q4_K_M
ollama run llama3.1:8b  # interactive

# API (OpenAI-compatible with --openai flag)
curl http://localhost:11434/api/generate -d '{
  "model": "llama3.1:8b",
  "prompt": "Explain tensor parallelism",
  "stream": false
}'
```

```python
from openai import OpenAI  # Ollama is OpenAI-compatible

client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
response = client.chat.completions.create(
    model="llama3.1:8b",
    messages=[{"role": "user", "content": "Hello"}],
)
```

**Ollama Modelfile** (custom system prompts + parameters):
```dockerfile
FROM llama3.1:8b
SYSTEM "You are a helpful coding assistant specializing in Python."
PARAMETER temperature 0.3
PARAMETER num_ctx 8192
PARAMETER num_predict 1024
```

---

## Cloud / Managed Inference

### AWS Bedrock

Fully managed inference for Claude, Llama, Mistral, Titan, Cohere, AI21. No GPU management.

```python
import boto3
import json

client = boto3.client("bedrock-runtime", region_name="us-east-1")

# Streaming invocation
response = client.invoke_model_with_response_stream(
    modelId="anthropic.claude-3-5-sonnet-20241022-v2:0",
    body=json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": "Explain vLLM's architecture"}],
    }),
    contentType="application/json",
)

for event in response["body"]:
    chunk = json.loads(event["chunk"]["bytes"])
    if chunk.get("type") == "content_block_delta":
        print(chunk["delta"]["text"], end="", flush=True)
```

**Bedrock Provisioned Throughput**: For consistent latency SLAs, purchase model units (MUs). Each MU guarantees N tokens/minute. Pays off at >80% utilization vs. on-demand.

### AWS SageMaker Inference

For self-managed model serving on SageMaker infrastructure:

```python
import sagemaker
from sagemaker.huggingface import HuggingFaceModel

# Deploy vLLM on SageMaker using DLC (Deep Learning Container)
huggingface_model = HuggingFaceModel(
    env={
        "HF_MODEL_ID": "meta-llama/Meta-Llama-3.1-8B-Instruct",
        "SM_NUM_GPUS": "4",
        "MAX_INPUT_LENGTH": "4096",
        "MAX_TOTAL_TOKENS": "8192",
        "HF_TOKEN": "...",
    },
    role=role,
    transformers_version="4.43.1",
    pytorch_version="2.1.0",
    py_version="py310",
    image_uri="763104351884.dkr.ecr.us-east-1.amazonaws.com/huggingface-pytorch-tgi-inference:2.1-tgi2.0-gpu-py310-cu121-ubuntu22.04",
)

predictor = huggingface_model.deploy(
    initial_instance_count=1,
    instance_type="ml.g5.12xlarge",  # 4× A10G 24GB
    container_startup_health_check_timeout=600,
)
```

---

## Quantization Tools

### AutoAWQ

```python
from awq import AutoAWQForCausalLM
from transformers import AutoTokenizer

model_path = "meta-llama/Meta-Llama-3.1-8B-Instruct"
quant_path = "llama-3.1-8b-awq-int4"

model = AutoAWQForCausalLM.from_pretrained(model_path, low_cpu_mem_usage=True)
tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)

quant_config = {
    "zero_point": True,
    "q_group_size": 128,   # quantize in groups of 128 weights
    "w_bit": 4,
    "version": "GEMM",     # GEMM is faster than GEMV for batched inference
}

model.quantize(tokenizer, quant_config=quant_config)
model.save_quantized(quant_path)
tokenizer.save_pretrained(quant_path)
```

### AutoGPTQ

```python
from auto_gptq import AutoGPTQForCausalLM, BaseQuantizeConfig
from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("meta-llama/Meta-Llama-3.1-8B-Instruct")
quantize_config = BaseQuantizeConfig(
    bits=4,
    group_size=128,
    damp_percent=0.01,
    desc_act=False,  # disable act-order for faster inference
)

model = AutoGPTQForCausalLM.from_pretrained(
    "meta-llama/Meta-Llama-3.1-8B-Instruct",
    quantize_config,
)

# Calibration data (128 samples from c4 or your domain data)
examples = tokenizer(calibration_texts, return_tensors="pt", padding=True)
model.quantize(examples)
model.save_quantized("llama-3.1-8b-gptq-4bit", use_safetensors=True)
```

---

## Observability

### OpenLLMetry / Langfuse / Helicone

```python
# Langfuse tracing with LiteLLM
import litellm
litellm.success_callback = ["langfuse"]

import os
os.environ["LANGFUSE_PUBLIC_KEY"] = "pk-..."
os.environ["LANGFUSE_SECRET_KEY"] = "sk-..."

# Every LiteLLM call now automatically traced:
# input tokens, output tokens, latency, model, cost, errors
response = litellm.completion(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello"}],
    metadata={
        "generation_name": "greeting-handler",  # Langfuse trace name
        "trace_user_id": "user-123",
    }
)
```
