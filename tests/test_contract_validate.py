"""M2 task 2: every validator check gets a test that makes it fail.

A check that has never been seen failing is untested code — and this validator is the only thing
standing between Crew 2 and a quietly broken file.
"""

from __future__ import annotations

import pandas as pd
import pytest

from hv.contract import CHECK_NAMES, apply_human_fields, build_contract, validate
from tests.synthetic import clean_frame, write_frame


@pytest.fixture
def built(tmp_path):
    """A clean frame, its CSV on disk, and the contract measured from it."""
    df = clean_frame()
    csv = write_frame(df, tmp_path / "clean_data.csv")
    return df, csv, build_contract(df, source="tests/synthetic.py", clean_csv=csv)


# ---------------------------------------------------------------- the happy path
def test_the_clean_file_passes_its_own_contract(built):
    _, csv, contract = built
    report = validate(csv, contract)
    assert report.passed, report.to_markdown()
    assert report.failures == []
    assert {c.name for c in report.checks} <= set(CHECK_NAMES)


def test_a_passing_report_reads_as_passed(built):
    _, csv, contract = built
    md = validate(csv, contract).to_markdown()
    assert "PASSED" in md and "agrees with the contract" in md


# ---------------------------------------------------------------- one failing test per check
def test_integrity_fails_when_the_file_changed_after_the_contract(built):
    df, csv, contract = built
    df.iloc[:10].to_csv(csv, index=False, lineterminator="\n")  # same columns, different bytes
    report = validate(csv, contract)
    assert "integrity" in report.failed_names
    assert "differs from" in next(c.message for c in report.failures if c.name == "integrity")


def test_check_hash_false_skips_integrity_entirely(built):
    df, csv, contract = built
    df.iloc[:10].to_csv(csv, index=False, lineterminator="\n")
    report = validate(csv, contract, check_hash=False)
    assert "integrity" not in {c.name for c in report.checks}
    assert "rows" in report.failed_names  # the row loss is still caught


def test_columns_fails_on_a_missing_column_and_hints_the_closest_name(built):
    df, _, contract = built
    report = validate(df.rename(columns={"OrderCount": "order_count"}), contract)
    assert "columns" in report.failed_names
    missing = next(c for c in report.failures if c.name == "columns" and c.column == "OrderCount")
    assert "declared in the contract but missing" in missing.message
    assert missing.hint == "closest name in the data: 'order_count'"


def test_columns_fails_on_an_undeclared_column(built):
    df, _, contract = built
    report = validate(df.assign(SecretScore=1), contract)
    unexpected = next(c for c in report.failures if c.name == "columns" and c.column == "SecretScore")
    assert "not declared in the contract" in unexpected.message


def test_dtype_fails_when_a_number_becomes_text(built):
    df, _, contract = built
    report = validate(df.assign(CityTier=df["CityTier"].astype(str)), contract)
    assert "dtype" in report.failed_names
    failure = next(c for c in report.failures if c.name == "dtype")
    assert failure.column == "CityTier"
    assert "declared int, found category" in failure.message


def test_values_fails_on_a_category_outside_allowed_values(built):
    df, _, contract = built
    broken = df.copy()
    broken.loc[0, "PreferredPaymentMode"] = "CC"  # the raw spelling the cleaning step maps away
    report = validate(broken, contract)
    assert "values" in report.failed_names
    failure = next(c for c in report.failures if c.name == "values")
    assert "outside allowed_values" in failure.message and "CC" in failure.message


def test_range_fails_and_names_the_unit_change_on_a_hundredfold(built):
    df, _, contract = built
    report = validate(df.assign(CashbackAmount=df["CashbackAmount"] * 100), contract)
    assert "range" in report.failed_names
    failure = next(c for c in report.failures if c.name == "range")
    assert failure.column == "CashbackAmount"
    assert failure.hint == "ratio ~= 100 - looks like a unit change"


def test_range_fails_without_a_unit_hint_when_the_ratio_is_ordinary(built):
    df, _, contract = built
    broken = df.copy()
    broken.loc[0, "Tenure"] = 999.0
    failure = next(c for c in validate(broken, contract).failures if c.name == "range")
    assert failure.column == "Tenure" and failure.hint is None


