from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from repoops.models import CommandOutcome, VerificationOutcome
from repoops.verification import CommandDefinition, execute_verification_plan


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
    (root / "README.md").write_text("verification fixture\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "repoops@example.invalid")
    _git(root, "config", "user.name", "RepoOps Fixture")
    _git(root, "add", "README.md")
    environment = os.environ.copy()
    environment["GIT_AUTHOR_DATE"] = "2026-01-01T00:00:00+00:00"
    environment["GIT_COMMITTER_DATE"] = "2026-01-01T00:00:00+00:00"
    _git(root, "commit", "-q", "-m", "verification baseline", env=environment)
    return root


def _registry(*definitions: CommandDefinition) -> dict[str, CommandDefinition]:
    return {definition.command_id: definition for definition in definitions}


def test_allowed_deterministic_command_produces_stable_evidence(tmp_path: Path) -> None:
    definition = CommandDefinition(
        "test.stable",
        "1",
        (sys.executable, "-c", "print('stable-evidence')"),
        environment_keys=(),
    )
    plan = {"request_id": "VERIFY-STABLE-001", "commands": ["test.stable"]}
    first_root = make_repository(tmp_path, "first")
    second_root = make_repository(tmp_path, "second")

    first = execute_verification_plan(first_root, plan, registry=_registry(definition))
    second = execute_verification_plan(second_root, plan, registry=_registry(definition))

    assert first.outcome is VerificationOutcome.VERIFIED
    assert second.outcome is VerificationOutcome.VERIFIED
    assert first.worktree_unchanged
    assert second.worktree_unchanged
    assert first.commands[0].outcome is CommandOutcome.PASS
    assert first.commands[0].stdout_preview == "stable-evidence\n"
    assert first.base_head == second.base_head
    assert first.commands[0].evidence_sha256 == second.commands[0].evidence_sha256
    assert first.receipt_sha256 == second.receipt_sha256


def test_nonzero_exit_is_failure_evidence_not_success(tmp_path: Path) -> None:
    root = make_repository(tmp_path)
    definition = CommandDefinition(
        "test.fail",
        "1",
        (sys.executable, "-c", "import sys; print('nope'); sys.exit(7)"),
        environment_keys=(),
    )

    receipt = execute_verification_plan(
        root,
        {"request_id": "VERIFY-FAIL-001", "commands": ["test.fail"]},
        registry=_registry(definition),
    )

    assert receipt.outcome is VerificationOutcome.FAILED
    assert receipt.commands[0].outcome is CommandOutcome.FAIL
    assert receipt.commands[0].exit_code == 7
    assert receipt.commands[0].stdout_preview == "nope\n"


def test_unknown_command_is_rejected_before_process_creation(tmp_path: Path) -> None:
    root = make_repository(tmp_path)

    receipt = execute_verification_plan(
        root,
        {"request_id": "VERIFY-UNKNOWN-001", "commands": ["rm.everything"]},
        registry={},
    )

    assert receipt.outcome is VerificationOutcome.FAILED
    assert receipt.commands[0].outcome is CommandOutcome.REJECTED
    assert receipt.commands[0].exit_code is None
    assert "not allowed by policy" in receipt.commands[0].stderr_preview
    assert receipt.worktree_unchanged


def test_shell_metacharacters_are_literal_argv_data(tmp_path: Path) -> None:
    root = make_repository(tmp_path)
    marker = root / "shell-expanded.txt"
    literal = "; touch shell-expanded.txt"
    definition = CommandDefinition(
        "test.literal-argv",
        "1",
        (
            sys.executable,
            "-c",
            "import sys; print(sys.argv[1])",
            literal,
        ),
        environment_keys=(),
    )

    receipt = execute_verification_plan(
        root,
        {"request_id": "VERIFY-ARGV-001", "commands": ["test.literal-argv"]},
        registry=_registry(definition),
    )

    assert receipt.outcome is VerificationOutcome.VERIFIED
    assert receipt.commands[0].stdout_preview == literal + "\n"
    assert not marker.exists()
    assert receipt.worktree_unchanged


def test_timeout_is_explicit_and_indeterminate(tmp_path: Path) -> None:
    root = make_repository(tmp_path)
    definition = CommandDefinition(
        "test.timeout",
        "1",
        (sys.executable, "-c", "import time; time.sleep(2)"),
        timeout_seconds=0.05,
        environment_keys=(),
    )

    receipt = execute_verification_plan(
        root,
        {"request_id": "VERIFY-TIMEOUT-001", "commands": ["test.timeout"]},
        registry=_registry(definition),
    )

    assert receipt.outcome is VerificationOutcome.INDETERMINATE
    assert receipt.commands[0].outcome is CommandOutcome.TIMEOUT
    assert receipt.commands[0].exit_code is not None
    assert receipt.worktree_unchanged


def test_oversized_output_is_hashed_completely_but_preview_is_bounded(tmp_path: Path) -> None:
    root = make_repository(tmp_path)
    payload = b"x" * 4096
    definition = CommandDefinition(
        "test.large-output",
        "1",
        (sys.executable, "-c", "import sys; sys.stdout.write('x' * 4096)"),
        max_output_bytes=32,
        environment_keys=(),
    )

    receipt = execute_verification_plan(
        root,
        {"request_id": "VERIFY-LARGE-001", "commands": ["test.large-output"]},
        registry=_registry(definition),
    )
    command = receipt.commands[0]

    assert receipt.outcome is VerificationOutcome.VERIFIED
    assert command.stdout_truncated
    assert command.stdout_preview == ("x" * 32) + "\n[TRUNCATED]"
    assert command.stdout_sha256 == hashlib.sha256(payload).hexdigest()


def test_secret_environment_value_is_redacted_from_receipt_and_preview(tmp_path: Path) -> None:
    root = make_repository(tmp_path)
    secret = "repoops-super-secret-value"
    definition = CommandDefinition(
        "test.secret-redaction",
        "1",
        (
            sys.executable,
            "-c",
            "import os; print(os.environ['REPOOPS_TEST_TOKEN'])",
        ),
        environment_keys=("REPOOPS_TEST_TOKEN",),
    )

    receipt = execute_verification_plan(
        root,
        {"request_id": "VERIFY-SECRET-001", "commands": ["test.secret-redaction"]},
        registry=_registry(definition),
        environment_source={"REPOOPS_TEST_TOKEN": secret},
    )
    command = receipt.commands[0]
    rendered = json.dumps(receipt.to_dict(), sort_keys=True)

    assert receipt.outcome is VerificationOutcome.VERIFIED
    assert secret not in rendered
    assert command.environment == (("REPOOPS_TEST_TOKEN", "[REDACTED]"),)
    assert command.stdout_preview == "[REDACTED]\n"
    assert command.stdout_sha256 == hashlib.sha256((secret + "\n").encode()).hexdigest()


def test_command_side_effect_makes_verification_indeterminate(tmp_path: Path) -> None:
    root = make_repository(tmp_path)
    definition = CommandDefinition(
        "test.side-effect",
        "1",
        (
            sys.executable,
            "-c",
            "from pathlib import Path; Path('unexpected.txt').write_text('changed')",
        ),
        environment_keys=(),
    )

    receipt = execute_verification_plan(
        root,
        {"request_id": "VERIFY-SIDE-EFFECT-001", "commands": ["test.side-effect"]},
        registry=_registry(definition),
    )

    assert receipt.commands[0].outcome is CommandOutcome.PASS
    assert receipt.outcome is VerificationOutcome.INDETERMINATE
    assert not receipt.worktree_unchanged
    assert receipt.post_worktree_diff_sha256 != receipt.worktree_diff_sha256
    assert (root / "unexpected.txt").exists()


def test_stale_worktree_identity_blocks_command_execution(tmp_path: Path) -> None:
    root = make_repository(tmp_path)
    marker = root / "should-not-exist.txt"
    definition = CommandDefinition(
        "test.marker",
        "1",
        (
            sys.executable,
            "-c",
            "from pathlib import Path; Path('should-not-exist.txt').write_text('ran')",
        ),
        environment_keys=(),
    )

    receipt = execute_verification_plan(
        root,
        {
            "request_id": "VERIFY-STALE-001",
            "expected_base_head": "0" * 40,
            "commands": ["test.marker"],
        },
        registry=_registry(definition),
    )

    assert receipt.outcome is VerificationOutcome.INDETERMINATE
    assert not receipt.commands
    assert any(
        check.name == "expected-base-head" and not check.passed for check in receipt.preconditions
    )
    assert not marker.exists()
