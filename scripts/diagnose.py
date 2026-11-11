#!/usr/bin/env python3
"""Diagnose single-turn Hit@k + multi-turn subspace failures on kept datasets."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from work_rag_evaluation.multiturn.runner import run_suite, write_report  # noqa: E402
from work_rag_evaluation.retrieval.hitk import evaluate_hitk, write_hitk_report  # noqa: E402
from work_rag_evaluation.retrieval.remap import remap_dataset  # noqa: E402


async def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--hitk-limit", type=int, default=200)
    p.add_argument("--skip-remap", action="store_true")
    p.add_argument("--skip-multiturn", action="store_true")
    p.add_argument("--skip-hitk", action="store_true")
    args = p.parse_args()

    report: dict = {"sections": {}}

    if not args.skip_hitk:
        legacy = ROOT / "datasets/retrieval/eval_clean_legacy.json"
        remapped = ROOT / "datasets/retrieval/eval_clean_remapped.json"
        if not args.skip_remap or not remapped.exists():
            print("Remapping Hit@k goldens (answer-as-query)...")
            stats = await remap_dataset(
                legacy, remapped, limit=args.hitk_limit, min_overlap=0.30
            )
            print("remap:", stats)
            report["sections"]["remap"] = stats
        print("Running Hit@k...")
        hitk = await evaluate_hitk(remapped, top_k=5, limit=args.hitk_limit)
        write_hitk_report(hitk, ROOT / "artifacts/hitk_latest.json")
        report["sections"]["hitk"] = {
            "n": hitk["n"],
            "hit1_rate": hitk["hit1_rate"],
            "hitk_rate": hitk["hitk_rate"],
            "mrr": hitk["mrr"],
            "by_category": hitk.get("by_category"),
        }
        # Diagnose miss patterns
        misses = [r for r in hitk["rows"] if not r["hitk"]]
        hit1_miss_hitk = [r for r in hitk["rows"] if (not r["hit1"]) and r["hitk"]]
        report["sections"]["hitk_diagnosis"] = {
            "miss_at_5": len(misses),
            "rank_gt1_but_in_top5": len(hit1_miss_hitk),
            "sample_misses": [
                {"q": r["query"], "rank": r["rank"], "got": r["retrieved"][:3]}
                for r in misses[:15]
            ],
        }
        print(
            f"Hit@1={hitk['hit1_rate']:.1%} Hit@5={hitk['hitk_rate']:.1%} "
            f"MRR={hitk['mrr']:.3f} n={hitk['n']}"
        )

    if not args.skip_multiturn:
        print("Running multi-turn...")
        mt = await run_suite(ROOT / "datasets/multiturn/conversations_v1.yaml")
        write_report(mt, ROOT / "artifacts/multiturn_latest.json")
        fail_finish = Counter()
        fail_sub = Counter()
        taxonomy = defaultdict(list)
        for c in mt["conversations"]:
            for t in c["turns"]:
                if t["passed"]:
                    continue
                key_f = (t["expected_finish"], t["got_finish"])
                fail_finish[key_f] += 1
                fail_sub[(t["expected_subspace"], t["got_subspace"])] += 1
                if t["expected_finish"] == "clarify" and t["got_finish"] != "clarify":
                    bucket = "clarify_miss"
                elif t["expected_finish"] == "stop" and t["got_finish"] == "clarify":
                    bucket = "over_clarify"
                elif t["expected_finish"] == "stop" and t["got_finish"] == "content_filter":
                    bucket = "false_offtopic"
                elif t["expected_subspace"] and t["expected_subspace"] != t["got_subspace"]:
                    bucket = "subspace_mismatch_or_sticky_leak"
                else:
                    bucket = "other"
                taxonomy[bucket].append(
                    {
                        "conv": c["id"],
                        "user": t["user"][:80],
                        "exp_finish": t["expected_finish"],
                        "got_finish": t["got_finish"],
                        "exp_sub": t["expected_subspace"],
                        "got_sub": t["got_subspace"],
                    }
                )
        report["sections"]["multiturn"] = {
            "passed": mt["passed"],
            "total": mt["total"],
            "fail_finish": {f"{a}->{b}": n for (a, b), n in fail_finish.items()},
            "taxonomy": {k: v for k, v in taxonomy.items()},
        }
        print(f"Multiturn {mt['passed']}/{mt['total']}")
        for bucket, items in taxonomy.items():
            print(f"  [{bucket}] {len(items)}")
            for it in items[:3]:
                print(f"    - {it['conv']}: {it['user']}")

    out = ROOT / "artifacts/diagnose_latest.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md = ["# Evaluation diagnosis", ""]
    hitk = report["sections"].get("hitk")
    if hitk:
        md += [
            "## Single-turn retrieval (Hit@k)",
            f"- n={hitk['n']}",
            f"- Hit@1={hitk['hit1_rate']:.1%}",
            f"- Hit@5={hitk['hitk_rate']:.1%}",
            f"- MRR={hitk['mrr']:.3f}",
            "",
            "Near-perfect expectation is **not** met. Remapped goldens are valid;",
            "misses indicate retrieval / ranking gaps on the live corpus.",
            "",
        ]
        diag = report["sections"].get("hitk_diagnosis") or {}
        md.append(f"- Miss@5 count: {diag.get('miss_at_5')}")
        md.append(f"- In top-5 but not top-1: {diag.get('rank_gt1_but_in_top5')}")
        md.append("")
    mt = report["sections"].get("multiturn")
    if mt:
        md += [
            "## Multi-turn (subspace / sticky / clarify)",
            f"- passed {mt['passed']}/{mt['total']}",
            "",
        ]
        for bucket, items in (mt.get("taxonomy") or {}).items():
            md.append(f"### {bucket} ({len(items)})")
            for it in items:
                md.append(
                    f"- `{it['conv']}` exp={it['exp_finish']}/{it['exp_sub']} "
                    f"got={it['got_finish']}/{it['got_sub']} — {it['user']}"
                )
            md.append("")
    (ROOT / "artifacts/diagnose_latest.md").write_text("\n".join(md), encoding="utf-8")
    print("wrote", out)
    print("wrote", ROOT / "artifacts/diagnose_latest.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