def test_nulls_fails_when_a_nullable_column_gains_nulls(built):
    df, _, contract = built
    broken = df.copy()
    broken.loc[[0, 1], "Tenure"] = None  # contract declares 4 nulls, this makes 6
    failure = next(c for c in validate(broken, contract).failures if c.name == "nulls")
    assert failure.column == "Tenure" and "contract declares up to 4" in failure.message


def test_nulls_fails_when_a_non_nullable_column_gains_one(built):
    df, _, contract = built
    broken = df.copy()
    broken.loc[0, "Gender"] = None
    failure = next(c for c in validate(broken, contract).failures if c.name == "nulls")
    assert failure.column == "Gender" and "declared not nullable" in failure.message


def test_rows_fails_when_rows_disappear(built):
    df, _, contract = built
    failure = next(c for c in validate(df.iloc[:18], contract).failures if c.name == "rows")
    assert "18 rows, contract declares 20" in failure.message


def test_key_fails_on_a_duplicate_primary_key(built):
    df, _, contract = built
    broken = df.copy()
    broken.loc[1, "CustomerID"] = broken.loc[0, "CustomerID"]
    failure = next(c for c in validate(broken, contract).failures if c.name == "key")
    assert failure.column == "CustomerID" and "1 duplicate" in failure.message


def test_key_fails_when_the_target_is_not_binary(built):
    df, _, contract = built
    broken = df.copy()
    broken.loc[0, "Churn"] = 2
    failures = [c for c in validate(broken, contract).failures if c.name == "key"]
    assert failures and failures[0].column == "Churn"
    assert failures[0].hint == "the target must be binary 0/1 with no nulls"


def test_key_fails_when_the_primary_key_is_gone(built):
    df, _, contract = built
    report = validate(df.drop(columns=["CustomerID"]), contract)
    assert any(c.name == "key" and "missing from the data" in c.message for c in report.failures)


def test_features_fails_when_crew_two_asks_for_a_protected_column(built):
    df, _, contract = built
    report = validate(df, contract, required_features=["Tenure", "Gender"])
    failures = [c for c in report.failures if c.name == "features"]
    assert [c.column for c in failures] == ["Gender"]
    assert "not declared as a feature" in failures[0].message


def test_features_fails_when_a_required_column_is_not_in_the_contract(built):
    df, _, contract = built
    report = validate(df, contract, required_features=["cashback_per_order"])
    assert [c.column for c in report.failures if c.name == "features"] == ["cashback_per_order"]


# ---------------------------------------------------------------- reporting behaviour
def test_two_breaks_are_reported_together(built):
    df, _, contract = built
    broken = df.rename(columns={"OrderCount": "order_count"}).assign(
        CashbackAmount=df["CashbackAmount"] * 100
    )
    report = validate(broken, contract)
    assert {"columns", "range"} <= report.failed_names
    assert len(report.failures) >= 3  # missing OrderCount, unexpected order_count, cashback range


def test_a_failing_report_lists_every_failure_in_markdown(built):
    df, _, contract = built
    report = validate(df.iloc[:18], contract)
    md = report.to_markdown()
    assert "FAILED" in md and "must not train" in md
    assert md.count("\n|") >= len(report.failures) + 2  # header, separator, one row per failure


def test_prose_cannot_change_the_verdict(built):
    df, csv, contract = built
    before = validate(csv, contract).to_dict()
    talked_up = apply_human_fields(
        contract,
        descriptions={"CashbackAmount": "always in whole dollars, verified twice"},
        rationales={"CashbackAmount": "trust me"},
        assumptions=["the data is perfect"],
    )
    after = validate(csv, talked_up).to_dict()
    assert before == after


def test_prose_cannot_rescue_broken_data(built):
    df, _, contract = built
    talked_up = apply_human_fields(contract, descriptions={"CityTier": "text is fine here"})
    report = validate(df.assign(CityTier=df["CityTier"].astype(str)), talked_up)
    assert not report.passed and "dtype" in report.failed_names


def test_a_contract_can_be_passed_as_a_path(built, tmp_path):
    from hv.contract import save_contract

    df, csv, contract = built
    path = tmp_path / "dataset_contract.json"
    save_contract(contract, path)
    assert validate(csv, path).passed


def test_every_check_name_is_one_of_the_documented_names(built):
    df, csv, contract = built
    broken = pd.concat([df, df.iloc[[0]]], ignore_index=True).assign(Extra=1)
    report = validate(broken, contract, required_features=["Gender"])
    assert {c.name for c in report.checks} <= set(CHECK_NAMES)
    assert not report.passed
