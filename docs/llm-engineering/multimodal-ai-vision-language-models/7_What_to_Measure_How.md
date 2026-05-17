# What to Measure & How

## Metrics Tables

### Quality
| Metric | Definition | Note |
|---|---|---|
| Task accuracy | metric per task (F1/EM/answer acc/action success) | on real inputs |
| Visual hallucination rate | answers asserting absent/misread content | headline reliability metric |
| Grounding accuracy | IoU / pointing / UI-element hit rate | for "where" tasks |
| Robustness delta | clean vs degraded-input accuracy | small = robust |
| Abstention correctness | correct "can't tell from image" | controls hallucination |

### Multimodal RAG
| Metric | Definition |
|---|---|
| Retrieval recall@k (right modality) | relevant visual/text retrieved |
| Answer faithfulness | grounded in retrieved evidence (RAGAS) |
| Retrieval-vs-generation error split | localize the failure |

### Cost / Latency
| Metric | Definition | Target |
|---|---|---|
| Image tokens / request | by resolution/tiling/frames | budgeted |
| Cost / successful task | $ incl. image tokens | vs text baseline |
| Latency p95 | incl. vision encode | within SLO |
| Resolution operating point | accuracy-vs-image-token knee | per use case |

## Instrumentation

Track image tokens explicitly (OTel GenAI; see *LLM Observability & LLMOps*):

```python
with tracer.start_as_current_span("chat vlm") as s:
    s.set_attribute("gen_ai.request.model", model)
    s.set_attribute("mm.modalities", "text,image")
    s.set_attribute("mm.image_count", n_images)
    s.set_attribute("mm.resolution_tier", "high")     # cost knob
    s.set_attribute("gen_ai.usage.input_tokens", u.input)       # includes image tokens
    s.set_attribute("gen_ai.usage.image_tokens", u.image)       # break out the driver
    s.set_attribute("eval.visual_hallucination", halluc_flag)
```

Break image tokens out from text tokens — otherwise the cost driver is invisible.

## Alerting Rules (sketch)

- `visual_hallucination_rate` ↑ vs baseline (esp. after model/resolution change) → block/rollback.
- `image_tokens_per_request` jump (resolution/frame policy drift) → cost review.
- `cost_per_successful_task` > budget for a multimodal feature → page owner.
- `grounding_accuracy < threshold` on a screen-agent surface → gate the agent.
- New VLM/provider version → re-run task + hallucination + cost sweep before ramp.

## Dashboard Checklist

- Task accuracy + visual-hallucination rate trend, by model/resolution.
- Accuracy-vs-image-token curve with current resolution operating point.
- Image tokens & cost per successful task vs text-only baseline.
- Grounding accuracy for "where"/UI surfaces.
- Multimodal-RAG: retrieval recall vs answer faithfulness (split view).
- Robustness panel: clean vs degraded-input accuracy.
