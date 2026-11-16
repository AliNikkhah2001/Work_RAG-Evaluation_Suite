#!/usr/bin/env python3
"""Generate RTL HTML comparing before vs after clarify stress full answers."""
from __future__ import annotations

import html
import json
from pathlib import Path

SUITE_ROOT = Path(__file__).resolve().parents[1]
RESULTS = SUITE_ROOT / "datasets" / "stress" / "results"
OUT = SUITE_ROOT / "docs" / "stress_clarify_before_after_rtl.html"
YAFT = "یافت نشد"
ERR = "خطا در پردازش"


def load(n: int, suffix: str) -> dict:
    return json.loads((RESULTS / f"stress_clarify_{n}{suffix}.json").read_text(encoding="utf-8"))


def flags(t: dict) -> list[str]:
    return list((t.get("assessment") or {}).get("flags") or [])


def score(t: dict):
    return (t.get("assessment") or {}).get("score")


def is_bad(t: dict) -> bool:
    if not t:
        return False
    fr = t.get("finish_reason")
    a = t.get("answer") or ""
    fl = flags(t)
    if t.get("err_flag") or ERR in a or fr == "error" or "hard_error" in fl:
        return True
    if fr == "content_filter" or "content_filter" in fl:
        return True
    if YAFT in a or "no_evidence" in fl:
        return True
    return False


def bad_reasons(t: dict) -> list[str]:
    fr = t.get("finish_reason")
    a = t.get("answer") or ""
    fl = flags(t)
    rs = []
    if t.get("err_flag") or ERR in a or fr == "error" or "hard_error" in fl:
        rs.append("خطای سخت")
    if fr == "content_filter" or "content_filter" in fl:
        rs.append("content_filter")
    if YAFT in a or "no_evidence" in fl:
        rs.append("یافت نشد / no_evidence")
    if "unexpected_no_evidence_on_definition" in fl:
        rs.append("تعریف بدون شواهد")
    if "weak_lexical_overlap" in fl:
        rs.append("هم‌پوشانی ضعیف")
    if "too_short" in fl:
        rs.append("پاسخ کوتاه")
    return rs or (["ضعیف"] if is_bad(t) else [])


def esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def follow(turns, qturn):
    if not qturn:
        return None
    tno = qturn.get("turn")
    for t in turns:
        if t.get("kind") == "clarify_reply" and t.get("turn") == (tno or 0) + 1:
            return t
    return None


def pair_turns(before: dict, after: dict) -> list[dict]:
    bq = [t for t in before["turns"] if t.get("kind") == "question"]
    aq = [t for t in after["turns"] if t.get("kind") == "question"]
    n = max(len(bq), len(aq))
    pairs = []
    for i in range(n):
        bt = bq[i] if i < len(bq) else None
        at = aq[i] if i < len(aq) else None
        q = (bt or at or {}).get("question") or ""
        bf = follow(before["turns"], bt) if bt else None
        af = follow(after["turns"], at) if at else None
        b_eval = bf if (bt and bt.get("finish_reason") == "clarify" and bf) else bt
        a_eval = af if (at and at.get("finish_reason") == "clarify" and af) else at

        def status(b, a):
            bb = is_bad(b) if b else False
            aa = is_bad(a) if a else False
            if bb and not aa:
                return "improved"
            if (not bb) and aa:
                return "regressed"
            if bb and aa:
                return "still_bad"
            return "ok"

        pairs.append(
            {
                "idx": i + 1,
                "question": q,
                "status": status(b_eval, a_eval),
                "before_eval": b_eval,
                "after_eval": a_eval,
            }
        )
    return pairs


def render_answer_block(label: str, t: dict | None, side: str) -> str:
    if not t:
        return f'<div class="ans empty {side}"><div class="ans-label">{esc(label)}</div><p class="muted">—</p></div>'
    fr = t.get("finish_reason") or "—"
    sc = score(t)
    fl = flags(t)
    bad = is_bad(t)
    klass = f"ans {side} {'bad' if bad else 'good'}"
    reasons = bad_reasons(t)
    badge = (
        f'<span class="badge bad">{esc(" · ".join(reasons))}</span>'
        if bad
        else '<span class="badge good">OK</span>'
    )
    body = esc(t.get("answer") or "")
    meta = f'fr=<code>{esc(str(fr))}</code> score=<code>{sc}</code> flags=<code>{esc(str(fl))}</code>'
    if t.get("kind") == "clarify_reply":
        meta += f' · reply=<code>{esc(t.get("question") or "")}</code>'
    if t.get("clarify_reply"):
        meta += f' · auto=<code>{esc(t.get("clarify_reply"))}</code>'
    return f'''<div class="{klass}">
  <div class="ans-label">{esc(label)} {badge}</div>
  <div class="meta">{meta}</div>
  <pre class="body">{body}</pre>
</div>'''


