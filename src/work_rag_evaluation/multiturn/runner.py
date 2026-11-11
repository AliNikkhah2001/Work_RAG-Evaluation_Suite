"""Multi-turn subspace / sticky / clarify evaluator."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ..clients import OrchClient


@dataclass
class TurnResult:
    user: str
    expected_finish: str | None
    expected_subspace: str | None
    got_finish: str | None
    got_subspace: str | None
    content: str
    ok_finish: bool
    ok_subspace: bool
    ok_extra: bool
    passed: bool
    notes: str = ""
    latency_ms: float = 0.0


@dataclass
class ConvResult:
    id: str
    passed: bool
    turns: list[TurnResult] = field(default_factory=list)


def load_conversations(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return list(data.get("conversations") or [])


def _finish_ok(expected: str | None, got: str | None) -> bool:
    if not expected:
        return True
    g = (got or "").strip()
    if expected == "greeting":
        # orch may use stop with greeting content; accept greeting|stop if content looks canned
        return g in {"greeting", "stop"}
    if expected == "content_filter":
        return g in {"content_filter", "content_filter"}
    return g == expected


def _subspace_ok(expected: str | None, got: str | None, keep_sticky: bool) -> bool:
    if not expected:
        return True
    return (got or "") == expected


def _extra_ok(turn: dict[str, Any], content: str, finish: str | None) -> bool:
    text = content or ""
    for bad in turn.get("must_not_contain") or []:
        if bad in text:
            return False
    must_any = turn.get("must_any") or []
    if must_any and not any(x in text for x in must_any):
        return False
    if turn.get("prefer_no_evidence"):
        # soft: refuse/no-evidence phrasing preferred; do not invent grades
        if any(x in text for x in ("سطح G5", "رتبه G5 معتبر", "G5 یکی از")):
            return False
    return True


async def run_conversation(
    conv: dict[str, Any],
    client: OrchClient,
) -> ConvResult:
    messages: list[dict[str, str]] = []
    request_id = f"mt-{conv['id']}"
    results: list[TurnResult] = []
    all_ok = True
    for turn in conv.get("turns") or []:
        user = turn["user"]
        messages.append({"role": "user", "content": user})
        t0 = time.monotonic()
        resp = await client.chat(messages, request_id=request_id)
        latency = (time.monotonic() - t0) * 1000
        content = resp["content"] or ""
        finish = resp["finish_reason"]
        # greeting shortcut: if content is greeting-like and expected greeting
        if turn.get("expected_finish") == "greeting" and finish == "stop":
            if any(x in content for x in ("سلام", "دانا", "دستیار")):
                finish = "greeting"
        subspace = (resp.get("rag") or {}).get("applied_subspace")
        ok_f = _finish_ok(turn.get("expected_finish"), finish)
        ok_s = _subspace_ok(
            turn.get("expected_subspace"),
            subspace,
            bool(turn.get("should_keep_sticky")),
        )
        ok_e = _extra_ok(turn, content, finish)
        # For greeting expected_finish we already coerced; subspace null ok
        if turn.get("expected_finish") == "greeting":
            ok_s = True
        passed = ok_f and ok_s and ok_e
        all_ok = all_ok and passed
        results.append(
            TurnResult(
                user=user,
                expected_finish=turn.get("expected_finish"),
                expected_subspace=turn.get("expected_subspace"),
                got_finish=finish,
                got_subspace=subspace,
                content=content[:500],
                ok_finish=ok_f,
                ok_subspace=ok_s,
                ok_extra=ok_e,
                passed=passed,
                notes=str(turn.get("notes") or ""),
                latency_ms=round(latency, 1),
            )
        )
        messages.append({"role": "assistant", "content": content})
    return ConvResult(id=conv["id"], passed=all_ok, turns=results)


async def run_suite(
    conversations_path: Path,
    *,
    only: str | None = None,
    orch_url: str | None = None,
) -> dict[str, Any]:
    convs = load_conversations(conversations_path)
    if only:
        convs = [c for c in convs if c["id"] == only]
    client = OrchClient(base_url=orch_url or OrchClient().base_url)
    out: list[dict[str, Any]] = []
    passed = 0
    for conv in convs:
        cr = await run_conversation(conv, client)
        if cr.passed:
            passed += 1
        out.append(
            {
                "id": cr.id,
                "passed": cr.passed,
                "turns": [asdict(t) for t in cr.turns],
            }
        )
    return {
        "suite": "multiturn_v1",
        "total": len(out),
        "passed": passed,
        "failed": len(out) - passed,
        "conversations": out,
    }


def write_report(result: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [f"# Multi-turn results", f"", f"passed {result['passed']}/{result['total']}", ""]
    for c in result["conversations"]:
        md.append(f"## {c['id']} — {'PASS' if c['passed'] else 'FAIL'}")
        for t in c["turns"]:
            mark = "✓" if t["passed"] else "✗"
            md.append(
                f"- {mark} finish exp={t['expected_finish']} got={t['got_finish']} | "
                f"sub exp={t['expected_subspace']} got={t['got_subspace']}"
            )
            if not t["passed"]:
                md.append(f"  Q: {t['user']}")
                md.append(f"  A: {t['content'][:200].replace(chr(10), ' ')}")
        md.append("")
    path.with_suffix(".md").write_text("\n".join(md), encoding="utf-8")
