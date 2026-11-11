#!/usr/bin/env python3
"""Run curated multi-turn subspace / sticky / clarify suite."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from work_rag_evaluation.multiturn.runner import run_suite, write_report  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--conversations",
        type=Path,
        default=ROOT / "datasets/multiturn/conversations_v1.yaml",
    )
    p.add_argument("--only", type=str, default=None)
    p.add_argument("--orch", type=str, default=None)
    p.add_argument(
        "--out",
        type=Path,
        default=ROOT / "artifacts/multiturn_latest.json",
    )
    args = p.parse_args()
    result = asyncio.run(run_suite(args.conversations, only=args.only, orch_url=args.orch))
    write_report(result, args.out)
    print(f"passed {result['passed']}/{result['total']} → {args.out}")
    for c in result["conversations"]:
        print(("PASS" if c["passed"] else "FAIL"), c["id"])
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
