# HarborVale Workflow — Implementation Plan

> Working language: terminal in English; Hebrew (masculine) only in HTML reports and Obsidian. Code / UI / files / commits in English.
> Spec: `DESIGN_HE.html` (design doc, approved D1–D12 on 2026-09-08). This plan argues from that spec.
> Environment: conda `harborvale` (Python 3.11), created in M0. Accounts: Railway exists, `gh` logged in as DorKatzav.
> Keep `PROJECT_LOG.md` (decisions, experiments, metrics, lessons) · commit after every passed gate ·
> one feature branch + PR per milestone · Hebrew HTML report + Obsidian update after every milestone.

**Goal:** Ship a CrewAI Flow in which a Data Analyst crew produces a cleaned dataset and a machine-checkable
`dataset_contract.json`, a Data Scientist crew builds a churn model only on top of that contract, and the Flow
validates the handoff, logs everything, saves artifacts in the repo and refuses to train when the contract and the
data disagree — surfaced in a Flask app deployed on Railway.

**Architecture:** Three layers. `hv/` is a deterministic, tested Python package (ingest, cleaning, EDA, contract build +
validate, features, training, evaluation, model card, run logging). `crews/` wraps `hv/` functions as CrewAI tools;
agents orchestrate and write prose (insights, contract descriptions and assumptions, evaluation narrative, model card),
never compute numbers. `flow/` is the CrewAI Flow: ingest → analyst crew → validate handoff → router → scientist crew →
validate outputs → publish, or fail gracefully with a readable report. `app/` is a Flask site that reads the committed
`artifacts/` and runs the validator live ("break it on purpose"); a password-protected live run is added in M7.

**Tech stack:** Python 3.11 · CrewAI 1.x (+ `crewai[tools]`) · OpenAI `gpt-5-mini` via CrewAI `LLM` · pandas · openpyxl ·
scikit-learn · matplotlib · joblib · pydantic 2 · Flask + Jinja2 + gunicorn · pytest · ruff · GitHub Actions · Railway (Railpack).

## Global constraints (from the spec)

- **The contract is a file.** Crew 2 assumes only `dataset_contract.json` + `clean_data.csv`. Its file tool refuses any path outside `<run>/crew1/` (D9).
- **Measured vs human fields.** Contract fields that the validator reads are computed by `hv.contract.build_contract`; the agent may only set `description`, `rationale`, `assumptions` (D5). The validator ignores human fields.
- **Deterministic data artifacts.** `clean_data.csv`, `features.csv`, `metrics.json` (rounded to 4 decimals) must be byte-identical across two runs. `SEED = 42` everywhere, `n_jobs=1` in models, CSVs written with `index=False, lineterminator="\n"`, pinned versions.
- **Fail = stop.** A failed handoff writes `FAILED.md`, does not run Crew 2, exits with code 2. No automatic retry (D6).
- **Missing values** stay in `clean_data.csv`, are declared in the contract (`nullable`, `null_count`), and are imputed inside the sklearn `Pipeline` on training folds only (D7).
- **Protected attributes** `Gender`, `MaritalStatus`: role `protected` in the contract, never features; fairness by group reported in the model card (D8).
- **Leakage guard is a test.** `CustomerID`, `Churn`, protected columns never in `X` (`hv.features.assert_no_leakage`).
- **Numbers are generated.** Every number in `insights.md`, `evaluation_report.md`, `model_card.md` comes from `stats.json` / `metrics.json` through a rendering tool; agents write prose around them.
- **Secrets** only in `.env` (gitignored) and Railway variables; `OPENAI_API_KEY` reaches Railway only in M7. `git grep -iE "sk-[A-Za-z0-9_-]{20,}|eyJ[A-Za-z0-9_-]{20,}"` must be empty before every push.
- **Provided files never modified:** `final_projec.html`, `data/raw/ecommerce_churn.xlsx`.
- **CI never calls OpenAI.** Tests and CI use `crews/stubs.py`.
- Own git repo in this folder; GitHub `DorKatzav/harborvale-workflow` (public). Never `git add -A` from the course root.

---

## 1. Architecture & data flow

```text
data/raw/ecommerce_churn.xlsx (Kaggle, provided, read-only)
        │
        ▼  scripts/run_flow.py  →  flow/main.py::HarborValeFlow
  @start  ingest              raw sha256, new runs/<run_id>/ (crew1/, crew2/), RunLogger
        │
        ▼
  @listen run_analyst_crew    crews/analyst (3 agents) → tools → hv.ingest / hv.cleaning / hv.eda / hv.contract
        │                     writes crew1/{clean_data.csv, eda_report.html, insights.md, dataset_contract.json, stats.json}
        ▼
  @listen validate_handoff    hv.contract.validate(crew1/clean_data.csv, crew1/dataset_contract.json, required_features)
        │
        ▼
  @router                     "handoff_ok" ────────────────────────────┐        "handoff_failed"
        │                                                              │              │
        ▼                                                              │              ▼
  @listen run_scientist_crew  crews/scientist (3 agents) → sandboxed   │      fail_gracefully → FAILED.md, exit 2
        │                     read of crew1/ only → hv.features /      │      (Crew 2 never runs)
        │                     hv.train / hv.evaluate / hv.model_card   │
        ▼                     writes crew2/{features.csv, model.joblib, evaluation_report.md, model_card.md, metrics.json}
  @listen validate_outputs    model loads + predicts on a contract-shaped row; ≥2 variants; 5 model-card sections
        │
        ▼
  @listen publish             manifest.json (sha256 per artifact, versions, durations, cost) → copy run to artifacts/

app/ (Flask on Railway) reads artifacts/ ; POST /api/validate runs hv.contract.validate on a tampered copy (no LLM)
M7: /live runs the Flow in a background thread on the server, log streamed by SSE, behind APP_PASSWORD
```

