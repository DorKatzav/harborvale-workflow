# Project Log — HarborVale Workflow

Decisions, experiments, metrics, failures, lessons. Newest entries last.
Decision ids: `D-M<milestone>-<n>`. Design-level decisions D1–D12 live in `DESIGN_HE.html`.

## 2026-09-08 — Planning (design)
- Read the brief (`final_projec.html`): CrewAI Flow coordinating a Data Analyst crew (≥3 agents, 4 artifacts) and a Data Scientist crew (≥3 agents, 4 artifacts), with a machine-enforced `dataset_contract.json` at the seam; Flask/Streamlit app; public repo with PRs; deployment optional.
- Reviewed how Dor works from Northwind and FunnelIQ (CLAUDE.md, PLAN.md, PROJECT_LOG.md, reports) and wrote `CLAUDE.md` for this project.
- Environment facts verified: `crewai` 1.15.16 exists only in anaconda `base` (3.13); `AI_dev` (3.11) lacks it; no Kaggle CLI or credentials; `gh` logged in as DorKatzav; the git root of this folder is the whole course repo.
- Locked with Dor in conversation: solo for now (teammate possible later); dataset = E-commerce Customer Churn (Kaggle, ankitverma2010); new conda env `harborvale` (Python 3.11); Flask + HTML/CSS (full deployment wanted); Railway; app = public display + live validation + "break it" panel, with a password-protected live full run as a later milestone; model gpt-5-mini.
- Cost estimate given (published prices 2026-09-08): gpt-5-mini $0.25 / $2.00 per 1M tokens → ~$0.10–0.30 per full run with agents calling deterministic tools; Railway Hobby $5/month incl. $5 usage.
- Design doc written and verified RTL in the browser: `DESIGN_HE.html` (decisions D1–D12).

## 2026-09-08 — Planning (approved)
- Dor approved D1–D12 ("מאשר הכל"): own repo + public GitHub `harborvale-workflow`; conda `harborvale` 3.11 pinned; raw xlsx committed read-only; agents orchestrate + write, `hv/` tools compute; own JSON contract + Python validator, measured fields from the tool and human fields from the agent, all failures reported together; fail = stop with FAILED.md + exit 2, no auto-retry; nulls kept and declared, imputed in Crew 2's Pipeline; Gender/MaritalStatus not features + fairness in the model card; Crew 2 file access sandboxed to crew1 artifacts; gpt-5-mini, stubs in tests/CI; one Flask service on Railway, live run behind password in M7; M0–M8 + optional M9.
- `PLAN.md` (contracts §3, milestones §4 with gates, protocol §5) and `PLAN_HE.html` written. Obsidian project pages created.
- Next: M0 (skeleton deployed). Dor's manual step for M0: create the Railway service from the GitHub repo and paste the domain into `.env` as `LIVE_URL`.

