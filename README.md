# HarborVale Workflow

Two AI crews, one contract between them, and a Flow that refuses to continue when the contract and the data
disagree.

A **Data Analyst crew** (CrewAI, three agents) cleans an e-commerce churn dataset and publishes a
machine-checkable `dataset_contract.json`. A **Data Scientist crew** (three agents) trains a churn model using
only that contract and the clean file — its tools refuse to open anything else. The **Flow** runs both, validates
the handoff between them with seventy checks, validates the model's outputs before publishing, hashes every
artifact into a manifest, and stops with a readable `FAILED.md` when something is wrong.

The scenario: Harbor & Vale's churn model read dollars as cents for five weeks because nothing sat between
the team that cleaned the data and the team that trained on it. The brief is in
[`final_projec.html`](final_projec.html); the design decisions (Hebrew) in [`DESIGN_HE.html`](DESIGN_HE.html);
the plan, contracts and gate checks in [`PLAN.md`](PLAN.md); every decision and number along the way in
[`PROJECT_LOG.md`](PROJECT_LOG.md).

**Live:** https://web-production-82f247.up.railway.app — the published run, a "break it" panel that runs the
validator on a tampered copy, and a live run of the whole Flow behind a password.

## Try it in ten minutes — the stranger test

No API key needed; the stub crews call the same tools the agents do, with canned prose.

```bash
git clone https://github.com/DorKatzav/harborvale-workflow.git && cd harborvale-workflow
python3.11 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

python scripts/run_flow.py --stub-crews --publish false                                # run once
python scripts/run_flow.py --stub-crews --skip-crew1 --tamper unit_change --publish false   # break it
python scripts/gate.py --m 5                                                            # the gate agrees
```

The first run ends `status:  verified` (exit 0): both crews ran, 70 handoff checks and 6 output checks passed.
The second multiplies `CashbackAmount` by 100 in the run's copy — the fault from the brief — and ends
`status:  handoff_failed` (exit 2) with a `FAILED.md` that says:

```
| check     | column         | what is wrong                                        | hint                                    |
| integrity | -              | sha256 47abbc60bafe differs from the contract's ...  | the clean file changed after the ...    |
| range     | CashbackAmount | observed [0, 32499] vs declared [0, 324.99] USD      | ratio ~= 100 - looks like a unit change |
```

Crew 2 never ran; `crew2/` is empty; nothing was published. The full walkthrough with expected outputs is
[`docs/STRANGER_TEST.md`](docs/STRANGER_TEST.md); the transcript of the last execution from a fresh clone is
[`docs/notes/stranger_test_run.txt`](docs/notes/stranger_test_run.txt); a refused run's `FAILED.md` is kept
verbatim in [`docs/notes/failed_run_example.md`](docs/notes/failed_run_example.md).

With `OPENAI_API_KEY` in `.env`, `python scripts/run_flow.py` runs the real crews with gpt-5-mini (about nine
minutes, under ten cents) and publishes into `artifacts/`.

## How it works

```
raw workbook ──► Crew 1: Data Quality Engineer · Business Analyst · Data Steward
                 clean_data.csv · eda_report.html · insights.md · dataset_contract.json
                                     │
                       validate_handoff (70 checks: integrity, columns, dtype, values,
                       range, nulls, rows, key, features)  ──► FAILED.md, exit 2
                                     │ handoff_ok
                 Crew 2: Feature Engineer · ML Engineer · Model Governance Officer
                 (sandboxed: may read only the contract and the clean file)
                 features.csv · model.joblib · metrics.json · evaluation_report.md · model_card.md
                                     │
                       validate_outputs (files, metrics shape, no leakage, beats baseline,
                       model scores a row, model card sections)  ──► FAILED.md, exit 3
                                     │ outputs_ok
                 publish: manifest.json with a sha256 per artifact ──► artifacts/
```

Three rules hold everything together:

