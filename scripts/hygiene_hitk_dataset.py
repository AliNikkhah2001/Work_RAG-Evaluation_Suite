#!/usr/bin/env python3
"""Flag/drop weak remapped Hit@k goldens (overlap below strict floor).

Offline-safe: filters an existing remapped JSON by `remap_overlap` without
calling KB. Use after a weak remap (historical min_overlap 0.30–0.35) or to
refresh `eval_clean_remapped_strict.json`.

Does NOT touch multiturn goldens (clarify/FAQ VALID_BUGS stay intact).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from work_rag_evaluation.retrieval.remap import (  # noqa: E402
    DEFAULT_MIN_OVERLAP,
    filter_remapped_dataset,
)


def main() -> int:
    p = argparse.ArgumentParser(
        description="Hygiene filter for remapped Hit@k goldens (strict overlap gate)."
    )
    p.add_argument(
        "--src",
        type=Path,
        default=ROOT / "datasets/retrieval/eval_clean_remapped.json",
        help="remapped dataset with remap_overlap fields",
    )
    p.add_argument(
        "--min-overlap",
        type=float,
        default=DEFAULT_MIN_OVERLAP,
        help=f"drop rows with remap_overlap < this (default {DEFAULT_MIN_OVERLAP})",
    )
    p.add_argument(
        "--write-strict",
        action="store_true",
        help="write kept rows to --dst (default eval_clean_remapped_strict.json)",
    )
    p.add_argument(
        "--dst",
        type=Path,
        default=ROOT / "datasets/retrieval/eval_clean_remapped_strict.json",
    )
    p.add_argument(
        "--report",
        type=Path,
        default=ROOT / "artifacts/hygiene_hitk_latest.json",
        help="JSON report of kept/dropped/flagged samples",
    )
    args = p.parse_args()

    if not args.src.exists():
        print(f"missing source: {args.src}", file=sys.stderr)
        return 2

    stats = filter_remapped_dataset(
        args.src,
        args.dst if args.write_strict else None,
        min_overlap=args.min_overlap,
        write=args.write_strict,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"hygiene min_overlap={stats['min_overlap']}: "
        f"kept={stats['kept']} dropped={stats['dropped']} "
        f"input_n={stats['input_n']} missing_overlap={stats['missing_overlap']}"
    )
    if stats.get("path"):
        print(f"wrote strict dataset → {stats['path']}")
    print(f"wrote report → {args.report}")
    for row in (stats.get("flagged_sample") or [])[:5]:
        print(f"  flag: ov={row.get('remap_overlap')} {row.get('reason')} — {row.get('query')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
