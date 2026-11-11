"""Hit@1 / Hit@k retrieval evaluation against remapped goldens."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..clients import KBClient


async def evaluate_hitk(
    dataset_path: Path,
    *,
    top_k: int = 5,
    limit: int | None = None,
) -> dict[str, Any]:
    data = json.loads(dataset_path.read_text(encoding="utf-8"))
    if limit:
        data = data[:limit]
    kb = KBClient()
    hit1 = hitk = 0
    rows: list[dict[str, Any]] = []
    for item in data:
        q = item["query"]
        expected = {str(x) for x in (item.get("expected_chunk_ids") or [])}
        res = await kb.search(q, top_k=top_k)
        finals = res.get("final_results") or []
        ids = []
        for row in finals:
            cid = row.get("chunk_id") or row.get("id")
            if cid is not None:
                ids.append(str(cid))
        ok1 = bool(ids) and ids[0] in expected
        okk = any(i in expected for i in ids[:top_k])
        if ok1:
            hit1 += 1
        if okk:
            hitk += 1
        rows.append(
            {
                "query": q[:120],
                "hit1": ok1,
                "hitk": okk,
                "retrieved": ids[:top_k],
                "expected": list(expected)[:5],
            }
        )
    n = len(data) or 1
    return {
        "suite": "hitk",
        "n": len(data),
        "top_k": top_k,
        "hit1": hit1,
        "hitk": hitk,
        "hit1_rate": round(hit1 / n, 4),
        "hitk_rate": round(hitk / n, 4),
        "rows": rows,
    }


def write_hitk_report(result: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [
        "# Hit@k results",
        "",
        f"n={result['n']} top_k={result['top_k']}",
        f"Hit@1={result['hit1']} ({result['hit1_rate']:.1%})",
        f"Hit@{result['top_k']}={result['hitk']} ({result['hitk_rate']:.1%})",
        "",
    ]
    misses = [r for r in result["rows"] if not r["hitk"]][:20]
    if misses:
        md.append("## Sample misses")
        for r in misses:
            md.append(f"- Q: {r['query']}")
            md.append(f"  got={r['retrieved'][:3]}")
    path.with_suffix(".md").write_text("\n".join(md), encoding="utf-8")