## 2. Repository structure

```text
HarborVale_Workflow/          git root; GitHub: DorKatzav/harborvale-workflow (public)
├── hv/                       deterministic core (tested, no LLM)
│   ├── __init__.py
│   ├── config.py             paths, SEED, TARGET, PRIMARY_KEY, PROTECTED, ENTITY_MAP, UNITS, get_llm()
│   ├── ingest.py             load_raw, load_data_dictionary, sha256_file, profile
│   ├── cleaning.py           clean → (df, CleaningReport); write_clean
│   ├── eda.py                stats, write_stats, render_eda_html
│   ├── contract.py           ColumnSpec, DatasetSpec, Contract, build_contract, apply_human_fields, validate, tamper
│   ├── features.py           feature_columns, build_features, assert_no_leakage, make_preprocessor, write_features
│   ├── train.py              VARIANTS, train_all
│   ├── evaluate.py           cv_scores, majority_baseline, fairness_by_group, feature_importances, predict_one
│   ├── model_card.py         render_evaluation_report, render_model_card, REQUIRED_SECTIONS
│   └── runlog.py             new_run_dir, RunLogger, write_manifest
├── crews/
│   ├── __init__.py
│   ├── analyst/  config/agents.yaml  config/tasks.yaml  crew.py  tools.py
│   ├── scientist/ config/agents.yaml config/tasks.yaml  crew.py  tools.py   (tools.py has the sandboxed reader)
│   └── stubs.py              run_analyst_stub, run_scientist_stub (same hv functions, canned prose, no LLM)
├── flow/
│   ├── __init__.py
│   ├── state.py              FlowState (pydantic)
│   └── main.py               HarborValeFlow, run_flow()
├── app/
│   ├── __init__.py  main.py (create_app)  artifacts.py (loader)  routes.py  live.py (M7)
│   ├── templates/  base.html index.html analyst.html contract.html scientist.html runs.html live.html
│   └── static/     style.css  app.js
├── artifacts/                last successful run (committed)
│   ├── crew1/  clean_data.csv  eda_report.html  insights.md  dataset_contract.json  stats.json
│   ├── crew2/  features.csv  model.joblib  evaluation_report.md  model_card.md  metrics.json
│   ├── manifest.json  events.jsonl  flow.log
├── runs/                     one folder per run (gitignored; .gitkeep)
├── scripts/  run_flow.py  break_it.py  gate.py  smoke_live.py
├── tests/    conftest.py (tiny synthetic frame + contract fixtures) + one test file per hv module, crews, flow, app
├── docs/     reports/M<N>_HE.html  reports/img/  notes/
├── data/raw/ecommerce_churn.xlsx
├── .github/workflows/ci.yml  requirements.txt  environment.yml  ruff.toml  .env.example  .gitignore
├── railway.json  railpack.json  Procfile
└── README.md  CLAUDE.md  PLAN.md  PLAN_HE.html  PROJECT_LOG.md  DESIGN_HE.html  final_projec.html
```

## 3. Shared contracts (single source of truth — every milestone builds on these)

### 3.1 `hv/config.py`
```python
ROOT = Path(__file__).resolve().parent.parent
RAW_PATH = ROOT / "data" / "raw" / "ecommerce_churn.xlsx"
RAW_SHEET = "E Comm"                      # verified in M1 against the real file
DICT_SHEET = "Data Dict"
ARTIFACTS_DIR = ROOT / "artifacts"; RUNS_DIR = ROOT / "runs"
SEED = 42
PRIMARY_KEY = "CustomerID"; TARGET = "Churn"
PROTECTED = ["Gender", "MaritalStatus"]
ENTITY_MAP = {                            # value → canonical value (exact match after strip)
    "PreferredLoginDevice": {"Phone": "Mobile Phone"},
    "PreferredPaymentMode": {"CC": "Credit Card", "COD": "Cash on Delivery"},
    "PreferedOrderCat":     {"Mobile": "Mobile Phone"},
}
UNITS = {"Tenure": "months", "WarehouseToHome": "km", "HourSpendOnApp": "hours",
         "OrderAmountHikeFromlastYear": "percent", "DaySinceLastOrder": "days", "CashbackAmount": "USD"}
CSV_KW = dict(index=False, lineterminator="\n")     # byte-identical CSVs
MODEL_NAME = "openai/gpt-5-mini"
def get_llm(): ...                        # crewai.LLM(model=MODEL_NAME); raises RuntimeError if OPENAI_API_KEY missing
```

### 3.2 `hv/ingest.py`
```python
def load_raw(path: Path = RAW_PATH, sheet: str = RAW_SHEET) -> pd.DataFrame      # exactly as on disk
def load_data_dictionary(path: Path = RAW_PATH, sheet: str = DICT_SHEET) -> dict[str, str]   # {} if sheet absent
def sha256_file(path: Path) -> str
def profile(df: pd.DataFrame) -> dict
# {"rows", "cols", "columns": {name: {"dtype", "null_count", "n_unique", "sample_values"[≤10]}},
#  "duplicate_rows", "duplicate_ids", "numeric_describe": {col: {"min","max","mean","std"}}}
```

