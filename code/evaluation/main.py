"""
Evaluation entry point: runs the pipeline on sample_claims.csv and reports
field-level accuracy against the ground truth.

Usage:
    python evaluation/main.py [--sample PATH] [--predictions PATH] [--report PATH]

Defaults:
    --sample       ../dataset/sample_claims.csv
    --predictions  ../evaluation_predictions.csv  (intermediate, not submitted)
    --report       ./evaluation_report.md
"""

import argparse
import logging
import os
import sys
from pathlib import Path

import diskcache
import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parents[1]))

load_dotenv(Path(__file__).parents[2] / ".env")

from data.loader import load_sample_claims
from evaluation.metrics import compute_metrics, print_report
from pipeline.claim_processor import process_claim
from pipeline.llm_client import config_from_env

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

OUTPUT_COLUMNS = [
    "user_id", "image_paths", "user_claim", "claim_object",
    "evidence_standard_met", "evidence_standard_met_reason", "risk_flags",
    "issue_type", "object_part", "claim_status", "claim_status_justification",
    "supporting_image_ids", "valid_image", "severity",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", default=None)
    parser.add_argument("--predictions", default=str(Path(__file__).parents[2] / "evaluation_predictions.csv"))
    parser.add_argument("--report", default=str(Path(__file__).parent / "evaluation_report.md"))
    args = parser.parse_args()

    config = config_from_env()
    logger.info(f"Provider: {config.provider} | Model: {config.model}")

    cache_dir = Path(__file__).parents[2] / os.environ.get("CACHE_DIR", "code/cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = diskcache.Cache(str(cache_dir))

    gold_df = load_sample_claims(args.sample)
    rows = gold_df.to_dict("records")
    logger.info(f"Evaluating {len(rows)} sample claims...")

    results = []
    for i, row in enumerate(rows):
        logger.info(f"  [{i+1}/{len(rows)}] {row['user_id']}")
        result = process_claim(row, config, cache)
        results.append(result)

    pred_df = pd.DataFrame(results, columns=OUTPUT_COLUMNS)
    pred_df.to_csv(args.predictions, index=False)
    logger.info(f"Predictions written to {args.predictions}")

    metrics = compute_metrics(pred_df, gold_df)
    report_text = print_report(metrics, pred_df, gold_df)

    _write_markdown_report(args.report, metrics, pred_df, gold_df, config)
    logger.info(f"Report written to {args.report}")
    cache.close()


def _write_markdown_report(path: str, metrics: dict, pred_df: pd.DataFrame, gold_df: pd.DataFrame, config):
    from evaluation.metrics import confusion_matrix_str

    provider = config.provider
    model = config.model

    lines = [
        "# Evaluation Report",
        "",
        "## Configuration",
        f"- Provider: `{provider}`",
        f"- Model: `{model}`",
        f"- Sample rows: {len(pred_df)}",
        "",
        "## Field-Level Accuracy",
        "| Field | Score |",
        "|---|---|",
    ]
    for k, v in metrics.items():
        lines.append(f"| `{k}` | {v:.3f} |")

    labels = ["supported", "contradicted", "not_enough_information"]
    cm = confusion_matrix_str(pred_df["claim_status"], gold_df["claim_status"], labels)
    lines += [
        "",
        "## Confusion Matrix — claim_status",
        "Rows = gold, Columns = predicted",
        "",
        "```",
        cm,
        "```",
        "",
        "## Operational Analysis",
        "",
        f"- Model calls for sample set: {len(pred_df)} (one per claim)",
        f"- Model calls for test set: ~44 (one per claim)",
        "- Images per claim: 1–3 (avg ~1.5)",
        "- Approx input tokens per claim: ~800 text + ~1 000–2 000 image tokens per image",
        "- Approx output tokens per claim: ~200",
        "- Estimated total input tokens (test set): ~260 000",
        "- Estimated total output tokens (test set): ~9 000",
        "- Estimated cost (claude-sonnet-4-6): ~$0.85",
        "- Approx latency: 2–5 s per claim; ~2–3 min total with MAX_CONCURRENCY=3",
        "- Caching: disk cache keyed by image + prompt hash; repeated runs on same data are free",
        "- Rate limits: Sonnet allows 4 000 RPM / 400 KTPM on Tier 1 — no throttling needed at this scale",
        "- Retry strategy: tenacity exponential backoff (3 attempts, 2–30 s)",
    ]

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
