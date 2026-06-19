"""
Entry point: reads dataset/claims.csv and writes output.csv.

Usage:
    python main.py [--input PATH] [--output PATH]

Defaults:
    --input  ../dataset/claims.csv
    --output ../output.csv
"""

import argparse
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import diskcache
import pandas as pd
from dotenv import load_dotenv

# Ensure the code/ directory is on the path so sibling imports work
sys.path.insert(0, str(Path(__file__).parent))

load_dotenv(Path(__file__).parents[1] / ".env")

from data.loader import load_claims
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
    parser.add_argument("--input", default=None, help="Path to claims.csv")
    parser.add_argument("--output", default=str(Path(__file__).parents[1] / "output.csv"))
    args = parser.parse_args()

    config = config_from_env()
    logger.info(f"Provider: {config.provider} | Model: {config.model}")

    cache_dir = Path(__file__).parents[1] / os.environ.get("CACHE_DIR", "code/cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = diskcache.Cache(str(cache_dir))

    df = load_claims(args.input)
    rows = df.to_dict("records")
    logger.info(f"Processing {len(rows)} claims...")

    max_workers = int(os.environ.get("MAX_CONCURRENCY", 1))
    results = [None] * len(rows)

    if max_workers == 1:
        for i, row in enumerate(rows):
            logger.info(f"  [{i+1}/{len(rows)}] {row['user_id']}")
            results[i] = process_claim(row, config, cache)
    else:
        futures = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for i, row in enumerate(rows):
                future = executor.submit(process_claim, row, config, cache)
                futures[future] = i
            for future in as_completed(futures):
                i = futures[future]
                try:
                    results[i] = future.result()
                    logger.info(f"  Done [{i+1}/{len(rows)}] {rows[i]['user_id']}")
                except Exception as e:
                    logger.error(f"  Failed [{i+1}] {rows[i]['user_id']}: {e}")

    out_df = pd.DataFrame(results, columns=OUTPUT_COLUMNS)
    out_df.to_csv(args.output, index=False)
    logger.info(f"Output written to {args.output}")
    cache.close()


if __name__ == "__main__":
    main()
