# Work RAG Evaluation Suite

Sibling evaluation component for the Work Credit RAG platform.

Owns **validated** multi-turn subspace/sticky/clarify suites and **remapped** retrieval Hit@k benchmarks. Legacy trees under the umbrella (`evaluation/`, `components/evaluation/`, most of `eval/`) are retired in favor of this repo.

## Critical stance

Do not trust prior goldens blindly. See [`docs/AUDIT.md`](docs/AUDIT.md):

- Legacy `eval_clean.json` chunk UUIDs scored **0/20 Hit@5** on the live KB after corpus rebuild.
- Historical Hit@5 **69.7%** used weak remap (`min_overlap` 0.30) — Investigator found most miss@5 were **label noise**. Acceptance gate is **`min_overlap=0.75`** → `eval_clean_remapped_strict.json`.
- Some multiturn clarify labels catch **product bugs** (VALID_BUGS) — do not drop them in Hit@k hygiene.

## Suites

| Suite | Entry | What it measures |
|---|---|---|
| Multi-turn | `python scripts/run_multiturn.py` | clarify, sticky, re-spec, greeting, offtopic, FAQ, supplements |
| Hit@k | `python scripts/remap_hitk_dataset.py` (+ hygiene) then `python scripts/run_hitk.py` | Hit@1 / Hit@5 after strict answer-as-query remapping |

## Defaults

| Knob | Default | Notes |
|---|---|---|
| `min_overlap` | **0.75** | `remap.py` / `diagnose.py` / `HitkRequest` / remap+hygiene CLIs |
| Strict dataset | `datasets/retrieval/eval_clean_remapped_strict.json` | acceptance Hit@k set |
| Weak historical | `datasets/retrieval/eval_clean_remapped.json` | frozen 0.30 remap; do not gate |

## Quick start

```bash
pip install -e .
# stack must be up: orch :8100, KB :8000 (POST /search/api healthy)

# Offline hygiene on an existing remapped file (no KB required):
python scripts/hygiene_hitk_dataset.py --write-strict

# Live remap then score (needs healthy KB search):
python scripts/remap_hitk_dataset.py \
  --src datasets/retrieval/eval_clean_legacy.json \
  --min-overlap 0.75 --strict
python scripts/run_hitk.py \
  --dataset datasets/retrieval/eval_clean_remapped_strict.json

# Full diagnose (remap → strict → Hit@k → multiturn)
python scripts/diagnose.py --use-strict
```

If KB `/search/api` returns 500, still ship/use the 0.75 defaults; live remap cannot re-run until search is fixed. Offline `--write-strict` hygiene still works when `remap_overlap` is present on the weak remapped file.

Artifacts land in `artifacts/`.

## Layout

```
datasets/multiturn/conversations_v1.yaml   # curated labels only (VALID_BUGS kept)
datasets/retrieval/                        # remapped Hit@k goldens (generated)
  eval_clean_remapped.json                 # historical weak remap
  eval_clean_remapped_strict.json          # min_overlap≥0.75 acceptance set
src/work_rag_evaluation/                   # runners + clients
scripts/                                   # CLIs (remap, hygiene, diagnose, hitk, multiturn)
docs/AUDIT.md                              # why we rejected/kept each legacy source
docs/DIAGNOSIS_2026-11-11.md               # includes polluted 69.7% caveat
```

## Parent wiring

Pinned as `components/evaluation` submodule of `Work_Credit-RAG_Phase1`. KB `/benchmarks` proxies to this suite (`EVAL_SUITE_URL`); this suite talks HTTP only.
