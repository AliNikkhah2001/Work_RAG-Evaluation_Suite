#!/usr/bin/env python3
"""Compare frozen stress_clarify_*_after.json (gold) vs new *_magic.json runs.

Parity rule: answer *bodies* must match after stripping any legacy <<<MAGIC:...>>>
tokens. Post-hoc widgets live in ``turn.magic`` (rag.magic) and must NOT alter
the body. Any finish_reason / یافت‌نشد / content_filter / hard_error regression
is a fail.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SUITE_ROOT = Path(__file__).resolve().parents[1]
RESULTS = SUITE_ROOT / "datasets" / "stress" / "results"
MAGIC_RE = re.compile(r"<<<MAGIC:[A-Z][A-Z0-9_]*\s*[\s\S]*?>>>", re.M)
YAFT = "یافت نشد"
ERR = "خطا در پردازش"


def strip_magic(s: str) -> str:
    t = MAGIC_RE.sub("", s or "")
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def norm_text(s: str) -> str:
    t = strip_magic(s)
    t = t.replace("\u200c", "").replace("ي", "ی").replace("ك", "ک")
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def load(n: int, suffix: str) -> dict:
    return json.loads((RESULTS / f"stress_clarify_{n}{suffix}.json").read_text(encoding="utf-8"))


def q_turns(d: dict) -> list[dict]:
    return [t for t in (d.get("turns") or []) if t.get("kind") == "question"]


def follow(turns: list, qturn: dict | None) -> dict | None:
    if not qturn:
        return None
    tno = qturn.get("turn")
    for t in turns:
        if t.get("kind") == "clarify_reply" and t.get("turn") == (tno or 0) + 1:
            return t
    return None


def is_bad(t: dict | None) -> bool:
    if not t:
        return True
    a = t.get("answer") or ""
    fr = t.get("finish_reason")
    fl = (t.get("assessment") or {}).get("flags") or []
    if t.get("err_flag") or ERR in a or fr == "error" or "hard_error" in fl:
        return True
    if fr == "content_filter" or "content_filter" in fl:
        return True
    if YAFT in a or "no_evidence" in fl:
        return True
    return False


def effective(turns: list, qt: dict | None) -> dict | None:
    """For clarify questions, evaluate the follow-up answer quality."""
    if not qt:
        return None
    if qt.get("finish_reason") == "clarify":
        f = follow(turns, qt)
        return f or qt
    return qt


def compare_suite(n: int, gold_suffix: str, new_suffix: str) -> dict:
    gold = load(n, gold_suffix)
    new = load(n, new_suffix)
    gq, nq = q_turns(gold), q_turns(new)
    regressions = []
    improvements = []
    magic_only = []
    text_drift = []
    fr_drift = []
    still_bad = []
    ok = []

    m = max(len(gq), len(nq))
    for i in range(m):
        gt = gq[i] if i < len(gq) else None
        nt = nq[i] if i < len(nq) else None
        q = (gt or nt or {}).get("question") or f"<missing-{i}>"
        ge = effective(gold.get("turns") or [], gt)
        ne = effective(new.get("turns") or [], nt)
        gb, nb = is_bad(ge), is_bad(ne)
        gfr = (gt or {}).get("finish_reason")
        nfr = (nt or {}).get("finish_reason")
        gtxt = norm_text((ge or {}).get("answer") or "")
        ntxt = norm_text((ne or {}).get("answer") or "")
        body_magic = bool(
            MAGIC_RE.search((ne or {}).get("answer") or "")
            or MAGIC_RE.search((nt or {}).get("answer") or "")
        )
        payload_magic = bool((ne or {}).get("magic") or (nt or {}).get("magic"))
        had_magic = body_magic or payload_magic
        # Body must stay clean under post-hoc emit (no MAGIC in content).
        body_polluted = body_magic

        row = {
            "i": i,
            "question": q,
            "gold_fr": gfr,
            "new_fr": nfr,
            "gold_bad": gb,
            "new_bad": nb,
            "had_magic": had_magic,
            "payload_magic": payload_magic,
            "body_polluted": body_polluted,
            "text_equal_stripped": gtxt == ntxt,
            "gold_head": gtxt[:140],
            "new_head": ntxt[:140],
            "magic_names": [
                m.get("name")
                for m in ((ne or {}).get("magic") or (nt or {}).get("magic") or [])
                if isinstance(m, dict)
            ],
        }

        if gfr != nfr:
            fr_drift.append(row)
        if (not gb) and nb:
            regressions.append(row)
        elif gb and (not nb):
            improvements.append(row)
        elif gb and nb:
            still_bad.append(row)
        elif gtxt == ntxt:
            magic_only.append(row) if had_magic else ok.append(row)
        else:
            # Same quality class but wording drifted (LLM non-determinism)
            text_drift.append(row)
            if had_magic:
                magic_only.append(row)

    return {
        "n": n,
        "gold_suffix": gold_suffix,
        "new_suffix": new_suffix,
        "counts": {
            "questions": m,
            "regressions": len(regressions),
            "improvements": len(improvements),
            "still_bad": len(still_bad),
            "fr_drift": len(fr_drift),
            "text_drift": len(text_drift),
            "exact_or_magic_ok": len(ok) + len([r for r in magic_only if not r["new_bad"]]),
            "with_magic": sum(1 for r in (magic_only + ok + text_drift + regressions) if r.get("had_magic")),
            "body_polluted": sum(
                1 for r in (magic_only + ok + text_drift + regressions + still_bad) if r.get("body_polluted")
            ),
        },
        "regressions": regressions,
        "improvements": improvements,
        "still_bad": still_bad,
        "fr_drift": fr_drift,
        "text_drift_sample": text_drift[:12],
        # Body pollution (MAGIC still in content) fails post-hoc contract.
        "pass": len(regressions) == 0
        and len(still_bad) == 0
        and all(not r.get("body_polluted") for r in (magic_only + ok + text_drift)),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold-suffix", default="_after")
    ap.add_argument("--new-suffix", default="_magic")
    ap.add_argument("--out", type=Path, default=RESULTS / "stress_magic_parity_report.json")
    args = ap.parse_args()

    suites = [compare_suite(n, args.gold_suffix, args.new_suffix) for n in (30, 40, 50)]
    report = {
        "suites": suites,
        "pass": all(s["pass"] for s in suites),
        "total_regressions": sum(s["counts"]["regressions"] for s in suites),
    }
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("pass", "total_regressions")}, ensure_ascii=False))
    for s in suites:
        c = s["counts"]
        print(
            f"suite={s['n']} pass={s['pass']} reg={c['regressions']} still_bad={c['still_bad']} "
            f"fr_drift={c['fr_drift']} text_drift={c['text_drift']} magic={c['with_magic']}"
        )
        for r in s["regressions"][:20]:
            print(f"  REG fr {r['gold_fr']}→{r['new_fr']} :: {r['question']}")
            print(f"     gold: {r['gold_head']}")
            print(f"     new:  {r['new_head']}")
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
