"""M8 audit: the gate's metrics comparison must see every kind of change, not only a moved number."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def gate():
    spec = importlib.util.spec_from_file_location("gate_script", ROOT / "scripts" / "gate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


COMMITTED = {
    "served": "hist_gb",
    "variants": {
        "hist_gb": {"roc_auc": {"mean": 0.9857, "std": 0.0051}},
        "logreg": {"roc_auc": {"mean": 0.89}},
    },
    "fairness": {"Gender": {"Male": {"recall": 0.86}}},
    "features": {"numeric": ["Tenure"]},
    "importances": {"Tenure": 0.0889},
}


def _fresh(**changes):
    import copy

    m = copy.deepcopy(COMMITTED)
    for path, value in changes.items():
        node = m
        *parents, last = path.split("/")
        for p in parents:
            node = node[p]
        if value is ...:
            del node[last]
        else:
            node[last] = value
    return m


def test_a_moved_number_within_tolerance_is_reported_but_not_beyond(gate):
    within = gate.metrics_diff(COMMITTED, _fresh(**{"variants/hist_gb/roc_auc/mean": 0.9840}))
    assert [d.path for d in within] == ["/variants/hist_gb/roc_auc/mean"]
    assert not any(d.beyond(gate.METRICS_TOLERANCE) for d in within)
    beyond = gate.metrics_diff(COMMITTED, _fresh(**{"variants/hist_gb/roc_auc/mean": 0.90}))
    assert beyond[0].beyond(gate.METRICS_TOLERANCE)


def test_a_flipped_served_model_is_a_difference(gate):
    diffs = gate.metrics_diff(COMMITTED, _fresh(served="logreg"))
    assert [d.path for d in diffs] == ["/served"] and diffs[0].beyond(gate.METRICS_TOLERANCE)


@pytest.mark.parametrize("path", ["variants/logreg", "fairness/Gender", "importances/Tenure"])
def test_a_deleted_key_is_a_difference(gate, path):
    diffs = gate.metrics_diff(COMMITTED, _fresh(**{path: ...}))
    assert diffs and all(d.beyond(gate.METRICS_TOLERANCE) for d in diffs)
    assert any(d.path.startswith("/" + path) for d in diffs)


def test_an_added_key_is_a_difference(gate):
    diffs = gate.metrics_diff(COMMITTED, _fresh(**{"features/categorical": ["Gender"]}))
    assert [d.path for d in diffs] == ["/features/categorical"]


def test_a_number_replaced_by_null_or_a_string_is_a_difference(gate):
    for bad in (None, "0.9857"):
        diffs = gate.metrics_diff(COMMITTED, _fresh(**{"variants/hist_gb/roc_auc/mean": bad}))
        assert diffs and diffs[0].beyond(gate.METRICS_TOLERANCE), bad


def test_a_changed_list_is_a_difference(gate):
    diffs = gate.metrics_diff(COMMITTED, _fresh(**{"features/numeric": ["Tenure", "Gender"]}))
    assert [d.path for d in diffs] == ["/features/numeric"] and diffs[0].beyond(gate.METRICS_TOLERANCE)


def test_identical_documents_have_no_differences(gate):
    assert gate.metrics_diff(COMMITTED, _fresh()) == []
