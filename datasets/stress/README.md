# Sticky multiturn stress datasets

Frozen baselines and after-fix reruns for long sticky conversations against
orchestrator `:8100` (dana-local / stage).

| Path | Contents |
|------|----------|
| `results/stress_clarify_{30,40,50}.json` | Pre QA-loop-fix clarify-aware baselines |
| `results/stress_clarify_{30,40,50}_after.json` | Post-fix reruns (2026-11-16) |
| `results/stress_{30,40,50}.json` | Non-clarify sticky baselines |
| `results/compare_clarify_before_after.json` | Structured before→after metrics |
| `results/eval_final_regression.json` | Hard-case pack + LLM judge |

Narrative compare: [`docs/STRESS_CLARIFY_BEFORE_AFTER_2026-11-16.md`](../../docs/STRESS_CLARIFY_BEFORE_AFTER_2026-11-16.md).

## Re-run

```bash
# from components/evaluation
python scripts/run_stress_clarify.py --turns 50 \
  --label after-fix-50 \
  --out artifacts/stress/stress_clarify_50_live.json

python scripts/compare_stress_clarify.py
python scripts/run_stress_regression.py
```

Fresh runs write under `artifacts/stress/` (gitignored with other artifacts).
Committed JSON under `results/` are the acceptance snapshot for the QA-loop pin.
