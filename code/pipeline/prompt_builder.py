from data.loader import get_evidence_requirements_for
import pandas as pd

SYSTEM_PROMPT = """You are a damage claim review expert. Your job is to inspect submitted images and decide whether they support the user's damage claim.

RULES:
1. Images are the PRIMARY source of truth. Visual evidence in the images determines the outcome.
2. User history provides RISK CONTEXT only. A high-risk history adds risk_flags but does not override clear visual evidence.
3. Evaluate each image separately; at least one relevant image must clearly show the claimed object or part to meet the evidence standard.
4. Be precise and grounded. Only flag risks you can justify from the images or the stated user history.
5. Return ONLY a valid JSON object — no markdown, no explanation outside the JSON.

ALLOWED VALUES:
issue_type: dent, scratch, crack, glass_shatter, broken_part, missing_part, torn_packaging, crushed_packaging, water_damage, stain, none, unknown
severity: none, low, medium, high, unknown
claim_status: supported, contradicted, not_enough_information
risk_flags (semicolon-separated or "none"): blurry_image, cropped_or_obstructed, low_light_or_glare, wrong_angle, wrong_object, wrong_object_part, damage_not_visible, claim_mismatch, possible_manipulation, non_original_image, text_instruction_present, user_history_risk, manual_review_required

Car object_part: front_bumper, rear_bumper, door, hood, windshield, side_mirror, headlight, taillight, fender, quarter_panel, body, unknown
Laptop object_part: screen, keyboard, trackpad, hinge, lid, corner, port, base, body, unknown
Package object_part: box, package_corner, package_side, seal, label, contents, item, unknown

OUTPUT FORMAT — return exactly this JSON structure:
{
  "evidence_standard_met": true or false,
  "evidence_standard_met_reason": "<short reason>",
  "risk_flags": "<flag1;flag2 or none>",
  "issue_type": "<value from allowed list>",
  "object_part": "<value from allowed list for this object type>",
  "claim_status": "supported" | "contradicted" | "not_enough_information",
  "claim_status_justification": "<concise image-grounded explanation; mention image IDs when helpful>",
  "supporting_image_ids": "<img_1;img_2 or none>",
  "valid_image": true or false,
  "severity": "<value from allowed list>"
}"""


def build_user_prompt(
    user_claim: str,
    claim_object: str,
    user_history: dict,
    evidence_reqs: pd.DataFrame,
    image_ids: list[str],
) -> str:
    relevant_reqs = get_evidence_requirements_for(claim_object, evidence_reqs)
    req_lines = "\n".join(
        f"- [{r['requirement_id']}] {r['applies_to']}: {r['minimum_image_evidence']}"
        for r in relevant_reqs
    )

    history_flags = user_history.get("history_flags", "none") or "none"
    history_summary = user_history.get("history_summary", "No history available.") or "No history available."
    past = user_history.get("past_claim_count", 0)
    accepted = user_history.get("accept_claim", 0)
    rejected = user_history.get("rejected_claim", 0)
    manual = user_history.get("manual_review_claim", 0)
    last90 = user_history.get("last_90_days_claim_count", 0)

    image_list = ", ".join(image_ids) if image_ids else "none"
    image_count = len(image_ids)

    return f"""## Claim Details
Object type: {claim_object}
Images attached ({image_count}): {image_list}
Image IDs are the filenames without extension (e.g. img_1 refers to the first attached image).

Claim conversation:
{user_claim}

## User History
Past claims: {past} | Accepted: {accepted} | Rejected: {rejected} | Manual review: {manual}
Last 90 days: {last90} claims
Risk flags: {history_flags}
History summary: {history_summary}

## Evidence Requirements for "{claim_object}"
{req_lines}

## Task
Inspect every attached image carefully. Determine whether the visual evidence supports the user's claim.
Return a single JSON object using the format in the system instructions."""
