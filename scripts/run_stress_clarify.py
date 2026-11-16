#!/usr/bin/env python3
"""Sticky streaming multi-turn stress with clarify auto-answers + full replies."""
from __future__ import annotations

import argparse
import json
import re
import time
import uuid
import urllib.request
from pathlib import Path

QUESTIONS = [
    "سلام",
    "گزارش اعتبارسنجی چک چیست؟",
    "رتبه آبی یعنی چه؟",
    "چطور امتیاز اعتباری را بهبود دهم؟",
    "نردبان اعتباری چیست؟",
    "تسهیلات اشخاص حقیقی چه اطلاعاتی دارد؟",
    "اعتبارسنجی چیست؟",
    "کفیل اعتباری کیست؟",
    "چک برگشتی چه تاثیری روی رتبه دارد؟",
    "امتیاز اعتباری چگونه محاسبه می‌شود؟",
    "تسهیلات اشخاص حقوقی شامل چیست؟",
    "رتبه زرد به چه معناست؟",
    "چگونه سوابق منفی را رفع کنم؟",
    "گزارش اعتباری مشتریان من چیست؟",
    "تامین‌کننده اعتباری چه نقشی دارد؟",
    "رتبه قرمز یعنی چه؟",
    "سابقه سفته در اعتبارسنجی ثبت می‌شود؟",
    "چطور می‌توانم رتبه خود را از زرد به آبی برسانم؟",
    "معرفی شرکت اعتبارسنجی ایران",
    "اعتبارسنجی چیست؟",
    "آیا چک صیادی در گزارش می‌آید؟",
    "تفاوت اعتبارسنجی حقیقی و حقوقی چیست؟",
    "نمره اعتباری خوب چند است؟",
    "ضمانت‌نامه بانکی چه ربطی به اعتبارسنجی دارد؟",
    "رتبه سبز یعنی چه؟",
    "چگونه بفهمم چرا امتیازم کم شده؟",
    "پنل مشتریان من چه امکاناتی دارد؟",
    "آیا تاخیر در اقساط روی رتبه اثر دارد؟",
    "گزارش هیات مدیره شرکت چیست؟",
    "اعتبارسنجی چیست؟",
    "چک مدت‌دار چگونه ارزیابی می‌شود؟",
    "کدهای دلیل کاهش امتیاز چه هستند؟",
    "آیا می‌توانم برای وام از گزارش استفاده کنم؟",
    "رتبه نارنجی یعنی چه؟",
    "چطور اعتراض به گزارش ثبت کنم؟",
    "سقف چک برگشتی چقدر است؟",
    "اعتبارسنجی برای کفالت چگونه است؟",
    "اطلاعات هویتی در گزارش تسهیلات چیست؟",
    "آیا سابقه قضایی در گزارش هست؟",
    "اعتبارسنجی چیست؟",
    "چگونه طرح‌های بهبود رتبه را ببینم؟",
    "تفاوت رتبه و امتیاز چیست؟",
    "آیا کارت اعتباری روی رتبه اثر دارد؟",
    "گزارش منفی چگونه پاک می‌شود؟",
    "اشخاص حقوقی چگونه اعتبارسنجی می‌شوند؟",
    "چک ضمانتی چیست؟",
    "آیا می‌توانم گزارش شخص دیگری را ببینم؟",
    "مدت نگهداری سوابق منفی چقدر است؟",
    "نردبان اعتباری برای چه کسانی است؟",
    "اعتبارسنجی چیست؟",
]


def call_stream(base: str, thread: str, messages: list, timeout: float, retries: int = 2):
    body = json.dumps(
        {"model": "gemma-4-31b", "stream": True, "messages": messages},
        ensure_ascii=False,
    ).encode("utf-8")
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(
            f"{base.rstrip('/')}/v1/chat/completions",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Request-ID": f"{thread}-a{attempt}",
            },
        )
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            last_exc = e
            time.sleep(1.5 * (attempt + 1))
            continue
        dt = time.time() - t0
        content_parts = []
        finish = None
        magic = None
        for line in raw.splitlines():
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                d = json.loads(payload)
            except json.JSONDecodeError:
                continue
            ch = (d.get("choices") or [{}])[0]
            delta = ch.get("delta") or {}
            if delta.get("content"):
                content_parts.append(delta["content"])
            if ch.get("finish_reason"):
                finish = ch.get("finish_reason")
            rag = d.get("rag") if isinstance(d, dict) else None
            if isinstance(rag, dict) and rag.get("magic"):
                magic = rag.get("magic")
        content = "".join(content_parts)
        # Retry transient processing failures from upstream KB blips
        if finish == "error" or "خطا در پردازش" in content:
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
        return content, finish, dt, len(json.dumps(messages, ensure_ascii=False)), magic
    if last_exc:
        raise last_exc
    return "خطا در پردازش درخواست.", "error", 0.0, len(json.dumps(messages, ensure_ascii=False)), None


def _strip_magic(text: str) -> str:
    """Ignore <<<MAGIC:...>>> payloads when routing clarify auto-replies."""
    return re.sub(r"<<<MAGIC:[A-Z][A-Z0-9_]*\s*[\s\S]*?>>>", "", text or "").strip()