## 2026-09-08 — M0: deployed skeleton — code complete, GATE 4/4 local (live check pending Railway)
- Own git repo initialised (course repo ignores the folder). GitHub: https://github.com/DorKatzav/harborvale-workflow (public). Branch `feat/m0-skeleton`, PR #1.
- conda env `harborvale` (Python 3.11.16): CrewAI **1.15.20** (pip resolved newer than base's 1.15.16), pandas 3.0.5, scikit-learn 1.9.0, Flask 3.1.3, pydantic 2.12.5, openai 2.54.0, gunicorn 26.2.0, pytest 9.1.1, ruff 0.16.6 — all pinned in `requirements.txt`.
- `hv/config.py` (paths, SEED, roles, ENTITY_MAP, UNITS, CSV_KW, get_llm), Flask `/health` (version, commit from `RAILWAY_GIT_COMMIT_SHA` or git, model_loaded, uptime), 8 tests, ruff, CI (OPENAI_API_KEY empty on purpose), Railway config with an explicit gunicorn start command (`--workers 1 --threads 4` so the M7 runner state is shared), `scripts/gate.py --m 0` with a key-material-only secret scan.
- Gate: PASS 4/4; live `/health` SKIPPED until Dor creates the Railway service and sets `LIVE_URL`. Local gunicorn smoke test returned `/health` with commit 2671cb5.
- Lesson: `ruff format --check` also formats code fences inside Markdown files; CI runs `ruff check` only.
- CI incident: first run failed with `ModuleNotFoundError: hv` — bare `pytest` on Actions does not put the repo root on `sys.path` (local `python -m pytest` does). Fixed with `pyproject.toml` `[tool.pytest.ini_options] pythonpath = ["."]`.
- PR #1 merged by Dor's approval (main 8951b3f). Railway service created by Dor; domain `web-production-82f247.up.railway.app`.
- Incident caught by the gate: the OpenAI key and LIVE_URL were pasted into `.env.example` (tracked) instead of `.env` (absent). Secret scan FAILED before any commit; content moved to `.env` (verified gitignored), `.env.example` restored from git. Never reached the repo. Rotation offered to Dor as optional.
- Second small fix: LIVE_URL pasted without a scheme (Railway shows the bare host) → gate prepends `https://` when missing.
- **GATE M0: PASS 5/5.** Live `/health` returns commit 8951b3f2b774 == origin/main, version 0.1.0, model_loaded false.
- Next: M1 — Crew-1 tools (ingest, cleaning, EDA). Dor: download the Kaggle file to `data/raw/ecommerce_churn.xlsx`.

## 2026-09-08 — M1 prerequisite: raw dataset committed
- Dor downloaded the Kaggle file; it landed as a single file named `data:raw:ecommerce_churn.xlsx` in the project root (macOS turns `/` into `:` in save dialogs). Moved to `data/raw/ecommerce_churn.xlsx` (555,610 bytes, sha256 db70f1e3…1bd44d). Never modified from here on.
- Sheets verified against `hv/config.py`: `E Comm` (5,630 data rows × 20 columns, header starts CustomerID, Churn, Tenure, PreferredLoginDevice, CityTier, WarehouseToHome) and `Data Dict` (22 × 4). `RAW_SHEET` / `DICT_SHEET` need no change.
- Onboarding page for a second contributor merged (PR #3): `docs/notes/ONBOARDING_HE.html`.

## 2026-09-08 — M1: Crew-1 tools (ingest, cleaning, EDA) — GATE PASSED (7/7), D-M1-1 pending approval
- Branch `feat/m1-analyst-tools`, PR #5. Tests first (synthetic 8-row frame with every kind of dirt), then `hv/ingest.py`, `hv/cleaning.py`, `hv/eda.py`; 21 new tests (29 total).
- Raw file facts (from `ingest.profile`): 5,630 × 20; 0 exact duplicate rows; 0 duplicate ids; **556 rows identical in every column except CustomerID**; nulls Tenure 264, WarehouseToHome 251, HourSpendOnApp 255, OrderAmountHikeFromlastYear 265, CouponUsed 256, OrderCount 258, DaySinceLastOrder 307; churn 16.84%.
- Entity map fixes: Phone→Mobile Phone 1,231; CC→Credit Card 273; COD→Cash on Delivery 365; Mobile→Mobile Phone 809. Entity map runs before duplicate detection: one extra pair became identical after the CC/Credit Card merge (556 raw → 557 dropped).
- Clean file: 5,073 rows, churn 16.58% (841), nulls kept (Tenure 231, WarehouseToHome 221, HourSpendOnApp 230, OrderAmountHike 252, CouponUsed 210, OrderCount 243, DaySinceLastOrder 288), sha256 ef1e1f758009fa57…; byte-identical across two runs (`stats.json` too).
- Findings (stats.json): tenure dominates — 0–1 months 51.3% churn (n 1,076) vs 7.4% / 5.7% / 5.3% for 2–6 / 7–12 / 13+; mean tenure 3.5 months (churned) vs 11.5 (stayed), r = −0.34. Complaint: 31.3% vs 10.8%, r = +0.25. Mobile Phone order category 26.3% vs Grocery 4.4%; Single 26.7% vs Married 11.3%; CityTier 3 21.9% vs tier 1 14.0%; Cash on Delivery 25.4%, E wallet 22.8%; churned customers ordered more recently (3.3 vs 4.8 days) and got less cashback (161.8 vs 180.8). Coupons: r ≈ 0.
- **D-M1-1 (proposed, pending Dor):** drop rows identical in all columns except CustomerID, keep the lowest id (default). Alternative B: keep them (`clean(drop_duplicate_records=False)`, `--keep-duplicate-records`). Rationale: identical records across CV folds inflate metrics by memorisation; cost: 557 rows (9.9%), churn rate 16.84% → 16.58%.
- Gate M1 7/7 (rows match report, no unmapped spellings, nulls exact, two runs identical, EDA self-contained). Report `docs/reports/M1_HE.html` with a screenshot of the generated EDA report.
- Lessons: pandas 3 string columns are dtype `str` (use `is_string_dtype`); skip constant columns before Pearson; entity map must run before duplicate detection.
- Housekeeping: the partner message (`docs/notes/PARTNER_SPLIT_MESSAGE.md`) was accidentally staged by `git add -A` and untracked again on the branch; it stays local.
- **D-M1-1 APPROVED by Dor (option A):** duplicate records dropped, lowest id kept. Clean file stays at 5,073 rows. PR #5 merged.
