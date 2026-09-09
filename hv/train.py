"""Train the three variants, pick one, and write down everything that decided it (PLAN.md §3.7).

Nothing here chooses by feel: every variant is scored the same way on the same folds, the served
model is the one with the best cross-validated ROC-AUC, and `metrics.json` carries the baseline next
to it so a reader can see whether the model earned its place.

`metrics.json` is byte-identical across runs (CLAUDE.md standing rule): fixed seed, `n_jobs=1`, four
decimals everywhere, sorted keys. The run's timestamp lives in `run_meta.json` instead, next to it -
a clock reading inside the metrics would make the file differ from itself on every run (D-M4-2).
"""

from __future__ import annotations

import json
import platform
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.base import clone
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from hv.config import PRIMARY_KEY, PROTECTED, SEED, TARGET
from hv.contract import Contract
from hv.evaluate import ROUND, cv_run, fairness_by_group, feature_importances, majority_baseline
from hv.features import (
    ENGINEERED,
    ENGINEERED_CATEGORICAL,
    ENGINEERED_NUMERIC,
    add_engineered,
    assert_no_leakage,
    feature_columns,
    make_preprocessor,
)

VARIANTS = {
    "logreg": LogisticRegression(max_iter=2000, class_weight="balanced", random_state=SEED),
    "random_forest": RandomForestClassifier(
        n_estimators=400, min_samples_leaf=2, class_weight="balanced_subsample",
        random_state=SEED, n_jobs=1,
    ),
    "hist_gb": HistGradientBoostingClassifier(learning_rate=0.05, max_iter=400, random_state=SEED),
}

MODEL_FILE = "model.joblib"
METRICS_FILE = "metrics.json"


def _model_columns(c: Contract) -> tuple[list[str], list[str]]:
    """The exact inputs of every variant: contract features plus the engineered ones."""
    numeric_raw, categorical_raw = feature_columns(c)
    numeric = numeric_raw + ENGINEERED_NUMERIC
    categorical = categorical_raw + ENGINEERED_CATEGORICAL
    assert_no_leakage(numeric + categorical, c)
    return numeric, categorical


def _pipeline(name: str, numeric: list[str], categorical: list[str]) -> Pipeline:
    return Pipeline(
        [("pre", make_preprocessor(numeric, categorical)), ("model", clone(VARIANTS[name]))]
    )


def train_all(
    fdf: pd.DataFrame,
    c: Contract,
    out_dir: Path,
    protected: pd.DataFrame | None = None,
) -> dict:
    """Score every variant, serve the best one, write `model.joblib` and `metrics.json`.

    `protected` is an optional frame of the primary key plus the protected columns, joined on the
    key to measure fairness. The features frame deliberately does not carry Gender or MaritalStatus,
    so they have to arrive separately or fairness cannot be measured at all (D-M4-1).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    numeric, categorical = _model_columns(c)
    X = fdf[numeric + categorical]
    y = fdf[TARGET].to_numpy()

    variants: dict[str, dict] = {}
    out_of_fold: dict[str, np.ndarray] = {}
    for name in VARIANTS:
        scores, oof = cv_run(_pipeline(name, numeric, categorical), X, y)
        variants[name] = scores
        out_of_fold[name] = oof

    served = max(variants, key=lambda name: variants[name]["roc_auc"]["mean"])
    served_pipe = _pipeline(served, numeric, categorical).fit(X, y)
    joblib.dump(
        {"pipeline": served_pipe, "served": served, "numeric": numeric, "categorical": categorical},
        out_dir / MODEL_FILE,
    )

    fairness: dict[str, dict] = {}
    if protected is not None:
        served_predictions = (out_of_fold[served] >= 0.5).astype(int)
        aligned = (
            fdf[[PRIMARY_KEY]]
            .merge(protected, on=PRIMARY_KEY, how="left")
            .reset_index(drop=True)
        )
        for column in PROTECTED:
            if column in aligned.columns:
                fairness[column] = fairness_by_group(y, served_predictions, aligned[column])

    metrics = {
        "n_rows": int(len(fdf)),
        "positive_rate": round(float(y.mean()), ROUND),
        "features": {
            "numeric": [n for n in numeric if n not in ENGINEERED],
            "categorical": [n for n in categorical if n not in ENGINEERED],
            "engineered": list(ENGINEERED),
        },
        "baseline": majority_baseline(y),
        "variants": variants,
        "served": served,
        "importances": feature_importances(served_pipe, X, y),
        "fairness": fairness,
        "versions": {
            "python": platform.python_version(),
            "scikit_learn": sklearn.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
    }
    (out_dir / METRICS_FILE).write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return metrics


def predict_one(model_path: Path, row: dict) -> float:
    """Churn probability for one contract-shaped row - a row of the clean file, not of features.csv.

    The engineered features are derived here, so a caller (the Flask app in M6, say) only ever has to
    know the columns the contract declares.
    """
    # joblib.load unpickles, so it only ever runs on model.joblib as written by train_all above and
    # committed to this repo - never on a file a user supplies. The M6/M7 app loads that same artifact.
    bundle = joblib.load(Path(model_path))
    frame = add_engineered(pd.DataFrame([dict(row)]))
    needed = bundle["numeric"] + bundle["categorical"]
    absent = [name for name in needed if name not in frame.columns]
    if absent:
        raise ValueError(f"the row is missing {absent}; it must be shaped like a clean_data.csv row")
    proba = bundle["pipeline"].predict_proba(frame[needed])[0, 1]
    return round(float(proba), ROUND)
