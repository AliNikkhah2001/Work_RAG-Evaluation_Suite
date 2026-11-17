"""Canonical test-suite registry + version staleness gate.

The registry is the single source of truth for every runnable suite across the
platform. It lives in the evaluation submodule because that is the only place
with visibility over all component repos, but it does **not** require the unit
tests to move: each suite declares its own ``rootdir`` / ``env`` so pytest runs
in place inside the owning repo.

Version linking
---------------
``registry/versions.lock.json`` records the KB snapshot (corpus date +
manifest id + pack pins) and model versions the suite set was last validated
against. :func:`check_stale` compares that to the live pins — read from the
kb-source DVC pin on disk, or from the KB ``/api/dvc`` endpoint when a stack is
up — and reports every suite whose ``validated_against`` no longer matches.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_DIR = ROOT / "registry"
SUITES_FILE = REGISTRY_DIR / "suites.yaml"
LOCK_FILE = REGISTRY_DIR / "versions.lock.json"

UNIT = "unit"
INTEGRATION = "integration"
E2E = "e2e"
KINDS = (UNIT, INTEGRATION, E2E)


class RegistryError(RuntimeError):
    """Raised when the registry is missing, malformed, or inconsistent."""


@dataclass
class Suite:
    """One runnable suite."""

    id: str
    name: str
    kind: str
    owner: str
    path: str
    runner: str
    requires: str = "none"
    rootdir: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    args: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    description: str = ""

    def resolve_path(self, umbrella: Path) -> Path:
        return umbrella / self.path

    def resolve_rootdir(self, umbrella: Path) -> Path:
        return umbrella / (self.rootdir or self.path)

    def exists(self, umbrella: Path) -> bool:
        return self.resolve_path(umbrella).exists()

    def needs_live_stack(self) -> bool:
        return self.requires != "none"


@dataclass
class Registry:
    suites: list[Suite]
    roots: dict[str, str]
    version: int
    updated: str
    umbrella: Path

    # ------------------------------------------------------------ lookup --

    def by_id(self, suite_id: str) -> Suite:
        for s in self.suites:
            if s.id == suite_id:
                return s
        raise RegistryError(f"unknown suite id: {suite_id}")

    def by_kind(self, *kinds: str) -> list[Suite]:
        wanted = set(kinds) or set(KINDS)
        return [s for s in self.suites if s.kind in wanted]

    def by_owner(self, owner: str) -> list[Suite]:
        return [s for s in self.suites if s.owner == owner]

    def by_tag(self, tag: str) -> list[Suite]:
        return [s for s in self.suites if tag in s.tags]

    def validate(self) -> list[str]:
        """Return a list of problems; empty means the registry is consistent."""
        problems: list[str] = []
        seen: set[str] = set()
        for s in self.suites:
            if s.id in seen:
                problems.append(f"duplicate suite id: {s.id}")
            seen.add(s.id)
            if s.kind not in KINDS:
                problems.append(f"{s.id}: unknown kind {s.kind!r}")
            if s.requires not in ("none", "kb", "orch", "stack"):
                problems.append(f"{s.id}: unknown requires {s.requires!r}")
            if s.owner not in self.roots:
                problems.append(f"{s.id}: unknown owner {s.owner!r}")
            if not s.exists(self.umbrella):
                problems.append(f"{s.id}: path does not exist: {s.path}")
        return problems

    # ------------------------------------------------------- version pin --

    def live_pin(self) -> dict[str, Any] | None:
        """KB snapshot pin from disk (kb-source) or the live KB, whichever exists."""
        from_live = self._live_pin_from_kb()
        if from_live:
            return from_live
        return self._pin_from_disk()

    def _pin_from_disk(self) -> dict[str, Any] | None:
        src = self.roots.get("kb_source")
        if not src:
            return None
        path = self.umbrella / src / ".dvc_pins" / "processed.json"
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _live_pin_from_kb(self) -> dict[str, Any] | None:
        base = os.environ.get("KB_BASE_URL")
        if not base:
            return None
        try:
            import urllib.request

            with urllib.request.urlopen(f"{base.rstrip('/')}/api/dvc", timeout=5) as r:
                data = json.loads(r.read().decode())
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def check_stale(self, *, live: dict[str, Any] | None = None) -> dict[str, Any]:
        """Compare pinned versions to live ones.

        Returns a report with ``stale`` (list of human-readable reasons) and
        ``ok`` (bool). A suite is stale when the live KB manifest differs from
        the manifest recorded in ``versions.lock.json``.
        """
        lock = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
        pinned_kb = lock.get("knowledgebase") or {}
        live_pin = live if live is not None else self.live_pin()

        if live_pin is None:
            return {
                "ok": True,
                "checked": False,
                "reason": "no live pin available (kb-source pin missing and KB unreachable)",
                "stale": [],
                "pinned_manifest": pinned_kb.get("manifest_id"),
                "live_manifest": None,
            }

        pinned_manifest = pinned_kb.get("manifest_id")
        live_manifest = live_pin.get("manifest_id")
        stale: list[str] = []
        if pinned_manifest != live_manifest:
            stale.append(
                f"KB snapshot changed: suites validated against {pinned_manifest}, "
                f"live is {live_manifest}"
            )
        for key in ("documents", "chunks", "entity_lists"):
            if pinned_kb.get(key) is not None and live_pin.get(key) is not None:
                if pinned_kb[key] != live_pin[key]:
                    stale.append(
                        f"KB {key}: pinned {pinned_kb[key]}, live {live_pin[key]}"
                    )
        pinned_packs = pinned_kb.get("packs") or {}
        live_packs = live_pin.get("packs") or {}
        for name, ver in pinned_packs.items():
            live_ver = live_packs.get(name)
            if live_ver and _norm_ver(live_ver) != _norm_ver(ver):
                stale.append(f"pack {name}: pinned {ver}, live {live_ver}")

        return {
            "ok": not stale,
            "checked": True,
            "reason": "in sync" if not stale else "; ".join(stale),
            "stale": stale,
            "pinned_manifest": pinned_manifest,
            "live_manifest": live_manifest,
        }

    def repin(self, *, live: dict[str, Any] | None = None) -> dict[str, Any]:
        """Rewrite the KB section of the lock file from the live pin."""
        live_pin = live if live is not None else self.live_pin()
        if live_pin is None:
            raise RegistryError("no live pin available to repin against")
        lock = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
        kb = lock.setdefault("knowledgebase", {})
        for key in ("corpus_date", "manifest_id", "documents", "chunks", "entity_lists"):
            if live_pin.get(key) is not None:
                kb[key] = live_pin[key]
        kb["packs"] = {k: _norm_ver(v) for k, v in (live_pin.get("packs") or {}).items()}
        manifest = kb["manifest_id"]
        for entry in (lock.get("suites") or {}).values():
            entry["validated_against"] = manifest
        LOCK_FILE.write_text(
            json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return lock


def _norm_ver(value: Any) -> str:
    """Normalise a pack pin: both ``1.0.7`` and ``prompts/orchestrator/v1.0.7.yaml``."""
    s = str(value)
    if s.endswith(".yaml"):
        s = Path(s).stem  # v1.0.7
    return s.lstrip("v")


def load_registry(umbrella: Path | None = None) -> Registry:
    """Load ``registry/suites.yaml`` + ``versions.lock.json``."""
    if not SUITES_FILE.is_file():
        raise RegistryError(f"missing registry: {SUITES_FILE}")
    raw = yaml.safe_load(SUITES_FILE.read_text(encoding="utf-8")) or {}

    umbrella_path: Path | None = Path(umbrella).resolve() if umbrella else None
    if umbrella_path is None:
        probe = ROOT
        while probe != probe.parent:
            if (probe / ".gitmodules").is_file():
                umbrella_path = probe
                break
            probe = probe.parent
    if umbrella_path is None or not umbrella_path.is_dir():
        # Fall back to the umbrella root implied by the evaluation repo location.
        umbrella_path = ROOT.parents[1]

    suites = [
        Suite(
            id=item["id"],
            name=item.get("name", item["id"]),
            kind=item.get("kind", UNIT),
            owner=item.get("owner", "evaluation"),
            path=item["path"],
            runner=item.get("runner", "pytest"),
            requires=item.get("requires", "none"),
            rootdir=item.get("rootdir"),
            env=dict(item.get("env") or {}),
            args=list(item.get("args") or []),
            tags=list(item.get("tags") or []),
            description=(item.get("description") or "").strip(),
        )
        for item in (raw.get("suites") or [])
    ]
    if not suites:
        raise RegistryError("registry contains no suites")

    return Registry(
        suites=suites,
        roots=dict(raw.get("roots") or {}),
        version=int(raw.get("version") or 1),
        updated=str(raw.get("updated") or ""),
        umbrella=umbrella_path,
    )
