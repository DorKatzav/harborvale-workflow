"""The dataset contract and its validator (PLAN.md §3.5).

Crew 1 publishes `dataset_contract.json`; Crew 2 may assume nothing else about the data. The
contract carries two kinds of fields: **measured** facts produced here from the clean frame, and
**human** prose (`description`, `rationale`, `assumptions`) that an agent may write. The validator
ignores the human fields entirely, so no amount of confident prose can make broken data pass.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pandas as pd
import pandas.api.types as ptypes
from pydantic import BaseModel

from hv.config import PRIMARY_KEY, PROTECTED, TARGET, UNITS

HUMAN_FIELDS = {"description", "rationale"}  # + the top-level "assumptions"
CONTRACT_VERSION = "1.0"

Dtype = Literal["int", "float", "category", "bool"]
Role = Literal["id", "target", "feature", "protected"]


# ---------------------------------------------------------------- models
class ColumnSpec(BaseModel):
    name: str
    dtype: Dtype
    role: Role
    unit: str | None = None
    nullable: bool
    null_count: int
    allowed_values: list[str] | None = None  # category columns
    min: float | None = None  # numeric columns
    max: float | None = None
    description: str = ""  # HUMAN
    rationale: str = ""  # HUMAN


class DatasetSpec(BaseModel):
    row_count: int
    primary_key: str
    target: str
    target_positive_rate: float
    sha256: str


class Contract(BaseModel):
    contract_version: str = CONTRACT_VERSION
    produced_by: str
    created_at: str
    source: str
    dataset: DatasetSpec
    columns: list[ColumnSpec]
    assumptions: list[str] = []  # HUMAN

    def column(self, name: str) -> ColumnSpec | None:
        """The spec for one column, or None when the contract does not declare it."""
        return next((c for c in self.columns if c.name == name), None)


# ---------------------------------------------------------------- helpers
def file_sha256(path: Path) -> str:
    """sha256 of a file, read in chunks.

    M1's `hv/ingest.py` exposes the same helper; kept local so the contract module has no
    dependency on the other track. De-duplicate in M5 when both halves meet.
    """
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def classify_dtype(s: pd.Series) -> Dtype:
    """Map a pandas dtype onto the four contract dtypes.

    pandas 3 gives text columns the `str` dtype rather than `object`, so both are accepted here
    (D-M2-1 in PROJECT_LOG.md); a categorical column is text as far as the contract cares.
    """
    d = s.dtype
    if ptypes.is_bool_dtype(d):
        return "bool"
    if ptypes.is_integer_dtype(d):
        return "int"
    if ptypes.is_float_dtype(d):
        return "float"
    if isinstance(d, pd.CategoricalDtype) or ptypes.is_string_dtype(d) or ptypes.is_object_dtype(d):
        return "category"
    raise ValueError(f"column {s.name!r}: dtype {d} is not one of int / float / category / bool")


# ---------------------------------------------------------------- build
def build_contract(
    df: pd.DataFrame,
    source: str,
    clean_csv: Path,
    produced_by: str = "analyst_crew",
    dictionary: dict[str, str] | None = None,
) -> Contract:
    """Measure the clean frame and return the contract that describes it.

    Every field here is measured from `df`; `description` is pre-filled from the data dictionary
    when one is given, and an agent may overwrite it later through `apply_human_fields`.
    """
    missing = [c for c in (PRIMARY_KEY, TARGET) if c not in df.columns]
    if missing:
        raise ValueError(f"cannot build a contract without {missing}; got columns {list(df.columns)}")
    dictionary = dictionary or {}

    columns: list[ColumnSpec] = []
    for name in df.columns:
        s = df[name]
        dtype = classify_dtype(s)
        if name == PRIMARY_KEY:
            role: Role = "id"
        elif name == TARGET:
            role = "target"
        elif name in PROTECTED:
            role = "protected"
        else:
            role = "feature"
        null_count = int(s.isna().sum())
        allowed_values = None
        col_min = col_max = None
        if dtype == "category":
            allowed_values = sorted({str(v) for v in s.dropna()})
        elif dtype in ("int", "float") and s.notna().any():
            col_min = float(s.min())
            col_max = float(s.max())
        columns.append(
            ColumnSpec(
                name=name,
                dtype=dtype,
                role=role,
                unit=UNITS.get(name),
                nullable=null_count > 0,
                null_count=null_count,
                allowed_values=allowed_values,
                min=col_min,
                max=col_max,
                description=dictionary.get(name, ""),
            )
        )

    dataset = DatasetSpec(
        row_count=int(len(df)),
        primary_key=PRIMARY_KEY,
        target=TARGET,
        target_positive_rate=round(float(pd.to_numeric(df[TARGET]).mean()), 4),
        sha256=file_sha256(Path(clean_csv)),
    )
    return Contract(
        produced_by=produced_by,
        created_at=datetime.now(UTC).replace(microsecond=0).isoformat(),
        source=source,
        dataset=dataset,
        columns=columns,
    )


def apply_human_fields(
    c: Contract,
    descriptions: dict[str, str] = {},  # noqa: B006 - read-only, never mutated (signature per PLAN.md §3.5)
    rationales: dict[str, str] = {},  # noqa: B006
    assumptions: list[str] = [],  # noqa: B006
) -> Contract:
    """Return a copy of the contract with only the human fields replaced.

    There is deliberately no way to reach a measured field from here: `min`, `max`,
    `allowed_values` and the rest are not parameters, so passing them raises TypeError.
    """
    out = c.model_copy(deep=True)
    known = {col.name for col in out.columns}
    unknown = sorted((set(descriptions) | set(rationales)) - known)
    if unknown:
        raise KeyError(f"unknown column(s) {unknown}; the contract declares {sorted(known)}")
    for col in out.columns:
        if col.name in descriptions:
            col.description = descriptions[col.name]
        if col.name in rationales:
            col.rationale = rationales[col.name]
    if assumptions:
        out.assumptions = list(assumptions)
    return out


# ---------------------------------------------------------------- save / load
def save_contract(c: Contract, path: Path) -> None:
    """Write the contract as JSON, field order preserved so humans can read it top to bottom."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(c.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def load_contract(path: Path | str) -> Contract:
    """Read a contract back; a malformed file fails here, loudly, with pydantic's own message."""
    return Contract.model_validate_json(Path(path).read_text(encoding="utf-8"))