def pick_clarify_reply(clarify_text: str, prior_user_q: str) -> str:
    """Choose a short subspace declaration for a clarify prompt."""
    # MAGIC clarify cards embed «چک»/«تسهیلات» JSON and must not steer routing.
    c = _strip_magic(clarify_text)
    q = prior_user_q or ""
    blob = c + " " + q

    # Cheque vs facilities
    if ("چک" in c and "تسهیلات" in c) or ("امتیاز چک" in c):
        if "چک" in q and "تسهیلات" not in q:
            return "چک"
        if "تسهیلات" in q or "وام" in q or "اقساط" in q:
            return "تسهیلات اشخاص حقیقی"
        return "چک"

    # Person vs legal
    if "حقیقی" in c and "حقوقی" in c:
        if any(w in q for w in ("حقوقی", "شرکت", "هیات مدیره", "هیئت مدیره", "سهامی")):
            return "حقوقی"
        return "حقیقی"

    if "شخصی" in c and ("شرکتی" in c or "حقوقی" in c):
        if any(w in q for w in ("حقوقی", "شرکت", "شرکتی")):
            return "شرکتی"
        return "شخصی"

    # Guarantor / ladder / general
    if "کفیل" in blob or "کفالت" in blob:
        return "کفیل"
    if "نردبان" in blob:
        return "نردبان اعتباری"
    if any(w in c for w in ("عمومی", "معرفی", "هیات مدیره", "هیئت مدیره")):
        return "عمومی"

    # Default: personal facilities (most common QA clarify fork)
    return "حقیقی"


def assess_turn(question: str, answer: str, finish: str | None) -> dict:
    """Lightweight heuristic reasonableness flags (not an LLM judge)."""
    a = answer or ""
    q = question or ""
    flags = []
    score = 1.0

    if finish == "error" or "خطا در پردازش" in a:
        flags.append("hard_error")
        score = 0.0
    elif finish == "content_filter":
        flags.append("content_filter")
        score = 0.4
    elif finish == "clarify":
        flags.append("clarify_ok" if ("؟" in a or "?" in a or "آیا" in a) else "clarify_odd")
        score = 0.7 if "clarify_ok" in flags else 0.4
    elif "یافت نشد" in a:
        flags.append("no_evidence")
        # Definition questions should rarely no-evidence
        if any(w in q for w in ("چیست", "چیه", "یعنی چه", "کیست")):
            flags.append("unexpected_no_evidence_on_definition")
            score = 0.35
        else:
            score = 0.55
    else:
        if len(a) < 40:
            flags.append("too_short")
            score = 0.45
        if finish not in ("stop", None):
            flags.append(f"unusual_finish:{finish}")
            score *= 0.8
        # topical overlap: at least one informative token from question in answer
        tokens = [t for t in re.split(r"[\s،,.؟?!:/()\-]+", q) if len(t) >= 3]
        hits = sum(1 for t in tokens if t in a)
        if tokens and hits == 0 and finish == "stop":
            flags.append("weak_lexical_overlap")
            score *= 0.7
        if not flags:
            flags.append("ok")

    return {"score": round(score, 2), "flags": flags}


