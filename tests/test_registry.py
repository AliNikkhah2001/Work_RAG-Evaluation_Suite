"""Self-tests for the suite registry and the version staleness gate.

These are the tests that keep the *registry* honest — that every declared suite
exists, that version pins round-trip, and that a KB bump is actually detected.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from work_rag_evaluation import registry as reg

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def registry() -> reg.Registry:
    return reg.load_registry()


def test_registry_loads(registry: reg.Registry) -> None:
    assert registry.suites, "registry must declare at least one suite"
    assert registry.version >= 1
    assert registry.umbrella.is_dir()


def test_registry_is_consistent(registry: reg.Registry) -> None:
    problems = registry.validate()
    assert problems == [], f"registry problems: {problems}"


def test_all_kinds_are_represented(registry: reg.Registry) -> None:
    kinds = {s.kind for s in registry.suites}
    assert kinds == set(reg.KINDS), f"missing kinds: {set(reg.KINDS) - kinds}"


def test_every_owner_is_a_known_root(registry: reg.Registry) -> None:
    for suite in registry.suites:
        assert suite.owner in registry.roots, f"{suite.id}: unknown owner {suite.owner}"


def test_unit_suites_require_no_live_stack(registry: reg.Registry) -> None:
    for suite in registry.by_kind(reg.UNIT):
        assert suite.requires == "none", f"{suite.id}: unit suite must not need a stack"


def test_live_suites_declare_their_dependency(registry: reg.Registry) -> None:
    for suite in registry.suites:
        if suite.kind in (reg.INTEGRATION, reg.E2E):
            assert suite.requires in ("kb", "orch", "stack"), f"{suite.id} missing requires"


def test_ids_are_unique(registry: reg.Registry) -> None:
    ids = [s.id for s in registry.suites]
    assert len(ids) == len(set(ids))


def test_lookup_helpers(registry: reg.Registry) -> None:
    first = registry.suites[0]
    assert registry.by_id(first.id) is first
    with pytest.raises(reg.RegistryError):
        registry.by_id("does-not-exist")
    assert registry.by_tag("multiturn")
    assert registry.by_owner("evaluation")


def test_lock_covers_every_suite(registry: reg.Registry) -> None:
    lock = json.loads(reg.LOCK_FILE.read_text(encoding="utf-8"))
    pinned = set(lock.get("suites") or {})
    declared = {s.id for s in registry.suites}
    assert declared <= pinned, f"suites missing a version pin: {declared - pinned}"


def test_lock_has_kb_and_model_pins(registry: reg.Registry) -> None:
    lock = json.loads(reg.LOCK_FILE.read_text(encoding="utf-8"))
    kb = lock["knowledgebase"]
    assert kb["corpus_date"]
    assert kb["manifest_id"].startswith("kb-")
    assert lock["models"]["llm"]["id"]
    assert lock["models"]["embedding"]["dim"] > 0


def test_check_stale_in_sync_against_own_pin(registry: reg.Registry) -> None:
    """Feeding the lock's own KB pin back in must report in-sync."""
    lock = json.loads(reg.LOCK_FILE.read_text(encoding="utf-8"))
    report = registry.check_stale(live=copy.deepcopy(lock["knowledgebase"]))
    assert report["ok"] is True
    assert report["checked"] is True


def test_check_stale_detects_manifest_bump(registry: reg.Registry) -> None:
    """A newer KB manifest must be flagged as stale."""
    lock = json.loads(reg.LOCK_FILE.read_text(encoding="utf-8"))
    live = copy.deepcopy(lock["knowledgebase"])
    live["manifest_id"] = "kb-99999999T000000Z"
    report = registry.check_stale(live=live)
    assert report["ok"] is False
    assert any("KB snapshot changed" in s for s in report["stale"])


def test_check_stale_detects_pack_bump(registry: reg.Registry) -> None:
    lock = json.loads(reg.LOCK_FILE.read_text(encoding="utf-8"))
    live = copy.deepcopy(lock["knowledgebase"])
    packs = dict(live.get("packs") or {})
    if not packs:
        pytest.skip("no packs pinned")
    name = next(iter(packs))
    packs[name] = "99.0.0"
    live["packs"] = packs
    report = registry.check_stale(live=live)
    assert report["ok"] is False
    assert any(name in s for s in report["stale"])


def test_check_stale_without_pin_is_not_a_failure(registry: reg.Registry) -> None:
    report = registry.check_stale(live=None)
    if report["checked"] is False:
        assert report["ok"] is True


def test_norm_ver_handles_both_shapes() -> None:
    assert reg._norm_ver("1.0.7") == "1.0.7"
    assert reg._norm_ver("v1.0.7") == "1.0.7"
    assert reg._norm_ver("prompts/orchestrator/v1.0.7.yaml") == "1.0.7"


def test_runner_selects_by_kind(registry: reg.Registry) -> None:
    from work_rag_evaluation import runner as run

    result = run.run(kinds=["unit"], dry_run=True, check_stale=False)
    assert result.suites
    assert all(s.kind == "unit" for s in result.suites)
    assert all(s.status == "skipped" for s in result.suites)
