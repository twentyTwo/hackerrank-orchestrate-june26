import os
from pathlib import Path
from typing import Optional

import pandas as pd

DATASET_DIR = Path(__file__).resolve().parents[2] / "dataset"


def load_claims(csv_path: Optional[str] = None) -> pd.DataFrame:
    path = csv_path or str(DATASET_DIR / "claims.csv")
    return pd.read_csv(path)


def load_sample_claims(csv_path: Optional[str] = None) -> pd.DataFrame:
    path = csv_path or str(DATASET_DIR / "sample_claims.csv")
    return pd.read_csv(path)


def load_user_history() -> dict:
    df = pd.read_csv(DATASET_DIR / "user_history.csv")
    return {row["user_id"]: row.to_dict() for _, row in df.iterrows()}


def load_evidence_requirements() -> pd.DataFrame:
    return pd.read_csv(DATASET_DIR / "evidence_requirements.csv")


def get_evidence_requirements_for(claim_object: str, df: pd.DataFrame) -> list[dict]:
    mask = df["claim_object"].isin([claim_object, "all"])
    return df[mask].to_dict("records")


def resolve_image_paths(image_paths_str: str) -> list[Path]:
    paths = [p.strip() for p in image_paths_str.split(";") if p.strip()]
    return [DATASET_DIR / p for p in paths]


def get_image_ids(image_paths_str: str) -> list[str]:
    paths = [p.strip() for p in image_paths_str.split(";") if p.strip()]
    return [Path(p).stem for p in paths]
