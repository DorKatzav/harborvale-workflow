"""The dataset contract and its validator (PLAN.md §3.5).

Crew 1 publishes `dataset_contract.json`; Crew 2 may assume nothing else about the data. The
contract carries two kinds of fields: **measured** facts produced here from the clean frame, and
**human** prose (`description`, `rationale`, `assumptions`) that an agent may write. The validator
ignores the human fields entirely, so no amount of confident prose can make broken data pass.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pandas as pd
import pandas.api.types as ptypes
from pydantic import BaseModel

from hv.config import PRIMARY_KEY, PROTECTED, READ_CSV_KW, SEED, TARGET, UNITS

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
    and both map to `category` (D-M2-3 in PROJECT_LOG.md); a categorical column is text as far
    as the contract cares.
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


# ---------------------------------------------------------------- validation
CHECK_NAMES = ("integrity", "columns", "dtype", "values", "range", "nulls", "rows", "key", "features")


@dataclass
class Check:
    """One question asked of the data, and the answer in words a human can act on."""

    name: str
    column: str | None
    passed: bool
    message: str
    hint: str | None = None


@dataclass
class ValidationReport:
    passed: bool
    checks: list[Check]
    source: str

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.passed]

    @property
    def failed_names(self) -> set[str]:
        """The distinct check names that failed - what the gate and the tests assert on."""
        return {c.name for c in self.failures}

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "source": self.source,
            "n_checks": len(self.checks),
            "n_failed": len(self.failures),
            "checks": [asdict(c) for c in self.checks],
        }

    def to_markdown(self) -> str:
        """The text of FAILED.md and of the app's break-it panel."""
        head = "PASSED" if self.passed else "FAILED"
        lines = [
            f"# Contract validation - {head}",
            "",
            f"**Source:** `{self.source}`  ",
            f"**Checks:** {len(self.checks) - len(self.failures)} passed, {len(self.failures)} failed",
            "",
        ]
        if self.passed:
            lines.append("The data agrees with the contract on every check.")
            return "\n".join(lines) + "\n"
        lines += ["| check | column | what is wrong | hint |", "|---|---|---|---|"]
        for c in self.failures:
            lines.append(f"| {c.name} | {c.column or '-'} | {c.message} | {c.hint or ''} |")
        lines += ["", "Crew 2 must not train on this file until the contract and the data agree."]
        return "\n".join(lines) + "\n"


def _unit_hint(observed_max: float, declared_max: float | None) -> str | None:
    """Name the x100 / x1000 smell - the Harbor & Vale incident was cents read as dollars."""
    if not declared_max or declared_max <= 0:
        return None
    ratio = observed_max / declared_max
    for factor in (100, 1000):
        if 0.9 * factor <= ratio <= 1.1 * factor:
            return f"ratio ~= {factor} - looks like a unit change"
    return None


