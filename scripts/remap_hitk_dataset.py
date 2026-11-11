#!/usr/bin/env python3
"""Remap legacy eval_clean chunk UUIDs against live KB via answer-as-query."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from work_rag_evaluation.retrieval.remap import remap_dataset  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--src", type=Path, required=True, help="legacy eval_clean.json")
    p.add_argument(
        "--dst",
        type=Path,
        default=ROOT / "datasets/retrieval/eval_clean_remapped.json",
    )
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--min-overlap", type=float, default=0.35)
    args = p.parse_args()
    stats = asyncio.run(
        remap_dataset(args.src, args.dst, limit=args.limit, min_overlap=args.min_overlap)
    )
    print(stats)
    return 0 if stats["kept"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
