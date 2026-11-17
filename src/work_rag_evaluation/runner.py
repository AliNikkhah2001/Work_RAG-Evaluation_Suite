"""Unified suite runner.

Runs any registered suite the way its owning repo expects: pytest suites run
**in place** with their own rootdir and ``PYTHONPATH``, while integration/e2e
suites delegate to the existing scripts under ``components/evaluation/scripts``.

Every run is stamped with the KB manifest it executed against, so a report can
never be mistaken for a run against a different corpus.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .registry import Registry, Suite, load_registry

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"

# runner name -> script under components/evaluation/scripts
SCRIPT_RUNNERS = {
    "run_multiturn": "run_multiturn.py",
    "run_magic_fire": "run_magic_fire.py",
    "run_hitk": "run_hitk.py",
    "run_stress_clarify": "run_stress_clarify.py",
    "run_stress_regression": "run_stress_regression.py",
    "run_stress_sticky": "run_stress_sticky.py",
}


@dataclass
class SuiteResult:
    id: str
    name: str
    kind: str
    owner: str
    status: str  # passed | failed | skipped | error
    returncode: int | None = None
    duration_s: float = 0.0
    detail: str = ""
    counts: dict[str, int] = field(default_factory=dict)
    report: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "passed"


@dataclass
class RunResult:
    suites: list[SuiteResult] = field(default_factory=list)
    manifest_id: str | None = None
    stale: dict[str, Any] = field(default_factory=dict)
    duration_s: float = 0.0

    @property
    def ok(self) -> bool:
        failed = any(s.status in ("failed", "error") for s in self.suites)
        return (not failed) and bool(self.stale.get("ok", True))

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_id": self.manifest_id,
            "ok": self.ok,
            "duration_s": round(self.duration_s, 1),
            "stale": self.stale,
            "suites": [asdict(s) for s in self.suites],
            "summary": self.summary(),
        }

    def summary(self) -> dict[str, int]:
        out = {"total": len(self.suites), "passed": 0, "failed": 0, "skipped": 0, "error": 0}
        for s in self.suites:
            out[s.status] = out.get(s.status, 0) + 1
        return out


def _parse_pytest_counts(stdout: str) -> dict[str, int]:
    """Extract passed/failed/skipped counts from a pytest summary line."""
    import re

    counts: dict[str, int] = {}
    for line in reversed(stdout.strip().splitlines()):
        if not any(w in line for w in ("passed", "failed", "error", "no tests ran")):
            continue
        for num, word in re.findall(
            r"(\d+)\s+(passed|failed|skipped|error|errors|warning|warnings)", line
        ):
            key = {"errors": "error", "warnings": "warning"}.get(word, word)
            counts[key] = counts.get(key, 0) + int(num)
        if counts:
            break
    return counts


def run_suite(
    suite: Suite,
    *,
    registry: Registry,
    out_dir: Path | None = None,
    extra_args: Iterable[str] = (),
    dry_run: bool = False,
) -> SuiteResult:
    """Run one suite and return its result."""
    umbrella = registry.umbrella
    started = time.time()
    out_dir = out_dir or (Path(__file__).resolve().parents[2] / "artifacts")
    out_dir.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env.update(suite.env)
    if "PYTHONPATH" in suite.env:
        env["PYTHONPATH"] = suite.env["PYTHONPATH"]

    if suite.runner == "pytest":
        cmd = [sys.executable, "-m", "pytest", str(suite.resolve_path(umbrella)), "-q"]
        cmd += list(extra_args)
        cwd = suite.resolve_rootdir(umbrella)
    elif suite.runner in SCRIPT_RUNNERS:
        script = SCRIPTS / SCRIPT_RUNNERS[suite.runner]
        cmd = [sys.executable, str(script), *suite.args]
        cmd += list(extra_args)
        cwd = SCRIPTS.parent
    elif suite.runner == "script":
        cmd = [sys.executable, str(suite.resolve_path(umbrella)), *suite.args]
        cmd += list(extra_args)
        cwd = umbrella
    else:
        return SuiteResult(
            id=suite.id,
            name=suite.name,
            kind=suite.kind,
            owner=suite.owner,
            status="error",
            detail=f"unknown runner: {suite.runner}",
        )

    if dry_run:
        return SuiteResult(
            id=suite.id,
            name=suite.name,
            kind=suite.kind,
            owner=suite.owner,
            status="skipped",
            detail=f"dry-run: {' '.join(cmd)} (cwd={cwd})",
        )

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=float(env.get("SUITE_TIMEOUT_S", 3600)),
        )
        stdout, stderr, rc = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as exc:
        return SuiteResult(
            id=suite.id,
            name=suite.name,
            kind=suite.kind,
            owner=suite.owner,
            status="error",
            detail=f"timeout after {exc.timeout}s",
            duration_s=round(time.time() - started, 1),
        )
    except OSError as exc:
        return SuiteResult(
            id=suite.id,
            name=suite.name,
            kind=suite.kind,
            owner=suite.owner,
            status="error",
            detail=f"could not start: {exc}",
            duration_s=round(time.time() - started, 1),
        )

    log_path = out_dir / f"{suite.id}.log"
    log_path.write_text(stdout + ("\n--- stderr ---\n" + stderr if stderr else ""), encoding="utf-8")

    counts = _parse_pytest_counts(stdout) if suite.runner == "pytest" else {}
    status = "passed" if rc == 0 else "failed"
    tail = (stderr or stdout).strip().splitlines()[-3:]
    return SuiteResult(
        id=suite.id,
        name=suite.name,
        kind=suite.kind,
        owner=suite.owner,
        status=status,
        returncode=rc,
        duration_s=round(time.time() - started, 1),
        detail=" | ".join(tail)[:500],
        counts=counts,
        report=str(log_path),
    )


def run(
    *,
    ids: Iterable[str] | None = None,
    kinds: Iterable[str] | None = None,
    tags: Iterable[str] | None = None,
    owners: Iterable[str] | None = None,
    umbrella: Path | None = None,
    out_dir: Path | None = None,
    check_stale: bool = True,
    fail_on_stale: bool = True,
    dry_run: bool = False,
    extra_args: Iterable[str] = (),
) -> RunResult:
    """Select suites and run them, gated on the version staleness check."""
    registry = load_registry(umbrella)

    problems = registry.validate()
    if problems:
        result = RunResult(stale={"ok": False, "checked": False, "stale": problems})
        for p in problems:
            result.suites.append(
                SuiteResult(id=p.split(":")[0], name=p, kind="unit", owner="evaluation", status="error", detail=p)
            )
        return result

    selected = registry.suites
    if ids:
        wanted = set(ids)
        selected = [s for s in selected if s.id in wanted]
        missing = wanted - {s.id for s in selected}
        if missing:
            raise SystemExit(f"unknown suite id(s): {', '.join(sorted(missing))}")
    if kinds:
        wanted_kinds = set(kinds)
        selected = [s for s in selected if s.kind in wanted_kinds]
    if tags:
        wanted_tags = set(tags)
        selected = [s for s in selected if wanted_tags & set(s.tags)]
    if owners:
        wanted_owners = set(owners)
        selected = [s for s in selected if s.owner in wanted_owners]

    result = RunResult()
    stale = registry.check_stale() if check_stale else {"ok": True, "checked": False, "stale": []}
    result.stale = stale
    result.manifest_id = stale.get("live_manifest") or stale.get("pinned_manifest")

    if fail_on_stale and not stale.get("ok", True):
        for s in selected:
            result.suites.append(
                SuiteResult(
                    id=s.id,
                    name=s.name,
                    kind=s.kind,
                    owner=s.owner,
                    status="skipped",
                    detail=f"stale: {stale.get('reason')}",
                )
            )
        return result

    started = time.time()
    for suite in selected:
        result.suites.append(
            run_suite(suite, registry=registry, out_dir=out_dir, extra_args=extra_args, dry_run=dry_run)
        )
    result.duration_s = time.time() - started
    return result


def write_report(result: RunResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "# Test suite run",
        "",
        f"- manifest: `{result.manifest_id}`",
        f"- ok: **{result.ok}**",
        f"- duration: {round(result.duration_s, 1)}s",
        f"- versions: {'in sync' if result.stale.get('ok') else result.stale.get('reason')}",
        "",
        "| Suite | Kind | Owner | Status | Counts | Time |",
        "|---|---|---|---|---|---|",
    ]
    for s in result.suites:
        counts = ", ".join(f"{k}={v}" for k, v in sorted(s.counts.items())) or s.detail[:60]
        lines.append(
            f"| `{s.id}` | {s.kind} | {s.owner} | {s.status} | {counts} | {s.duration_s}s |"
        )
    lines.append("")
    path.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")
