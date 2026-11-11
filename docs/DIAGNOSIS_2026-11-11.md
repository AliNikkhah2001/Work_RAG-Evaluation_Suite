# Diagnosis — remapped Hit@k + multiturn (2026-11-11)

Live stack: KB `:8000` (pgvector, 1471 chunks), orch `:8100`, Evaluation Suite `:8300`.
Goldens: `datasets/retrieval/eval_clean_remapped.json` (165 kept / 35 dropped @ **weak** floor 0.30) + `datasets/multiturn/conversations_v1.yaml`.

## Label-noise caveat (Round 1 / Investigator-Samples)

**Historical Hit@5 = 69.7% is polluted.** Remap used `min_overlap` 0.30–0.35; Investigator review of miss@5 found **~39/50** were **WEAK REMAP label noise**, not ranking bugs.

| Gate | `min_overlap` | Dataset | Status |
|---|---|---|---|
| Historical (polluted) | 0.30 | `eval_clean_remapped.json` | frozen snapshot only |
| **Current / acceptance** | **0.75** | `eval_clean_remapped_strict.json` | required for Hit@k claims |

Defaults in `remap.py`, `diagnose.py`, `HitkRequest`, and remap/hygiene scripts are **0.75**. Do **not** treat the weak 69.7% figure as a retrieval regression baseline.

Offline hygiene (no KB): `python scripts/hygiene_hitk_dataset.py --write-strict` filters the weak remapped file by stored `remap_overlap`. Live re-remap needs healthy `POST /search/api` (if KB returns 500, ship defaults/code only and re-run later).

**Multiturn clarify/FAQ goldens are VALID_BUGS** — hygiene does **not** delete them.

## Single-turn retrieval (Hit@k) — historical weak remap

| Metric | Value |
|---|---|
| n | 165 |
| Hit@1 | **57.6%** |
| Hit@5 | **69.7%** (polluted — do not gate on this) |
| MRR | 0.622 |
| Miss@5 | 50 (~39 weak labels per Investigator) |
| In top-5 but not top-1 | 20 |

Near-perfect retrieval is **not** met. Re-score on the **strict** set after KB search is healthy before attributing misses to ranking/coverage.

### Failure modes (Hit@k) — under weak labels

1. **Hard miss (rank −1 / outside top-5)** — ~30% of queries on the weak set. Mix of true corpus gaps and bad goldens (overlap in [0.3, 0.75)).
2. **Rank > 1 but ≤ 5** — 20 queries. Hybrid/rerank ordering noise when labels are valid.
3. **Remap drop (35 @ 0.30)** — answer text no longer overlaps any live chunk; corpus drift / deleted docs. Not scored.
4. **Strict hygiene drop** — rows with `remap_overlap` &lt; 0.75 (~83 of 165 on the 2026-11-11 remapped file) are dropped from the acceptance set.

### Likely causes (residual after strict remap)

- Corpus gaps for ops/API and some ضمیمه tabular facts after rebuild
- Dense+BM25+rerank still under-ranks paraphrases vs lexical neighbors
- Answer-as-query remap can still anchor on a *different* supporting chunk than query retrieval prefers (residual label noise even at 0.75)

## Multi-turn (subspace / sticky / clarify)

| Result | Value |
|---|---|
| Passed | **7/12** |

### Taxonomy

| Class | Count | Meaning |
|---|---|---|
| `clarify_miss` | 2 | Expected clarify, got stop |
| `over_clarify` | 1 | Expected stop/FAQ, got clarify |
| `subspace_mismatch_or_sticky_leak` | 3 | Wrong/missing applied subspace (or sticky leak) |

### Cases

1. **clarify_miss** — `وضعیت اعتباری چطور است` in `conv_cheque_02` / `conv_facilities_person_01`  
   After a granular subspace turn, orch answers (`stop`) instead of clarifying ambiguous credit-status. Sticky context over-commits.

2. **over_clarify** — `اعتبارسنجی چیست` in `conv_greeting_faq`  
   Product bug: FAQ should `stop`/general; orch still routes to nardban/kafil clarify. Dataset label is correct; system fails.

3. **subspace_mismatch_or_sticky_leak**
   - Legal facilities open turn: expected `facilities_legal`, got `None` (applied_subspace missing from chat API and/or content inference failed).
   - Board role after legal facilities: expected switch to `general`, stayed `facilities_legal` (sticky leak).
   - Explicit “none of the above” CEO question: expected `general`, got `None`.

### Scoring caveats

- Orchestrator often omits `rag.applied_subspace`; suite falls back to content heuristics → some “None” may be instrumentation gaps, not routing bugs.
- Prefer fixing orch to emit `applied_subspace` before treating all `None` as product failures.

## Sole-source wiring

- `kb_manager.evaluation` backend **removed** (ImportError stub).
- KB `/benchmarks` UI proxies Hit@k + multiturn to `EVAL_SUITE_URL` (compose: `http://evaluation:8300`).
- Suite talks HTTP only (`/search/api`, orch chat). No KB package imports.
