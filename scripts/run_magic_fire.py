#!/usr/bin/env python3
"""Score the magic_fire dataset (offline rules + optional live API).

Offline (default): imports orchestrator ``magic_precheck`` + ``collect_magic_payload``
and checks expect.names / params_contains. No LLM call (deterministic path).

Live: POST /v1/chat/completions and compare ``rag.magic``.

Usage:
  PYTHONPATH=../orchestrator/src python scripts/run_magic_fire.py
  PYTHONPATH=../orchestrator/src python scripts/run_magic_fire.py --live --base http://127.0.0.1:8100
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DS = ROOT / "datasets" / "magic" / "magic_fire_v1.jsonl"


def load_rows(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def params_match(got: dict, want: dict) -> bool:
    for k, v in (want or {}).items():
        if got.get(k) != v:
            return False
    return True


def score_offline(rows: list[dict]) -> dict:
    from work_rag_orchestrator.magic_judge import magic_precheck
    from work_rag_orchestrator.magic_emit import collect_magic_payload

    ok = fail = 0
    failures = []
    for r in rows:
        q = r["query"]
        fr = r.get("finish_reason") or "stop"
        fam = magic_precheck(q, fr)
        gate_ok = (len(fam) > 0) == bool(r.get("precheck_should_gate"))
        # clarify finish always gates
        if fr == "clarify":
            gate_ok = True
        payload = collect_magic_payload(
            {
                "query": q,
                "needs_clarification": fr == "clarify",
                "supplemental": [],
            },
            r.get("answer") or "",
            finish_reason=fr,
            families=fam,
        )
        names = [p.get("name") for p in payload]
        exp = r.get("expect") or {}
        exp_names = exp.get("names") or []
        fire_ok = (bool(names) == bool(exp.get("fire"))) and (
            set(names) == set(exp_names) if exp_names or not names else True
        )
        # Allow timeline when expected timeline even if extra empty
        if exp_names and set(exp_names).issubset(set(names)) and len(names) <= len(exp_names) + 0:
            fire_ok = set(names) == set(exp_names)
        pc = exp.get("params_contains") or {}
        param_ok = True
        if pc and payload:
            param_ok = params_match(payload[0].get("params") or {}, pc)
        passed = gate_ok and fire_ok and param_ok
        if passed:
            ok += 1
        else:
            fail += 1
            failures.append(
                {
                    "id": r["id"],
                    "query": q,
                    "expect": exp_names,
                    "got": names,
                    "fam": sorted(fam),
                    "gate_ok": gate_ok,
                    "param_ok": param_ok,
                    "params": (payload[0].get("params") if payload else None),
                }
            )
    return {"ok": ok, "fail": fail, "total": len(rows), "failures": failures}


def score_live(rows: list[dict], base: str, limit: int | None = None) -> dict:
    ok = fail = 0
    failures = []
    for r in rows[: limit or len(rows)]:
        if r.get("finish_reason") == "content_filter":
            continue
        body = json.dumps(
            {
                "model": "gemma-4-31b",
                "messages": [{"role": "user", "content": r["query"]}],
                "stream": False,
            }
        ).encode()
        req = urllib.request.Request(
            base.rstrip("/") + "/v1/chat/completions",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                d = json.loads(resp.read().decode())
        except Exception as e:
            fail += 1
            failures.append({"id": r["id"], "error": str(e)})
            continue
        magic = (d.get("rag") or {}).get("magic") or []
        names = [m.get("name") for m in magic]
        fr = (d.get("choices") or [{}])[0].get("finish_reason")
        exp = r.get("expect") or {}
        exp_names = exp.get("names") or []
        # Soft: if expect clarify and finish=clarify with CLARIFY_OPTIONS
        if "CLARIFY_OPTIONS" in exp_names:
            passed = "CLARIFY_OPTIONS" in names or fr == "clarify"
        elif not exp.get("fire"):
            passed = names == []
        else:
            passed = set(exp_names) == set(names)
        pc = exp.get("params_contains") or {}
        if passed and pc and magic:
            passed = params_match(magic[0].get("params") or {}, pc)
        if passed:
            ok += 1
        else:
            fail += 1
            failures.append(
                {
                    "id": r["id"],
                    "query": r["query"],
                    "expect": exp_names,
                    "got": names,
                    "finish": fr,
                    "ms": int((time.time() - t0) * 1000),
                }
            )
        print(
            json.dumps(
                {"id": r["id"], "ok": passed, "got": names, "finish": fr},
                ensure_ascii=False,
            )
        )
    return {"ok": ok, "fail": fail, "total": ok + fail, "failures": failures}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=Path, default=DEFAULT_DS)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--base", default="http://127.0.0.1:8100")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    rows = load_rows(args.dataset)
    if args.limit:
        rows = rows[: args.limit]
    if args.live:
        report = score_live(rows, args.base, args.limit)
    else:
        report = score_offline(rows)
    out = args.out or (
        ROOT
        / "datasets"
        / "magic"
        / ("magic_fire_live_report.json" if args.live else "magic_fire_offline_report.json")
    )
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"pass={report['ok']}/{report['total']} fail={report['fail']} -> {out}",
        file=sys.stderr,
    )
    if report["failures"][:15]:
        print("first failures:", file=sys.stderr)
        for f in report["failures"][:15]:
            print(f"  {f}", file=sys.stderr)
    return 0 if report["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
