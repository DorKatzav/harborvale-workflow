"""M2 task 3: every preset breaks the handoff, and breaks it in the way it claims to."""

from __future__ import annotations

import pytest

from hv.config import SEED
from hv.contract import PRESETS, build_contract, tamper, validate
from tests.synthetic import clean_frame, write_frame

# what each preset is supposed to trip, and nothing else
EXPECTED_FAILURES = {
    "unit_change": {"range"},
    "rename_column": {"columns"},
    "drop_contract_field": {"columns"},
    "bad_category": {"values"},
    "dtype_change": {"dtype"},
    "row_loss": {"rows"},
}


@pytest.fixture
def built(tmp_path):
    df = clean_frame()
    csv = write_frame(df, tmp_path / "clean_data.csv")
    return df, csv, build_contract(df, source="tests/synthetic.py", clean_csv=csv)


def test_the_six_presets_are_the_documented_ones():
    assert PRESETS == [
        "unit_change",
        "rename_column",
        "drop_contract_field",
        "bad_category",
        "dtype_change",
        "row_loss",
    ]
    assert set(PRESETS) == set(EXPECTED_FAILURES)


@pytest.mark.parametrize("preset", PRESETS)
def test_every_preset_fails_validation(built, preset):
    df, _, contract = built
    broken_df, broken_contract = tamper(df, contract, preset)
    report = validate(broken_df, broken_contract)
    assert not report.passed, f"{preset} slipped through the validator"


@pytest.mark.parametrize("preset", PRESETS)
def test_every_preset_trips_exactly_its_own_check(built, preset):
    df, _, contract = built
    broken_df, broken_contract = tamper(df, contract, preset)
    assert validate(broken_df, broken_contract).failed_names == EXPECTED_FAILURES[preset]


@pytest.mark.parametrize("preset", PRESETS)
def test_tamper_never_touches_its_inputs(built, preset):
    df, _, contract = built
    before_frame, before_contract = df.copy(deep=True), contract.model_copy(deep=True)
    tamper(df, contract, preset)
    assert df.equals(before_frame)
    assert contract == before_contract


def test_unit_change_multiplies_by_a_hundred_and_says_so(built):
    df, _, contract = built
    broken, _ = tamper(df, contract, "unit_change")
    assert broken["CashbackAmount"].max() == pytest.approx(df["CashbackAmount"].max() * 100)
    failure = next(c for c in validate(broken, contract).failures if c.name == "range")
    assert failure.hint == "ratio ~= 100 - looks like a unit change"


def test_rename_column_is_reported_with_the_new_name_as_a_hint(built):
    df, _, contract = built
    broken, _ = tamper(df, contract, "rename_column")
    assert "order_count" in broken.columns and "OrderCount" not in broken.columns
    hints = [c.hint for c in validate(broken, contract).failures if c.column == "OrderCount"]
    assert hints == ["closest name in the data: 'order_count'"]


def test_drop_contract_field_leaves_the_data_alone_and_the_contract_short(built):
    df, csv, contract = built
    broken_df, broken_contract = tamper(df, contract, "drop_contract_field")
    assert broken_df.equals(df)  # only the contract lost a row
    assert broken_contract.column("Tenure") is None
    assert len(broken_contract.columns) == len(contract.columns) - 1
    # the file is untouched, so its hash still matches: only the missing declaration fails
    report = validate(csv, broken_contract)
    assert report.failed_names == {"columns"}
    assert next(c for c in report.checks if c.name == "integrity").passed


def test_bad_category_puts_back_the_raw_spelling(built):
    df, _, contract = built
    broken, _ = tamper(df, contract, "bad_category")
    assert (broken["PreferredPaymentMode"] == "CC").sum() == 1  # 5% of 20 rows
    assert "CC" not in contract.column("PreferredPaymentMode").allowed_values


def test_row_loss_drops_a_tenth_of_the_rows(built):
    df, _, contract = built
    broken, _ = tamper(df, contract, "row_loss")
    assert len(broken) == 18
    assert broken.index.is_monotonic_increasing  # the surviving rows keep their order


@pytest.mark.parametrize("preset", ["bad_category", "row_loss"])
def test_the_sampled_presets_are_seeded(built, preset):
    df, _, contract = built
    first, _ = tamper(df, contract, preset, seed=SEED)
    again, _ = tamper(df, contract, preset, seed=SEED)
    other, _ = tamper(df, contract, preset, seed=SEED + 1)
    assert first.equals(again)
    assert not first.equals(other)


def test_an_unknown_preset_is_refused(built):
    df, _, contract = built
    with pytest.raises(ValueError, match="unknown preset"):
        tamper(df, contract, "delete_everything")


def test_a_preset_says_which_column_it_needs(built):
    df, _, contract = built
    with pytest.raises(KeyError, match="CashbackAmount"):
        tamper(df.drop(columns=["CashbackAmount"]), contract, "unit_change")


def test_dtype_change_writes_labels_not_digits(built):
    """D-M2-2: `astype(str)` turns 1 into "1", which a CSV reads straight back as an int.

    The break has to be a value that cannot be mistaken for a number, or it disappears on the way to
    Crew 2 - which is the one journey this whole project is about.
    """
    df, _, contract = built
    broken, _ = tamper(df, contract, "dtype_change")
    assert set(broken["CityTier"]) == {"Tier 1", "Tier 2", "Tier 3"}


def test_dtype_change_survives_a_csv_round_trip(built, tmp_path):
    df, _, contract = built
    broken, broken_contract = tamper(df, contract, "dtype_change")
    csv = write_frame(broken, tmp_path / "tampered.csv")
    report = validate(csv, broken_contract, check_hash=False)  # isolate it from the hash change
    assert report.failed_names == {"dtype"}
    assert next(c for c in report.failures if c.name == "dtype").column == "CityTier"
