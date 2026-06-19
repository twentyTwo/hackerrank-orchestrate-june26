from collections import defaultdict

import pandas as pd


def _flag_set(value: str) -> set:
    if pd.isna(value) or str(value).strip().lower() == "none":
        return set()
    return {f.strip() for f in str(value).split(";") if f.strip()}


def _id_set(value: str) -> set:
    if pd.isna(value) or str(value).strip().lower() == "none":
        return set()
    return {v.strip() for v in str(value).split(";") if v.strip()}


def exact_match(pred: pd.Series, gold: pd.Series) -> float:
    correct = (pred.astype(str).str.strip() == gold.astype(str).str.strip()).sum()
    return correct / len(gold) if len(gold) else 0.0


def bool_match(pred: pd.Series, gold: pd.Series) -> float:
    p = pred.astype(str).str.strip().str.lower().map({"true": True, "false": False})
    g = gold.astype(str).str.strip().str.lower().map({"true": True, "false": False})
    return (p == g).sum() / len(g) if len(g) else 0.0


def set_f1(pred: pd.Series, gold: pd.Series) -> float:
    total_p = total_r = 0.0
    n = len(pred)
    for p, g in zip(pred, gold):
        ps, gs = _flag_set(p), _flag_set(g)
        if not ps and not gs:
            total_p += 1.0
            total_r += 1.0
            continue
        if not ps or not gs:
            continue
        inter = len(ps & gs)
        total_p += inter / len(ps)
        total_r += inter / len(gs)
    precision = total_p / n if n else 0.0
    recall = total_r / n if n else 0.0
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def confusion_matrix_str(pred: pd.Series, gold: pd.Series, labels: list[str]) -> str:
    counts: dict[tuple, int] = defaultdict(int)
    for p, g in zip(pred.astype(str).str.strip(), gold.astype(str).str.strip()):
        counts[(g, p)] += 1

    col_w = max(len(l) for l in labels) + 2
    header = f"{'':>{col_w}}" + "".join(f"{l:>{col_w}}" for l in labels)
    lines = [header]
    for gold_label in labels:
        row = f"{gold_label:>{col_w}}"
        for pred_label in labels:
            row += f"{counts[(gold_label, pred_label)]:>{col_w}}"
        lines.append(row)
    return "\n".join(lines)


def compute_metrics(pred_df: pd.DataFrame, gold_df: pd.DataFrame) -> dict:
    shared_cols = [
        "claim_status", "evidence_standard_met", "severity",
        "issue_type", "valid_image", "risk_flags",
    ]

    metrics = {}
    for col in shared_cols:
        if col not in pred_df.columns or col not in gold_df.columns:
            continue
        if col in ("evidence_standard_met", "valid_image"):
            metrics[col] = bool_match(pred_df[col], gold_df[col])
        elif col == "risk_flags":
            metrics[col + "_set_f1"] = set_f1(pred_df[col], gold_df[col])
        else:
            metrics[col] = exact_match(pred_df[col], gold_df[col])

    return metrics


def print_report(metrics: dict, pred_df: pd.DataFrame, gold_df: pd.DataFrame) -> str:
    lines = []
    lines.append("=" * 60)
    lines.append("EVALUATION REPORT")
    lines.append("=" * 60)
    lines.append(f"Total rows: {len(pred_df)}")
    lines.append("")
    lines.append("Per-field accuracy / F1:")
    for k, v in metrics.items():
        lines.append(f"  {k:<35} {v:.3f}")

    lines.append("")
    lines.append("Confusion matrix — claim_status (rows=gold, cols=pred):")
    labels = ["supported", "contradicted", "not_enough_information"]
    lines.append(confusion_matrix_str(pred_df["claim_status"], gold_df["claim_status"], labels))
    lines.append("=" * 60)

    report = "\n".join(lines)
    print(report)
    return report
