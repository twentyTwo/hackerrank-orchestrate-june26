# Multi-Modal Evidence Review — Solution

Verifies damage claims using images, conversation transcripts, user history, and evidence requirements.

## Requirements

Python 3.11+

```bash
pip install -r requirements.txt
```

## Configuration

Copy `.env.example` to `.env` and fill in your settings:

```bash
cp ../.env.example ../.env
```

Key settings:

| Variable | Description |
|---|---|
| `LLM_PROVIDER` | `ollama` (local testing) or `claude` (final output) |
| `ANTHROPIC_API_KEY` | Required when `LLM_PROVIDER=claude` |
| `OLLAMA_MODEL` | Ollama model name (default: `llama3.2-vision:11b`) |
| `CLAUDE_MODEL` | Claude model ID (default: `claude-sonnet-4-6`) |
| `PROMPT_VERSION` | Bump to invalidate the disk cache |
| `MAX_CONCURRENCY` | `1` for Ollama, `3`–`5` for Claude |

## Run — final output

```bash
# from the code/ directory
python main.py
```

Writes `output.csv` to the repo root.

Optional flags:

```bash
python main.py --input ../dataset/claims.csv --output ../output.csv
```

## Run — evaluation on sample data

```bash
python evaluation/main.py
```

Writes:
- `../evaluation_predictions.csv` — predictions for all sample rows
- `evaluation/evaluation_report.md` — accuracy metrics and operational analysis

## Local testing with Ollama

1. Install [Ollama](https://ollama.com) and pull a vision model:

```bash
ollama pull llama3.2-vision:11b
# or
ollama pull qwen2.5vl:7b
```

2. Set `LLM_PROVIDER=ollama` in `.env`.
3. Run evaluation: `python evaluation/main.py`
4. Iterate on prompts in `pipeline/prompt_builder.py`, bump `PROMPT_VERSION` in `.env` to clear cache.

## Cloud run with Claude

1. Set `LLM_PROVIDER=claude` and `ANTHROPIC_API_KEY=<your key>` in `.env`.
2. Set `MAX_CONCURRENCY=3` for parallel processing.
3. Run: `python main.py`

## Project layout

```
code/
├── main.py                    # entry point → output.csv
├── requirements.txt
├── data/
│   ├── loader.py              # CSV loading and lookups
│   └── image_utils.py         # image resize + base64 encoding
├── pipeline/
│   ├── llm_client.py          # unified Ollama / Claude interface
│   ├── prompt_builder.py      # constructs the VLM prompt
│   ├── output_parser.py       # JSON parsing + Pydantic validation
│   └── claim_processor.py     # per-claim orchestration + caching
└── evaluation/
    ├── main.py                # evaluation entry point
    ├── metrics.py             # accuracy, F1, confusion matrix
    └── evaluation_report.md   # generated after running evaluation
```
