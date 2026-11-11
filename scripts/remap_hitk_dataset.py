#!/usr/bin/env python3
"""Remap legacy eval_clean chunk UUIDs against live KB via answer-as-query."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from work_rag_evaluation.retrieval.remap import (  # noqa: E402
    DEFAULT_MIN_OVERLAP,
    remap_dataset,
)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--src", type=Path, required=True, help="legacy eval_clean.json")
    p.add_argument(
        "--dst",
        type=Path,
        default=ROOT / "datasets/retrieval/eval_clean_remapped.json",
    )
    p.add_argument("--limit", type=int, default=None)
    p.add_argument(
        "--min-overlap",
        type=float,
        default=DEFAULT_MIN_OVERLAP,
        help=f"token overlap floor (default {DEFAULT_MIN_OVERLAP})",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help=(
            "also write datasets/retrieval/eval_clean_remapped_strict.json "
            f"(same kept rows when min-overlap>={DEFAULT_MIN_OVERLAP})"
        ),
    )
    args = p.parse_args()
    stats = asyncio.run(
        remap_dataset(args.src, args.dst, limit=args.limit, min_overlap=args.min_overlap)
    )
    print(stats)
    if args.strict:
        strict_dst = ROOT / "datasets/retrieval/eval_clean_remapped_strict.json"
        if args.min_overlap >= DEFAULT_MIN_OVERLAP:
            # Already strict — copy kept rows without a second KB pass.
            rows = json.loads(args.dst.read_text(encoding="utf-8"))
            strict_dst.parent.mkdir(parents=True, exist_ok=True)
            strict_dst.write_text(
                json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(
                {
                    "kept": len(rows),
                    "dropped": 0,
                    "path": str(strict_dst),
                    "min_overlap": args.min_overlap,
                    "copied_from": str(args.dst),
                }
            )
        else:
            strict_stats = asyncio.run(
                remap_dataset(
                    args.src,
                    strict_dst,
                    limit=args.limit,
                    min_overlap=DEFAULT_MIN_OVERLAP,
                )
            )
            print("strict:", strict_stats)
    return 0 if stats["kept"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
