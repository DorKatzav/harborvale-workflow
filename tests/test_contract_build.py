"""M2 task 1: the contract is measured from the data, and prose can never reach a measured field."""

from __future__ import annotations

import pytest

from hv.config import UNITS
from hv.contract import apply_human_fields, build_contract, file_sha256, load_contract, save_contract
from tests.synthetic import clean_frame, write_frame


@pytest.fixture
def built(tmp_path):
    df = clean_frame()
    csv = write_frame(df, tmp_path / "clean_data.csv")
    return df, csv, build_contract(df, source="tests/synthetic.py", clean_csv=csv)


def test_dtype_and_role_classification(built):
    _, _, c = built
    by_name = {col.name: col for col in c.columns}
    assert by_name["CustomerID"].dtype == "int" and by_name["CustomerID"].role == "id"
    assert by_name["Churn"].dtype == "int" and by_name["Churn"].role == "target"
    assert by_name["Gender"].role == "protected" and by_name["MaritalStatus"].role == "protected"
    assert by_name["Tenure"].dtype == "float" and by_name["Tenure"].role == "feature"
    assert by_name["PreferredPaymentMode"].dtype == "category"
    assert by_name["CityTier"].dtype == "int"  # cast to int by cleaning, so numeric in the contract


def test_category_columns_get_sorted_allowed_values(built):
    _, _, c = built
    mode = c.column("PreferredPaymentMode")
    assert mode.allowed_values == sorted(mode.allowed_values)
    assert mode.allowed_values == ["Cash on Delivery", "Credit Card", "Debit Card", "E wallet", "UPI"]
    assert mode.min is None and mode.max is None


def test_numeric_columns_get_min_max_and_no_allowed_values(built):
    df, _, c = built
    tenure = c.column("Tenure")
    assert tenure.allowed_values is None
    assert tenure.min == df["Tenure"].min() and tenure.max == df["Tenure"].max()


def test_unit_comes_from_config(built):
    _, _, c = built
    assert c.column("CashbackAmount").unit == UNITS["CashbackAmount"] == "USD"
    assert c.column("Tenure").unit == "months"
    assert c.column("Gender").unit is None  # not in UNITS


def test_nullable_and_null_count_are_measured(built):
    df, _, c = built
    for col in c.columns:
        observed = int(df[col.name].isna().sum())
        assert col.null_count == observed
        assert col.nullable is (observed > 0)
    assert c.column("Tenure").nullable is True
    assert c.column("CustomerID").nullable is False


def test_dataset_spec_records_rows_hash_and_positive_rate(built):
    df, csv, c = built
    assert c.dataset.row_count == len(df) == 20
    assert c.dataset.primary_key == "CustomerID" and c.dataset.target == "Churn"
    assert c.dataset.target_positive_rate == 0.2
    assert c.dataset.sha256 == file_sha256(csv)
    assert c.contract_version == "1.0" and c.produced_by == "analyst_crew"


def test_description_prefilled_from_the_data_dictionary(tmp_path):
    df = clean_frame()
    csv = write_frame(df, tmp_path / "clean_data.csv")
    c = build_contract(df, "s", csv, dictionary={"Tenure": "Tenure of a customer in the organization"})
    assert c.column("Tenure").description == "Tenure of a customer in the organization"
    assert c.column("Churn").description == ""


def test_build_contract_refuses_a_frame_without_key_or_target(tmp_path):
    df = clean_frame().drop(columns=["Churn"])
    csv = write_frame(df, tmp_path / "no_target.csv")
    with pytest.raises(ValueError, match="Churn"):
        build_contract(df, "s", csv)


def test_apply_human_fields_replaces_only_prose(built):
    _, _, c = built
    out = apply_human_fields(
        c,
        descriptions={"Tenure": "months since signup"},
        rationales={"Tenure": "strongest churn driver in the EDA"},
        assumptions=["one row per customer"],
    )
    assert out.column("Tenure").description == "months since signup"
    assert out.column("Tenure").rationale == "strongest churn driver in the EDA"
    assert out.assumptions == ["one row per customer"]
    # every measured field survived untouched, and the original object was not mutated
    for before, after in zip(c.columns, out.columns, strict=True):
        assert before.model_dump(exclude={"description", "rationale"}) == after.model_dump(
            exclude={"description", "rationale"}
        )
    assert c.column("Tenure").description == ""


def test_apply_human_fields_rejects_an_unknown_column(built):
    _, _, c = built
    with pytest.raises(KeyError, match="Tenur"):
        apply_human_fields(c, descriptions={"Tenur": "typo"})


@pytest.mark.parametrize("measured", ["min", "max", "allowed_values", "null_count", "dtype"])
def test_apply_human_fields_cannot_reach_a_measured_field(built, measured):
    _, _, c = built
    with pytest.raises(TypeError):
        apply_human_fields(c, **{measured: 0})


def test_contract_round_trips_through_json(built, tmp_path):
    _, _, c = built
    path = tmp_path / "dataset_contract.json"
    save_contract(c, path)
    assert load_contract(path) == c
