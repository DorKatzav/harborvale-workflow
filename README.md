# HarborVale Workflow

A CrewAI Flow in which a **Data Analyst crew** cleans a dataset and publishes a machine-checkable
`dataset_contract.json`, a **Data Scientist crew** builds a churn model only on top of that contract, and the
**Flow** validates the handoff, logs everything, saves every artifact in the repo, and refuses to train when the
contract and the data disagree.

The scenario (Harbor & Vale's churn model read dollars as cents for five weeks) and the requirements are in
`final_projec.html`. Design decisions: `DESIGN_HE.html` (Hebrew). Plan, contracts and gates: `PLAN.md`.

## Status

| Milestone | What | Status |
|---|---|---|
| M0 | Skeleton deployed: repo, env, `/health`, CI, gate | done — gate 5/5, live on Railway |
| M1 | Crew-1 tools: ingest, cleaning, EDA | |
| M2 | The contract and the validator (+ six "break it" presets) | |
| M3 | Crew 1 in CrewAI | |
| M4 | Crew-2 tools: features, training, evaluation, model card | |
| M5 | Crew 2 + the Flow end to end | |
| M6 | Flask app with the break-it panel, deployed | |
| M7 | Live run behind a password | |
| M8 | Wrap-up, stranger test | |

## Setup

```bash
conda create -n harborvale python=3.11
conda activate harborvale
pip install -r requirements.txt
cp .env.example .env          # OPENAI_API_KEY needed only to run the real crews (M3+)
```

Run the app locally: `flask --app app.main run` then open `http://127.0.0.1:5000/health`.
Tests: `pytest -q && ruff check .`. Milestone gate: `python scripts/gate.py --m 0`.

Live: https://web-production-82f247.up.railway.app/health

## Dataset

E-commerce Customer Churn (Kaggle, ankitverma2010). The raw file is committed under `data/raw/` and never modified.