### 3.3 `hv/cleaning.py`
```python
@dataclass
class CleaningReport:
    rows_in: int; rows_out: int; duplicate_rows_dropped: int; duplicate_ids_dropped: int
    entity_fixes: dict[str, dict[str, int]]        # {column: {old_value: rows_changed}}
    dtype_casts: dict[str, str]                    # {column: "int"|"float"}
    nulls_kept: dict[str, int]                     # {column: null_count} for columns with nulls
    def to_dict(self) -> dict
def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, CleaningReport]
    # 1 strip whitespace in object columns  2 apply ENTITY_MAP  3 drop exact duplicate rows (keep first)
    # 4 drop duplicate CustomerID (keep first)  5 cast CustomerID/Churn/CityTier/Complain/SatisfactionScore/
    #   NumberOfDeviceRegistered/NumberOfAddress → int; nullable numerics stay float  6 sort by CustomerID, reset index
    # never imputes, never drops rows for nulls
def write_clean(df: pd.DataFrame, path: Path) -> str     # df.to_csv(path, **CSV_KW); returns sha256
```

### 3.4 `hv/eda.py`
```python
def stats(df: pd.DataFrame) -> dict
# {"n_rows","n_cols","churn_rate","churn_count","nulls":{col:n},
#  "churn_by_category": {col: {value: {"n","churn_rate"}}}  for every object column + CityTier,
#  "numeric_by_churn": {col: {"mean_churn","mean_stay"}},
#  "correlation_with_churn": {col: r}  (numeric, sorted by |r| desc),
#  "top_drivers": [col ×5], "complain_churn_rate", "no_complain_churn_rate",
#  "tenure_buckets": {"0-1","2-6","7-12","13+": {"n","churn_rate"}}}
def write_stats(s: dict, path: Path) -> None            # json, indent=2, sort_keys=True
def render_eda_html(df: pd.DataFrame, s: dict, out_path: Path) -> Path
# self-contained HTML (matplotlib PNGs embedded base64): churn rate, churn by tier/category, numeric distributions by
# churn, correlation bar, null map; a descriptive-statistics table
```

### 3.5 `hv/contract.py`
```python
class ColumnSpec(BaseModel):
    name: str
    dtype: Literal["int", "float", "category", "bool"]
    role: Literal["id", "target", "feature", "protected"]
    unit: str | None = None
    nullable: bool
    null_count: int
    allowed_values: list[str] | None = None      # category columns
    min: float | None = None                     # numeric columns
    max: float | None = None
    description: str = ""                        # HUMAN
    rationale: str = ""                          # HUMAN
class DatasetSpec(BaseModel):
    row_count: int; primary_key: str; target: str; target_positive_rate: float; sha256: str
class Contract(BaseModel):
    contract_version: str = "1.0"; produced_by: str; created_at: str; source: str
    dataset: DatasetSpec; columns: list[ColumnSpec]; assumptions: list[str] = []   # HUMAN
HUMAN_FIELDS = {"description", "rationale"}      # + top-level "assumptions"

def build_contract(df: pd.DataFrame, source: str, clean_csv: Path, produced_by="analyst_crew",
                   dictionary: dict[str, str] | None = None) -> Contract
    # dtype: integer → "int", float → "float", object/category → "category", bool → "bool"
    # role: PRIMARY_KEY → "id", TARGET → "target", PROTECTED → "protected", else "feature"
    # category → allowed_values sorted; numeric → min/max; unit from UNITS; nullable = null_count > 0
    # description pre-filled from dictionary when available (agent may overwrite)
def apply_human_fields(c: Contract, descriptions: dict[str, str] = {}, rationales: dict[str, str] = {},
                       assumptions: list[str] = []) -> Contract      # ONLY these; unknown column names raise
def save_contract(c: Contract, path: Path) -> None; def load_contract(path: Path) -> Contract

@dataclass
class Check:  name: str; column: str | None; passed: bool; message: str; hint: str | None = None
@dataclass
class ValidationReport:
    passed: bool; checks: list[Check]; source: str
    @property failures -> list[Check]; def to_dict(); def to_markdown() -> str   # used for FAILED.md and the app
def validate(data: Path | pd.DataFrame, contract: Contract | Path,
             required_features: list[str] | None = None, check_hash: bool = True) -> ValidationReport
    # ALL checks run, every failure is reported:
    #  integrity   sha256(file) == dataset.sha256                     (only when data is a Path and check_hash)
    #  columns     missing (hint: closest name via difflib) / unexpected
    #  dtype       per column (int/float/category/bool as classified in build_contract)
    #  values      category: rows with a value not in allowed_values (count + up to 5 samples)
    #  range       numeric: observed min/max within [min, max]; hint when max_obs/max ∈ [90,110] or [900,1100]:
    #              "ratio ≈ 100 — looks like a unit change"
    #  nulls       nullable false → any null fails; nullable true → null_count_obs ≤ declared
    #  rows        row_count == dataset.row_count
    #  key         primary key unique and non-null;  target present, binary {0,1}
    #  features    each required feature declared with role == "feature"   (when required_features given)
PRESETS = ["unit_change", "rename_column", "drop_contract_field", "bad_category", "dtype_change", "row_loss"]
def tamper(df: pd.DataFrame, c: Contract, preset: str, seed: int = SEED) -> tuple[pd.DataFrame, Contract]
    # unit_change: CashbackAmount *= 100 · rename_column: OrderCount → order_count ·
    # drop_contract_field: remove Tenure from contract.columns · bad_category: 5% of PreferredPaymentMode → "CC" ·
    # dtype_change: CityTier.astype(str) · row_loss: drop 10% rows (seeded)
```

