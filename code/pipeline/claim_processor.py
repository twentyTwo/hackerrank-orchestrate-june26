import hashlib
import logging
import os
from pathlib import Path

import diskcache
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from data.image_utils import load_and_encode
from data.loader import (
    get_image_ids,
    resolve_image_paths,
    load_evidence_requirements,
    load_user_history,
)
from pipeline.llm_client import ModelConfig, call_vlm
from pipeline.output_parser import VLMOutput, fallback_output, parse_vlm_output
from pipeline.prompt_builder import SYSTEM_PROMPT, build_user_prompt

logger = logging.getLogger(__name__)

_evidence_reqs = None
_user_history = None


def _get_evidence_reqs():
    global _evidence_reqs
    if _evidence_reqs is None:
        _evidence_reqs = load_evidence_requirements()
    return _evidence_reqs


def _get_user_history():
    global _user_history
    if _user_history is None:
        _user_history = load_user_history()
    return _user_history


def _cache_key(system_prompt: str, user_prompt: str, images: list[tuple[bytes, str]], model: str, version: str) -> str:
    h = hashlib.sha256()
    h.update(system_prompt.encode())
    h.update(user_prompt.encode())
    for img_bytes, _ in images:
        h.update(img_bytes)
    h.update(model.encode())
    h.update(version.encode())
    return h.hexdigest()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def _call_with_retry(system_prompt, user_prompt, images, config):
    return call_vlm(system_prompt, user_prompt, images, config)


def process_claim(row: dict, config: ModelConfig, cache: diskcache.Cache) -> dict:
    user_id = row["user_id"]
    image_paths_str = row["image_paths"]
    user_claim = row["user_claim"]
    claim_object = row["claim_object"]

    max_px = int(os.environ.get("IMAGE_MAX_PX", 1024))
    prompt_version = os.environ.get("PROMPT_VERSION", "v1")

    image_ids = get_image_ids(image_paths_str)
    image_file_paths = resolve_image_paths(image_paths_str)

    images: list[tuple[bytes, str]] = []
    for p in image_file_paths:
        try:
            img_bytes, media_type = load_and_encode(p, max_px=max_px)
            images.append((img_bytes, media_type))
        except Exception as e:
            logger.warning(f"Could not load image {p}: {e}")

    history = _get_user_history().get(user_id, {
        "past_claim_count": 0, "accept_claim": 0, "manual_review_claim": 0,
        "rejected_claim": 0, "last_90_days_claim_count": 0,
        "history_flags": "none", "history_summary": "No history available.",
    })

    user_prompt = build_user_prompt(
        user_claim=user_claim,
        claim_object=claim_object,
        user_history=history,
        evidence_reqs=_get_evidence_reqs(),
        image_ids=image_ids,
    )

    key = _cache_key(SYSTEM_PROMPT, user_prompt, images, config.model, prompt_version)

    raw: str
    if key in cache:
        logger.debug(f"Cache hit for {user_id}")
        raw = cache[key]
    else:
        try:
            raw = _call_with_retry(SYSTEM_PROMPT, user_prompt, images, config)
            cache[key] = raw
        except Exception as e:
            logger.error(f"VLM call failed for {user_id}: {e}")
            output = fallback_output()
            return _build_result_row(row, output)

    try:
        output = parse_vlm_output(raw, claim_object)
    except Exception as e:
        logger.error(f"Parse failed for {user_id}: {e}\nRaw: {raw[:300]}")
        output = fallback_output()

    return _build_result_row(row, output)


def _build_result_row(row: dict, output: VLMOutput) -> dict:
    return {
        "user_id": row["user_id"],
        "image_paths": row["image_paths"],
        "user_claim": row["user_claim"],
        "claim_object": row["claim_object"],
        "evidence_standard_met": output.evidence_standard_met,
        "evidence_standard_met_reason": output.evidence_standard_met_reason,
        "risk_flags": output.risk_flags,
        "issue_type": output.issue_type,
        "object_part": output.object_part,
        "claim_status": output.claim_status,
        "claim_status_justification": output.claim_status_justification,
        "supporting_image_ids": output.supporting_image_ids,
        "valid_image": output.valid_image,
        "severity": output.severity,
    }
