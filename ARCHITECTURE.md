# Architecture — Multi-Modal Evidence Review

## Overview

This system verifies damage claims by combining image evidence (via a Vision Language Model), structured claim context, user history, and evidence requirements. It reads `dataset/claims.csv` and produces `output.csv` with a structured prediction for each row.

Two runtime modes are supported via a single `.env` switch:

| Mode | Model | Purpose |
|---|---|---|
| `ollama` | `llama3.2-vision:11b` (local) | Fast iteration and prompt tuning |
| `claude` | `claude-sonnet-4-6` (cloud) | Final scored output |

---

## Repository Layout

```
.
├── AGENTS.md
├── ARCHITECTURE.md                  ← this file
├── problem_statement.md
├── README.md
├── .env                             ← secrets and mode switch (never committed)
├── .env.example                     ← committed template
├── code/
│   ├── main.py                      ← entry point: claims.csv → output.csv
│   ├── requirements.txt
│   ├── pipeline/
│   │   ├── claim_processor.py       ← per-claim orchestration
│   │   ├── llm_client.py            ← unified Ollama / Claude interface
│   │   ├── prompt_builder.py        ← constructs VLM prompt with all context
│   │   └── output_parser.py         ← JSON → validated OutputRow (Pydantic)
│   ├── data/
│   │   ├── loader.py                ← CSV loading, user_history and evidence_req lookups
│   │   └── image_utils.py           ← load, resize, base64-encode images
│   ├── cache/                       ← disk cache (git-ignored)
│   └── evaluation/
│       ├── main.py                  ← runs pipeline on sample_claims.csv
│       ├── metrics.py               ← field-level accuracy, confusion matrix
│       └── evaluation_report.md     ← cost / latency / token analysis (generated)
└── dataset/
    ├── sample_claims.csv            ← labeled (inputs + expected outputs)
    ├── claims.csv                   ← input-only (run system on this)
    ├── user_history.csv
    ├── evidence_requirements.csv
    └── images/
        ├── sample/
        └── test/
```

---

## Data Flow

```
claims.csv
    │
    ▼
loader.py ──────────────────────────────────────────────────────┐
    │  loads each row, attaches:                                 │
    │  • user_history (from user_history.csv by user_id)         │
    │  • evidence_requirement (from evidence_requirements.csv    │
    │    by claim_object + issue family)                         │
    ▼                                                            │
image_utils.py                                                   │
    │  for each image_path:                                      │
    │  • load from disk                                          │
    │  • resize to max 1024 px                                   │
    │  • encode to base64                                        │
    ▼                                                            │
prompt_builder.py                                                │
    │  assembles one prompt containing:                          │
    │  • system role + output schema instructions                │
    │  • inline evidence requirement text                        │
    │  • user history summary + risk context                     │
    │  • claim conversation (user_claim)                         │
    │  • all encoded images                                      │
    ▼                                                            │
llm_client.py  ──── .env: LLM_PROVIDER ────► Ollama | Claude   │
    │  sends prompt + images in one VLM call                     │
    │  enforces JSON output mode                                 │
    │  retries on transient errors (tenacity)                    │
    ▼                                                            │
output_parser.py                                                 │
    │  parses raw JSON response                                  │
    │  validates against Pydantic OutputRow schema               │
    │  coerces values to allowed enumerations                    │
    ▼                                                            │
output.csv  ◄───────────────────────────────────────────────────┘
```

---

## VLM Call Design

Each claim is processed in a **single VLM call** containing all images and all relevant context. This avoids multi-step chaining overhead and is appropriate at the ~44-claim scale of this challenge.

### Prompt structure (per claim)

```
[SYSTEM]
You are a damage-claim review agent. Analyze the submitted images and
return a JSON object matching the required schema exactly.
Allowed values for each field: <enum lists from problem_statement>

[EVIDENCE REQUIREMENT]
<relevant row from evidence_requirements.csv for this claim_object and issue family>

[USER HISTORY]
Past claims: N | Accepted: A | Rejected: R | Manual review: M
Risk flags: <history_flags>
Summary: <history_summary>

[CLAIM CONVERSATION]
<user_claim verbatim>

[TASK]
Object type: <claim_object>
Images attached: <count>

Inspect each image carefully. Return a single JSON object with these fields:
evidence_standard_met, evidence_standard_met_reason, risk_flags, issue_type,
object_part, claim_status, claim_status_justification, supporting_image_ids,
valid_image, severity

[IMAGES]
<base64-encoded images passed as vision content>
```

---

## LLM Client Interface

`llm_client.py` exposes a single function regardless of provider:

```python
def call_vlm(
    prompt: str,
    images: list[bytes],   # raw image bytes, resized
    model_config: ModelConfig,
) -> str:                  # raw JSON string
```

Internally it dispatches to:

- **Ollama**: `POST /api/chat` with `model`, `messages` (role=user, content with image parts), `format="json"`, `stream=false`
- **Claude**: `anthropic.Anthropic().messages.create(...)` with `model`, `messages` containing `image` content blocks + text

Both paths return the raw JSON string; parsing is handled downstream.

---

## Caching Layer

Disk cache keyed by `sha256(image_bytes_concatenated + prompt_template_hash)`.