### 3.6 `hv/features.py`
```python
ENGINEERED = ["cashback_per_order", "orders_per_tenure_month", "coupon_rate", "recency_bucket"]
# cashback_per_order = CashbackAmount / OrderCount (OrderCount 0 or NaN → NaN)
# orders_per_tenure_month = OrderCount / (Tenure + 1)
# coupon_rate = CouponUsed / OrderCount (same NaN rule)
# recency_bucket = cut(DaySinceLastOrder, [-1, 3, 7, 14, inf]) → "0-3","4-7","8-14","15+" (NaN stays NaN)
def feature_columns(c: Contract) -> tuple[list[str], list[str]]    # (numeric, categorical) raw features, role == "feature"
def build_features(df: pd.DataFrame, c: Contract) -> pd.DataFrame  # [PRIMARY_KEY] + raw features + ENGINEERED + [TARGET]
def assert_no_leakage(columns: list[str], c: Contract) -> None     # ValueError if id / target / protected present
def make_preprocessor(numeric: list[str], categorical: list[str]) -> ColumnTransformer
    # numeric: SimpleImputer(median) + StandardScaler ; categorical: SimpleImputer(most_frequent) + OneHotEncoder(handle_unknown="ignore")
def write_features(fdf: pd.DataFrame, path: Path) -> str            # CSV_KW, returns sha256
```

### 3.7 `hv/train.py` and `hv/evaluate.py`
```python
VARIANTS = {
  "logreg":        LogisticRegression(max_iter=2000, class_weight="balanced", random_state=SEED),
  "random_forest": RandomForestClassifier(n_estimators=400, min_samples_leaf=2, class_weight="balanced_subsample", random_state=SEED, n_jobs=1),
  "hist_gb":       HistGradientBoostingClassifier(learning_rate=0.05, max_iter=400, random_state=SEED),
}
def train_all(fdf: pd.DataFrame, c: Contract, out_dir: Path) -> dict   # writes model.joblib + metrics.json; returns metrics
# metrics.json = {"trained_at", "n_rows", "positive_rate", "features": {"numeric": [], "categorical": [], "engineered": []},
#   "baseline": {...}, "variants": {name: {"roc_auc","pr_auc","f1","precision","recall","accuracy" (mean,std), "precision_at_top10"}},
#   "served": name (best roc_auc mean), "importances": {feature: value} (served, permutation, n_repeats=5, seed),
#   "fairness": {"Gender": {group: {...}}, "MaritalStatus": {...}} (served, OOF predictions), "versions": {...}}
# every float rounded to 4 decimals

def cv_scores(pipe, X, y, n_splits=5, seed=SEED) -> dict           # StratifiedKFold(shuffle=True); OOF proba via cross_val_predict
def majority_baseline(y) -> dict
def precision_at_top(y_true, proba, frac=0.10) -> float
def fairness_by_group(y_true, y_pred, groups: pd.Series) -> dict    # {group: {"n","recall","precision","positive_rate"}}
def feature_importances(pipe, X, y, seed=SEED) -> dict[str, float]  # permutation_importance on raw feature columns
def predict_one(model_path: Path, row: dict) -> float               # probability of churn for one contract-shaped row
```

### 3.8 `hv/model_card.py`
```python
REQUIRED_SECTIONS = ["Purpose", "Training data", "Metrics", "Limitations", "Ethical considerations"]
def render_evaluation_report(metrics: dict, narrative: dict[str, str]) -> str   # comparison table from metrics + agent prose
def render_model_card(metrics: dict, c: Contract, sections: dict[str, str]) -> str
    # headings exactly REQUIRED_SECTIONS; "Training data" from the contract (rows, columns, nulls, positive rate, source);
    # "Metrics" table + fairness table from metrics; agent prose per section; raises if a section is missing
```

### 3.9 `hv/runlog.py`
```python
def new_run_dir(root: Path = RUNS_DIR, run_id: str | None = None) -> Path     # runs/<YYYYMMDD-HHMMSS>/ + crew1/ crew2/
class RunLogger:
    def __init__(self, run_dir: Path)                     # events.jsonl + flow.log
    def event(self, step: str, status: str, **fields)     # status: start|ok|fail|skip ; fields json-serialisable
    @contextmanager
    def step(self, name: str)                             # logs start/ok/fail + duration_s
def write_manifest(run_dir: Path, artifacts: dict[str, Path], extra: dict) -> Path
    # {"run_id","created_at","artifacts":{name:{"path","sha256","bytes"}},"versions":{python,pandas,sklearn,crewai},
    #  "durations_s":{step:s},"llm":{"model","calls","cost_usd"}, ...extra}
```

