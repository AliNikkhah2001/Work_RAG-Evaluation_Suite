# Critical audit of legacy evaluation sources (2026-11-11)

Presumption: every prior eval asset is **untrusted** until live-validated.

## Verdict table

| Source | Verdict | Why |
|---|---|---|
| `evaluation/bench_runner.py` structure | **Salvage** | Good sticky/clarify/respec design; labels need curation |
| Clarify: `وضعیت اعتباری چطور است` | **Keep** | Live orch returns `finish_reason=clarify` |
| Clarify: `بدهکار شدم چیکار کنم` | **Reject** | Live returns `content_filter` (offtopic), not clarify |
| Clarify: `اعتبارسنجی چیست` | **Relabel → stop/general** | FAQ should answer; live currently clarifies (nardban/kafil) — that is a product bug to catch, not a golden clarify |
| Sticky / re-spec turns | **Keep** (spot-check) | Cheque sticky + facilities↔cheque re-spec are valid |
| `evaluation/ragas_eval.py` (1.3k LOC) | **Rewrite thin** | Bloated; custom metrics OK but not as-is |
| `evaluation/report.py` (1.5k LOC) | **Rewrite thin** | Keep JSON summary + short MD |
| `components/evaluation/*` | **Delete** | Duplicate of `evaluation/` |
| `eval/run_llm_*` / guardrails samples | **Defer** | Valuable later; not needed for subspace/Hit@k MVP |
| `eval/run_e2e.py` | **Delete** | Drifted ports; incomplete |
| `eval_clean.json` chunk UUIDs | **Invalid** | Live Hit@1/Hit@5 by ID = **0/20** after corpus rebuild |
| `eval_clean.json` queries + answers | **Salvage via remap** | Remap expected IDs by searching with `expected_answer` text against live KB |
| KB `kb_manager/evaluation/*` package | **Removed** | KB UI proxies to Evaluation Suite (`EVAL_SUITE_URL`); suite calls HTTP `/search/api` only |

## Hit@k remapping rule (non-tautological)

1. For each golden `(query, expected_answer)`, call `/search/api` with **`expected_answer`** (answer-as-query) → candidate chunk ids that *contain* the ground truth.
2. Keep top overlapping candidates as `expected_chunk_ids` only if token overlap ≥ **`min_overlap` (default 0.75)**.
3. Evaluate Hit@k by searching with **`query` only** against those remapped ids.
4. Drop items that cannot remap (no answer overlap) — do not invent IDs from query-only hits (that would force ~100% Hit@k).
5. **Strict hygiene:** `scripts/hygiene_hitk_dataset.py --write-strict` drops rows with `remap_overlap` &lt; 0.75 into `eval_clean_remapped_strict.json`. Historical weak remap (0.30–0.35) produced the polluted Hit@5≈69.7% snapshot — not an acceptance baseline.
6. Multiturn clarify/FAQ goldens are **VALID_BUGS** — never deleted by Hit@k hygiene.

Content-proxy check (query search vs answer overlap ≥0.25): ~18–21/30 on a random sample — retrieval is useful but **not** near-perfect until remapped goldens exist.

## Product expectations for multiturn MVP

| Behavior | Expectation |
|---|---|
| Scattered credit status | `clarify` |
| Greeting | `greeting` / canned |
| Granular cheque / facilities | `stop` + matching `applied_subspace` |
| Sticky anaphora | same subspace after granular |
| Explicit re-spec | subspace switches |
| Offtopic debt slang | `content_filter` (not clarify) |
| «اعتبارسنجی چیست» | `stop` + general FAQ answer (fail if clarify) |
| Shareholders list | `stop` + entity/supplement evidence |
