"""Read the raw workbook exactly as it is on disk, plus a profile of what is in it (PLAN.md §3.2)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from hv.config import DICT_SHEET, PRIMARY_KEY, RAW_PATH, RAW_SHEET


def load_raw(path: Path = RAW_PATH, sheet: str = RAW_SHEET) -> pd.DataFrame:
    """The data sheet, untouched: no renames, no casts, no cleaning."""
    return pd.read_excel(path, sheet_name=sheet)


def load_data_dictionary(path: Path = RAW_PATH, sheet: str = DICT_SHEET) -> dict[str, str]:
    """{column: description} from the workbook's dictionary sheet; {} when the sheet is absent.

    The Kaggle sheet has a blank first column and a header row containing "Variable" followed by the
    description column (spelled "Discerption" in the file). We locate the header by content, not position.
    """
    try:
        raw = pd.read_excel(path, sheet_name=sheet, header=None)
    except ValueError:  # worksheet not found
        return {}
    for i in range(len(raw)):
        cells = ["" if pd.isna(v) else str(v).strip() for v in raw.iloc[i]]
        if "Variable" not in cells:
            continue
        vi = cells.index("Variable")
        di = vi + 1
        out: dict[str, str] = {}
        for j in range(i + 1, len(raw)):
            row = raw.iloc[j]
            var = row.iloc[vi]
            if pd.isna(var) or not str(var).strip():
                continue
            desc = row.iloc[di] if di < len(row) else None
            out[str(var).strip()] = "" if desc is None or pd.isna(desc) else str(desc).strip()
        return out
    return {}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_text(s: pd.Series) -> bool:
    return pd.api.types.is_string_dtype(s) or pd.api.types.is_object_dtype(s)


def profile(df: pd.DataFrame) -> dict:
    """Facts about a frame: shape, per-column nulls/uniques/samples, duplicates, numeric ranges."""
    columns: dict[str, dict] = {}
    numeric: dict[str, dict] = {}
    for col in df.columns:
        s = df[col]
        non_null = s.dropna()
        if _is_text(s):
            samples = [str(v) for v in non_null.value_counts().index[:10]]
        else:
            samples = [v.item() if hasattr(v, "item") else v for v in sorted(non_null.unique())[:10]]
        columns[col] = {
            "dtype": str(s.dtype),
            "null_count": int(s.isna().sum()),
            "n_unique": int(non_null.nunique()),
            "sample_values": samples,
        }
        if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
            numeric[col] = {
                "min": float(non_null.min()) if len(non_null) else None,
                "max": float(non_null.max()) if len(non_null) else None,
                "mean": round(float(non_null.mean()), 4) if len(non_null) else None,
                "std": round(float(non_null.std()), 4) if len(non_null) > 1 else None,
            }
    non_key = [c for c in df.columns if c != PRIMARY_KEY]
    return {
        "rows": int(len(df)),
        "cols": int(df.shape[1]),
        "columns": columns,
        "duplicate_rows": int(df.duplicated().sum()),
        "duplicate_ids": int(df[PRIMARY_KEY].duplicated().sum()) if PRIMARY_KEY in df.columns else 0,
        "duplicate_records": int(df.duplicated(subset=non_key).sum()),
        "numeric_describe": numeric,
    }