def cards(plist, title, cls, n, before_label: str, after_label: str):
    if not plist:
        return f'<h3 class="{cls}">{esc(title)} (۰)</h3>'
    parts = [f'<h3 class="{cls}">{esc(title)} ({len(plist)})</h3>']
    for p in plist:
        be, ae = p["before_eval"], p["after_eval"]
        why_b = " · ".join(bad_reasons(be)) if be and is_bad(be) else "OK"
        why_a = " · ".join(bad_reasons(ae)) if ae and is_bad(ae) else "OK"
        parts.append(
            f'''
            <article class="pair {p['status']}" id="s{n}-q{p['idx']}">
              <header>
                <span class="qnum">سوال {p['idx']}</span>
                <span class="status-pill {p['status']}">{esc(p['status'])}</span>
                <h4>{esc(p['question'])}</h4>
                <p class="delta">قبل: <b>{esc(why_b)}</b> → بعد: <b>{esc(why_a)}</b></p>
              </header>
              <div class="cols">
                {render_answer_block(before_label, be, "before")}
                {render_answer_block(after_label, ae, "after")}
              </div>
            </article>'''
        )
    return "\n".join(parts)


def suite_section(
    n: int,
    before_suffix: str = "",
    after_suffix: str = "_after",
    before_label: str = "پاسخ قدیم (قبل از فیکس)",
    after_label: str = "پاسخ جدید (بعد از فیکس)",
) -> str:
    before, after = load(n, before_suffix), load(n, after_suffix)
    pairs = pair_turns(before, after)
    improved = [p for p in pairs if p["status"] == "improved"]
    still = [p for p in pairs if p["status"] == "still_bad"]
    regressed = [p for p in pairs if p["status"] == "regressed"]
    ok = [p for p in pairs if p["status"] == "ok"]
    summary = f"""
    <div class="suite-sum">
      <div class="kpi"><b>قبل</b><br>avg {before.get('avg_reasonableness')} · CF {before.get('flag_counts',{}).get('content_filter',0)} · no_ev {before.get('flag_counts',{}).get('no_evidence',0)} · err {before.get('err_turns')}</div>
      <div class="kpi"><b>بعد</b><br>avg {after.get('avg_reasonableness')} · CF {after.get('flag_counts',{}).get('content_filter',0)} · no_ev {after.get('flag_counts',{}).get('no_evidence',0)} · err {after.get('err_turns')}</div>
      <div class="kpi improved"><b>بهبود یافته</b><br>{len(improved)}</div>
      <div class="kpi still"><b>هنوز ضعیف</b><br>{len(still)}</div>
      <div class="kpi ok"><b>سالم ماند</b><br>{len(ok)}</div>
      <div class="kpi reg"><b>پسرفت</b><br>{len(regressed)}</div>
    </div>
    """
    body = summary
    body += cards(improved, "بهبود یافته — قبلاً غلط، الان درست/بهتر", "improved-h", n, before_label, after_label)
    body += cards(still, "هنوز ضعیف در هر دو", "still-h", n, before_label, after_label)
    body += cards(regressed, "پسرفت (قبلاً بهتر)", "reg-h", n, before_label, after_label)
    body += cards(ok, "سالم در هر دو اجرا (مرجع)", "ok-h", n, before_label, after_label)
    return f'''
    <section class="suite" id="suite-{n}">
      <h2>بسته {n} نوبت (clarify-aware)</h2>
      <p class="muted">thread قبل: <code>{esc(before.get("thread"))}</code> · بعد: <code>{esc(after.get("thread"))}</code></p>
      {body}
    </section>
    '''


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Generate RTL before/after HTML for stress clarify.")
    ap.add_argument(
        "--mode",
        choices=("qa-fix", "magic-parity"),
        default="magic-parity",
        help="qa-fix: baseline vs _after; magic-parity: _after (gold) vs _magic (current)",
    )
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    if args.mode == "magic-parity":
        before_suffix, after_suffix = "_after", "_magic"
        before_label = "پاسخ قدیم (baseline بعد از فیکس QA — بدون جادو)"
        after_label = "پاسخ جدید (اجرای فعلی + MAGIC)"
        hero_blurb = (
            "مقایسهٔ baseline پایدار (_after) با اجرای فعلی پس از افزودن MAGIC tokens. "
            "پاسخ‌ها باید از نظر کیفیت برابر باشند؛ تفاوت مجاز فقط ویجت‌های جادویی است."
        )
        footer_src = "stress_clarify_*{_after,_magic}.json"
    else:
        before_suffix, after_suffix = "", "_after"
        before_label = "پاسخ قدیم (قبل از فیکس)"
        after_label = "پاسخ جدید (بعد از فیکس)"
        hero_blurb = (
            "همان بستهٔ سؤال‌ها روی dana-local قبل و بعد از فیکس‌های QA-loop "
            "(orchestrator #26/#27/#29/#30 · guardrails #9/#11)."
        )
        footer_src = "stress_clarify_*{{,_after}}.json"

    suites_html = "\n".join(
        suite_section(n, before_suffix, after_suffix, before_label, after_label) for n in (30, 40, 50)
    )
    total_imp = total_still = total_reg = 0
    rows = []
    for n in (30, 40, 50):
        pairs = pair_turns(load(n, before_suffix), load(n, after_suffix))
        imp = sum(1 for p in pairs if p["status"] == "improved")
        stil = sum(1 for p in pairs if p["status"] == "still_bad")
        reg = sum(1 for p in pairs if p["status"] == "regressed")
        total_imp += imp
        total_still += stil
        total_reg += reg
        b, a = load(n, before_suffix), load(n, after_suffix)
        rows.append(
            f"<tr><td>{n}</td><td>{b.get('avg_reasonableness')} → <b>{a.get('avg_reasonableness')}</b></td>"
            f"<td>{b.get('flag_counts',{}).get('content_filter',0)} → {a.get('flag_counts',{}).get('content_filter',0)}</td>"
            f"<td>{b.get('flag_counts',{}).get('no_evidence',0)} → {a.get('flag_counts',{}).get('no_evidence',0)}</td>"
            f"<td class='improved'>{imp}</td><td class='still'>{stil}</td><td class='reg'>{reg}</td></tr>"
        )

    css = Path(__file__).with_name("_stress_html_styles.css")
    # inline styles kept in template for single-file open
    doc = f'''<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>مقایسه پاسخ‌های استرس Clarify ۳۰/۴۰/۵۰ — قبل و بعد</title>
<style>
:root {{ --bg:#f6f3ee; --ink:#1c1917; --muted:#78716c; --card:#fffdf9; --line:#e7e0d5; --before:#fef2f2; --after:#ecfdf5; --bad:#b91c1c; --good:#047857; --imp:#0f766e; --still:#b45309; --reg:#9f1239; --ok:#57534e; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; padding:0 1rem 3rem; font-family:"Vazirmatn","Tahoma","Segoe UI",sans-serif; background:radial-gradient(1200px 600px at 10% -10%,#fde68a55,transparent),radial-gradient(900px 500px at 100% 0%,#99f6e455,transparent),var(--bg); color:var(--ink); line-height:1.7; }}
header.hero {{ max-width:1100px; margin:0 auto; padding:2rem 0 1rem; }}
header.hero h1 {{ font-size:1.6rem; margin:0 0 .5rem; }}
header.hero p {{ color:var(--muted); margin:.25rem 0; }}
nav {{ max-width:1100px; margin:0 auto 1.5rem; display:flex; gap:.75rem; flex-wrap:wrap; }}
nav a {{ text-decoration:none; color:var(--ink); background:var(--card); border:1px solid var(--line); padding:.4rem .8rem; border-radius:8px; }}
table.summary {{ width:100%; max-width:1100px; margin:0 auto 2rem; border-collapse:collapse; background:var(--card); border:1px solid var(--line); border-radius:12px; overflow:hidden; }}
table.summary th, table.summary td {{ padding:.65rem .75rem; border-bottom:1px solid var(--line); text-align:center; }}
table.summary th {{ background:#faf7f2; }}
.improved {{ color:var(--imp); font-weight:700; }} .still {{ color:var(--still); font-weight:700; }} .reg {{ color:var(--reg); font-weight:700; }}
.suite {{ max-width:1100px; margin:0 auto 3rem; }}
.suite h2 {{ border-bottom:2px solid var(--line); padding-bottom:.4rem; }}
.suite-sum {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:.75rem; margin:1rem 0 1.5rem; }}
.kpi {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:.75rem; font-size:.92rem; }}
.kpi.improved {{ border-color:#99f6e4; background:#f0fdfa; }} .kpi.still {{ border-color:#fcd34d; background:#fffbeb; }} .kpi.reg {{ border-color:#fda4af; background:#fff1f2; }}
h3.improved-h {{ color:var(--imp); }} h3.still-h {{ color:var(--still); }} h3.reg-h {{ color:var(--reg); }} h3.ok-h {{ color:var(--ok); }}
.pair {{ background:var(--card); border:1px solid var(--line); border-radius:14px; margin:1rem 0; padding:1rem 1.1rem; }}
.pair.improved {{ border-color:#5eead4; box-shadow:0 0 0 2px #99f6e433; }}
.pair.still_bad {{ border-color:#fbbf24; }} .pair.regressed {{ border-color:#fb7185; }}
.pair header h4 {{ margin:.35rem 0; font-size:1.05rem; }}
.qnum {{ font-size:.8rem; color:var(--muted); margin-left:.5rem; }}
.status-pill {{ display:inline-block; font-size:.75rem; padding:.15rem .55rem; border-radius:999px; background:#e7e5e4; color:#44403c; }}
.status-pill.improved {{ background:#ccfbf1; color:#0f766e; }} .status-pill.still_bad {{ background:#fef3c7; color:#b45309; }}
.status-pill.regressed {{ background:#ffe4e6; color:#9f1239; }} .status-pill.ok {{ background:#f5f5f4; color:#57534e; }}
.delta {{ color:var(--muted); font-size:.9rem; margin:0; }}
.cols {{ display:grid; grid-template-columns:1fr 1fr; gap:.85rem; margin-top:.85rem; }}
@media (max-width:860px) {{ .cols {{ grid-template-columns:1fr; }} }}
.ans {{ border-radius:10px; padding:.75rem .85rem; border:1px solid var(--line); min-height:8rem; }}
.ans.before {{ background:var(--before); }} .ans.after {{ background:var(--after); }}
.ans.bad {{ outline:2px solid #f87171aa; }} .ans.good {{ outline:2px solid #34d39966; }}
.ans-label {{ font-weight:700; margin-bottom:.35rem; display:flex; gap:.5rem; flex-wrap:wrap; align-items:center; }}
.badge {{ font-size:.72rem; font-weight:700; padding:.12rem .45rem; border-radius:6px; }}
.badge.bad {{ background:#fecaca; color:var(--bad); }} .badge.good {{ background:#a7f3d0; color:var(--good); }}
.meta {{ font-size:.78rem; color:var(--muted); margin-bottom:.4rem; }}
.meta code {{ font-size:.75rem; background:#00000008; padding:0 .25rem; border-radius:4px; }}
pre.body {{ white-space:pre-wrap; word-break:break-word; margin:0; font-family:inherit; font-size:.92rem; max-height:28rem; overflow:auto; }}
.muted {{ color:var(--muted); font-size:.9rem; }}
footer {{ max-width:1100px; margin:2rem auto; color:var(--muted); font-size:.85rem; }}
.legend {{ max-width:1100px; margin:0 auto 1.5rem; display:flex; gap:.75rem; flex-wrap:wrap; font-size:.85rem; }}
.legend span {{ padding:.25rem .6rem; border-radius:8px; border:1px solid var(--line); background:var(--card); }}
</style>
</head>
<body>
<header class="hero">
  <h1>مقایسه پاسخ‌های قدیمی و جدید — استرس Clarify ۳۰ / ۴۰ / ۵۰</h1>
  <p>{esc(hero_blurb)}</p>
  <p>پاسخ‌های غلط قبلی و موارد بهبودیافته هایلایت شده‌اند؛ متن کامل قدیم و جدید کنار هم آمده است.</p>
</header>
<nav>
  <a href="#summary">خلاصه</a>
  <a href="#suite-30">۳۰ نوبت</a>
  <a href="#suite-40">۴۰ نوبت</a>
  <a href="#suite-50">۵۰ نوبت</a>
</nav>
<div class="legend">
  <span class="improved">بهبود یافته: {total_imp}</span>
  <span class="still">هنوز ضعیف: {total_still}</span>
  <span class="reg">پسرفت: {total_reg}</span>
  <span>قرمز کم‌رنگ = قدیم مشکل‌دار · سبز = جدید سالم</span>
</div>
<table class="summary" id="summary">
  <thead><tr><th>بسته</th><th>avg score</th><th>content_filter</th><th>no_evidence</th><th>بهبود</th><th>هنوز ضعیف</th><th>پسرفت</th></tr></thead>
  <tbody>{''.join(rows)}</tbody>
</table>
{suites_html}
<footer>
  منبع: <code>datasets/stress/results/{esc(footer_src)}</code> ·
  بازتولید: <code>python scripts/gen_stress_clarify_html.py --mode {esc(args.mode)}</code>
</footer>
</body>
</html>
'''
    out_path = args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(doc, encoding="utf-8")
    print(
        f"WROTE {out_path} ({out_path.stat().st_size} bytes) mode={args.mode} "
        f"improved={total_imp} still={total_still} reg={total_reg}"
    )


if __name__ == "__main__":
    main()
