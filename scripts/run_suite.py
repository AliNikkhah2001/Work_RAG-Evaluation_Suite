#!/usr/bin/env python3
"""Unified test-suite entry point.

    python scripts/run_suite.py --list
    python scripts/run_suite.py --list --kind unit
    python scripts/run_suite.py --suite kb-unit
    python scripts/run_suite.py --kind unit
    python scripts/run_suite.py --all
    python scripts/run_suite.py --check-stale
    python scripts/run_suite.py --repin
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from work_rag_evaluation.registry import KINDS, RegistryError, load_registry  # noqa: E402
from work_rag_evaluation.runner import run, write_report  # noqa: E402

ARTIFACTS = ROOT / "artifacts"


def _cmd_list(args: argparse.Namespace) -> int:
    reg = load_registry()
    suites = reg.suites
    if args.kind:
        suites = [s for s in suites if s.kind in set(args.kind)]
    if args.owner:
        suites = [s for s in suites if s.owner in set(args.owner)]
    if args.tag:
        suites = [s for s in suites if set(args.tag) & set(s.tags)]

    print(f"registry v{reg.version} · updated {reg.updated} · {len(suites)} suite(s)\n")
    width = max(len(s.id) for s in suites) if suites else 10
    for s in suites:
        req = "" if s.requires == "none" else f"  [{s.requires}]"
        print(f"  {s.id:<{width}}  {s.kind:<11} {s.owner:<14}{req}")
        print(f"  {'':<{width}}  {s.description.splitlines()[0] if s.description else ''}")
    problems = reg.validate()
    if problems:
        print("\nREGISTRY PROBLEMS:")
        for p in problems:
            print(f"  ! {p}")
        return 1
    return 0


def _cmd_check_stale(args: argparse.Namespace) -> int:
    reg = load_registry()
    report = reg.check_stale()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


def _cmd_repin(args: argparse.Namespace) -> int:
    reg = load_registry()
    lock = reg.repin()
    print(
        f"repinned to {lock['knowledgebase']['manifest_id']} "
        f"({lock['knowledgebase']['documents']} docs / "
        f"{lock['knowledgebase']['chunks']} chunks / "
        f"{lock['knowledgebase']['entity_lists']} entity lists)"
    )
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    result = run(
        ids=args.suite or None,
        kinds=args.kind or None,
        tags=args.tag or None,
        owners=args.owner or None,
        check_stale=not args.no_stale_check,
        fail_on_stale=not args.no_fail_on_stale,
        dry_run=args.dry_run,
        extra_args=args.pytest_args or (),
    )
    out = args.out or (ARTIFACTS / "suite_run_latest.json")
    write_report(result, out)

    for s in result.suites:
        counts = ", ".join(f"{k}={v}" for k, v in sorted(s.counts.items()))
        print(f"  {s.status.upper():<8} {s.id:<26} {counts or s.detail[:70]}")
    summary = result.summary()
    print(
        f"\n{summary['passed']}/{summary['total']} passed · "
        f"manifest={result.manifest_id} · ok={result.ok}"
    )
    print(f"report: {out}")
    if not result.stale.get("ok", True):
        print(f"\nSTALE VERSIONS: {result.stale.get('reason')}")
    return 0 if result.ok else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Unified test-suite runner")
    p.add_argument("--list", action="store_true", help="list registered suites and exit")
    p.add_argument("--suite", action="append", help="run only this suite id (repeatable)")
    p.add_argument("--kind", action="append", choices=list(KINDS), help="filter by kind")
    p.add_argument("--owner", action="append", help="filter by owning repo")
    p.add_argument("--tag", action="append", help="filter by tag")
    p.add_argument("--all", action="store_true", help="run every suite")
    p.add_argument("--check-stale", action="store_true", help="only check version staleness")
    p.add_argument("--repin", action="store_true", help="rewrite the version lock from the live pin")
    p.add_argument("--no-stale-check", action="store_true", help="skip the staleness gate")
    p.add_argument("--no-fail-on-stale", action="store_true", help="report stale but still run")
    p.add_argument("--dry-run", action="store_true", help="print commands without running")
    p.add_argument("--out", type=Path, default=None, help="report path (json + md)")
    p.add_argument("pytest_args", nargs="*", help="extra args passed to the underlying runner")
    args = p.parse_args(argv)

    try:
        if args.list:
            return _cmd_list(args)
        if args.check_stale:
            return _cmd_check_stale(args)
        if args.repin:
            return _cmd_repin(args)
        if not (args.all or args.suite or args.kind or args.tag or args.owner):
            p.error("nothing selected — pass --all, --suite, --kind, --tag or --owner")
        return _cmd_run(args)
    except RegistryError as exc:
        print(f"registry error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
