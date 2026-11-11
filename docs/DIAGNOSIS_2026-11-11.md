# Diagnosis — remapped Hit@k + multiturn (2026-11-11)

Live stack: KB `:8000` (pgvector, 1471 chunks), orch `:8100`, Evaluation Suite `:8300`.
Goldens: `datasets/retrieval/eval_clean_remapped.json` (165 kept / 35 dropped) + `datasets/multiturn/conversations_v1.yaml`.

## Single-turn retrieval (Hit@k)

| Metric | Value |
|---|---|
| n | 165 |
| Hit@1 | **57.6%** |
| Hit@5 | **69.7%** |
| MRR | 0.622 |
| Miss@5 | 50 |
| In top-5 but not top-1 | 20 |

Near-perfect retrieval is **not** met. Remap validates goldens; misses are real ranking/coverage gaps.

### Failure modes (Hit@k)

1. **Hard miss (rank −1 / outside top-5)** — ~30% of queries. Typical themes in samples:
   - Cloud / API / integration ops (اتصالی ابری، قرارداد API، ذخیره خودکار گزارش)
   - Cross-source data fusion (ثبت احوال + ثبت اسناد، مالیات/بیمه/بانک)
   - Niche score tables / roles (Customer Role، تعهدات ارزی، اطلاعات تماس)
   - Edge policy (بلایای طبیعی، اعتبار زمانی گزارش چک، تاخیر قسط قبل از گزارش ماهانه)
2. **Rank > 1 but ≤ 5** — 20 queries. Hybrid/rerank ordering noise; content is findable but not top-1.
3. **Remap drop (35)** — answer text no longer overlaps any live chunk; corpus drift / deleted docs. Not scored.

### Likely causes

- Corpus gaps for ops/API and some ضمیمه tabular facts after rebuild
- Dense+BM25+rerank still under-ranks paraphrases vs lexical neighbors
- Answer-as-query remap can anchor on a *different* supporting chunk than the one query retrieval prefers (label noise residual)

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
