"""Remap stale expected_chunk_ids by answer-as-query search (non-tautological)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..clients import KBClient


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def token_overlap(a: str, b: str) -> float:
    ta = set(re.findall(r"[\w\u0600-\u06ff]{3,}", _norm(a)))
    tb = set(re.findall(r"[\w\u0600-\u06ff]{3,}", _norm(b)))
    if not ta:
        return 0.0
    return len(ta & tb) / len(ta)


def _chunk_text(item: dict[str, Any]) -> str:
    return str(item.get("content_preview") or item.get("content") or item.get("text") or "")


def _chunk_id(item: dict[str, Any]) -> str | None:
    cid = item.get("chunk_id") or item.get("id")
    return str(cid) if cid is not None else None


async def remap_item(
    item: dict[str, Any],
    kb: KBClient,
    *,
    top_k: int = 8,
    min_overlap: float = 0.35,
) -> dict[str, Any] | None:
    """Find live chunk ids whose text overlaps expected_answer."""
    answer = (item.get("expected_answer") or "").strip()
    query = (item.get("query") or "").strip()
    if not answer or not query:
        return None
    # Answer-as-query: retrieve chunks that contain the ground-truth text
    probe = answer[:400]
    res = await kb.search(probe, top_k=top_k)
    finals = res.get("final_results") or []
    scored: list[tuple[float, str]] = []
    for row in finals:
        cid = _chunk_id(row)
        if not cid:
            continue
        ov = token_overlap(answer, _chunk_text(row))
        if ov >= min_overlap:
            scored.append((ov, cid))
    scored.sort(reverse=True)
    if not scored:
        return None
    ids = [cid for _, cid in scored[:3]]
    return {
        "query": query,
        "expected_answer": answer,
        "expected_chunk_ids": ids,
        "category": item.get("category"),
        "difficulty": item.get("difficulty"),
        "remap_overlap": scored[0][0],
        "legacy_expected_chunk_ids": item.get("expected_chunk_ids") or [],
    }


async def remap_dataset(
    src: Path,
    dst: Path,
    *,
    limit: int | None = None,
    min_overlap: float = 0.35,
) -> dict[str, Any]:
    raw = json.loads(src.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("dataset must be a JSON list")
    if limit:
        raw = raw[:limit]
    kb = KBClient()
    out: list[dict[str, Any]] = []
    dropped = 0
    for item in raw:
        remapped = await remap_item(item, kb, min_overlap=min_overlap)
        if remapped is None:
            dropped += 1
            continue
        out.append(remapped)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"kept": len(out), "dropped": dropped, "path": str(dst)}
