# Glossary

Key terms across all clusters. These also appear as hover tooltips on
every page (look for the dotted underline).

## A

**Agent** [↗](https://www.anthropic.com/research/building-effective-agents)
: An LLM-driven system that plans and takes actions via tools to accomplish a goal.

**ANN** [↗](https://en.wikipedia.org/wiki/Nearest_neighbor_search)
: Approximate Nearest Neighbor search: fast similarity lookup that trades exactness for speed.

## C

**Choreography**
: Services react to events independently with no central coordinator.

**Chunking**
: Splitting documents into smaller passages before embedding and indexing.

**Concept drift**
: A shift in the relationship P(Y|X) so past patterns no longer hold.

**Confusion matrix**
: A table of true/false positives and negatives for a classifier.

**Context window**
: The maximum number of tokens a model can attend to in one request.

**Continuous batching**
: Dynamically adding/removing requests from a running inference batch to maximize GPU use.

## D

**Data contract** [↗](https://docs.getdbt.com/docs/collaborate/govern/model-contracts)
: An enforced agreement on the schema and semantics of data between producer and consumer.

**Data drift**
: A shift in the input distribution P(X) over time.

**Data mesh** [↗](https://martinfowler.com/articles/data-mesh-principles.html)
: A decentralized approach treating data as a product owned by domain teams.

**Dead-letter queue**
: A queue holding messages that could not be processed successfully.

**Dependency inversion**
: Depend on abstractions, not concrete implementations.

**Design pattern** [↗](https://refactoring.guru/design-patterns)
: A reusable, named solution to a recurring software design problem.

**DPO** [↗](https://arxiv.org/abs/2305.18290)
: Direct Preference Optimization: preference alignment without a separate reward model.

## E

**Embedding** [↗](https://www.sbert.net/)
: A dense numeric vector representing the meaning of text so similar items sit close together.

**Eval** [↗](https://docs.anthropic.com/en/docs/test-and-evaluate/develop-tests)
: A structured test that scores a model's quality on representative inputs.

**Event-driven architecture** [↗](https://martinfowler.com/articles/201701-event-driven.html)
: A style where components communicate by producing and reacting to events.

**Eventual consistency**
: A model where replicas converge to the same state given enough time without updates.

**Experiment tracking** [↗](https://mlflow.org/docs/latest/index.html)
: Recording parameters, metrics, and artifacts across training runs for comparison.

## F

**F1 score** [↗](https://en.wikipedia.org/wiki/F-score)
: The harmonic mean of precision and recall.

**Factory**
: A pattern that creates objects without exposing concrete construction logic.

**Feature store** [↗](https://docs.feast.dev/)
: Infrastructure that stores and serves features consistently for training and inference.

**Fine-tuning** [↗](https://huggingface.co/docs/transformers/training)
: Continuing training of a pretrained model on task- or domain-specific data.

## H

**Hallucination**
: Confident model output that is unsupported or factually wrong.

## I

**Idempotency**
: An operation that produces the same result no matter how many times it is applied.

## K

**KV cache**
: Cached attention keys/values from prior tokens so each new token is cheap to generate.

## L

**Latency**
: Time to complete a single request, end to end.

**Liskov substitution**
: Subtypes must be usable anywhere their base type is expected.

**LoRA** [↗](https://arxiv.org/abs/2106.09685)
: Low-Rank Adaptation: fine-tuning by training small added matrices instead of all weights.

## M

**Message broker**
: Middleware that routes messages between producers and consumers.

**MLOps** [↗](https://cloud.google.com/architecture/mlops-continuous-delivery-and-automation-pipelines-in-machine-learning)
: Engineering practices for reliably building, deploying, and operating ML in production.

**Model registry**
: A versioned catalog of trained models and their lifecycle stage.

## O

**Orchestration**
: A central coordinator explicitly directs each step of a workflow.

## P

**PagedAttention** [↗](https://arxiv.org/abs/2309.06180)
: A memory technique that pages the KV cache to boost LLM serving throughput.

**PEFT** [↗](https://huggingface.co/docs/peft/index)
: Parameter-Efficient Fine-Tuning: methods that update only a small fraction of model parameters.

**Precision** [↗](https://scikit-learn.org/stable/modules/model_evaluation.html)
: Of the items predicted positive, the fraction that are actually positive.

**Prompt caching** [↗](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching)
: Reusing computation for a repeated prompt prefix to cut cost and latency.

## Q

**QLoRA** [↗](https://arxiv.org/abs/2305.14314)
: LoRA applied on top of a quantized base model to cut fine-tuning memory dramatically.

**Quantization**
: Representing model weights/activations in fewer bits to reduce memory and speed inference.

## R

**RAG** [↗](https://arxiv.org/abs/2005.11401)
: Retrieval-Augmented Generation: grounding LLM output in documents fetched at inference time.

**ReAct** [↗](https://arxiv.org/abs/2210.03629)
: An agent pattern interleaving reasoning steps with tool actions.

**Recall** [↗](https://scikit-learn.org/stable/modules/model_evaluation.html)
: Of the actual positives, the fraction the model correctly identified.

**Reranking**
: A second-stage model that reorders retrieved candidates by relevance to the query.

**RLHF**
: Reinforcement Learning from Human Feedback: aligning a model using human preference signals.

**ROC AUC**
: Area under the ROC curve: probability a random positive ranks above a random negative.

## S

**Saga** [↗](https://microservices.io/patterns/data/saga.html)
: A sequence of local transactions with compensating actions for distributed consistency.

**Singleton**
: A pattern ensuring a class has exactly one shared instance.

**SOLID** [↗](https://en.wikipedia.org/wiki/SOLID)
: Five OO design principles: SRP, OCP, LSP, ISP, DIP.

**Strategy**
: A pattern that makes interchangeable algorithms selectable at runtime.

## T

**Throughput**
: Work completed per unit time, e.g. tokens or requests per second.

**Token**
: The sub-word unit LLMs read and generate; billing and context limits are counted in tokens.

**Tool use** [↗](https://docs.anthropic.com/en/docs/build-with-claude/tool-use/overview)
: Letting a model call external functions/APIs via structured outputs.

**Training-serving skew**
: Discrepancy between features computed at training time and at serving time.

**TTFT**
: Time To First Token: latency from request until the first output token streams back.

## V

**Vector database** [↗](https://www.pinecone.io/learn/vector-database/)
: A store optimized for similarity search over embedding vectors.
