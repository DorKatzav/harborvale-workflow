import numpy as np
import pandas as pd

from hv import cleaning


def test_entity_map_fixes_are_applied_and_counted(raw_frame):
    df, rep = cleaning.clean(raw_frame)
    assert set(df["PreferredLoginDevice"]) == {"Mobile Phone", "Computer"}
    assert "CC" not in set(df["PreferredPaymentMode"]) and "COD" not in set(df["PreferredPaymentMode"])
    assert "Mobile" not in set(df["PreferedOrderCat"])
    assert rep.entity_fixes == {
        "PreferredLoginDevice": {"Phone": 1},
        "PreferredPaymentMode": {"CC": 1, "COD": 1},
        "PreferedOrderCat": {"Mobile": 1},
    }


def test_whitespace_is_stripped_before_mapping(raw_frame):
    df, _ = cleaning.clean(raw_frame)
    assert (df.loc[df["CustomerID"] == 3, "PreferredPaymentMode"] == "Cash on Delivery").all()


def test_exact_duplicate_rows_and_duplicate_records_are_dropped(raw_frame):
    df, rep = cleaning.clean(raw_frame)
    assert rep.rows_in == 8
    assert rep.duplicate_rows_dropped == 1  # second id-4 row
    assert rep.duplicate_ids_dropped == 0  # nothing left after the exact-duplicate pass
    assert rep.duplicate_records_dropped == 1  # id 6 (same record as id 5, higher id)
    assert rep.rows_out == 6
    assert list(df["CustomerID"]) == [1, 2, 3, 4, 5, 7]  # lowest id kept, sorted


def test_duplicate_records_can_be_kept(raw_frame):
    df, rep = cleaning.clean(raw_frame, drop_duplicate_records=False)
    assert rep.duplicate_records_dropped == 0
    assert rep.rows_out == 7


def test_nulls_are_preserved_and_reported(raw_frame):
    df, rep = cleaning.clean(raw_frame)
    assert df["Tenure"].isna().sum() == 1
    assert df["OrderCount"].isna().sum() == 1  # id 4 (its duplicate is gone)
    assert rep.nulls_kept == {"Tenure": 1, "OrderCount": 1}


def test_integer_columns_are_cast_and_nullable_numerics_stay_float(raw_frame):
    df, rep = cleaning.clean(raw_frame)
    for col in ["CustomerID", "Churn", "CityTier", "Complain", "SatisfactionScore",
                "NumberOfDeviceRegistered", "NumberOfAddress"]:  # fmt: skip
        assert pd.api.types.is_integer_dtype(df[col]), col
    assert pd.api.types.is_float_dtype(df["Tenure"])
    assert rep.dtype_casts["CustomerID"] == "int"


def test_clean_is_idempotent(raw_frame):
    once, _ = cleaning.clean(raw_frame)
    twice, rep = cleaning.clean(once)
    pd.testing.assert_frame_equal(once, twice)
    assert rep.rows_in == rep.rows_out and rep.entity_fixes == {}


def test_write_clean_is_byte_identical_across_runs(raw_frame, tmp_path):
    df, _ = cleaning.clean(raw_frame)
    h1 = cleaning.write_clean(df, tmp_path / "a.csv")
    h2 = cleaning.write_clean(df, tmp_path / "b.csv")
    assert h1 == h2
    assert (tmp_path / "a.csv").read_bytes() == (tmp_path / "b.csv").read_bytes()
    assert b"\r\n" not in (tmp_path / "a.csv").read_bytes()


def test_report_to_dict_is_json_friendly(raw_frame):
    _, rep = cleaning.clean(raw_frame)
    d = rep.to_dict()
    assert d["rows_in"] == 8 and isinstance(d["entity_fixes"], dict)
    assert all(not isinstance(v, np.integer) for v in d.values() if not isinstance(v, dict))
