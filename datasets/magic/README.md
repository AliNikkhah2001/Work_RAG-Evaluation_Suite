# Magic fire dataset v1

Goldens for Dana `rag.magic` emission. **≥100** curated prompts covering:

- False gauges from incidental numbers (ماده ۵، سال ۱۳۸۵، ۶۸ تأمین‌کننده)
- ICS widgets: `COMPANY_TIMELINE`, `SHAREHOLDERS`, `CREDITORS`
- Score widgets only when query has explicit score/colour/grade + product
- Clarify vs colour-rank (must not skip to gauge)
- Negatives: generic FAQ, greeting, OOS company history

## Schema (JSONL)

Each line: `id`, `query`, `answer` (optional prose), `finish_reason`, `expect.fire`, `expect.names`, `expect.params_contains`, `family`, `precheck_should_gate`, `notes`, `tags`.

## Runner

```bash
python scripts/run_magic_fire.py --dataset datasets/magic/magic_fire_v1.jsonl
# live API (optional):
python scripts/run_magic_fire.py --live --base http://127.0.0.1:8100
```

Samples: **103** (fire=69, none=34)
Families: {'timeline': 14, 'none': 33, 'creditors': 8, 'shareholders': 6, 'gauge_cheque': 13, 'gauge_person': 10, 'gauge_legal': 4, 'bands': 7, 'clarify': 8}

## Precheck vs LLM

Offline runner scores **deterministic fallback** after high-recall `magic_precheck`. Production calls versioned KB `magic_judge*` prompts for every non-clarify family when precheck hits.
