#!/usr/bin/env python3
"""Final QA loop regression pack + LLM judge (hard cases: safteh, guarantee, sawabegh)."""
from __future__ import annotations

import json
import os
import re
import time
import uuid
import urllib.request
from pathlib import Path

BASE = os.environ.get("ORCH_BASE", "http://127.0.0.1:8100").rstrip("/")
JUDGE_URL = os.environ.get("JUDGE_URL", "http://127.0.0.1:4000/v1/chat/completions")
JUDGE_KEY = os.environ.get("JUDGE_KEY", "sk-litellm-local-dev-change-me")
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "chat-primary")
_SUITE_ROOT = Path(__file__).resolve().parents[1]
OUT = Path(
    os.environ.get(
        "OUT",
        str(_SUITE_ROOT / "artifacts" / "stress" / "eval_final_regression.json"),
    )
)
ABSTAIN = "یافت نشد"

CASES = [
    {
        "name": "safteh",
        "hard": True,
        "stream": True,
        "turns": [{"role": "user", "content": "سفته چیست؟"}],
        "clarify_reply": "حقیقی",
        "expect_notes": "سفته not registered; NO content_filter; NO یافت نشد",
    },
    {
        "name": "guarantee_legal",
        "hard": True,
        "stream": True,
        "turns": [
            {
                "role": "user",
                "content": "ضمانت‌نامه بانکی چه ربطی به اعتبارسنجی دارد؟",
            }
        ],
        "clarify_reply": "حقوقی",
        "expect_notes": "ضمانت‌نامه bank letter topic, not personal ضامن only",
    },
    {
        "name": "sawabegh",
        "hard": True,
        "stream": False,
        "turns": [{"role": "user", "content": "چگونه سوابق منفی را رفع کنم؟"}],
        "clarify_reply": None,
        "expect_notes": "clarify not content_filter",
    },
    {
        "name": "cheque_postdated",
        "stream": True,
        "turns": [
            {"role": "user", "content": "چک مدت‌دار چگونه ارزیابی می‌شود؟"}
        ],
        "clarify_reply": None,
        "expect_notes": "stop; prefer no bare یافت نشد",
    },
    {
        "name": "credit_card",
        "stream": True,
        "turns": [
            {"role": "user", "content": "آیا کارت اعتباری روی رتبه اثر دارد؟"}
        ],
        "clarify_reply": "حقیقی",
        "expect_notes": "answer about credit card / rating",
    },
    {
        "name": "cheque_ceiling",
        "stream": True,
        "turns": [{"role": "user", "content": "سقف چک برگشتی چقدر است؟"}],
        "clarify_reply": None,
        "expect_notes": "honest refuse/ceiling OK",
    },
    {
        "name": "nardban",
        "stream": True,
        "turns": [{"role": "user", "content": "نردبان اعتباری برای چه کسانی است؟"}],
        "clarify_reply": None,
        "expect_notes": "answer about نردبان audience",
    },
]


def http_json(url, payload, headers=None, timeout=180):
    data = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def parse_stream(raw: str) -> tuple[str, str | None, dict, list[str], float]:
    t0 = time.time()
    content: list[str] = []
    fr = None
    rag: dict = {}
    comments: list[str] = []
    for line in raw.splitlines():
        if line.startswith(":"):
            comments.append(line.strip())
            continue
        if not line.startswith("data:"):
            continue
        p = line[5:].strip()
        if p == "[DONE]":
            break
        try:
            d = json.loads(p)
        except json.JSONDecodeError:
            continue
        ch = (d.get("choices") or [{}])[0]
        if (ch.get("delta") or {}).get("content"):
            content.append(ch["delta"]["content"])
        if ch.get("finish_reason"):
            fr = ch.get("finish_reason")
        if d.get("rag"):
            rag = d["rag"]
    return "".join(content), fr, rag, comments, time.time() - t0


