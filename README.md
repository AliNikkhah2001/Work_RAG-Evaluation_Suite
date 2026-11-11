# Work RAG Evaluation Suite

Sibling evaluation component for the Work Credit RAG platform.

Owns **validated** multi-turn subspace/sticky/clarify suites and **remapped** retrieval Hit@k benchmarks. Legacy trees under the umbrella (`evaluation/`, `components/evaluation/`, most of `eval/`) are retired in favor of this repo.

## Critical stance

Do not trust prior goldens blindly. See [`docs/AUDIT.md`](docs/AUDIT.md):

- Legacy `eval_clean.json` chunk UUIDs scored **0/20 Hit@5** on the live KB after corpus rebuild.
- Some multiturn clarify labels were wrong for current product behavior.

## Suites

| Suite | Entry | What it measures |
|---|---|---|
| Multi-turn | `python scripts/run_multiturn.py` | clarify, sticky, re-spec, greeting, offtopic, FAQ, supplements |
| Hit@k | `python scripts/remap_hitk_dataset.py` then `python scripts/run_hitk.py` | Hit@1 / Hit@5 after answer-as-query remapping |

## Quick start

```bash
pip install -e .
# stack must be up: orch :8100, KB :8000
python scripts/run_multiturn.py

# remap then score (src = path to legacy eval_clean.json)
python scripts/remap_hitk_dataset.py \
  --src ../Chatbot_production_v1/components/knowledgebase/kb-manager/kb_manager/evaluation/datasets/eval_clean.json \
  --limit 100
python scripts/run_hitk.py --limit 100
```

Artifacts land in `artifacts/`.

## Layout

```
datasets/multiturn/conversations_v1.yaml   # curated labels only
datasets/retrieval/                        # remapped Hit@k goldens (generated)
src/work_rag_evaluation/                   # runners + clients
scripts/                                   # CLIs
docs/AUDIT.md                              # why we rejected/kept each legacy source
```

## Parent wiring

Pinned as `components/evaluation` submodule of `Work_Credit-RAG_Phase1`. KB keeps its internal `kb_manager/evaluation` package for the KB UI; this suite talks HTTP only.