- **The contract is a file, not a conversation.** Measured fields (dtype, role, ranges, allowed values, null
  counts, the clean file's sha256) come from code; agents may write only `description`, `rationale` and
  `assumptions`, and the validator ignores those. Six "break it" presets each have a test that makes the
  validator fail.
- **Tools compute, agents describe.** Every number in `insights.md`, the evaluation report and the model card is
  rendered from `stats.json` / `metrics.json`. Two real runs produced different prose and byte-identical data
  artifacts.
- **Determinism you can check.** `clean_data.csv`, `stats.json`, `features.csv` and `metrics.json` are byte-identical
  across runs on one machine (seed 42, `n_jobs=1`, round-trip float parsing) and within a stated tolerance
  across CPU architectures (D-M4-4); the gates re-derive them on every CI run.

## The model, in numbers

From `artifacts/crew2/metrics.json` (5,073 customers, churn rate 16.58%, five stratified folds):

| model | ROC-AUC | precision@top10 |
|---|---|---|
| baseline (majority) | 0.5000 | 0.1658 |
| logreg | 0.8913 ± 0.0169 | 0.7712 |
| random_forest | 0.9770 ± 0.0086 | 0.9487 |
| **hist_gb** (served) | **0.9857 ± 0.0051** | **0.9724** |

Of the 507 customers the served model ranks highest, 97.2% really churned. Tenure, complaints and the number of
addresses carry most of the signal — the same drivers the analyst crew's EDA found on its own. `Gender` and
`MaritalStatus` are never inputs; recall is measured per group anyway and reported in the model card.

## Status

| Milestone | What | Status |
|---|---|---|
| M0 | Skeleton deployed: repo, env, `/health`, CI, gate | done — gate 5/5, live on Railway |
| M1 | Crew-1 tools: ingest, cleaning, EDA | done — gate 7/7, 5,073 clean rows (D-M1-1) |
| M2 | The contract and the validator (+ six "break it" presets) | done — gate 5/5, 5,073 rows under contract |
| M3 | Crew 1 in CrewAI | done — 3 agents / 4 tasks, gate 8/8, real run $0.037 / 177 s |
| M4 | Crew-2 tools: features, training, evaluation, model card | done — gate 7/7, hist_gb served (roc_auc 0.9857) |
| M5 | Crew 2 + the Flow end to end | done — gate 7/7, golden run through the Flow: 21 calls, $0.074, 506 s |
| M6 | Flask app with the break-it panel, deployed | done — gate 7/7 live, all six faults refused |
| M7 | Live run behind a password | done — gate 6/6 live: a real run on Railway, verified in 503 s, $0.073 |
| M8 | Wrap-up: adversarial audit, stranger test, final report | done — see `docs/reports/M8_HE.html` and `FINAL_HE.html` |

## Repository map

```
hv/          the tools: ingest, cleaning, eda, contract (+ validator, tamper), features, train, evaluate,
             model_card, runlog, config — a tested Python package, no notebooks
crews/       analyst/ and scientist/ (agents, tasks, tools), stubs.py (no LLM), sandbox.py
flow/        the CrewAI Flow: state.py, main.py
app/         the Flask site: pages, the break-it endpoint, the live run
scripts/     run_flow.py · break_it.py · gate.py (one gate per milestone) · build_contract.py
artifacts/   the golden run: crew1/, crew2/, manifest.json, flow.log (committed; runs/ is not)
tests/       every validator check has a test that makes it fail; the crews are stubbed, CI never calls OpenAI
docs/        reports/M*_HE.html (Hebrew milestone reports), STRANGER_TEST.md, notes/
```

## Setup for development

```bash
conda create -n harborvale python=3.11 && conda activate harborvale
pip install -r requirements.txt
cp .env.example .env          # OPENAI_API_KEY for the real crews; LIVE_URL and APP_PASSWORD for the live gates
pytest -q && ruff check .
python scripts/gate.py --m 5  # any of 0..8
flask --app app.main run      # http://127.0.0.1:5000
```

CI (`.github/workflows/ci.yml`) runs ruff, pytest and gates 1–6 on ubuntu on every push, with no key.

## Dataset

E-commerce Customer Churn (Kaggle, ankitverma2010): 5,630 customers, 20 columns. The raw workbook is committed
under `data/raw/` and never modified; cleaning removes 557 duplicate records (D-M1-1), leaving 5,073.
