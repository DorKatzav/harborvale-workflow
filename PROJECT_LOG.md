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
