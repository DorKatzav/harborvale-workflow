# The stranger test

Someone who has never seen this repository clones it, sets up an environment, runs the whole Flow once,
breaks the handoff on purpose, and sees it refused. No API key is needed: `--stub-crews` runs the same tools
the agents call, with canned prose. The whole thing takes about ten minutes, most of it `pip install`.

The transcript of the last execution, from a fresh clone and a fresh virtualenv, is in
[`notes/stranger_test_run.txt`](notes/stranger_test_run.txt); gate M8 checks that it exists and says what it must.

## Steps

```bash
git clone https://github.com/DorKatzav/harborvale-workflow.git
cd harborvale-workflow
python3.11 -m venv .venv && source .venv/bin/activate     # or: conda create -n harborvale python=3.11
pip install -r requirements.txt
```

**1. Run the Flow once.** Both crews (stubbed), the contract check between them, the outputs check after,
nothing published (`artifacts/` stays what git says):

```bash
python scripts/run_flow.py --stub-crews --publish false
```

Expected: every step `ok`, `validate_handoff ... checks=70 failed=[]`, `validate_outputs ... checks=6 failed=[]`,
`status:  verified`, exit code 0, and a run directory under `runs/` holding all eleven files plus `manifest.json`.

**2. Break it.** Multiply `CashbackAmount` by 100 in the run's copy of the clean file (dollars read as cents —
the fault in the brief) and try again:

```bash
python scripts/run_flow.py --stub-crews --skip-crew1 --tamper unit_change --publish false
```

Expected: `validate_handoff fail ... failed=['integrity', 'range']`, `status:  handoff_failed`, exit code 2, and
`FAILED.md` in the run directory naming `CashbackAmount` with the hint `ratio ~= 100 - looks like a unit change`.
Crew 2 never ran: `crew2/` is empty. The other five faults are `--tamper rename_column | drop_contract_field |
bad_category | dtype_change | row_loss`.

**3. Run again, and see the gate agree.**

```bash
python scripts/gate.py --m 5
pytest -q
```

Expected: `GATE M5: PASS 7/7` — including "committed data artifacts equal a fresh stub run": your machine
reproduced `clean_data.csv` and `features.csv` byte for byte and `metrics.json` within the cross-machine
tolerance (D-M4-4). Then the test suite, green, with no key in the environment.

## What you just saw

- The seam between the crews is a file, `dataset_contract.json`, and the Flow validates it against
  `clean_data.csv` before Crew 2 is allowed to start. Prose in the contract cannot change the verdict.
- A refused run stops with a readable `FAILED.md`, an exit code a script can act on, and nothing published.
- The data artifacts are deterministic; the agents' prose is not, and the project says so rather than hiding it.

## With a key

`OPENAI_API_KEY` in `.env`, then `python scripts/run_flow.py` runs the real crews with gpt-5-mini (about nine
minutes, under a dollar) and publishes into `artifacts/`. The same run is available behind a password on the
deployed site at `/live`.