### 3.10 Crews
```python
# crews/analyst/tools.py (each a crewai @tool; every tool takes/returns str paths or JSON strings)
profile_raw_data(raw_path) -> json           clean_dataset(raw_path, out_dir) -> json (CleaningReport + clean_csv)
run_eda(clean_csv, out_dir) -> json (stats + eda_html)   build_contract_measured(clean_csv, out_dir) -> json (contract_path + columns)
write_contract_human_fields(contract_path, descriptions_json, rationales_json, assumptions_json) -> str
write_insights(out_dir, sections_json) -> str   # renders insights.md: key-numbers table from stats.json + sections
                                                # required sections: Overview, Cleaning, Who churns, Drivers, Recommendations
# crews/analyst/crew.py
@dataclass AnalystResult: clean_csv, eda_html, insights_md, contract_json, stats_json: Path; llm_calls: int; cost_usd: float
def run_analyst_crew(raw_path: Path, out_dir: Path) -> AnalystResult     # 3 agents, sequential, tasks from config/tasks.yaml

# crews/scientist/tools.py
class SandboxError(Exception)
def _guard(path, allowed_dir)                      # raises SandboxError if path resolves outside allowed_dir
read_crew1_artifact(path) -> str                   # guarded
validate_against_contract(clean_csv, contract_json) -> json (ValidationReport)
engineer_features(clean_csv, contract_json, out_dir) -> json
train_and_evaluate(features_csv, contract_json, out_dir) -> json (metrics)
write_evaluation_report(out_dir, narrative_json) -> str
write_model_card(out_dir, sections_json) -> str
# crews/scientist/crew.py
@dataclass ScientistResult: features_csv, model_path, evaluation_md, model_card_md, metrics_json: Path; llm_calls; cost_usd
def run_scientist_crew(contract_json: Path, clean_csv: Path, out_dir: Path) -> ScientistResult

# crews/stubs.py — same signatures, same hv calls, canned prose, no LLM
def run_analyst_stub(raw_path, out_dir) -> AnalystResult
def run_scientist_stub(contract_json, clean_csv, out_dir) -> ScientistResult
```

### 3.11 Flow
```python
class FlowState(BaseModel):
    run_id: str = ""; run_dir: str = ""; raw_path: str = str(RAW_PATH); raw_sha256: str = ""
    tamper: str | None = None; stub_crews: bool = False; skip_crew1: bool = False
    crew1: dict[str, str] = {}; crew2: dict[str, str] = {}
    validation: dict = {}; outputs_check: dict = {}
    status: Literal["pending", "handoff_ok", "handoff_failed", "outputs_failed", "published"] = "pending"
    llm_calls: int = 0; cost_usd: float = 0.0; started_at: str = ""; finished_at: str = ""
class HarborValeFlow(Flow[FlowState]):  ingest → run_analyst_crew → validate_handoff → route → run_scientist_crew → validate_outputs → publish | fail_gracefully
def run_flow(raw_path=RAW_PATH, tamper=None, stub_crews=False, skip_crew1=False, publish=True) -> FlowState
# scripts/run_flow.py exit codes: 0 published · 2 handoff failed · 3 outputs failed · 1 unexpected error
# --skip-crew1 copies artifacts/crew1/ into the run; --tamper applies hv.contract.tamper to the run's copy
```

### 3.12 App
```text
GET /            story + last run summary (manifest)            GET /analyst    crew-1 artifacts (EDA iframe, insights, contract table)
GET /contract    contract table + last validation + break-it panel   GET /scientist  features preview, variants table, model card
GET /runs        golden run + server runs (M7)                  GET /health     {"status","version","commit","model_loaded"}
POST /api/validate   json {"preset": <PRESETS>} or multipart file "clean_data" → ValidationReport.to_dict() (200 either way, "passed" inside)
M7: GET /live (password form) · POST /live/start · GET /live/events (SSE tail of events.jsonl) · GET /live/status
```

---

## 4. Milestones

Every milestone follows §5. Gate = `python scripts/gate.py --m N` → `GATE M<N>: PASS k/k`.

### M0 — Deployed skeleton on day one
- **Branch:** `feat/m0-skeleton` · **Report:** `docs/reports/M0_HE.html`
- **Goal:** own repo, public GitHub, conda env with CrewAI importable, Flask `/health` live on Railway, CI green.
- **Tasks:**
  1. `git init` in the project folder (course repo ignores it via its own `.gitignore` entry); `.gitignore` (env, runs/, __pycache__, .pytest_cache, .ruff_cache, .DS_Store, catboost_info, *.log); first commit with CLAUDE.md, PLAN.md, DESIGN_HE.html, final_projec.html, PROJECT_LOG.md.
  2. `gh repo create DorKatzav/harborvale-workflow --public --source . --push`.
  3. `conda create -n harborvale python=3.11`; install and pin: crewai, crewai-tools, openai, pandas, openpyxl, scikit-learn, matplotlib, joblib, pydantic, python-dotenv, flask, gunicorn, pytest, ruff → `requirements.txt` (exact `==`), `environment.yml`.
  4. `hv/__init__.py` (`__version__ = "0.1.0"`), `hv/config.py` (§3.1), `app/main.py::create_app()` with `/health` reading `RAILWAY_GIT_COMMIT_SHA` / `git rev-parse` fallback, `Procfile` + `railway.json` + `railpack.json` (explicit `gunicorn app.main:app` start), `.env.example` (`OPENAI_API_KEY=`, `LIVE_URL=`, `APP_PASSWORD=`).
  5. `tests/test_health.py`, `tests/test_config.py`; `ruff.toml` (line 110, E F I B UP); `.github/workflows/ci.yml` (ruff + pytest, python 3.11).
  6. `scripts/gate.py` skeleton with M0 checks; README stub (what it is, how to run, status table).
  7. **Dor:** Railway service from the GitHub repo, copy the public domain into `.env` as `LIVE_URL`.
- **Gate (--m 0):** (1) pytest green (2) ruff clean (3) `import crewai` in the env (4) secret scan empty (5) `GET {LIVE_URL}/health` 200 with the main commit hash (SKIP with reason if `LIVE_URL` unset).
- **Failure signals:** CrewAI install conflicts on Python 3.11 → pin the last version that installs cleanly and log it; Railway "no start command" → railpack.json.

