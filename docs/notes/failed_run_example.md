# Run example-unit-change — handoff_failed

**Stopped at:** `validate_handoff`  
**Run directory:** `runs/example-unit-change`

# Contract validation - FAILED

**Source:** `runs/example-unit-change/crew1/clean_data.csv`  
**Checks:** 68 passed, 2 failed

| check | column | what is wrong | hint |
|---|---|---|---|
| integrity | - | sha256 47abbc60bafe differs from the contract's ef1e1f758009 | the clean file changed after the contract was written |
| range | CashbackAmount | observed [0, 32499] vs declared [0, 324.99] USD | ratio ~= 100 - looks like a unit change |

Crew 2 must not train on this file until the contract and the data agree.

Crew 2 did not run and `crew2/` is empty. Fix the data or the contract upstream, then rerun.