- Implemented with `diskcache.Cache` stored in `code/cache/`.
- Cache is **read before every VLM call** and **written after a successful response**.
- Speeds up iterative prompt tuning — unchanged claims on the same images are never re-sent.
- Invalidated by bumping the prompt template version string in `.env` (`PROMPT_VERSION=v1`).
- Cache directory is git-ignored.

---

## Output Schema (Pydantic)

```python
class OutputRow(BaseModel):
    user_id: str
    image_paths: str
    user_claim: str
    claim_object: Literal["car", "laptop", "package"]
    evidence_standard_met: bool
    evidence_standard_met_reason: str
    risk_flags: str          # semicolon-separated or "none"
    issue_type: IssueType    # enum
    object_part: str         # validated per claim_object
    claim_status: Literal["supported", "contradicted", "not_enough_information"]
    claim_status_justification: str
    supporting_image_ids: str  # semicolon-separated or "none"
    valid_image: bool
    severity: Literal["none", "low", "medium", "high", "unknown"]
```

If the VLM returns an invalid enum value, `output_parser.py` attempts fuzzy coercion (e.g. `"dented"` → `"dent"`) before failing hard.

---

## Evaluation Pipeline

`code/evaluation/main.py`:

1. Runs the full pipeline on `dataset/sample_claims.csv` (20 labeled rows).
2. Compares each output field against the ground truth.
3. Reports per-field exact-match accuracy and a confusion matrix for `claim_status`.

Primary tuning metric: **`claim_status` exact-match accuracy** across the 20 sample rows.

Secondary metrics tracked: `evidence_standard_met`, `severity`, `issue_type`, `valid_image`.

`risk_flags` is evaluated as a set-match (order-insensitive).

---

## Environment Configuration

`.env.example` (committed):

```env
# ── Mode switch ────────────────────────────────────────────────
LLM_PROVIDER=ollama             # ollama | claude

# ── Ollama (local testing) ─────────────────────────────────────
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2-vision:11b

# ── Claude (final output) ──────────────────────────────────────
ANTHROPIC_API_KEY=               # set in real .env, never commit
CLAUDE_MODEL=claude-sonnet-4-6

# ── Shared ─────────────────────────────────────────────────────
PROMPT_VERSION=v1                # bump to invalidate cache
CACHE_DIR=code/cache
MAX_CONCURRENCY=3                # 1 for Ollama, 3-5 for Claude
IMAGE_MAX_PX=1024                # resize limit before encoding
```

`.env` (local only, git-ignored) contains the real `ANTHROPIC_API_KEY`.

---

## Dependencies

```
anthropic          # Claude API
ollama             # Ollama Python client
pandas             # CSV I/O
Pillow             # image load and resize
python-dotenv      # .env loading
tenacity           # retry + exponential backoff
diskcache          # disk-based VLM response cache
pydantic           # output schema validation
asyncio / httpx    # concurrent requests (Claude mode)
```

---

## Cost and Latency Estimate

Assumptions: Claude Sonnet 4.6 pricing, ~2 images per claim at 1024 px max, ~800 input tokens of text context per claim.

| Dataset | Claims | Images | Est. Input tokens | Est. Output tokens | Est. Cost |
|---|---|---|---|---|---|
| sample | 20 | ~30 | ~120 K | ~10 K | ~$0.40 |
| test | 44 | ~70 | ~260 K | ~22 K | ~$0.85 |

Ollama (local): cost $0, latency ~5–15 s per claim depending on GPU.

Claude (cloud): ~2–5 s per claim with `MAX_CONCURRENCY=3`, total runtime ~2–3 min for the test set.

---

## Local LLM Options (Ollama)

| Model | VRAM | Quality | Notes |
|---|---|---|---|
| `llama3.2-vision:11b` | ~8 GB | ★★★★ | **Recommended default** |
| `qwen2.5vl:7b` | ~6 GB | ★★★★ | Strong alternative; excellent at structured output |
| `minicpm-v:8b` | ~6 GB | ★★★ | Good if GPU < 8 GB |
| `moondream` | ~2 GB | ★★ | Last resort on very low VRAM |

---

## Cloud LLM Options

| Model ID | Strengths | Use case |
|---|---|---|
| `claude-sonnet-4-6` | Best cost/quality, excellent structured JSON | **Final output (default)** |
| `claude-haiku-4-5-20251001` | 10× cheaper, slightly lower quality | Budget alternative |
| `claude-opus-4-8` | Highest quality, 5× more expensive | Only if Sonnet misses hard cases |

---

## Key Design Decisions

**Single VLM call per claim** — At 44 claims the overhead of multi-step chaining (extract intent → analyze image → synthesize) is not justified. One prompt with all context is simpler and easier to debug.

**Evidence requirements injected into prompt** — Rather than relying on the model's general knowledge of what constitutes sufficient evidence, the relevant `minimum_image_evidence` text is injected verbatim. This anchors the `evidence_standard_met` decision to the dataset's defined standard.

**Disk cache by content hash** — Prompt tuning requires running the same images many times. Caching saves API cost and iteration time without changing the output contract.

**Pydantic validation as a gate** — The output is not written to CSV until it passes schema validation. Coercion is attempted first; hard failures are logged with the raw model output for debugging.

**Ollama for development, Claude for submission** — Local iteration is free and fast. The final run on `claims.csv` uses Claude Sonnet, which produces more reliable structured output and better visual reasoning on ambiguous cases.