### M1 — Crew-1 tools: ingest, cleaning, EDA (no agents yet)
- **Branch:** `feat/m1-analyst-tools` · **Report:** `docs/reports/M1_HE.html`
- **Dor first:** download the Kaggle dataset, save as `data/raw/ecommerce_churn.xlsx` (commit it; ~0.7 MB).
- **Tasks:**
  1. Verify sheet names; fix `RAW_SHEET` / `DICT_SHEET` if they differ. `hv/ingest.py` (§3.2) + `tests/test_ingest.py` (profile of a 6-row synthetic frame: null counts, duplicates, sample values).
  2. `hv/cleaning.py` (§3.3) + `tests/test_cleaning.py`: entity map fixes counted; exact duplicate rows dropped; duplicate ids dropped; NaN preserved; int casts; idempotent (`clean(clean(df)[0])` equals); `write_clean` twice → same sha256.
  3. `hv/eda.py` (§3.4) + `tests/test_eda.py`: churn_rate correct on a synthetic frame; every object column appears in `churn_by_category`; html file self-contained (no `src="http`), contains the churn-rate figure.
  4. `scripts/run_crew1_tools.py` (temporary, removed in M3): runs ingest → clean → eda on the real file into `artifacts/crew1/` and prints the CleaningReport. Record the real numbers in PROJECT_LOG (rows in/out, duplicates, entity fixes, nulls per column, churn rate).
- **Gate (--m 1):** (1) tests green (2) `artifacts/crew1/clean_data.csv` exists, row count matches CleaningReport (3) zero rows with `Phone`/`CC`/`COD`/`Mobile` in the three mapped columns (4) null counts in the clean file equal `CleaningReport.nulls_kept` (nothing imputed) (5) two consecutive runs produce identical sha256 (6) `eda_report.html` and `stats.json` present, `stats.churn_rate` between 0.05 and 0.5.
- **Failure signals:** sheet name differs → config only; unexpected extra spellings → extend ENTITY_MAP and log it as D-M1-1.

### M2 — The contract and the validator
- **Branch:** `feat/m2-contract` · **Report:** `docs/reports/M2_HE.html`
- **Tasks:**
  1. `hv/contract.py` models + `build_contract` + `apply_human_fields` + save/load (§3.5) + `tests/test_contract_build.py`: dtype/role classification on a synthetic frame; category allowed_values sorted; unit from UNITS; nullable/null_count; `apply_human_fields` refuses an unknown column and cannot touch `min`/`max`/`allowed_values` (passing them raises TypeError).
  2. `validate` (§3.5) + `tests/test_contract_validate.py`: clean synthetic frame passes; each check has one failing test with the exact expected message fragment; the unit-change hint text appears for ×100; all failures are reported together (tamper two things → two failures); `check_hash=False` skips integrity; changing `description` does not change the report.
  3. `tamper` + `PRESETS` + `tests/test_tamper.py` (each preset fails validation; failing check names asserted per preset).
  4. `scripts/break_it.py --preset X [--clean artifacts/crew1/clean_data.csv --contract artifacts/crew1/dataset_contract.json]`: writes a tampered copy to a temp dir, validates by path, prints the markdown report, exit 2 on failure.
  5. Build the real contract for the M1 clean file into `artifacts/crew1/dataset_contract.json` (measured fields only, descriptions from the data dictionary when present).
- **Gate (--m 2):** (1) tests green (2) real clean file passes its real contract (3) all six presets fail on the real files with the expected check names, `unit_change` includes the ratio hint (4) validation result unchanged after editing a description in a temp copy of the contract (5) `dataset_contract.json` round-trips through `load_contract` unchanged.
- **Failure signals:** float precision makes `min`/`max` fail on the same file → compare with `math.isclose(rel_tol=1e-9)` and store 6 significant digits.

