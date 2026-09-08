# CLAUDE.md — HarborVale Workflow working agreement

Read this first in every session. Then read the tail of `PROJECT_LOG.md` (last entry) to know where we are.
The brief is `final_projec.html` (never modified): a CrewAI Flow that coordinates a Data Analyst crew and a
Data Scientist crew, with a machine-enforced `dataset_contract.json` at the seam between them.

## Language and reporting (Dor's preferences — same as Northwind and FunnelIQ)

- **Terminal conversation: English only**, short and professional. This includes questions, instructions for
  manual steps, and short replies. Hebrew never goes to the terminal (it renders badly there).
- **Hebrew (masculine forms, לשון זכר) lives only in two places:** HTML report pages and the Obsidian vault.
- **After every big action** (milestone, gate, deploy, large refactor): a Hebrew summary as an HTML page
  (`docs/reports/M<N>_HE.html` for milestones; `docs/notes/*_HE.html` for anything else), opened in the browser.
  Small things: a short English summary in the terminal, no HTML.
- **Anything long or with options** (architecture choices, a design, a comparison) goes to a Hebrew HTML page,
  not the terminal. The terminal message is a short pointer plus the question to answer.
- Hebrew HTML pages: `lang="he" dir="rtl"`, the Northwind design system (Suez One + Assistant + IBM Plex Mono;
  paper / wind / tape / gate palette — copy the `<style>` block from `../Funnell_IQ/DESIGN_HE.html` or the
  latest `docs/reports/M*_HE.html`). Numbers in tables use `class="num"` (LTR, monospace). Real `<table>`
  markup is fine in HTML. Verify RTL rendering in the browser (rtl-accessible-sites check) before calling it done.
- Never use markdown tables when writing Hebrew; in Obsidian use labeled bullet lists.
- All code, UI text, file names, commits, PR titles and bodies: English.
- Report findings as they are, even when unflattering (FunnelIQ M4: the business rule beat the model).
- Start each milestone with a plain paragraph of what it does and why (Dor is learning through the project).

## How Dor likes to work (the philosophy)

- **Design first, code second.** A new project starts with a Hebrew design doc (`DESIGN_HE.html`) with numbered
  decisions D1–Dn, each with options, a recommendation and a cost. Nothing is built until Dor approves it
  ("מאשר הכל"). Then `PLAN.md` (English: contracts, milestones, gate checks, protocol) + `PLAN_HE.html`.
- **Milestones with gates.** Work is cut into M0…Mn. Every milestone has a `scripts/gate.py --m N` that prints
  `GATE M<N>: PASS k/k` (or FAIL / SKIP with a reason). Fix, don't skip. A validation that has never been seen
  failing is untested code — break things on purpose and show the gate catching it.
- **Build only the current milestone.** Do not run ahead into the next one, and do not add unrequested
  features. If something extra is forced, do it and say plainly that it was not in the plan and why.
  Anything optional — offer it, don't add it. If blocked on a manual step, ask before working ahead.
- **Decisions are logged, surprises are decisions.** `D-M<N>-<n>` in `PROJECT_LOG.md` with alternatives and
  cost. Never a silent patch. Append; never rewrite history.
- **Numbers are generated, never typed.** Reports and findings read from `metrics.json` / generated stats.
- **Tests next to the code, no notebooks.** ML and pipeline code are tested Python packages. `pytest -q &&
  ruff check .` must be green before any push. CI runs the same.
- **Provided files are sacred.** The brief and any raw dataset are never modified.
- **Adversarial pass before wrap-up.** Stress tests / audit agents look for what the gates missed; measured
  non-fixes are documented as accepted limits.
- **Dor owns manual steps** (keys, cloud consoles, approvals). Collect them in PLAN.md §7; never type his
  passwords into a browser; never commit secrets.
- Two review moments per milestone: Dor reads the Hebrew report, then approves the merge.

## Sources of truth (do not re-derive, do not contradict)

- `final_projec.html` — the brief (Crew 1 / Crew 2 outputs, Flow requirements, tech stack).
- `DESIGN_HE.html` — design decisions D1–D12 (approved 2026-09-08).
- `PLAN.md` — contracts (§3: every function signature and file format), milestones M0–M8 (+ optional M9) with gate checks (§4), protocol (§5), standing rules (§6), Dor's manual steps (§7).
- `PROJECT_LOG.md` — decisions, experiments, metrics, incidents, lessons. Newest entries last.
- Obsidian vault `~/Documents/Obsidian Vault/Projects/HarborVale/` — Hebrew notebook: home page with a status
  table, `שלבים/` one note per milestone, `Log/<date> — M<N>.md`, `החלטות.md` (ADR style).
  Write the `.md` files directly (the Obsidian MCP server times out). Never write to the old `~/Obsidian`.

