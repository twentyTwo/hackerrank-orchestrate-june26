import json
import re
from typing import Any, Optional

from pydantic import BaseModel, field_validator, model_validator
from typing import Literal

ISSUE_TYPES = {
    "dent", "scratch", "crack", "glass_shatter", "broken_part", "missing_part",
    "torn_packaging", "crushed_packaging", "water_damage", "stain", "none", "unknown",
}

CAR_PARTS = {
    "front_bumper", "rear_bumper", "door", "hood", "windshield", "side_mirror",
    "headlight", "taillight", "fender", "quarter_panel", "body", "unknown",
}

LAPTOP_PARTS = {
    "screen", "keyboard", "trackpad", "hinge", "lid", "corner", "port", "base", "body", "unknown",
}

PACKAGE_PARTS = {
    "box", "package_corner", "package_side", "seal", "label", "contents", "item", "unknown",
}

VALID_PARTS: dict[str, set] = {"car": CAR_PARTS, "laptop": LAPTOP_PARTS, "package": PACKAGE_PARTS}

RISK_FLAGS = {
    "none", "blurry_image", "cropped_or_obstructed", "low_light_or_glare", "wrong_angle",
    "wrong_object", "wrong_object_part", "damage_not_visible", "claim_mismatch",
    "possible_manipulation", "non_original_image", "text_instruction_present",
    "user_history_risk", "manual_review_required",
}

_ISSUE_ALIASES = {
    "dented": "dent", "scratched": "scratch", "cracked": "crack",
    "shattered": "glass_shatter", "glass shatter": "glass_shatter",
    "broken": "broken_part", "missing": "missing_part",
    "torn": "torn_packaging", "crushed": "crushed_packaging",
    "water": "water_damage", "stained": "stain",
}

_PART_ALIASES = {
    "front bumper": "front_bumper", "rear bumper": "rear_bumper",
    "side mirror": "side_mirror", "front_glass": "windshield",
    "glass": "windshield", "bumper": "rear_bumper",
}


class VLMOutput(BaseModel):
    evidence_standard_met: bool
    evidence_standard_met_reason: str
    risk_flags: str
    issue_type: str
    object_part: str
    claim_status: Literal["supported", "contradicted", "not_enough_information"]
    claim_status_justification: str
    supporting_image_ids: str
    valid_image: bool
    severity: Literal["none", "low", "medium", "high", "unknown"]

    @field_validator("issue_type", mode="before")
    @classmethod
    def coerce_issue_type(cls, v: Any) -> str:
        v = str(v).strip().lower().replace(" ", "_")
        if v in ISSUE_TYPES:
            return v
        alias = _ISSUE_ALIASES.get(v.replace("_", " "), v)
        return alias if alias in ISSUE_TYPES else "unknown"

    @field_validator("risk_flags", mode="before")
    @classmethod
    def coerce_risk_flags(cls, v: Any) -> str:
        if isinstance(v, list):
            v = ";".join(str(x) for x in v)
        parts = [p.strip().lower() for p in str(v).split(";") if p.strip()]
        valid = [p for p in parts if p in RISK_FLAGS]
        return ";".join(valid) if valid else "none"

    @field_validator("supporting_image_ids", mode="before")
    @classmethod
    def coerce_image_ids(cls, v: Any) -> str:
        if isinstance(v, list):
            v = ";".join(str(x) for x in v)
        return str(v).strip() or "none"

    @field_validator("object_part", mode="before")
    @classmethod
    def normalise_part(cls, v: Any) -> str:
        v_norm = str(v).strip().lower().replace(" ", "_")
        alias = _PART_ALIASES.get(v_norm.replace("_", " "), v_norm)
        return alias if alias else "unknown"


def _extract_json(text: str) -> dict:
    text = text.strip()
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Extract first JSON object from text
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    raise ValueError(f"No valid JSON found in model output:\n{text[:500]}")


def parse_vlm_output(raw: str, claim_object: str) -> VLMOutput:
    data = _extract_json(raw)
    output = VLMOutput(**data)
    # Validate object_part against the claim_object's allowed set
    allowed = VALID_PARTS.get(claim_object, set())
    if allowed and output.object_part not in allowed:
        output.object_part = "unknown"
    return output


def fallback_output() -> VLMOutput:
    return VLMOutput(
        evidence_standard_met=False,
        evidence_standard_met_reason="Model output could not be parsed.",
        risk_flags="manual_review_required",
        issue_type="unknown",
        object_part="unknown",
        claim_status="not_enough_information",
        claim_status_justification="Automated review failed; manual review required.",
        supporting_image_ids="none",
        valid_image=False,
        severity="unknown",
    )
