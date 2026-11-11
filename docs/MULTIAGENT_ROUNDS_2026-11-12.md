# Multiagent fix loop — 2026-11-12

Roles: Judge (loop) → Investigators (samples / stack / models) → Engineers → diagnose → retry (max 3 boots).

## Round 0 findings (investigators)

- Most Hit@k “misses” were **weak-remap label noise** (ov floor 0.3), not ranking.
- Multiturn clarify/FAQ/sticky labels were **product-correct**.
- Model A/B: **low impact** until code fixed; live `/search/api` was 500 (`entity_lists` missing on eval-proxy branch).
- Orch: missing `rag.applied_subspace`; clarify/FAQ bugs; prompt pin `1.0.4` dropped `answer_system`.

## Round 1 (boot 1)

| Change | Owner |
|---|---|
| Restore `entity_lists` + search from entity-lists tip | KB |
| Pin `prompts_orchestrator` **1.0.3** (answer_system) | KB packs |
| Emit `applied_subspace` / sticky on `rag` | Orch |
| Force clarify bare «وضعیت اعتباری…» | Orch |
| FAQ «اعتبارسنجی چیست» → stop/general | Orch |
| Sticky re-spec board/CEO/هیچکدوم | Orch |
| Remap `min_overlap=0.75` + strict dataset | Eval |

**Metrics:** multiturn **7/12 → 11/12**; strict Hit@k pending mid-round.

**Judge:** CONTINUE (1 multiturn fail left).

## Round 2 (boot 2)

| Change | Owner |
|---|---|
| Pin `facilities_person` on explicit حقیقی re-spec | Orch |
| Suite inference: metadata first; facilities > incidental چک | Eval |

**Metrics:** multiturn **12/12**; Hit@k strict **Hit@1 86.6% / Hit@5 98.8% / MRR 0.916** (n=82).

**Judge:** **STOP** — stretch targets met. Skip Round 3 metric boot unless pursuing Hit@1 soft-miss or live full remap.

## Uncommitted (need PR)

- `components/orchestrator` — routing + RAGMetadata
- `components/evaluation` — strict remap + scorer
- `components/knowledgebase` — entity_lists restore, prompt pin, eval proxy (branch `feature/kb-eval-suite-http-proxy`)
