"""End-to-end API smoke across the full stack.

Absorbs the former ``components/knowledgebase/kb-manager/test_endpoints.py`` and
the ad-hoc ``dev/tests/test_api*.py`` scratch scripts into a single, asserting,
skippable suite.

Skipped automatically when the stack is not up, so it is safe to include in the
default unit run.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import pytest

KB_BASE = os.environ.get("KB_BASE_URL", "http://127.0.0.1:8000")
ORCH_BASE = os.environ.get("ORCH_BASE_URL", "http://127.0.0.1:8100")
GUARD_BASE = os.environ.get("GUARDRAILS_BASE_URL", "http://127.0.0.1:8200")

# GET endpoints exposed by kb-manager (from the retired test_endpoints.py).
KB_ENDPOINTS = [
    "/",
    "/documents",
    "/chunks",
    "/pipeline",
    "/versions",
    "/monitoring",
    "/search",
    "/transparency",
    "/ingestion",
]


def _get(url: str, timeout: float = 8.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.status, r.read()


def _post(url: str, payload: dict, timeout: float = 60.0):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def _chat(base: str, message: str, timeout: float = 90.0) -> dict:
    """POST /v1/chat/completions and reassemble the SSE stream.

    The orchestrator streams OpenAI-style chunks interleaved with agent
    progress comments, so we collect every `data:` frame and join the deltas.
    """
    req = urllib.request.Request(
        f"{base}/v1/chat/completions",
        data=json.dumps(
            {"model": "chat-primary", "messages": [{"role": "user", "content": message}]}
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    content = ""
    finish: str | None = None
    rag: dict = {}
    with urllib.request.urlopen(req, timeout=timeout) as r:
        assert r.status == 200
        for raw in r.read().decode("utf-8").splitlines():
            if not raw.startswith("data:"):
                continue
            body = raw[len("data:") :].strip()
            if not body or body == "[DONE]":
                continue
            try:
                frame = json.loads(body)
            except json.JSONDecodeError:
                continue
            choice = (frame.get("choices") or [{}])[0]
            delta = choice.get("delta") or {}
            content += delta.get("content") or ""
            finish = choice.get("finish_reason") or finish
            if isinstance(frame.get("rag"), dict):
                rag = frame["rag"]
    return {"content": content, "finish_reason": finish, "rag": rag}


def _reachable(url: str) -> bool:
    try:
        _get(url, timeout=4)
        return True
    except Exception:
        return False


requires_kb = pytest.mark.skipif(
    not _reachable(f"{KB_BASE}/health"), reason=f"KB not reachable at {KB_BASE}"
)
requires_orch = pytest.mark.skipif(
    not _reachable(f"{ORCH_BASE}/ready"), reason=f"orchestrator not reachable at {ORCH_BASE}"
)


@requires_kb
@pytest.mark.parametrize("endpoint", KB_ENDPOINTS)
def test_kb_endpoints_respond(endpoint: str) -> None:
    """Every kb-manager GET endpoint answers 200."""
    status, _ = _get(f"{KB_BASE}{endpoint}")
    assert status == 200, f"{endpoint} -> {status}"


@requires_kb
def test_kb_search_returns_chunks() -> None:
    """The KB search API returns at least one result for a known credit query."""
    status, payload = _post(f"{KB_BASE}/search/api", {"query": "اعتبارسنجی چیست", "top_k": 3})
    assert status == 200
    assert payload.get("final_results"), f"no final_results: {payload}"


@requires_orch
def test_orchestrator_chat_smoke() -> None:
    """A greeting through the orchestrator returns a non-empty completion."""
    result = _chat(ORCH_BASE, "سلام")
    assert result["content"].strip(), f"empty completion: {result}"
    assert result["finish_reason"] == "stop", f"finish_reason={result['finish_reason']}"


@requires_orch
def test_orchestrator_does_not_leak_magic_into_body() -> None:
    """MAGIC widget markers must never appear in the chat body (rag.magic only)."""
    result = _chat(ORCH_BASE, "امتیاز ۶۱۰ حقیقی در چه رنگی است؟")
    assert "<<<MAGIC:" not in result["content"], "MAGIC marker leaked into the message body"


@requires_orch
def test_orchestrator_grounds_credit_question() -> None:
    """A real credit question must return citations from the KB, not an empty answer."""
    result = _chat(ORCH_BASE, "اعتبارسنجی چیست؟")
    assert result["content"].strip()
    assert result["rag"].get("citations"), f"no citations: {result['rag'].keys()}"
