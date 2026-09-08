"""Project-wide constants: paths, seed, column roles, entity map, units, LLM factory (PLAN.md §3.1)."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_PATH = ROOT / "data" / "raw" / "ecommerce_churn.xlsx"
RAW_SHEET = "E Comm"  # verified in M1 against the real file
DICT_SHEET = "Data Dict"
ARTIFACTS_DIR = ROOT / "artifacts"
RUNS_DIR = ROOT / "runs"

SEED = 42
PRIMARY_KEY = "CustomerID"
TARGET = "Churn"
PROTECTED = ["Gender", "MaritalStatus"]

# value -> canonical value, applied after whitespace strip (exact match)
ENTITY_MAP: dict[str, dict[str, str]] = {
    "PreferredLoginDevice": {"Phone": "Mobile Phone"},
    "PreferredPaymentMode": {"CC": "Credit Card", "COD": "Cash on Delivery"},
    "PreferedOrderCat": {"Mobile": "Mobile Phone"},
}

UNITS: dict[str, str] = {
    "Tenure": "months",
    "WarehouseToHome": "km",
    "HourSpendOnApp": "hours",
    "OrderAmountHikeFromlastYear": "percent",
    "DaySinceLastOrder": "days",
    "CashbackAmount": "USD",
}

# byte-identical CSVs across platforms and runs
CSV_KW: dict = {"index": False, "lineterminator": "\n"}

MODEL_NAME = "openai/gpt-5-mini"


def get_llm():
    """Return the CrewAI LLM used by every agent.

    gpt-5 models reject a non-default temperature; never set it."""
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set; put it in .env (see .env.example)")
    from crewai import LLM

    return LLM(model=MODEL_NAME)