### M3 — Crew 1 in CrewAI
- **Branch:** `feat/m3-analyst-crew` · **Report:** `docs/reports/M3_HE.html`
- **Dor first:** `OPENAI_API_KEY` into `.env`.
- **Tasks:**
  1. `crews/analyst/tools.py` (§3.10) + `tests/test_analyst_tools.py` (tools call hv and return JSON; `write_insights` renders the key-numbers table from stats.json and refuses a missing required section; `write_contract_human_fields` only touches human fields).
  2. `crews/analyst/config/agents.yaml` (Data Quality Engineer, Business Analyst, Data Steward — role/goal/backstory in English, backstory mentions Harbor & Vale's incident), `config/tasks.yaml` (profile_and_clean → explore → write_insights → author_contract; each task names its tool and its expected output; `author_contract` instructs: "you may only set description, rationale, assumptions; measured fields are facts, not opinions").
  3. `crews/analyst/crew.py` (§3.10): `@CrewBase AnalystCrew`, `Process.sequential`, `get_llm()`, `max_iter=8` per agent, `verbose` from env; `run_analyst_crew` collects paths, LLM call count and cost from `crew.usage_metrics`.
  4. `crews/stubs.py::run_analyst_stub` + `tests/test_stubs.py` (produces the same five files from the same hv calls, no network; `OPENAI_API_KEY` unset in the test).
  5. Real run: `python -m crews.analyst.crew` into a run dir; copy into `artifacts/crew1/`; log time, calls, cost.
- **Gate (--m 3):** (1) tests green with `OPENAI_API_KEY` unset (2) five files in `artifacts/crew1/` (3) contract validates the clean file (4) diff between `build_contract` on the clean file and the committed contract is empty outside HUMAN_FIELDS (5) `insights.md` has the five required sections and its key-numbers table equals stats.json values (6) PROJECT_LOG records duration, calls, cost of the real run.
- **Failure signals:** agent loops / exceeds max_iter → simplify task descriptions, give the tool's JSON explicitly in the next task's context; gpt-5-mini rejects `temperature` → never set it.

### M4 — Crew-2 tools: features, training, evaluation, model card
- **Branch:** `feat/m4-scientist-tools` · **Report:** `docs/reports/M4_HE.html`
- **Tasks:**
  1. `hv/features.py` (§3.6) + `tests/test_features.py`: `feature_columns` excludes id/target/protected; engineered values on a 4-row frame incl. NaN rules; `assert_no_leakage(["CustomerID"])`, `(["Churn"])`, `(["Gender"])` raise; `build_features` raises on a column absent from the contract; `write_features` twice → same sha256.
  2. `hv/evaluate.py` (§3.7) + `tests/test_evaluate.py`: majority baseline on `[0,0,0,1]`; `precision_at_top` on a hand-made ranking; `fairness_by_group` on two groups; `cv_scores` returns all keys on a 200-row synthetic set.
  3. `hv/train.py` (§3.7) + `tests/test_train.py` (synthetic 300 rows: three variants trained, `served` set, `model.joblib` loads and `predict_one` returns a probability in [0,1] for a contract-shaped row; `metrics.json` identical across two runs).
  4. `hv/model_card.py` (§3.8) + `tests/test_model_card.py` (missing section raises; headings present; fairness table rendered).
  5. `scripts/run_crew2_tools.py` (temporary, removed in M5): real run on `artifacts/crew1/` into `artifacts/crew2/`; record metrics in PROJECT_LOG (baseline, three variants, served, top importances, fairness by gender/marital status).
- **Gate (--m 4):** (1) tests green (2) `metrics.json` has `baseline` + ≥3 variants + `served` (3) leakage test: no id/target/protected column in `metrics.features` (4) model loads and predicts on the first row of `clean_data.csv` (5) two runs → identical `features.csv` and `metrics.json` (6) served ROC-AUC > baseline.
- **Failure signals:** ROC-AUC ≈ 1.0 → something leaks (check engineered features against Churn); HistGB nondeterminism → set `OMP_NUM_THREADS=1` in `hv/config.py` before sklearn import and re-check.

### M5 — Crew 2 + the Flow end to end
- **Branch:** `feat/m5-flow` · **Report:** `docs/reports/M5_HE.html`
- **Tasks:**
  1. `crews/scientist/tools.py` (§3.10) + `tests/test_sandbox.py`: `read_crew1_artifact("data/raw/…")` raises SandboxError; `../` escapes raise; a path inside crew1/ works; every scientist tool goes through `_guard`.
  2. `crews/scientist/config/*.yaml` (Feature Engineer, ML Engineer, Model Governance Officer; tasks validate → engineer_features → train_compare → evaluation_report → model_card), `crew.py`, `stubs.py::run_scientist_stub`, tests.
  3. `flow/state.py`, `flow/main.py` (§3.11) + `tests/test_flow.py` with stubs: happy path → status `published`, eight artifacts + manifest; `tamper="unit_change"` → status `handoff_failed`, `FAILED.md` exists, `crew2/` empty; `skip_crew1` copies committed artifacts; `publish=False` leaves `artifacts/` untouched.
  4. `hv/runlog.py` (§3.9) + `tests/test_runlog.py` (events.jsonl lines, manifest hashes match files).
  5. `scripts/run_flow.py` with flags and exit codes; `.gitignore` runs/ ; remove the temporary M1/M4 scripts.
  6. Real full run (both crews, gpt-5-mini) → `artifacts/`. Real tampered run → keep its `FAILED.md` as `docs/notes/failed_run_example.md`. Record durations, calls, cost.
- **Gate (--m 5):** (1) tests green (stubs) (2) `artifacts/manifest.json` lists eight artifacts whose sha256 match the files (3) `run_flow.py --stub-crews --publish false` exits 0 (4) `run_flow.py --stub-crews --skip-crew1 --tamper unit_change --publish false` exits 2 and writes FAILED.md mentioning `CashbackAmount` and the ratio hint (5) sandbox test green (6) data artifacts of the committed run equal a fresh stub run byte-for-byte (`clean_data.csv`, `features.csv`, `metrics.json`).
- **Failure signals:** CrewAI router API differences → read the installed version's `crewai.flow` source; agent writes to the wrong folder → tools receive `out_dir` explicitly and never default to `artifacts/`.

### M6 — The app: five pages + break-it panel, deployed
- **Branch:** `feat/m6-app` · **Report:** `docs/reports/M6_HE.html` (+ screenshots `docs/reports/img/m6_*.jpg`)
- **Tasks:**
  1. Visual language chosen with the frontend-design skill (distinct from FunnelIQ; English UI); `static/style.css`, `templates/base.html`.
  2. `app/artifacts.py` (loads manifest, contract, stats, metrics, markdown → HTML via `markdown` package) + `app/routes.py` for `/`, `/analyst`, `/contract`, `/scientist`, `/runs`, `/health` + `tests/test_routes.py` (each 200; contract table lists every column; markdown rendered).
  3. `POST /api/validate` (§3.12) + `tests/test_api_validate.py` (each preset → `passed: false` with the expected check; untampered → `passed: true`; uploaded CSV path; oversize upload → 413).
  4. Break-it panel: preset buttons + file upload, result rendered as the check table with failures first; `app.js` minimal fetch.
  5. Deploy; `scripts/smoke_live.py` (all pages 200, validate preset live).
- **Gate (--m 6):** (1) tests green (2) all pages 200 on `LIVE_URL` (3) `POST {LIVE_URL}/api/validate {"preset":"unit_change"}` → `passed false` with the ratio hint (4) untampered validate live → `passed true` (5) screenshots present.
- **Failure signals:** model.joblib loading on Railway needs the same sklearn version → pinned; large `eda_report.html` → serve as static file, not inline.

### M7 — Live run behind a password
- **Branch:** `feat/m7-live-run` · **Report:** `docs/reports/M7_HE.html`
- **Dor first:** `APP_PASSWORD` and `OPENAI_API_KEY` as Railway variables (only now).
- **Tasks:**
  1. `app/live.py`: `LiveRunner` (single background thread, lock, status `idle|running|done|failed`, run_dir), `start()` rejects when running; SSE generator tailing `events.jsonl`; password check via `APP_PASSWORD` (session cookie).
  2. Routes (§3.12) + templates + `tests/test_live.py` (401 without password; start with stubs in tests via `HV_STUB_CREWS=1`; second start → 409; events stream yields lines).
  3. `/runs` lists server runs from `runs/` with status and duration; a note that server runs are not committed.
  4. gunicorn: single worker + threads (`--workers 1 --threads 4`) so the runner state is shared; timeout raised for SSE.
- **Gate (--m 7):** (1) tests green (2) live: `GET /live` without password → 401/redirect (3) live full run started with the password completes (`status done`) and its events appeared in the stream (4) second start during a run → 409 (5) `OPENAI_API_KEY` absent from git history.
- **Failure signals:** Railway memory during training → `n_jobs=1` already; if OOM, run Crew 2 tools with `max_iter` lower for hist_gb on the server only (logged decision).

### M8 — Wrap-up
- **Branch:** `feat/m8-wrapup` · **Report:** `docs/reports/M8_HE.html` + `docs/reports/FINAL_HE.html`
- **Tasks:** README (stranger test: clone → env → run once → break it → run again; both outputs shown), adversarial audit with Opus agents (validator bypasses, sandbox escapes, non-determinism), measured fixes or accepted limits, `docs/STRANGER_TEST.md` executed from a fresh clone, PROJECT_LOG closed, Obsidian home marked complete.
- **Gate (--m 8):** all gates M0–M7 green in a fresh run; stranger test executed from a clean clone; README links resolve.

### M9 (optional) — Supabase
- Upload `clean_data.csv` and a `runs` table; `/runs` reads from Supabase. Only if time remains after M8.

---

## 5. Per-milestone protocol (the checklist for every M)

1. `git checkout -b feat/m<N>-<slug>` from an up-to-date `main`.
2. Open with a plain-English paragraph: what this milestone does and why.
3. Build with tests next to the code; small commits (`feat:` / `test:` / `docs:` / `fix:`).
4. `python scripts/gate.py --m N` → `GATE M<N>: PASS k/k`. Fix, don't skip.
5. `docs/reports/M<N>_HE.html` (Hebrew, RTL, Northwind design system); verify RTL in the browser.
6. Short English terminal summary: what was built, gate result, what's next.
7. Obsidian `~/Documents/Obsidian Vault/Projects/HarborVale/`: home status table, milestone note, `Log/<date> — M<N>.md`, `החלטות.md`.
8. `PROJECT_LOG.md` entry; push; `gh pr create`; CI green; Dor reviews the report and approves the merge; confirm Railway redeployed.
9. Report/log/README-status changes go on `docs/m<N>-report` after the feature PR.

## 6. Standing rules
- Provided files never modified. Artifacts of the golden run are committed; `runs/` is not.
- Every validator check has a test that makes it fail. Every preset has a test.
- Any data surprise is a `D-M<N>-x` decision with alternatives and cost.
- Numbers in reports come from `stats.json` / `metrics.json` renderers, never typed.
- Secrets scan before every push. `OPENAI_API_KEY` on Railway only from M7.
- Do not work ahead of the current milestone; if blocked on a manual step, ask.

## 7. Manual steps Dor owns (collected)
- **M0:** Railway service from the GitHub repo; paste the public domain into `.env` as `LIVE_URL`.
- **M1:** download the Kaggle dataset to `data/raw/ecommerce_churn.xlsx`.
- **M3:** `OPENAI_API_KEY` into `.env`.
- **M7:** `APP_PASSWORD` + `OPENAI_API_KEY` as Railway variables.
- **Every M:** read the Hebrew report, approve the merge.

## 8. Definition of Done
- [ ] Public GitHub repo, small PRs, green CI
- [ ] Crew 1: three agents, five files in `artifacts/crew1/`
- [ ] Crew 2: three agents, five files in `artifacts/crew2/`
- [ ] ≥3 model variants compared; model card with the five sections and a fairness table
- [ ] One Flow runs everything, with a router and a readable failure path (exit 2, FAILED.md)
- [ ] Six break-it presets fail with clear messages, in tests, in the CLI and on the live site
- [ ] Data artifacts byte-identical across runs; manifest with hashes per run
- [ ] Flask app on Railway with the break-it panel; live run behind a password
- [ ] README stranger test executed from a fresh clone; Hebrew final report; Obsidian complete
- [ ] Zero secrets in the repo history
