import pytest

from hv import config


def test_roles_do_not_overlap():
    assert config.PRIMARY_KEY != config.TARGET
    assert config.PRIMARY_KEY not in config.PROTECTED
    assert config.TARGET not in config.PROTECTED


def test_entity_map_values_are_canonical():
    for column, mapping in config.ENTITY_MAP.items():
        for old, new in mapping.items():
            assert old != new, f"{column}: identity mapping {old!r}"
            assert new not in mapping, f"{column}: canonical value {new!r} is itself remapped"


def test_units_only_name_known_style_columns():
    assert config.UNITS["CashbackAmount"] == "USD"
    assert all(isinstance(u, str) and u for u in config.UNITS.values())


def test_get_llm_requires_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        config.get_llm()


def test_csv_kw_is_deterministic():
    assert config.CSV_KW == {"index": False, "lineterminator": "\n"}
