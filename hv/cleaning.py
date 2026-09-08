"""Deterministic cleaning: strip → entity map → duplicates → casts → sort. Never imputes (PLAN.md §3.3)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

from hv.config import CSV_KW, ENTITY_MAP, PRIMARY_KEY
from hv.ingest import sha256_file

# columns that are integers by meaning; cast only when they carry no nulls (nullable numerics stay float)
INT_COLUMNS = [
    "CustomerID",
    "Churn",
    "CityTier",
    "Complain",
    "SatisfactionScore",
    "NumberOfDeviceRegistered",
    "NumberOfAddress",
]


@dataclass
class CleaningReport:
    rows_in: int = 0
    rows_out: int = 0
    duplicate_rows_dropped: int = 0
    duplicate_ids_dropped: int = 0
    duplicate_records_dropped: int = 0  # identical in every column except the primary key (D-M1-1)
    entity_fixes: dict[str, dict[str, int]] = field(default_factory=dict)
    dtype_casts: dict[str, str] = field(default_factory=dict)
    nulls_kept: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _is_text(s: pd.Series) -> bool:
    return pd.api.types.is_string_dtype(s) or pd.api.types.is_object_dtype(s)


def clean(df: pd.DataFrame, drop_duplicate_records: bool = True) -> tuple[pd.DataFrame, CleaningReport]:
    """Return a cleaned copy and a report of exactly what changed.

    drop_duplicate_records: rows equal in every column except CustomerID are collapsed to the lowest id
    (decision D-M1-1). Set False to keep them.
    """
    rep = CleaningReport(rows_in=int(len(df)))
    out = df.copy()

    # 1 whitespace
    for col in out.columns:
        if _is_text(out[col]):
            out[col] = out[col].str.strip()

    # 2 entity map
    for col, mapping in ENTITY_MAP.items():
        if col not in out.columns:
            continue
        counts = {old: int((out[col] == old).sum()) for old in mapping}
        counts = {k: v for k, v in counts.items() if v}
        if counts:
            rep.entity_fixes[col] = counts
            out[col] = out[col].replace(mapping)

    # 3 exact duplicate rows
    before = len(out)
    out = out.drop_duplicates(keep="first")
    rep.duplicate_rows_dropped = before - len(out)

    # 4 duplicate ids (keep the first occurrence)
    before = len(out)
    out = out.drop_duplicates(subset=[PRIMARY_KEY], keep="first")
    rep.duplicate_ids_dropped = before - len(out)

    # 5 duplicate records: same values, different id → keep the lowest id (D-M1-1)
    if drop_duplicate_records:
        non_key = [c for c in out.columns if c != PRIMARY_KEY]
        out = out.sort_values(PRIMARY_KEY, kind="stable")
        before = len(out)
        out = out.drop_duplicates(subset=non_key, keep="first")
        rep.duplicate_records_dropped = before - len(out)

    # 6 casts: integer-by-meaning columns without nulls → int64
    for col in INT_COLUMNS:
        if col in out.columns and out[col].notna().all():
            if not pd.api.types.is_integer_dtype(out[col]):
                out[col] = out[col].astype("int64")
            rep.dtype_casts[col] = "int"

    # 7 order
    out = out.sort_values(PRIMARY_KEY, kind="stable").reset_index(drop=True)

    rep.rows_out = int(len(out))
    rep.nulls_kept = {c: int(n) for c, n in out.isna().sum().items() if n}
    return out, rep


def write_clean(df: pd.DataFrame, path: Path) -> str:
    """Write the CSV with the project's deterministic settings; return its sha256."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, **CSV_KW)
    return sha256_file(path)
