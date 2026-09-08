import hashlib

import pandas as pd

from hv import ingest
from hv.config import RAW_PATH


def test_profile_counts_rows_columns_nulls_and_duplicates(raw_frame):
    p = ingest.profile(raw_frame)
    assert p["rows"] == 8 and p["cols"] == 20
    assert p["columns"]["Tenure"]["null_count"] == 1
    assert p["columns"]["OrderCount"]["null_count"] == 2
    assert p["duplicate_rows"] == 1  # id 4 appears twice
    assert p["duplicate_ids"] == 1
    assert p["duplicate_records"] == 2  # ids 4/4 and 5/6 are identical apart from CustomerID


def test_profile_lists_sample_values_and_numeric_ranges(raw_frame):
    p = ingest.profile(raw_frame)
    assert "Phone" in p["columns"]["PreferredLoginDevice"]["sample_values"]
    assert p["columns"]["PreferredLoginDevice"]["n_unique"] == 3
    assert p["numeric_describe"]["CashbackAmount"]["max"] == 324.99
    assert "PreferredLoginDevice" not in p["numeric_describe"]


def test_sha256_file_matches_hashlib(tmp_path):
    f = tmp_path / "x.csv"
    f.write_bytes(b"a,b\n1,2\n")
    assert ingest.sha256_file(f) == hashlib.sha256(b"a,b\n1,2\n").hexdigest()


def test_load_data_dictionary_parses_variable_description_table(tmp_path):
    # mimics the Kaggle sheet: a blank first column, a header row "Data | Variable | Discerption"
    sheet = pd.DataFrame(
        [
            [None, "Data", "Variable", "Discerption"],
            [None, "E Comm", "Churn", "Churn Flag"],
            [None, "E Comm", "Tenure", "Tenure of customer"],
        ]
    )
    path = tmp_path / "raw.xlsx"
    with pd.ExcelWriter(path) as xw:
        sheet.to_excel(xw, sheet_name="Data Dict", header=False, index=False)
        pd.DataFrame({"CustomerID": [1]}).to_excel(xw, sheet_name="E Comm", index=False)
    d = ingest.load_data_dictionary(path)
    assert d == {"Churn": "Churn Flag", "Tenure": "Tenure of customer"}


def test_load_data_dictionary_is_empty_when_sheet_missing(tmp_path):
    path = tmp_path / "raw.xlsx"
    pd.DataFrame({"CustomerID": [1]}).to_excel(path, sheet_name="E Comm", index=False)
    assert ingest.load_data_dictionary(path) == {}


def test_load_raw_reads_the_real_file_as_on_disk():
    if not RAW_PATH.exists():  # the dataset is committed; guard for a bare checkout
        import pytest

        pytest.skip("raw dataset not present")
    df = ingest.load_raw()
    assert df.shape == (5630, 20)
    assert list(df.columns[:3]) == ["CustomerID", "Churn", "Tenure"]
    assert (df["PreferredLoginDevice"] == "Phone").sum() > 0  # raw stays raw
