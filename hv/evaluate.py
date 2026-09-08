"""How Crew 2 measures a model honestly (PLAN.md §3.7).

Every number here comes from data the model did not train on. Accuracy alone would flatter any model
on this dataset - 83% of the customers stay, so "nobody churns" scores 83% - which is why the
majority baseline is computed alongside every variant and printed next to it.

`precision_at_top` is the one the business actually spends money on: the retention budget goes to
the top slice of the ranked list, so the question is how many of those flagged customers really left.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold

from hv.config import SEED

ROUND = 4
METRIC_NAMES = ["roc_auc", "pr_auc", "f1", "precision", "recall", "accuracy"]


def _r(x: float) -> float:
    return round(float(x), ROUND)


def precision_at_top(y_true, proba, frac: float = 0.10) -> float:
    """Of the highest-scoring `frac` of customers, what share really churned."""
    y_true = np.asarray(y_true)
    proba = np.asarray(proba)
    k = max(1, int(round(frac * len(y_true))))
    top = np.argsort(-proba, kind="stable")[:k]  # stable so ties do not depend on the sort
    return _r(y_true[top].mean())


def majority_baseline(y) -> dict:
    """The model that always answers with the majority class - the number every variant must beat."""
    y = np.asarray(y)
    majority = int(pd.Series(y).mode().iloc[0])
    predicted = np.full_like(y, majority)
    positive_rate = float(np.mean(y == 1))
    return {
        "strategy": "majority",
        "predicted_class": majority,
        "accuracy": _r(accuracy_score(y, predicted)),
        "precision": _r(precision_score(y, predicted, zero_division=0)),
        "recall": _r(recall_score(y, predicted, zero_division=0)),
        "f1": _r(f1_score(y, predicted, zero_division=0)),
        "roc_auc": 0.5,  # a constant answer cannot rank anyone
        "pr_auc": _r(positive_rate),
        "precision_at_top10": _r(positive_rate),
    }


def _fold_metrics(y_true, proba) -> dict:
    predicted = (proba >= 0.5).astype(int)
    return {
        "roc_auc": roc_auc_score(y_true, proba),
        "pr_auc": average_precision_score(y_true, proba),
        "f1": f1_score(y_true, predicted, zero_division=0),
        "precision": precision_score(y_true, predicted, zero_division=0),
        "recall": recall_score(y_true, predicted, zero_division=0),
        "accuracy": accuracy_score(y_true, predicted),
    }


def cv_run(pipe, X: pd.DataFrame, y, n_splits: int = 5, seed: int = SEED) -> tuple[dict, np.ndarray]:
    """One stratified pass: per-fold metrics and the out-of-fold probability of every row.

    Public because `hv.train` needs both halves of the same pass; `cv_scores` and `oof_proba`
    are the two convenience views on it.

    Both come out of the same loop - refitting the folds a second time to collect the out-of-fold
    predictions would double the cost of every run for nothing.
    """
    X = X.reset_index(drop=True)
    y = np.asarray(y)
    folds = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    oof = np.zeros(len(y), dtype=float)
    per_fold: list[dict] = []

    for train_idx, test_idx in folds.split(X, y):
        model = clone(pipe)
        model.fit(X.iloc[train_idx], y[train_idx])
        proba = model.predict_proba(X.iloc[test_idx])[:, 1]
        oof[test_idx] = proba
        per_fold.append(_fold_metrics(y[test_idx], proba))

    scores = {
        name: {
            "mean": _r(np.mean([f[name] for f in per_fold])),
            "std": _r(np.std([f[name] for f in per_fold])),
        }
        for name in METRIC_NAMES
    }
    scores["precision_at_top10"] = precision_at_top(y, oof)
    return scores, oof


def cv_scores(pipe, X: pd.DataFrame, y, n_splits: int = 5, seed: int = SEED) -> dict:
    """Cross-validated scores: mean and std per metric, plus precision on the top 10% of the ranking."""
    return cv_run(pipe, X, y, n_splits, seed)[0]


def oof_proba(pipe, X: pd.DataFrame, y, n_splits: int = 5, seed: int = SEED) -> np.ndarray:
    """Out-of-fold churn probability per row - what fairness and the top-10% cut are measured on."""
    return cv_run(pipe, X, y, n_splits, seed)[1]


def fairness_by_group(y_true, y_pred, groups: pd.Series) -> dict:
    """Per group: how many, how many churners we caught, how often we were right, how often we flagged.

    Gender and MaritalStatus are never model inputs. They are still measured here, because a model
    that quietly catches churners in one group and misses them in another is a model nobody should
    deploy, and you only find that out by looking.
    """
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    groups = pd.Series(groups).reset_index(drop=True)
    out: dict[str, dict] = {}
    for value in sorted(groups.dropna().unique(), key=str):
        mask = (groups == value).to_numpy()
        out[str(value)] = {
            "n": int(mask.sum()),
            "recall": _r(recall_score(y_true[mask], y_pred[mask], zero_division=0)),
            "precision": _r(precision_score(y_true[mask], y_pred[mask], zero_division=0)),
            "positive_rate": _r(y_pred[mask].mean()),
        }
    return out


def feature_importances(pipe, X: pd.DataFrame, y, seed: int = SEED) -> dict[str, float]:
    """Permutation importance on the raw feature columns of an already fitted pipeline.

    Shuffle one column, see how much the ranking suffers. Reported per original column rather than
    per one-hot output, so "PreferredPaymentMode" stays one answer instead of five.
    """
    result = permutation_importance(
        pipe, X, np.asarray(y), n_repeats=5, random_state=seed, n_jobs=1, scoring="roc_auc"
    )
    importances = {name: _r(value) for name, value in zip(X.columns, result.importances_mean, strict=True)}
    return dict(sorted(importances.items(), key=lambda kv: kv[1], reverse=True))
