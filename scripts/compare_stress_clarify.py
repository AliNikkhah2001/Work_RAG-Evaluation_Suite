#!/usr/bin/env python3
"""Compare clarify stress baselines (before) vs after-fix reruns."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

SUITE_ROOT = Path(__file__).resolve().parents[1]
RESULTS = SUITE_ROOT / "datasets" / "stress" / "results"
DOCS = SUITE_ROOT / "docs"
YAFT = "یافت نشد"
ERR = "خطا در پردازش"

KEY_QS = [
    "چگونه سوابق منفی را رفع کنم؟",
    "سابقه سفته در اعتبارسنجی ثبت می‌شود؟",
    "ضمانت‌نامه بانکی چه ربطی به اعتبارسنجی دارد؟",
    "چک مدت‌دار چگونه ارزیابی می‌شود؟",
    "آیا کارت اعتباری روی رتبه اثر دارد؟",
    "سقف چک برگشتی چقدر است؟",
    "نردبان اعتباری برای چه کسانی است؟",
]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def metrics(d: dict) -> dict:
    turns = d.get("turns") or []
    q_turns = [t for t in turns if t.get("kind") == "question"]
    c_turns = [t for t in turns if t.get("kind") == "clarify_reply"]
    flags = Counter()
    yaft = err = cf = clarify = stop = no_ev = 0
    scores = []
    for t in turns:
        a = t.get("answer") or ""
        fr = t.get("finish_reason")
        if YAFT in a:
            yaft += 1
        if ERR in a or t.get("err_flag"):
            err += 1
        if fr == "content_filter":
            cf += 1
        if fr == "clarify":
            clarify += 1
        if fr == "stop":
            stop += 1
        ass = t.get("assessment") or {}
        if ass.get("score") is not None:
            scores.append(ass["score"])
        for f in ass.get("flags") or []:
            flags[f] += 1
            if f == "no_evidence":
                no_ev += 1
    return {
        "planned_questions": d.get("planned_questions"),
        "total_turns": len(turns),
        "ok_turns": d.get("ok_turns"),
        "err_turns": d.get("err_turns"),
        "clarify_count": clarify,
        "clarify_followups": len(c_turns),
        "stop": stop,
        "content_filter": cf,
        "yaft_in_answer": yaft,
        "no_evidence_flag": no_ev,
        "hard_error": flags.get("hard_error", 0),
        "avg_reasonableness": round(sum(scores) / len(scores), 3) if scores else 0,
        "avg_dt_s": d.get("avg_dt_s"),
        "flag_counts": dict(flags),
        "question_turns": len(q_turns),
    }


def find_q(turns: list, q: str) -> list[dict]:
    return [t for t in turns if t.get("kind") == "question" and t.get("question") == q]


def head(s: str, n: int = 160) -> str:
    return re.sub(r"\s+", " ", (s or ""))[:n]


def compare_suite(n: int) -> dict:
    before = load(RESULTS / f"stress_clarify_{n}.json")
    after = load(RESULTS / f"stress_clarify_{n}_after.json")
    mb, ma = metrics(before), metrics(after)
    key_cases = []
    for q in KEY_QS:
        if n < KEY_QS.index(q) + 1 and q not in [t.get("question") for t in before.get("turns") or []]:
            # still try — question may appear later in list
            pass
        bt = find_q(before.get("turns") or [], q)
        at = find_q(after.get("turns") or [], q)
        if not bt and not at:
            continue
        b0 = bt[0] if bt else {}
        a0 = at[0] if at else {}
        # include clarify follow-up answer if present
        def follow(turns, qturn):
            if not qturn:
                return None
            tno = qturn.get("turn")
            for t in turns:
                if t.get("kind") == "clarify_reply" and t.get("turn") == (tno or 0) + 1:
                    return t
            return None

        bf = follow(before.get("turns") or [], b0)
        af = follow(after.get("turns") or [], a0)
        key_cases.append(
            {
                "question": q,
                "before": {
                    "fr": b0.get("finish_reason"),
                    "flags": (b0.get("assessment") or {}).get("flags"),
                    "score": (b0.get("assessment") or {}).get("score"),
                    "clarify_reply": b0.get("clarify_reply"),
                    "ans": head(b0.get("answer") or ""),
                    "follow_fr": (bf or {}).get("finish_reason"),
                    "follow_flags": ((bf or {}).get("assessment") or {}).get("flags"),
                    "follow_ans": head((bf or {}).get("answer") or "") if bf else None,
                },
                "after": {
                    "fr": a0.get("finish_reason"),
                    "flags": (a0.get("assessment") or {}).get("flags"),
                    "score": (a0.get("assessment") or {}).get("score"),
                    "clarify_reply": a0.get("clarify_reply"),
                    "ans": head(a0.get("answer") or ""),
                    "follow_fr": (af or {}).get("finish_reason"),
                    "follow_flags": ((af or {}).get("assessment") or {}).get("flags"),
                    "follow_ans": head((af or {}).get("answer") or "") if af else None,
                },
            }
        )
    delta = {
        "avg_reasonableness": round(ma["avg_reasonableness"] - mb["avg_reasonableness"], 3),
        "content_filter": ma["content_filter"] - mb["content_filter"],
        "yaft_in_answer": ma["yaft_in_answer"] - mb["yaft_in_answer"],
        "no_evidence_flag": ma["no_evidence_flag"] - mb["no_evidence_flag"],
        "err_turns": (ma["err_turns"] or 0) - (mb["err_turns"] or 0),
        "hard_error": ma["hard_error"] - mb["hard_error"],
    }
    return {"n": n, "before": mb, "after": ma, "delta": delta, "key_cases": key_cases}


def main():
    suites = []
    for n in (30, 40, 50):
        after_path = RESULTS / f"stress_clarify_{n}_after.json"
        if not after_path.exists():
            print(f"MISSING after for {n}: {after_path}")
            continue
        suites.append(compare_suite(n))
    out = {"suites": suites}
    RESULTS.mkdir(parents=True, exist_ok=True)
    DOCS.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS / "compare_clarify_before_after.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # Markdown report
    lines = ["# Clarify stress before vs after QA-loop fixes", ""]
    lines.append("| Suite | avg score before → after (Δ) | content_filter | یافت‌نشد answers | no_evidence flags | hard_error |")
    lines.append("|---|---|---|---|---|---|")
    for s in suites:
        b, a, d = s["before"], s["after"], s["delta"]
        lines.append(
            f"| {s['n']} | {b['avg_reasonableness']} → {a['avg_reasonableness']} ({d['avg_reasonableness']:+}) "
            f"| {b['content_filter']}→{a['content_filter']} ({d['content_filter']:+}) "
            f"| {b['yaft_in_answer']}→{a['yaft_in_answer']} ({d['yaft_in_answer']:+}) "
            f"| {b['no_evidence_flag']}→{a['no_evidence_flag']} ({d['no_evidence_flag']:+}) "
            f"| {b['hard_error']}→{a['hard_error']} ({d['hard_error']:+}) |"
        )
    lines.append("")
    for s in suites:
        lines.append(f"## Key cases — {s['n']} turns")
        lines.append("")
        for kc in s["key_cases"]:
            lines.append(f"### {kc['question']}")
            lines.append(f"- **before**: fr={kc['before']['fr']} flags={kc['before']['flags']} score={kc['before']['score']}")
            lines.append(f"  - ans: {kc['before']['ans']}")
            if kc["before"]["follow_ans"] is not None:
                lines.append(
                    f"  - follow ({kc['before']['clarify_reply']}): fr={kc['before']['follow_fr']} "
                    f"flags={kc['before']['follow_flags']} :: {kc['before']['follow_ans']}"
                )
            lines.append(f"- **after**: fr={kc['after']['fr']} flags={kc['after']['flags']} score={kc['after']['score']}")
            lines.append(f"  - ans: {kc['after']['ans']}")
            if kc["after"]["follow_ans"] is not None:
                lines.append(
                    f"  - follow ({kc['after']['clarify_reply']}): fr={kc['after']['follow_fr']} "
                    f"flags={kc['after']['follow_flags']} :: {kc['after']['follow_ans']}"
                )
            lines.append("")
    md_path = DOCS / "STRESS_CLARIFY_BEFORE_AFTER_2026-11-16.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(md_path.read_text(encoding="utf-8"))
    print(f"WROTE {out_path} and {md_path}")


if __name__ == "__main__":
    main()