def validate(
    data: Path | pd.DataFrame,
    contract: Contract | Path,
    required_features: list[str] | None = None,
    check_hash: bool = True,
) -> ValidationReport:
    """Compare data against a contract and report **every** disagreement, not just the first.

    A partial answer is worse than none here: the Flow shows this report to a human, so it runs all
    the checks and lists all the failures at once.
    """
    c = contract if isinstance(contract, Contract) else load_contract(contract)
    if isinstance(data, pd.DataFrame):
        df, path, source = data, None, "<DataFrame>"
    else:
        path = Path(data)
        df, source = pd.read_csv(path, **READ_CSV_KW), str(path)

    checks: list[Check] = []
    add = checks.append

    # integrity - is this the very file the contract was written for?
    if path is not None and check_hash:
        observed = file_sha256(path)
        ok = observed == c.dataset.sha256
        add(
            Check(
                "integrity",
                None,
                ok,
                f"sha256 {observed[:12]} {'matches' if ok else 'differs from'} "
                f"the contract's {c.dataset.sha256[:12]}",
                None if ok else "the clean file changed after the contract was written",
            )
        )

    # columns - declared vs present, in both directions
    declared = [col.name for col in c.columns]
    observed_cols = list(df.columns)
    missing = [n for n in declared if n not in observed_cols]
    unexpected = [n for n in observed_cols if n not in declared]
    for n in missing:
        close = difflib.get_close_matches(n, unexpected or observed_cols, n=1, cutoff=0.6)
        add(
            Check(
                "columns",
                n,
                False,
                f"column {n!r} is declared in the contract but missing from the data",
                f"closest name in the data: {close[0]!r}" if close else None,
            )
        )
    for n in unexpected:
        add(
            Check(
                "columns",
                n,
                False,
                f"column {n!r} is in the data but not declared in the contract",
                "declare it in the contract or drop it from the clean file",
            )
        )
    if not missing and not unexpected:
        add(Check("columns", None, True, f"all {len(declared)} declared columns present, none extra"))

    # per column: dtype, allowed values, range, nulls
    for spec in c.columns:
        if spec.name not in df.columns:
            continue
        s = df[spec.name]

        try:
            observed_dtype = classify_dtype(s)
        except ValueError as e:
            add(Check("dtype", spec.name, False, str(e)))
            continue
        ok = observed_dtype == spec.dtype
        add(
            Check(
                "dtype",
                spec.name,
                ok,
                f"declared {spec.dtype}, found {observed_dtype} (pandas {s.dtype})",
                None if ok else f"cast {spec.name} back to {spec.dtype} or update the contract",
            )
        )

        if spec.dtype == "category" and spec.allowed_values is not None:
            values = s.dropna().astype(str)
            offending = values[~values.isin(spec.allowed_values)]
            ok = offending.empty
            samples = sorted(set(offending))[:5]
            add(
                Check(
                    "values",
                    spec.name,
                    ok,
                    f"{len(offending)} row(s) hold a value outside allowed_values"
                    + (f"; e.g. {samples}" if samples else ""),
                    None if ok else f"allowed: {spec.allowed_values}",
                )
            )

        if spec.dtype in ("int", "float") and spec.min is not None and spec.max is not None:
            numeric = pd.to_numeric(s, errors="coerce")
            if numeric.notna().any():
                obs_min, obs_max = float(numeric.min()), float(numeric.max())
                below = obs_min < spec.min and not math.isclose(obs_min, spec.min, rel_tol=1e-9)
                above = obs_max > spec.max and not math.isclose(obs_max, spec.max, rel_tol=1e-9)
                ok = not (below or above)
                add(
                    Check(
                        "range",
                        spec.name,
                        ok,
                        f"observed [{obs_min:g}, {obs_max:g}] vs declared [{spec.min:g}, {spec.max:g}]"
                        + (f" {spec.unit}" if spec.unit else ""),
                        None if ok else _unit_hint(obs_max, spec.max),
                    )
                )

        observed_nulls = int(s.isna().sum())
        if not spec.nullable:
            ok = observed_nulls == 0
            add(
                Check(
                    "nulls",
                    spec.name,
                    ok,
                    f"{observed_nulls} null(s) in a column declared not nullable",
                    None if ok else "the contract says this column is always filled",
                )
            )
        else:
            ok = observed_nulls <= spec.null_count
            add(
                Check(
                    "nulls",
                    spec.name,
                    ok,
                    f"{observed_nulls} null(s), contract declares up to {spec.null_count}",
                    None if ok else "more nulls than Crew 1 measured - the file is not the clean file",
                )
            )

    # rows
    ok = len(df) == c.dataset.row_count
    add(
        Check(
            "rows",
            None,
            ok,
            f"{len(df)} rows, contract declares {c.dataset.row_count}",
            None if ok else "rows were added or dropped after the contract was written",
        )
    )

    # key - the primary key identifies a row, the target is binary
    pk = c.dataset.primary_key
    if pk not in df.columns:
        add(Check("key", pk, False, f"primary key {pk!r} is missing from the data"))
    else:
        duplicated, key_nulls = int(df[pk].duplicated().sum()), int(df[pk].isna().sum())
        ok = duplicated == 0 and key_nulls == 0
        add(
            Check(
                "key",
                pk,
                ok,
                f"{duplicated} duplicate and {key_nulls} null primary key value(s)",
                None if ok else "one row per customer is the whole point of the primary key",
            )
        )
    target = c.dataset.target
    if target not in df.columns:
        add(Check("key", target, False, f"target {target!r} is missing from the data"))
    else:
        values = set(df[target].dropna().unique())
        target_nulls = int(df[target].isna().sum())
        ok = values <= {0, 1} and target_nulls == 0
        add(
            Check(
                "key",
                target,
                ok,
                f"target values {sorted(values, key=str)}, {target_nulls} null(s)",
                None if ok else "the target must be binary 0/1 with no nulls",
            )
        )

    # features - everything Crew 2 asked for is declared, and declared as a feature
    for name in required_features or []:
        spec = c.column(name)
        ok = spec is not None and spec.role == "feature"
        add(
            Check(
                "features",
                name,
                ok,
                f"required feature {name!r} "
                + ("is declared with role 'feature'" if ok else "is not declared as a feature"),
                None if ok else "Crew 2 may only train on columns the contract marks as features",
            )
        )

    return ValidationReport(passed=all(ch.passed for ch in checks), checks=checks, source=source)


# ---------------------------------------------------------------- tampering
PRESETS = ["unit_change", "rename_column", "drop_contract_field", "bad_category", "dtype_change", "row_loss"]


def _require(df: pd.DataFrame, column: str, preset: str) -> None:
    if column not in df.columns:
        raise KeyError(f"preset {preset!r} needs the column {column!r}; got {list(df.columns)}")


def tamper(
    df: pd.DataFrame, c: Contract, preset: str, seed: int = SEED
) -> tuple[pd.DataFrame, Contract]:
    """Break the handoff on purpose, one realistic way at a time (PLAN.md §3.5).

    Returns a tampered copy of the frame and of the contract; the inputs are never modified. Each
    preset is something that has actually happened to somebody: a unit swapped, a column renamed in
    an upstream job, a contract row deleted, a raw spelling that came back, a number read as text,
    rows lost in a filter.
    """
    if preset not in PRESETS:
        raise ValueError(f"unknown preset {preset!r}; known presets: {PRESETS}")
    out, contract = df.copy(deep=True), c.model_copy(deep=True)

    if preset == "unit_change":
        _require(out, "CashbackAmount", preset)
        out["CashbackAmount"] = out["CashbackAmount"] * 100  # dollars read as cents
    elif preset == "rename_column":
        _require(out, "OrderCount", preset)
        out = out.rename(columns={"OrderCount": "order_count"})
    elif preset == "drop_contract_field":
        if contract.column("Tenure") is None:
            raise KeyError(f"preset {preset!r} needs Tenure to be declared in the contract")
        contract.columns = [col for col in contract.columns if col.name != "Tenure"]
    elif preset == "bad_category":
        _require(out, "PreferredPaymentMode", preset)
        picked = out.sample(frac=0.05, random_state=seed).index
        out.loc[picked, "PreferredPaymentMode"] = "CC"  # the raw spelling, un-cleaned
    elif preset == "dtype_change":
        _require(out, "CityTier", preset)
        # labels, not digits: "1" would be read straight back as an int and the break would vanish
        out["CityTier"] = "Tier " + out["CityTier"].astype(str)  # D-M2-2
    elif preset == "row_loss":
        dropped = out.sample(frac=0.10, random_state=seed).index
        out = out.drop(index=dropped)

    return out, contract
