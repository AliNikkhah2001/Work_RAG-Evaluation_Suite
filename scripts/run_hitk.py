#!/usr/bin/env python3
"""Run Hit@1 / Hit@k on a remapped retrieval dataset."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from work_rag_evaluation.retrieval.hitk import evaluate_hitk, write_hitk_report  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    strict = ROOT / "datasets/retrieval/eval_clean_remapped_strict.json"
    weak = ROOT / "datasets/retrieval/eval_clean_remapped.json"
    p.add_argument(
        "--dataset",
        type=Path,
        default=strict if strict.exists() else weak,
        help="prefer eval_clean_remapped_strict.json (min_overlap≥0.75) when present",
    )
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--out", type=Path, default=ROOT / "artifacts/hitk_latest.json")
    args = p.parse_args()
    if not args.dataset.exists():
        print(f"missing remapped dataset: {args.dataset}", file=sys.stderr)
        print("run scripts/remap_hitk_dataset.py first", file=sys.stderr)
        return 2
    result = asyncio.run(evaluate_hitk(args.dataset, top_k=args.top_k, limit=args.limit))
    write_hitk_report(result, args.out)
    print(
        f"Hit@1={result['hit1_rate']:.1%} Hit@{args.top_k}={result['hitk_rate']:.1%} "
        f"n={result['n']} → {args.out}"
    )
    # Near-perfect gate for remapped set (configurable later)
    return 0 if result["hitk_rate"] >= 0.85 else 1


if __name__ == "__main__":
    raise SystemExit(main())
