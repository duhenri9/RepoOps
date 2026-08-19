from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path
from typing import Any

from repoops.git_adapter import execute_git_plan
from repoops.models import Outcome

BINARY_PAYLOAD = bytes([0, 255, 1, 2])
BINARY_SHA256 = hashlib.sha256(BINARY_PAYLOAD).hexdigest()


def _git(root: Path, *arguments: str, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def make_repository(parent: Path, name: str = "repo") -> Path:
    root = parent / name
    root.mkdir()
    (root / "src").mkdir()
    (root / "docs").mkdir()
    (root / "assets").mkdir()
    (root / "src/service.py").write_text("VALUE = 'old'\n", encoding="utf-8")
    (root / "docs/obsolete.md").write_text("obsolete\n", encoding="utf-8")
    (root / "docs/guide-old.md").write_text("guide\n", encoding="utf-8")
    (root / "assets/blob.bin").write_bytes(BINARY_PAYLOAD)
    (root / "README.md").write_text("fixture repository\n", encoding="utf-8")

    _git(root, "init", "-q")
    _git(root, "config", "user.email", "repoops@example.invalid")
    _git(root, "config", "user.name", "RepoOps Fixture")
    _git(root, "add", "-A")
    environment = os.environ.copy()
    environment["GIT_AUTHOR_DATE"] = "2026-01-01T00:00:00+00:00"
    environment["GIT_COMMITTER_DATE"] = "2026-01-01T00:00:00+00:00"
    _git(root, "commit", "-q", "-m", "fixture baseline", env=environment)
    return root


def accepted_plan() -> dict[str, Any]:
    return {
        "request_id": "GIT-ACCEPTED-001",
        "allowed_paths": [
            "src/service.py",
            "docs/obsolete.md",
            "docs/guide-old.md",
            "docs/guide.md",
            "assets/blob.bin",
            "assets/blob-renamed.bin",
        ],
        "operations": [
            {
                "kind": "replace",
                "path": "src/service.py",
                "expected_before": "VALUE = 'old'\n",
                "replacement": "VALUE = 'new'\n",
            },
            {
                "kind": "delete",
                "path": "docs/obsolete.md",
                "expected_before": "obsolete\n",
            },
            {
                "kind": "rename",
                "path": "docs/guide-old.md",
                "destination": "docs/guide.md",
                "expected_before": "guide\n",
            },
            {
                "kind": "rename",
                "path": "assets/blob.bin",
                "destination": "assets/blob-renamed.bin",
                "expected_before_sha256": BINARY_SHA256,
            },
        ],
        "required_checks": [
            {
                "name": "service-updated",
                "kind": "equals",
                "path": "src/service.py",
                "value": "VALUE = 'new'\n",
            },
            {"name": "obsolete-removed", "kind": "absent", "path": "docs/obsolete.md"},
            {"name": "guide-renamed", "kind": "exists", "path": "docs/guide.md"},
            {
                "name": "binary-preserved",
                "kind": "sha256",
                "path": "assets/blob-renamed.bin",
                "value": BINARY_SHA256,
            },
        ],
    }


def test_real_worktree_replace_delete_text_rename_and_binary_rename(tmp_path: Path) -> None:
    root = make_repository(tmp_path)
    receipt = execute_git_plan(root, accepted_plan())

    assert receipt.outcome is Outcome.ACCEPTED
    assert receipt.changed_paths == (
        "assets/blob-renamed.bin",
        "assets/blob.bin",
        "docs/guide-old.md",
        "docs/guide.md",
        "docs/obsolete.md",
        "src/service.py",
    )
    assert not receipt.scope_violations
    assert all(check.passed for check in receipt.checks)
    assert "diff --git" in receipt.unified_diff
    assert receipt.unified_diff_sha256 != hashlib.sha256(b"").hexdigest()
    assert not receipt.worktree_restored
    assert (root / "src/service.py").read_text(encoding="utf-8") == "VALUE = 'new'\n"
    assert not (root / "docs/obsolete.md").exists()
    assert (root / "assets/blob-renamed.bin").read_bytes() == BINARY_PAYLOAD


def test_dirty_worktree_is_indeterminate_and_not_mutated(tmp_path: Path) -> None:
    root = make_repository(tmp_path)
    (root / "README.md").write_text("dirty\n", encoding="utf-8")

    receipt = execute_git_plan(root, accepted_plan())

    assert receipt.outcome is Outcome.INDETERMINATE
    assert receipt.dirty_before
    assert (root / "src/service.py").read_text(encoding="utf-8") == "VALUE = 'old'\n"
    assert any(check.name == "clean-worktree-precondition" for check in receipt.checks)


def test_out_of_scope_operation_is_rejected_before_mutation(tmp_path: Path) -> None:
    root = make_repository(tmp_path)
    plan: dict[str, Any] = {
        "request_id": "GIT-REJECT-SCOPE-001",
        "allowed_paths": ["src/service.py"],
        "operations": [
            {
                "kind": "delete",
                "path": "docs/obsolete.md",
                "expected_before": "obsolete\n",
            }
        ],
        "required_checks": [],
    }

    receipt = execute_git_plan(root, plan)

    assert receipt.outcome is Outcome.REJECTED
    assert receipt.scope_violations == ("docs/obsolete.md",)
    assert (root / "docs/obsolete.md").read_text(encoding="utf-8") == "obsolete\n"
    assert _git(root, "status", "--porcelain=v1") == ""


def test_parent_escape_is_rejected_without_touching_outside_file(tmp_path: Path) -> None:
    root = make_repository(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    plan: dict[str, Any] = {
        "request_id": "GIT-REJECT-ESCAPE-001",
        "allowed_paths": ["../outside.txt"],
        "operations": [
            {
                "kind": "replace",
                "path": "../outside.txt",
                "expected_before": "outside\n",
                "replacement": "escaped\n",
            }
        ],
        "required_checks": [],
    }

    receipt = execute_git_plan(root, plan)

    assert receipt.outcome is Outcome.REJECTED
    assert outside.read_text(encoding="utf-8") == "outside\n"
    assert _git(root, "status", "--porcelain=v1") == ""


def test_failed_post_mutation_check_restores_clean_worktree(tmp_path: Path) -> None:
    root = make_repository(tmp_path)
    plan: dict[str, Any] = {
        "request_id": "GIT-ROLLBACK-001",
        "allowed_paths": ["src/service.py"],
        "operations": [
            {
                "kind": "replace",
                "path": "src/service.py",
                "expected_before": "VALUE = 'old'\n",
                "replacement": "VALUE = 'new'\n",
            }
        ],
        "required_checks": [
            {
                "name": "deliberately-wrong",
                "kind": "contains",
                "path": "src/service.py",
                "value": "never-present",
            }
        ],
    }

    receipt = execute_git_plan(root, plan)

    assert receipt.outcome is Outcome.REJECTED
    assert receipt.worktree_restored
    assert "VALUE = 'new'" in receipt.unified_diff
    assert (root / "src/service.py").read_text(encoding="utf-8") == "VALUE = 'old'\n"
    assert _git(root, "status", "--porcelain=v1") == ""


def test_stale_file_precondition_is_indeterminate_without_mutation(tmp_path: Path) -> None:
    root = make_repository(tmp_path)
    plan = accepted_plan()
    first = plan["operations"][0]
    assert isinstance(first, dict)
    first["expected_before"] = "VALUE = 'stale'\n"

    receipt = execute_git_plan(root, plan)

    assert receipt.outcome is Outcome.INDETERMINATE
    assert any(check.name == "fresh-state-precondition" for check in receipt.checks)
    assert _git(root, "status", "--porcelain=v1") == ""


def test_git_receipt_is_deterministic_for_same_baseline_and_plan(tmp_path: Path) -> None:
    first_root = make_repository(tmp_path, "first")
    second_root = make_repository(tmp_path, "second")

    first = execute_git_plan(first_root, accepted_plan())
    second = execute_git_plan(second_root, accepted_plan())

    assert first.outcome is Outcome.ACCEPTED
    assert second.outcome is Outcome.ACCEPTED
    assert first.base_head == second.base_head
    assert first.unified_diff_sha256 == second.unified_diff_sha256
    assert first.receipt_sha256 == second.receipt_sha256
