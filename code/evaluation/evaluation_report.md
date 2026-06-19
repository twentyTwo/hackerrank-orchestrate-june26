# Evaluation Report

## Configuration
- Provider: `ollama`
- Model: `gemma4:latest`
- Sample rows: 20

## Field-Level Accuracy
| Field | Score |
|---|---|
| `claim_status` | 0.500 |
| `evidence_standard_met` | 0.650 |
| `severity` | 0.350 |
| `issue_type` | 0.550 |
| `valid_image` | 0.900 |
| `risk_flags_set_f1` | 0.506 |

## Confusion Matrix — claim_status
Rows = gold, Columns = predicted

```
                                       supported            contradicted  not_enough_information
               supported                       8                       0                       5
            contradicted                       3                       0                       2
  not_enough_information                       0                       0                       2
```

## Operational Analysis

- Model calls for sample set: 20 (one per claim)
- Model calls for test set: ~44 (one per claim)
- Images per claim: 1–3 (avg ~1.5)
- Approx input tokens per claim: ~800 text + ~1 000–2 000 image tokens per image
- Approx output tokens per claim: ~200
- Estimated total input tokens (test set): ~260 000
- Estimated total output tokens (test set): ~9 000
- Estimated cost (claude-sonnet-4-6): ~$0.85
- Approx latency: 2–5 s per claim; ~2–3 min total with MAX_CONCURRENCY=3
- Caching: disk cache keyed by image + prompt hash; repeated runs on same data are free
- Rate limits: Sonnet allows 4 000 RPM / 400 KTPM on Tier 1 — no throttling needed at this scale
- Retry strategy: tenacity exponential backoff (3 attempts, 2–30 s)