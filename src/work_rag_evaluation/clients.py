"""HTTP clients for orchestrator + KB (trust_env=False for Squid)."""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

import httpx

# Prefer full endpoint URLs; fall back to service base + path for compose.
_orch_base = os.environ.get("ORCH_BASE_URL", "http://127.0.0.1:8100").rstrip("/")
_kb_base = os.environ.get("KB_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
DEFAULT_ORCH = os.environ.get(
    "ORCH_CHAT_URL",
    f"{_orch_base}/v1/chat/completions" if not _orch_base.endswith("/v1/chat/completions") else _orch_base,
)
DEFAULT_KB = os.environ.get(
    "KB_SEARCH_URL",
    f"{_kb_base}/search/api" if not _kb_base.endswith("/search/api") else _kb_base,
)
DEFAULT_MODEL = os.environ.get("EVAL_MODEL", "ics-helper-agent")


class OrchClient:
    def __init__(self, base_url: str = DEFAULT_ORCH, timeout: float = 180.0) -> None:
        self.base_url = base_url
        self.timeout = timeout

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        request_id: str | None = None,
        filter_path: str | None = None,
        model: str = DEFAULT_MODEL,
    ) -> dict[str, Any]:
        rid = request_id or f"eval-{uuid.uuid4().hex[:12]}"
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "request_id": rid,
        }
        if filter_path:
            body["filter_path"] = filter_path
        headers = {
            "Content-Type": "application/json",
            "X-Request-ID": rid,
        }
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            resp = await client.post(self.base_url, content=json.dumps(body, ensure_ascii=False), headers=headers)
            resp.raise_for_status()
            data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        return {
            "request_id": rid,
            "content": msg.get("content") or "",
            "finish_reason": choice.get("finish_reason") or data.get("finish_reason"),
            "rag": data.get("rag") or {},
            "raw": data,
        }


class KBClient:
    def __init__(self, base_url: str = DEFAULT_KB, timeout: float = 60.0) -> None:
        self.base_url = base_url
        self.timeout = timeout

    async def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        filter_path: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"query": query, "top_k": top_k}
        if filter_path:
            body["filter_path"] = filter_path
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            resp = await client.post(
                self.base_url,
                content=json.dumps(body, ensure_ascii=False),
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return resp.json()
