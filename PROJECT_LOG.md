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
