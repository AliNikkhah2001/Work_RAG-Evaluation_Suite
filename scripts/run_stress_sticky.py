#!/usr/bin/env python3
"""Sticky streaming multi-turn stress against local/dev orchestrator."""
from __future__ import annotations

import argparse
import json
import time
import uuid
import urllib.error
import urllib.request
from pathlib import Path

QUESTIONS = [
    "سلام",
    "گزارش اعتبارسنجی چک چیست؟",
    "رتبه آبی یعنی چه؟",
    "چطور امتیاز اعتباری را بهبود دهم؟",
    "نردبان اعتباری چیست؟",
    "تسهیلات اشخاص حقیقی چه اطلاعاتی دارد؟",
    "اعتبارسنجی چیست؟",  # QA probe early
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
    "اعتبارسنجی چیست؟",  # probe @20
    "آیا چک صیادی در گزارش می‌آید؟",
    "تفاوت اعتبارسنجی حقیقی و حقوقی چیست؟",
    "نمره اعتباری خوب چند است؟",
    "ضمانت‌نامه بانکی چه ربطی به اعتبارسنجی دارد؟",
    "رتبه سبز یعنی چه؟",
    "چگونه بفهمم چرا امتیازم کم شده؟",
    "پنل مشتریان من چه امکاناتی دارد؟",
    "آیا تاخیر در اقساط روی رتبه اثر دارد؟",
    "گزارش هیات مدیره شرکت چیست؟",
    "اعتبارسنجی چیست؟",  # probe @30
    "چک مدت‌دار چگونه ارزیابی می‌شود؟",
    "کدهای دلیل کاهش امتیاز چه هستند؟",
    "آیا می‌توانم برای وام از گزارش استفاده کنم؟",
    "رتبه نارنجی یعنی چه؟",
    "چطور اعتراض به گزارش ثبت کنم؟",
    "سقف چک برگشتی چقدر است؟",
    "اعتبارسنجی برای کفالت چگونه است؟",
    "اطلاعات هویتی در گزارش تسهیلات چیست؟",
    "آیا سابقه قضایی در گزارش هست؟",
    "اعتبارسنجی چیست؟",  # probe @40
    "چگونه طرح‌های بهبود رتبه را ببینم؟",
    "تفاوت رتبه و امتیاز چیست؟",
    "آیا کارت اعتباری روی رتبه اثر دارد؟",
    "گزارش منفی چگونه پاک می‌شود؟",
    "اشخاص حقوقی چگونه اعتبارسنجی می‌شوند؟",
    "چک ضمانتی چیست؟",
    "آیا می‌توانم گزارش شخص دیگری را ببینم؟",
    "مدت نگهداری سوابق منفی چقدر است؟",
    "نردبان اعتباری برای چه کسانی است؟",
    "اعتبارسنجی چیست؟",  # probe @50
]


def call_stream(base: str, thread: str, messages: list, timeout: float):
    body = json.dumps(
        {"model": "gemma-4-31b", "stream": True, "messages": messages},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{base.rstrip('/')}/v1/chat/completions",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Request-ID": thread,
        },
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    dt = time.time() - t0
    content_parts = []
    finish = None
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
    content = "".join(content_parts)
    return content, finish, dt, len(raw), len(json.dumps(messages, ensure_ascii=False))


def main():
    suite_root = Path(__file__).resolve().parents[1]
    default_out = suite_root / "artifacts" / "stress" / "stress_sticky_latest.json"
    ap = argparse.ArgumentParser(
        description="Sticky streaming multiturn stress (no clarify auto-reply)."
    )
    ap.add_argument("--base", default="http://127.0.0.1:8100")
    ap.add_argument("--turns", type=int, default=50)
    ap.add_argument("--timeout", type=float, default=180)
    ap.add_argument("--out", type=Path, default=default_out)
    ap.add_argument("--label", default="")
    args = ap.parse_args()

    n = min(args.turns, len(QUESTIONS))
    thread = f"stress-{args.turns}t-{uuid.uuid4().hex[:8]}"
    messages = []
    rows = []
    first_error_turn = None
    print(f"START label={args.label or args.turns} THREAD={thread} turns={n} base={args.base}", flush=True)

    for i in range(n):
        q = QUESTIONS[i]
        messages.append({"role": "user", "content": q})
        row = {
            "turn": i + 1,
            "question": q,
            "ok": False,
            "finish_reason": None,
            "err_flag": False,
            "dt_s": None,
            "ans_chars": 0,
            "payload_chars": None,
            "preview": "",
            "exception": None,
        }
        try:
            content, fr, dt, raw_len, payload_chars = call_stream(
                args.base, thread, messages, args.timeout
            )
            err = ("خطا در پردازش" in (content or "")) or fr == "error"
            row.update(
                {
                    "ok": (not err) and bool(content),
                    "finish_reason": fr,
                    "err_flag": err,
                    "dt_s": round(dt, 2),
                    "ans_chars": len(content or ""),
                    "payload_chars": payload_chars,
                    "raw_len": raw_len,
                    "preview": (content or "").replace("\n", " ")[:180],
                }
            )
            messages.append({"role": "assistant", "content": content or ""})
            status = "ERR" if err else "OK"
            print(
                f"T{i+1:02d} {status} fr={fr} dt={dt:.1f}s payload={payload_chars} ans={len(content or '')} :: {row['preview'][:100]}",
                flush=True,
            )
            if err and first_error_turn is None:
                first_error_turn = i + 1
                print(f"FIRST_ERROR_AT_TURN={first_error_turn}", flush=True)
        except Exception as e:
            row["exception"] = f"{type(e).__name__}: {e}"
            row["err_flag"] = True
            if first_error_turn is None:
                first_error_turn = i + 1
            print(f"T{i+1:02d} EXC {row['exception']}", flush=True)
            # keep going with a placeholder so history still grows like WebUI after a failure
            messages.append({"role": "assistant", "content": "خطا در پردازش درخواست."})
        rows.append(row)

    summary = {
        "label": args.label or f"{n}-turn",
        "thread": thread,
        "base": args.base,
        "requested_turns": n,
        "completed_turns": len(rows),
        "ok_turns": sum(1 for r in rows if r["ok"]),
        "err_turns": sum(1 for r in rows if r["err_flag"]),
        "first_error_turn": first_error_turn,
        "avg_dt_s": round(
            sum(r["dt_s"] for r in rows if r["dt_s"] is not None)
            / max(1, sum(1 for r in rows if r["dt_s"] is not None)),
            2,
        ),
        "max_dt_s": max((r["dt_s"] or 0) for r in rows),
        "final_payload_chars": rows[-1]["payload_chars"] if rows else 0,
        "probe_turns": [
            r
            for r in rows
            if r["question"] == "اعتبارسنجی چیست؟"
        ],
        "turns": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"DONE ok={summary['ok_turns']}/{summary['completed_turns']} err={summary['err_turns']} "
        f"first_err={first_error_turn} avg_dt={summary['avg_dt_s']}s max_dt={summary['max_dt_s']}s "
        f"out={args.out}",
        flush=True,
    )
    # non-zero exit if any error
    raise SystemExit(1 if summary["err_turns"] else 0)


if __name__ == "__main__":
    main()