## Per-milestone protocol (every M, no shortcuts)

1. `git checkout -b feat/m<N>-<slug>` from an up-to-date `main`; one feature branch + PR per milestone.
2. Open with a short plain-English paragraph: what this milestone does and why.
3. Build with tests next to the code; small commits with `feat:` / `test:` / `docs:` / `fix:` prefixes.
4. `python scripts/gate.py --m <N>` must print `GATE M<N>: PASS k/k`.
5. Hebrew report `docs/reports/M<N>_HE.html` (+ screenshots in `docs/reports/img/m<N>_*.jpg` when there is UI).
6. Short English terminal summary: what was built, gate result, what's next.
7. Obsidian: home status table, milestone note, `Log/<date> — M<N>.md`, `החלטות.md` for any `D-M<N>-x`.
8. `PROJECT_LOG.md` entry; push; `gh pr create`; CI green; **Dor reviews the Hebrew report and approves the merge.**
9. Docs of a milestone (report, log, README status) go on a separate `docs/m<N>-report` branch + PR after the feature PR.

## Standing rules (project-specific)

- **The contract is a file, not a conversation.** `dataset_contract.json` is the only thing Crew 2 may assume.
  Crew 2 never reads raw data or Crew 1 internals; the Flow validates the contract against `clean_data.csv`
  before Crew 2 runs, and stops with a readable message when they disagree.
- Every validation has a test that makes it fail (renamed column, changed unit, deleted contract row).
- Artifacts are saved inside the repo, steps are deterministic (fixed seeds, pinned versions), and every run
  writes a clear log.
- Measured contract fields come from `hv.contract.build_contract`; agents may set only `description`, `rationale`,
  `assumptions`. The validator ignores human fields. Nulls are kept in `clean_data.csv` and imputed inside the sklearn
  Pipeline. `Gender` / `MaritalStatus` are never features. `CustomerID` / `Churn` never in X.
- Data artifacts (`clean_data.csv`, `features.csv`, `metrics.json`) must be byte-identical across runs (seed 42,
  `n_jobs=1`, `CSV_KW`, 4-decimal rounding). Agent prose may differ between runs; that is documented, not hidden.
- Tests and CI use `crews/stubs.py`; CI never calls OpenAI. Tools write only to the run directory; only the Flow
  copies to `artifacts/` after every check passes.
- Secrets only in `.env` (gitignored). `git grep -iE "sk-[A-Za-z0-9_-]{20,}|eyJ[A-Za-z0-9_-]{20,}"` must stay
  empty before every push. `.gitignore` covers `.env`, `runs/`, data dumps and virtual environments.

## Environment

- `gh` is logged in as DorKatzav. Git root of this folder is the whole course repo — this project gets its own
  repo + public GitHub repo (like FunnelIQ), never `git add -A` from the course root.
- Python: **conda env `harborvale`** (3.11), created in M0, everything pinned in `requirements.txt`:
  `source /opt/homebrew/anaconda3/bin/activate harborvale`. Never use `AI_dev` or `base` for this project
  (`crewai` in `base` is unpinned; `AI_dev` lacks it). Use `python`, not `python3` (`/usr/bin/python3` is the empty macOS one).
- LLM: OpenAI `gpt-5-mini` through CrewAI `LLM` (`hv/config.py::get_llm`). gpt-5 models reject a non-default
  `temperature` — never set it. Key name `OPENAI_API_KEY` in `.env`; on Railway only from M7.
- No Kaggle CLI or credentials on this machine — datasets are downloaded by Dor or from a direct URL.
- Report viewer: `python -m http.server 8765` from the project folder, then open in Chrome.

## Lessons already paid for (from Northwind and FunnelIQ — don't repeat)

- Never `git add -A` from the course root; the repo root is the whole course folder.
- Provider calls fail: one retry with backoff, then mark the item failed and continue — never abort the run.
- The gate's secret scan must match key material only (it once matched itself).
- Chart/table clipping and font overrides: verify UI with a real browser screenshot, not by reading the code.
- A "typical profile" made of column medians is not a real row; use real rows for defaults and examples.
- Structured outputs with an independent Python validator + one retry: zero failures on real runs.
- Keep the start command explicit in deploy config (Railway may switch builders).
