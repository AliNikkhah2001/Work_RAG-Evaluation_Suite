#!/usr/bin/env python3
"""Serve Evaluation Suite API (default :8300)."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.environ.get("EVAL_HOST", "0.0.0.0")
    port = int(os.environ.get("EVAL_PORT", "8300"))
    uvicorn.run(
        "work_rag_evaluation.api:app",
        host=host,
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    main()
