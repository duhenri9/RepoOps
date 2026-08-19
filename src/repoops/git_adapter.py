"""Bounded local-Git adapter for RepoOps V0.2.

The adapter mutates only an already-clean local worktree. It never commits, pushes,
fetches, contacts a remote, or executes request-supplied commands. Git is used as an
evidence source: base identity, actual changed paths and a unified diff are collected
with a temporary index so the user's real index is not modified.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from repoops.models import CheckEvidence, GitReceipt, Outcome

GIT_CLAIM_BOUNDARY = (
    "RepoOps V0.2 proves only the bounded local-worktree mutation, Git diff/path evidence, "
    "fresh-worktree precondition and declared verification checks in this receipt. It does "
    "not commit, push, authenticate remote authority, run arbitrary verification commands or "
    "certify repository-wide correctness."
)


class GitAdapterError(RuntimeError):
    """Raised when Git or filesystem evidence cannot be collected safely."""


def _canonical_json(payload: object) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _run_git(
    root: Path,
    arguments: list[str],
    *,
    env: Mapping[str, str] | None = None,
) -> str:
    completed: subprocess.CompletedProcess[str] = subprocess.run(
        ["git", *arguments],
        cwd=root,
        env=dict(env) if env is not None else None,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "git command failed"
        raise GitAdapterError(f"git {' '.join(arguments)}: {detail}")
    return completed.stdout


def _run_git_bytes(
    root: Path,
    arguments: list[str],
    *,
    env: Mapping[str, str],
) -> bytes:
    completed: subprocess.CompletedProcess[bytes] = subprocess.run(
        ["git", *arguments],
        cwd=root,
        env=dict(env),
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode(errors="replace").strip() or "git command failed"
        raise GitAdapterError(f"git {' '.join(arguments)}: {detail}")
    return completed.stdout


def _discover_root(repository: Path) -> Path:
    candidate = repository.resolve()
    if not candidate.is_dir():
        raise GitAdapterError(f"repository path is not a directory: {candidate}")
    output = _run_git(candidate, ["rev-parse", "--show-toplevel"]).strip()
    root = Path(output).resolve()
    if not root.is_dir():
        raise GitAdapterError("Git returned a repository root that is not a directory")
    return root


def _normalise_relative_path(raw: object) -> str:
    rendered = str(raw).replace("\\", "/")
    path = PurePosixPath(rendered)
    if not rendered or path.is_absolute() or ".." in path.parts or ".git" in path.parts:
        raise GitAdapterError(f"unsafe repository-relative path: {rendered!r}")
    normalised = path.as_posix()
    if normalised in {"", "."}:
        raise GitAdapterError(f"unsafe repository-relative path: {rendered!r}")
    return normalised


def _safe_path(root: Path, relative: str) -> Path:
    root = root.resolve()
    parts = PurePosixPath(relative).parts
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise GitAdapterError(f"symlink path is outside the V0.2 write model: {relative}")
    if not current.parent.resolve().is_relative_to(root):
        raise GitAdapterError(f"path escapes repository root: {relative}")
    return current


def _status_entries(root: Path) -> tuple[str, ...]:
    output = _run_git(root, ["status", "--porcelain=v1", "--untracked-files=all"])
    return tuple(line for line in output.splitlines() if line)


def _parse_changed_paths(raw: bytes) -> tuple[str, ...]:
    fields = raw.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    changed: set[str] = set()
    index = 0
    while index < len(fields):
        status = fields[index].decode("ascii", errors="replace")
        index += 1
        if status.startswith(("R", "C")):
            if index + 1 >= len(fields):
                raise GitAdapterError("malformed Git rename/copy name-status evidence")
            changed.add(fields[index].decode("utf-8", errors="surrogateescape"))
            changed.add(fields[index + 1].decode("utf-8", errors="surrogateescape"))
            index += 2
        else:
            if index >= len(fields):
                raise GitAdapterError("malformed Git name-status evidence")
            changed.add(fields[index].decode("utf-8", errors="surrogateescape"))
            index += 1
    return tuple(sorted(changed))


def _git_attempt_evidence(root: Path) -> tuple[tuple[str, ...], str]:
    """Return actual changed paths and unified diff without touching the real index."""

    with tempfile.TemporaryDirectory(prefix="repoops-index-") as directory:
        temporary_index = Path(directory) / "index"
        environment = os.environ.copy()
        environment["GIT_INDEX_FILE"] = str(temporary_index)
        _run_git(root, ["read-tree", "HEAD"], env=environment)
        _run_git(root, ["add", "-A", "--", "."], env=environment)
        changed_raw = _run_git_bytes(
            root,
            ["diff", "--cached", "--name-status", "-z", "--find-renames", "HEAD", "--"],
            env=environment,
        )
        unified_diff = _run_git(
            root,
            ["diff", "--cached", "--binary", "--no-color", "--find-renames", "HEAD", "--"],
            env=environment,
        )
    return _parse_changed_paths(changed_raw), unified_diff


def _check_path(root: Path, raw_check: Mapping[str, Any]) -> CheckEvidence:
    name = str(raw_check.get("name", "unnamed-check"))
    kind = str(raw_check.get("kind", ""))
    try:
        relative = _normalise_relative_path(raw_check.get("path", ""))
        path = _safe_path(root, relative)
    except GitAdapterError as error:
        return CheckEvidence(name=name, passed=False, detail=str(error))

    if kind == "absent":
        passed = not path.exists()
        return CheckEvidence(name=name, passed=passed, detail=f"absent({relative})={passed}")
    if kind == "exists":
        passed = path.is_file()
        return CheckEvidence(name=name, passed=passed, detail=f"exists({relative})={passed}")
    if not path.is_file():
        return CheckEvidence(name=name, passed=False, detail=f"missing file: {relative}")

    payload = path.read_bytes()
    if kind == "sha256":
        expected = str(raw_check.get("value", ""))
        observed = _sha256_bytes(payload)
        passed = observed == expected
        return CheckEvidence(name=name, passed=passed, detail=f"sha256({relative})={observed}")

    try:
        content = payload.decode("utf-8")
    except UnicodeDecodeError:
        return CheckEvidence(name=name, passed=False, detail=f"non-UTF8 file: {relative}")

    expected = str(raw_check.get("value", ""))
    if kind == "contains":
        passed = expected in content
    elif kind == "not_contains":
        passed = expected not in content
    elif kind == "equals":
        passed = content == expected
    else:
        return CheckEvidence(name=name, passed=False, detail=f"unsupported check kind: {kind}")
    return CheckEvidence(name=name, passed=passed, detail=f"{kind}({relative})={passed}")


def _precondition(path: Path, operation: Mapping[str, Any]) -> tuple[bool, str]:
    if not path.is_file():
        return False, "missing file"
    payload = path.read_bytes()
    if "expected_before_sha256" in operation:
        expected_hash = str(operation["expected_before_sha256"])
        observed_hash = _sha256_bytes(payload)
        return observed_hash == expected_hash, f"sha256={observed_hash}"
    if "expected_before" not in operation:
        return False, "missing expected_before or expected_before_sha256"
    try:
        content = payload.decode("utf-8")
    except UnicodeDecodeError:
        return False, "target is non-UTF8; use expected_before_sha256"
    return content == str(operation["expected_before"]), "text precondition"


def _receipt(
    *,
    request_id: str,
    outcome: Outcome,
    base_head: str,
    dirty_before: tuple[str, ...] = (),
    changed_paths: tuple[str, ...] = (),
    scope_violations: tuple[str, ...] = (),
    checks: tuple[CheckEvidence, ...] = (),
    unified_diff: str = "",
    worktree_restored: bool = False,
) -> GitReceipt:
    diff_sha256 = _sha256_bytes(unified_diff.encode("utf-8", errors="surrogateescape"))
    unsigned: dict[str, Any] = {
        "schema": "repoops.git-receipt.v0.2",
        "request_id": request_id,
        "outcome": outcome.value,
        "base_head": base_head,
        "dirty_before": list(dirty_before),
        "changed_paths": list(changed_paths),
        "scope_violations": list(scope_violations),
        "checks": [
            {"name": check.name, "passed": check.passed, "detail": check.detail} for check in checks
        ],
        "unified_diff": unified_diff,
        "unified_diff_sha256": diff_sha256,
        "worktree_restored": worktree_restored,
        "claim_boundary": GIT_CLAIM_BOUNDARY,
    }
    digest = _sha256_bytes(_canonical_json(unsigned))
    return GitReceipt(
        schema="repoops.git-receipt.v0.2",
        request_id=request_id,
        outcome=outcome,
        base_head=base_head,
        dirty_before=dirty_before,
        changed_paths=changed_paths,
        scope_violations=scope_violations,
        checks=checks,
        unified_diff=unified_diff,
        unified_diff_sha256=diff_sha256,
        worktree_restored=worktree_restored,
        claim_boundary=GIT_CLAIM_BOUNDARY,
        receipt_sha256=digest,
    )


def _restore(root: Path, snapshots: Mapping[str, bytes | None]) -> None:
    """Restore only files captured by this bounded attempt."""

    for relative, original in snapshots.items():
        path = _safe_path(root, relative)
        if original is None:
            if path.exists():
                if not path.is_file():
                    raise GitAdapterError(f"cannot restore non-file path: {relative}")
                path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(original)


def execute_git_plan(repository: Path, plan: Mapping[str, Any]) -> GitReceipt:
    """Execute one bounded plan against a clean local Git worktree.

    Rejected contract/scope attempts and stale/dirty preconditions do not mutate the
    worktree. If post-mutation verification fails, RepoOps restores the exact file
    snapshots captured before the attempt. Accepted changes are intentionally left
    uncommitted for an external authority to review/commit.
    """

    request_id = str(plan.get("request_id", "UNKNOWN"))
    try:
        root = _discover_root(repository)
        base_head = _run_git(root, ["rev-parse", "HEAD"]).strip()
    except GitAdapterError as error:
        return _receipt(
            request_id=request_id,
            outcome=Outcome.INDETERMINATE,
            base_head="",
            checks=(CheckEvidence("git-repository-precondition", False, str(error)),),
        )

    dirty_before = _status_entries(root)
    if dirty_before:
        return _receipt(
            request_id=request_id,
            outcome=Outcome.INDETERMINATE,
            base_head=base_head,
            dirty_before=dirty_before,
            checks=(
                CheckEvidence(
                    "clean-worktree-precondition",
                    False,
                    "worktree/index must be clean before bounded mutation",
                ),
            ),
        )

    try:
        allowed_paths = {_normalise_relative_path(item) for item in list(plan["allowed_paths"])}
        raw_operations = [dict(item) for item in list(plan["operations"])]
        raw_checks = [dict(item) for item in list(plan.get("required_checks", []))]
    except (KeyError, TypeError, ValueError, GitAdapterError) as error:
        return _receipt(
            request_id=request_id,
            outcome=Outcome.REJECTED,
            base_head=base_head,
            checks=(CheckEvidence("contract", False, f"invalid V0.2 plan: {error}"),),
        )

    operations: list[dict[str, Any]] = []
    contract_violations: list[str] = []
    touched: set[str] = set()
    for operation in raw_operations:
        kind = str(operation.get("kind", ""))
        if kind not in {"replace", "delete", "rename"}:
            contract_violations.append(f"unsupported operation kind: {kind}")
            continue
        try:
            source = _normalise_relative_path(operation.get("path", ""))
        except GitAdapterError as error:
            contract_violations.append(str(error))
            continue
        operation["path"] = source
        operation_paths = {source}
        if kind == "rename":
            try:
                destination = _normalise_relative_path(operation.get("destination", ""))
            except GitAdapterError as error:
                contract_violations.append(str(error))
                continue
            operation["destination"] = destination
            operation_paths.add(destination)
        outside = operation_paths - allowed_paths
        if outside:
            contract_violations.extend(sorted(outside))
            continue
        overlap = touched & operation_paths
        if overlap:
            contract_violations.append(
                "overlapping operation path(s): " + ", ".join(sorted(overlap))
            )
            continue
        touched.update(operation_paths)
        operations.append(operation)

    if contract_violations:
        return _receipt(
            request_id=request_id,
            outcome=Outcome.REJECTED,
            base_head=base_head,
            scope_violations=tuple(sorted(set(contract_violations))),
            checks=(CheckEvidence("bounded-authority", False, "operation contract rejected"),),
        )

    snapshots: dict[str, bytes | None] = {}
    stale_details: list[str] = []
    try:
        for operation in operations:
            source = str(operation["path"])
            source_path = _safe_path(root, source)
            matches, detail = _precondition(source_path, operation)
            if not matches:
                stale_details.append(f"{source}: {detail}")
            snapshots[source] = source_path.read_bytes() if source_path.is_file() else None
            if str(operation["kind"]) == "rename":
                destination = str(operation["destination"])
                destination_path = _safe_path(root, destination)
                if destination_path.exists():
                    stale_details.append(f"{destination}: rename destination already exists")
                snapshots[destination] = (
                    destination_path.read_bytes() if destination_path.is_file() else None
                )
    except (OSError, GitAdapterError) as error:
        stale_details.append(str(error))

    if stale_details:
        return _receipt(
            request_id=request_id,
            outcome=Outcome.INDETERMINATE,
            base_head=base_head,
            checks=(
                CheckEvidence(
                    "fresh-state-precondition",
                    False,
                    "; ".join(sorted(stale_details)),
                ),
            ),
        )

    mutated = False
    try:
        for operation in operations:
            source = str(operation["path"])
            source_path = _safe_path(root, source)
            kind = str(operation["kind"])
            if kind == "replace":
                if "replacement" not in operation:
                    raise GitAdapterError(f"replace operation missing replacement: {source}")
                source_path.write_text(str(operation["replacement"]), encoding="utf-8")
            elif kind == "delete":
                source_path.unlink()
            else:
                destination = str(operation["destination"])
                destination_path = _safe_path(root, destination)
                if not destination_path.parent.is_dir():
                    raise GitAdapterError(f"rename destination parent is missing: {destination}")
                source_path.rename(destination_path)
            mutated = True

        changed_paths, unified_diff = _git_attempt_evidence(root)
        scope_violations = tuple(sorted(set(changed_paths) - allowed_paths))
        checks = tuple(_check_path(root, check) for check in raw_checks)
        if scope_violations or not all(check.passed for check in checks):
            _restore(root, snapshots)
            return _receipt(
                request_id=request_id,
                outcome=Outcome.REJECTED,
                base_head=base_head,
                changed_paths=changed_paths,
                scope_violations=scope_violations,
                checks=checks,
                unified_diff=unified_diff,
                worktree_restored=True,
            )

        return _receipt(
            request_id=request_id,
            outcome=Outcome.ACCEPTED,
            base_head=base_head,
            changed_paths=changed_paths,
            scope_violations=scope_violations,
            checks=checks,
            unified_diff=unified_diff,
            worktree_restored=False,
        )
    except (OSError, GitAdapterError) as error:
        restored = False
        if mutated:
            try:
                _restore(root, snapshots)
                restored = True
            except (OSError, GitAdapterError):
                restored = False
        return _receipt(
            request_id=request_id,
            outcome=Outcome.INDETERMINATE,
            base_head=base_head,
            checks=(CheckEvidence("git-adapter", False, str(error)),),
            unified_diff="",
            worktree_restored=restored,
        )