def chat_once(messages, stream: bool, thread: str):
    body = {"model": "gemma-4-31b", "stream": stream, "messages": messages}
    if stream:
        data = json.dumps(body, ensure_ascii=False).encode()
        req = urllib.request.Request(
            f"{BASE}/v1/chat/completions",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json", "X-Request-ID": thread},
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        ans, fr, rag, comments, dt = parse_stream(raw)
        audit = {}
        return ans, fr, rag, audit, comments, dt
    d = http_json(
        f"{BASE}/v1/chat/completions",
        body,
        headers={"X-Request-ID": thread},
        timeout=180,
    )
    ch = (d.get("choices") or [{}])[0]
    ans = (ch.get("message") or {}).get("content") or ""
    fr = ch.get("finish_reason")
    rag = d.get("rag") or {}
    audit = d.get("audit") or {}
    return ans, fr, rag, audit, [], 0.0


def run_case(case: dict) -> dict:
    thread = f"final-{case['name']}-{uuid.uuid4().hex[:8]}"
    msgs = list(case["turns"])
    stream = case["stream"]
    ans, fr, rag, audit, comments, dt = chat_once(msgs, stream, thread)
    transcript = [{"fr": fr, "ans_head": ans[:220], "dt": round(dt, 2)}]
    if fr == "clarify" and case.get("clarify_reply"):
        msgs.append({"role": "assistant", "content": ans})
        msgs.append({"role": "user", "content": case["clarify_reply"]})
        ans, fr, rag, audit, comments, dt = chat_once(msgs, stream, thread)
        transcript.append(
            {
                "kind": "clarify_reply",
                "reply": case["clarify_reply"],
                "fr": fr,
                "ans_head": ans[:220],
                "dt": round(dt, 2),
            }
        )

    final = ans or ""
    has_yaft = ABSTAIN in final
    cites = len((rag or {}).get("citations") or [])
    scope_broadened = (rag or {}).get("scope_broadened")
    if scope_broadened is None:
        scope_broadened = audit.get("scope_broadened")
    scope_to = (rag or {}).get("scope_broadened_to") or audit.get(
        "scope_broadened_to"
    )
    buffering = any("guarded_generate buffering" in c for c in comments)

    heur = heuristic_pass(case["name"], fr, final, has_yaft, cites)

    return {
        "name": case["name"],
        "hard": case.get("hard", False),
        "stream": stream,
        "expect": case.get("expect_notes"),
        "fr": fr,
        "dt": round(sum(t.get("dt", 0) for t in transcript), 2),
        "has_yaft": has_yaft,
        "cites": cites,
        "scope_broadened": scope_broadened,
        "scope_to": scope_to,
        "buffering": buffering,
        "ans_head": final[:260].replace("\n", " "),
        "ans_full": final,
        "comments_tail": comments[-4:],
        "applied_subspace": (rag or {}).get("applied_subspace")
        or audit.get("applied_subspace"),
        "heuristic_pass": heur["pass"],
        "heuristic_reasons": heur["reasons"],
        "failure_class": heur.get("failure_class"),
        "transcript": transcript,
    }


def heuristic_pass(
    name: str, fr: str | None, ans: str, has_yaft: bool, cites: int
) -> dict:
    reasons: list[str] = []
    failure_class = None
    ok = True

    if fr in ("content_filter", "error"):
        ok = False
        reasons.append(f"bad_finish:{fr}")
        failure_class = "code_bug"

    if "خطا در پردازش" in ans:
        ok = False
        reasons.append("processing_error_text")
        failure_class = failure_class or "code_bug"

    if name == "safteh":
        if has_yaft and len(ans.split(ABSTAIN)[-1].strip()) < 40:
            ok = False
            reasons.append("bare_abstain")
            failure_class = failure_class or "code_bug"
        if "سفته" not in ans and fr != "clarify":
            ok = False
            reasons.append("missing_safteh_topic")
        if fr == "clarify":
            ok = False
            reasons.append("expected_answer_after_clarify")
            failure_class = failure_class or "code_bug"
        if ok and not any(
            x in ans for x in ("لحاظ", "ثبت", "گزارش", "نمی‌شود", "نمی شود")
        ):
            ok = False
            reasons.append("missing_not_registered_signal")

    elif name == "guarantee_legal":
        if fr == "clarify":
            ok = False
            reasons.append("stuck_clarify")
        if "ضمانت کردن" in ans and "ضمانت‌نامه" not in ans and "ضمانت نامه" not in ans:
            if "ضامن" in ans or "شخص ثالث" in ans:
                ok = False
                reasons.append("personal_guarantor_not_letter")
                failure_class = failure_class or "code_bug"
        if ok and not any(
            k in ans for k in ("ضمانت", "نامه", "بانک", "گزارش")
        ):
            ok = False
            reasons.append("off_topic")

    elif name == "sawabegh":
        if fr != "clarify":
            ok = False
            reasons.append(f"expected_clarify_got_{fr}")
            failure_class = failure_class or "kb_or_policy"
        if not any(k in ans for k in ("تسهیلات", "چک", "حقیقی", "حقوقی")):
            ok = False
            reasons.append("weak_clarify_text")

    elif name == "cheque_postdated":
        if has_yaft and cites == 0:
            ok = False
            reasons.append("bare_abstain_no_cites")
            failure_class = failure_class or "kb_or_policy"
        if fr not in ("stop", "clarify"):
            ok = False
            reasons.append(f"unexpected_fr:{fr}")

    elif name == "credit_card":
        if has_yaft:
            ok = False
            reasons.append("abstain")
            failure_class = failure_class or "kb_or_policy"

    elif name == "cheque_ceiling":
        pass  # honest refusal OK

    elif name == "nardban":
        if has_yaft:
            ok = False
            reasons.append("abstain")
            failure_class = failure_class or "kb_or_policy"
        if "نردبان" not in ans:
            ok = False
            reasons.append("missing_nardban")

    return {"pass": ok, "reasons": reasons, "failure_class": failure_class}


def judge_hard_cases(cases: list[dict]) -> dict:
    hard = [c for c in cases if c.get("hard")]
    prompt = (
        "You are evaluating Persian credit-scoring chatbot answers after QA fixes.\n"
        'Return ONLY JSON: {"pass":true|false,"score":0|1|2,"hard_cases":{'
        '"safteh":true|false,"guarantee_legal":true|false,"sawabegh":true|false'
        '},"reason":"..."}\n'
        "Rules:\n"
        "- safteh: after clarify حقیقی, must explain سفته is NOT in credit report; NOT content_filter; NOT bare یافت نشد.\n"
        "- guarantee_legal: after clarify حقوقی, must discuss bank guarantee letters (ضمانت‌نامه), not only personal ضامن/ضمانت کردن.\n"
        "- sawabegh: must clarify (facilities vs cheque), NOT content_filter.\n"
        "pass=true only if all three hard_cases are true.\n\n"
        f"Results:\n{json.dumps(hard, ensure_ascii=False)[:8000]}\n"
    )
    try:
        d = http_json(
            JUDGE_URL,
            {
                "model": JUDGE_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "max_tokens": 350,
            },
            headers={"Authorization": f"Bearer {JUDGE_KEY}"},
            timeout=120,
        )
        text = (d.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        return {"pass": False, "score": None, "reason": text[:300], "raw": True}
    except Exception as e:
        return {"pass": False, "score": None, "reason": f"judge_error:{e}"}


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cases = []
    for spec in CASES:
        print(f"RUN {spec['name']} ...", flush=True)
        cases.append(run_case(spec))
        print(
            f"  fr={cases[-1]['fr']} heur={cases[-1]['heuristic_pass']} "
            f"{cases[-1]['ans_head'][:100]}",
            flush=True,
        )

    judge = judge_hard_cases(cases)
    print("JUDGE", json.dumps(judge, ensure_ascii=False), flush=True)

    hard_pass = bool(judge.get("pass"))
    heur_all_hard = all(
        c["heuristic_pass"] for c in cases if c.get("hard")
    )
    regression_pass = hard_pass and heur_all_hard

    remaining_fails = []
    for c in cases:
        if c.get("hard"):
            hc = (judge.get("hard_cases") or {}).get(c["name"])
            if hc is False or not c["heuristic_pass"]:
                remaining_fails.append(
                    {
                        "name": c["name"],
                        "class": c.get("failure_class") or "code_bug",
                        "heuristic": c["heuristic_reasons"],
                    }
                )
        elif not c["heuristic_pass"]:
            remaining_fails.append(
                {
                    "name": c["name"],
                    "class": c.get("failure_class") or "kb_or_policy",
                    "heuristic": c["heuristic_reasons"],
                }
            )

    doc = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "cases": cases,
        "judge": judge,
        "judge_score": judge.get("score"),
        "hard_cases": judge.get("hard_cases"),
        "regression_pass": regression_pass,
        "remaining_fails": remaining_fails,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}", flush=True)
    return 0 if regression_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())