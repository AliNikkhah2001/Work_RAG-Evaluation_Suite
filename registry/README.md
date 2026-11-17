# Test registry

Single source of truth for **every** runnable test suite in the platform.

The evaluation submodule is the only component with visibility over all repos,
so the registry lives here. It does **not** require the unit tests to move:
each suite declares its own `rootdir` and `env`, so pytest runs *in place*
inside the owning repo (`kb-manager`, `orchestrator`, `guardrails`).

## Files

| File | Purpose |
|---|---|
| `suites.yaml` | Every suite: id, kind, owner, path, runner, requirements, tags |
| `versions.lock.json` | The KB snapshot + model versions the suite set was last validated against |

## Kinds

| Kind | Meaning | Needs a live stack? |
|---|---|---|
| `unit` | Offline, deterministic | No |
| `integration` | Needs KB `:8000` and/or orchestrator `:8100` | Yes |
| `e2e` | Needs the full stack | Yes |

## Running

```bash
cd components/evaluation

python scripts/run_suite.py --list                 # every registered suite
python scripts/run_suite.py --kind unit            # offline suites only
python scripts/run_suite.py --suite kb-unit        # one suite
python scripts/run_suite.py --tag reason-codes     # by tag
python scripts/run_suite.py --all                  # everything (needs the stack)
```

Reports are written to `artifacts/suite_run_latest.json` (and `.md`) and stamped
with the KB manifest the run executed against.

## Version linking — no stale tests

`versions.lock.json` records the KB corpus date, manifest id, document/chunk/
entity-list counts, pack pins and model versions. `run_suite.py` checks the live
pins (kb-source DVC pin on disk, or the KB `/api/dvc` endpoint when a stack is
up) **before running**:

```bash
python scripts/run_suite.py --check-stale   # exit 1 when stale
python scripts/run_suite.py --repin         # re-pin after an intentional KB bump
```

A mismatch **fails the run**: suites are marked `skipped` with a `stale: …`
reason and the process exits 1. This is what stops a KB or model bump from
silently passing old tests. Re-pin deliberately after re-validating.

## Adding a suite

1. Add an entry to `suites.yaml` (`id`, `kind`, `owner`, `path`, `runner`, `requires`).
2. Add a matching entry to `versions.lock.json` under `suites`.
3. `python scripts/run_suite.py --list` — the registry validates that the path exists.
4. `python scripts/run_suite.py --suite <id> --dry-run` — confirms the command.