def main():
    suite_root = Path(__file__).resolve().parents[1]
    default_out = suite_root / "artifacts" / "stress" / "stress_clarify_latest.json"
    ap = argparse.ArgumentParser(
        description="Sticky streaming multiturn stress with clarify auto-answers (Evaluation Suite)."
    )
    ap.add_argument("--base", default="http://127.0.0.1:8100")
    ap.add_argument("--turns", type=int, default=50)
    ap.add_argument("--timeout", type=float, default=180)
    ap.add_argument("--out", type=Path, default=default_out)
    ap.add_argument("--label", default="")
    args = ap.parse_args()

    n = min(args.turns, len(QUESTIONS))
    thread = f"stress-clarify-{args.turns}t-{uuid.uuid4().hex[:8]}"
    messages: list[dict] = []
    rows: list[dict] = []
    first_error_turn = None
    planned = QUESTIONS[:n]
    qi = 0
    turn_no = 0
    max_turns = n * 2  # room for clarify replies

    print(
        f"START label={args.label or args.turns} THREAD={thread} planned_qs={n} base={args.base}",
        flush=True,
    )

    while qi < n and turn_no < max_turns:
        q = planned[qi]
        qi += 1
        turn_no += 1
        messages.append({"role": "user", "content": q})
        row = {
            "turn": turn_no,
            "kind": "question",
            "question": q,
            "answer": "",
            "finish_reason": None,
            "err_flag": False,
            "dt_s": None,
            "payload_chars": None,
            "ans_chars": 0,
            "assessment": None,
            "clarify_reply": None,
            "magic": None,
            "exception": None,
        }
        try:
            content, fr, dt, payload_chars, magic = call_stream(
                args.base, thread, messages, args.timeout
            )
            err = ("خطا در پردازش" in (content or "")) or fr == "error"
            row.update(
                {
                    "answer": content or "",
                    "finish_reason": fr,
                    "err_flag": err,
                    "dt_s": round(dt, 2),
                    "payload_chars": payload_chars,
                    "ans_chars": len(content or ""),
                    "assessment": assess_turn(q, content or "", fr),
                    "magic": magic,
                }
            )
            messages.append({"role": "assistant", "content": content or ""})
            status = "ERR" if err else "OK"
            print(
                f"T{turn_no:02d} Q {status} fr={fr} dt={dt:.1f}s score={row['assessment']['score']} "
                f"flags={row['assessment']['flags']} :: {(content or '')[:100].replace(chr(10),' ')}",
                flush=True,
            )
            if err and first_error_turn is None:
                first_error_turn = turn_no

            # Auto-answer clarify with a subspace declaration, then continue
            if fr == "clarify" and not err:
                reply = pick_clarify_reply(content or "", q)
                row["clarify_reply"] = reply
                turn_no += 1
                messages.append({"role": "user", "content": reply})
                crow = {
                    "turn": turn_no,
                    "kind": "clarify_reply",
                    "question": reply,
                    "answer": "",
                    "finish_reason": None,
                    "err_flag": False,
                    "dt_s": None,
                    "payload_chars": None,
                    "ans_chars": 0,
                    "assessment": None,
                    "clarify_reply": None,
                    "magic": None,
                    "in_response_to": q,
                    "exception": None,
                }
                try:
                    c2, fr2, dt2, payload2, magic2 = call_stream(
                        args.base, thread, messages, args.timeout
                    )
                    err2 = ("خطا در پردازش" in (c2 or "")) or fr2 == "error"
                    crow.update(
                        {
                            "answer": c2 or "",
                            "finish_reason": fr2,
                            "err_flag": err2,
                            "dt_s": round(dt2, 2),
                            "payload_chars": payload2,
                            "ans_chars": len(c2 or ""),
                            "assessment": assess_turn(q, c2 or "", fr2),
                            "magic": magic2,
                        }
                    )
                    messages.append({"role": "assistant", "content": c2 or ""})
                    st2 = "ERR" if err2 else "OK"
                    print(
                        f"T{turn_no:02d} C {st2} reply={reply!r} fr={fr2} dt={dt2:.1f}s "
                        f"score={crow['assessment']['score']} :: {(c2 or '')[:100].replace(chr(10),' ')}",
                        flush=True,
                    )
                    if err2 and first_error_turn is None:
                        first_error_turn = turn_no
                except Exception as e:
                    crow["exception"] = f"{type(e).__name__}: {e}"
                    crow["err_flag"] = True
                    crow["answer"] = "خطا در پردازش درخواست."
                    messages.append({"role": "assistant", "content": crow["answer"]})
                    if first_error_turn is None:
                        first_error_turn = turn_no
                    print(f"T{turn_no:02d} C EXC {crow['exception']}", flush=True)
                rows.append(row)
                rows.append(crow)
                continue
        except Exception as e:
            row["exception"] = f"{type(e).__name__}: {e}"
            row["err_flag"] = True
            row["answer"] = "خطا در پردازش درخواست."
            row["assessment"] = assess_turn(q, row["answer"], "error")
            messages.append({"role": "assistant", "content": row["answer"]})
            if first_error_turn is None:
                first_error_turn = turn_no
            print(f"T{turn_no:02d} Q EXC {row['exception']}", flush=True)

        rows.append(row)

    scores = [r["assessment"]["score"] for r in rows if r.get("assessment")]
    summary = {
        "label": args.label or f"{n}-turn-clarify",
        "thread": thread,
        "base": args.base,
        "planned_questions": n,
        "total_turns_incl_clarify": len(rows),
        "ok_turns": sum(1 for r in rows if not r["err_flag"]),
        "err_turns": sum(1 for r in rows if r["err_flag"]),
        "clarify_count": sum(1 for r in rows if r.get("kind") == "question" and r.get("finish_reason") == "clarify"),
        "clarify_followups": sum(1 for r in rows if r.get("kind") == "clarify_reply"),
        "first_error_turn": first_error_turn,
        "avg_dt_s": round(
            sum(r["dt_s"] for r in rows if r["dt_s"] is not None)
            / max(1, sum(1 for r in rows if r["dt_s"] is not None)),
            2,
        ),
        "max_dt_s": max((r["dt_s"] or 0) for r in rows) if rows else 0,
        "avg_reasonableness": round(sum(scores) / len(scores), 3) if scores else 0,
        "flag_counts": {},
        "turns": rows,
    }
    for r in rows:
        for f in (r.get("assessment") or {}).get("flags") or []:
            summary["flag_counts"][f] = summary["flag_counts"].get(f, 0) + 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"DONE ok={summary['ok_turns']}/{summary['total_turns_incl_clarify']} err={summary['err_turns']} "
        f"clarify={summary['clarify_count']} avg_score={summary['avg_reasonableness']} "
        f"flags={summary['flag_counts']} out={args.out}",
        flush=True,
    )
    raise SystemExit(1 if summary["err_turns"] else 0)


if __name__ == "__main__":
    main()
