"""Policy-bounded verification command execution for RepoOps V0.3.

A request may select only stable command IDs already present in a trusted registry.
Definitions contain exact argv arrays; the request never supplies a shell string or
arbitrary extra arguments. Command evidence is an input to acceptance, not acceptance itself.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, BinaryIO

from repoops.git_adapter import GitAdapterError, _discover_root, _git_attempt_evidence, _run_git
from repoops.models import (
    CheckEvidence,
    CommandEvidence,
    CommandOutcome,
    VerificationOutcome,
    VerificationReceipt,
)

VERIFICATION_CLAIM_BOUNDARY = (
    "RepoOps V0.3 proves only the execution evidence for commands resolved from the declared "
    "registry against the recorded local Git worktree state. A VERIFIED command receipt is "
    "verification evidence; it does not certify delivery, grant merge authority, permit "
    "arbitrary shell execution, or establish repository-wide correctness."
)
DEFAULT_ENVIRONMENT_KEYS = (
    "CI",
    "HOME",
    "LANG",
    "LC_ALL",
    "PATH",
    "PYTHONHASHSEED",
    "PYTHONPATH",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "TMPDIR",
    "USERPROFILE",
)
_SECRET_NAME = re.compile(
    r"(?:TOKEN|SECRET|PASSWORD|PASSWD|API[_-]?KEY|PRIVATE[_-]?KEY|CREDENTIAL|AUTH)",
    re.IGNORECASE,
)
_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


@dataclass(frozen=True)
class CommandDefinition:
    """Trusted executable policy entry; requests select IDs, never construct argv."""

    command_id: str
    version: str
    argv: tuple[str, ...]
    timeout_seconds: float = 60.0
    max_output_bytes: int = 16_384
    environment_keys: tuple[str, ...] = DEFAULT_ENVIRONMENT_KEYS

    def __post_init__(self) -> None:
        if not self.command_id or not self.version or not self.argv:
            raise ValueError("command definition requires id, version and non-empty argv")
        if self.timeout_seconds <= 0:
            raise ValueError("command timeout must be positive")
        if self.max_output_bytes < 1:
            raise ValueError("max_output_bytes must be positive")
        if any("\0" in value for value in self.argv):
            raise ValueError("argv cannot contain NUL bytes")


def default_registry() -> dict[str, CommandDefinition]:
    """Return the deliberately small, read-oriented self-verification registry."""

    python = sys.executable
    definitions = (
        CommandDefinition(
            "repoops.pytest",
            "1",
            (python, "-m", "pytest", "-q", "-p", "no:cacheprovider"),
            timeout_seconds=90.0,
        ),
        CommandDefinition(
            "repoops.ruff-check",
            "1",
            (python, "-m", "ruff", "check", "src", "tests", "tools"),
        ),
        CommandDefinition(
            "repoops.ruff-format-check",
            "1",
            (python, "-m", "ruff", "format", "--check", "src", "tests", "tools"),
        ),
        CommandDefinition(
            "repoops.mypy",
            "1",
            (python, "-m", "mypy", "--no-incremental", "src"),
            timeout_seconds=90.0,
        ),
    )
    return {definition.command_id: definition for definition in definitions}


def _canonical_json(payload: object) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _definition_sha256(definition: CommandDefinition) -> str:
    return _sha256(
        _canonical_json(
            {
                "command_id": definition.command_id,
                "version": definition.version,
                "argv": list(definition.argv),
                "timeout_seconds": definition.timeout_seconds,
                "max_output_bytes": definition.max_output_bytes,
                "environment_keys": list(definition.environment_keys),
            }
        )
    )


def _build_environment(
    definition: CommandDefinition,
    source: Mapping[str, str],
) -> tuple[dict[str, str], tuple[tuple[str, str], ...], tuple[str, ...]]:
    child: dict[str, str] = {}
    evidence: list[tuple[str, str]] = []
    secret_values: list[str] = []
    for key in definition.environment_keys:
        if key not in source:
            continue
        value = source[key]
        child[key] = value
        if _SECRET_NAME.search(key):
            evidence.append((key, "[REDACTED]"))
            if value:
                secret_values.append(value)
        else:
            evidence.append((key, value))
    unique_secrets = tuple(sorted(set(secret_values), key=len, reverse=True))
    return child, tuple(sorted(evidence)), unique_secrets


def _redact(text: str, secrets: tuple[str, ...]) -> str:
    redacted = text
    for secret in secrets:
        redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


def _stream_evidence(
    stream: BinaryIO,
    max_output_bytes: int,
    secret_values: tuple[str, ...],
) -> tuple[str, str, bool]:
    stream.flush()
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(0)

    digest = hashlib.sha256()
    while True:
        chunk = stream.read(65_536)
        if not chunk:
            break
        digest.update(chunk)

    stream.seek(0)
    preview_bytes = stream.read(max_output_bytes)
    preview = preview_bytes.decode("utf-8", errors="replace")
    preview = _redact(preview, secret_values)
    truncated = size > max_output_bytes
    if truncated:
        preview += "\n[TRUNCATED]"
    return digest.hexdigest(), preview, truncated


def _command_evidence(
    definition: CommandDefinition,
    *,
    outcome: CommandOutcome,
    exit_code: int | None,
    stdout_preview: str,
    stderr_preview: str,
    stdout_sha256: str,
    stderr_sha256: str,
    stdout_truncated: bool,
    stderr_truncated: bool,
    environment: tuple[tuple[str, str], ...],
    redacted_argv: tuple[str, ...] | None = None,
) -> CommandEvidence:
    definition_sha256 = _definition_sha256(definition)
    argv = redacted_argv if redacted_argv is not None else definition.argv
    unsigned: dict[str, Any] = {
        "command_id": definition.command_id,
        "definition_version": definition.version,
        "definition_sha256": definition_sha256,
        "outcome": outcome.value,
        "argv": list(argv),
        "timeout_seconds": definition.timeout_seconds,
        "exit_code": exit_code,
        "stdout_preview": stdout_preview,
        "stderr_preview": stderr_preview,
        "stdout_sha256": stdout_sha256,
        "stderr_sha256": stderr_sha256,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "environment": [list(item) for item in environment],
    }
    return CommandEvidence(
        command_id=definition.command_id,
        definition_version=definition.version,
        definition_sha256=definition_sha256,
        outcome=outcome,
        argv=argv,
        timeout_seconds=definition.timeout_seconds,
        exit_code=exit_code,
        stdout_preview=stdout_preview,
        stderr_preview=stderr_preview,
        stdout_sha256=stdout_sha256,
        stderr_sha256=stderr_sha256,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
        environment=environment,
        evidence_sha256=_sha256(_canonical_json(unsigned)),
    )


def _rejected_command(command_id: str, detail: str) -> CommandEvidence:
    definition = CommandDefinition(command_id or "UNKNOWN", "unresolved", ("[NOT_EXECUTED]",))
    return _command_evidence(
        definition,
        outcome=CommandOutcome.REJECTED,
        exit_code=None,
        stdout_preview="",
        stderr_preview=detail,
        stdout_sha256=_EMPTY_SHA256,
        stderr_sha256=_sha256(detail.encode()),
        stdout_truncated=False,
        stderr_truncated=False,
        environment=(),
    )


def run_definition(
    root: Path,
    definition: CommandDefinition,
    *,
    environment_source: Mapping[str, str] | None = None,
) -> CommandEvidence:
    """Execute one trusted definition with no shell and bounded output evidence."""

    source = os.environ if environment_source is None else environment_source
    child_environment, environment_evidence, secret_values = _build_environment(definition, source)
    redacted_argv = tuple(_redact(value, secret_values) for value in definition.argv)

    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        try:
            process = subprocess.Popen(
                list(definition.argv),
                cwd=root,
                env=child_environment,
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                shell=False,
            )
        except OSError as error:
            detail = _redact(str(error), secret_values)
            return _command_evidence(
                definition,
                outcome=CommandOutcome.ERROR,
                exit_code=None,
                stdout_preview="",
                stderr_preview=detail,
                stdout_sha256=_EMPTY_SHA256,
                stderr_sha256=_sha256(str(error).encode()),
                stdout_truncated=False,
                stderr_truncated=False,
                environment=environment_evidence,
                redacted_argv=redacted_argv,
            )

        timed_out = False
        try:
            exit_code = process.wait(timeout=definition.timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            exit_code = process.wait()

        stdout_sha256, stdout_preview, stdout_truncated = _stream_evidence(
            stdout_file,
            definition.max_output_bytes,
            secret_values,
        )
        stderr_sha256, stderr_preview, stderr_truncated = _stream_evidence(
            stderr_file,
            definition.max_output_bytes,
            secret_values,
        )

    if timed_out:
        outcome = CommandOutcome.TIMEOUT
    elif exit_code == 0:
        outcome = CommandOutcome.PASS
    else:
        outcome = CommandOutcome.FAIL
    return _command_evidence(
        definition,
        outcome=outcome,
        exit_code=exit_code,
        stdout_preview=stdout_preview,
        stderr_preview=stderr_preview,
        stdout_sha256=stdout_sha256,
        stderr_sha256=stderr_sha256,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
        environment=environment_evidence,
        redacted_argv=redacted_argv,
    )


def _receipt(
    *,
    request_id: str,
    outcome: VerificationOutcome,
    base_head: str,
    changed_paths: tuple[str, ...],
    worktree_diff_sha256: str,
    post_worktree_diff_sha256: str,
    worktree_unchanged: bool,
    preconditions: tuple[CheckEvidence, ...],
    commands: tuple[CommandEvidence, ...],
) -> VerificationReceipt:
    unsigned: dict[str, Any] = {
        "schema": "repoops.verification-receipt.v0.3",
        "request_id": request_id,
        "outcome": outcome.value,
        "base_head": base_head,
        "changed_paths": list(changed_paths),
        "worktree_diff_sha256": worktree_diff_sha256,
        "post_worktree_diff_sha256": post_worktree_diff_sha256,
        "worktree_unchanged": worktree_unchanged,
        "preconditions": [asdict(check) for check in preconditions],
        "commands": [asdict(command) for command in commands],
        "claim_boundary": VERIFICATION_CLAIM_BOUNDARY,
    }
    for command in unsigned["commands"]:
        command["outcome"] = command["outcome"].value
    return VerificationReceipt(
        schema="repoops.verification-receipt.v0.3",
        request_id=request_id,
        outcome=outcome,
        base_head=base_head,
        changed_paths=changed_paths,
        worktree_diff_sha256=worktree_diff_sha256,
        post_worktree_diff_sha256=post_worktree_diff_sha256,
        worktree_unchanged=worktree_unchanged,
        preconditions=preconditions,
        commands=commands,
        claim_boundary=VERIFICATION_CLAIM_BOUNDARY,
        receipt_sha256=_sha256(_canonical_json(unsigned)),
    )


def execute_verification_plan(
    repository: Path,
    plan: Mapping[str, Any],
    *,
    registry: Mapping[str, CommandDefinition] | None = None,
    environment_source: Mapping[str, str] | None = None,
) -> VerificationReceipt:
    """Resolve command IDs from policy and collect bounded verification evidence."""

    request_id = str(plan.get("request_id", "UNKNOWN"))
    try:
        root = _discover_root(repository)
        base_head = _run_git(root, ["rev-parse", "HEAD"]).strip()
        changed_paths, worktree_diff = _git_attempt_evidence(root)
    except GitAdapterError as error:
        return _receipt(
            request_id=request_id,
            outcome=VerificationOutcome.INDETERMINATE,
            base_head="",
            changed_paths=(),
            worktree_diff_sha256=_EMPTY_SHA256,
            post_worktree_diff_sha256=_EMPTY_SHA256,
            worktree_unchanged=False,
            preconditions=(CheckEvidence("git-evidence", False, str(error)),),
            commands=(),
        )

    worktree_diff_sha256 = _sha256(worktree_diff.encode("utf-8", errors="surrogateescape"))
    preconditions: list[CheckEvidence] = []
    expected_head = plan.get("expected_base_head")
    if expected_head is not None:
        passed = str(expected_head) == base_head
        preconditions.append(
            CheckEvidence(
                "expected-base-head",
                passed,
                f"expected={expected_head} observed={base_head}",
            )
        )
    expected_diff = plan.get("expected_worktree_diff_sha256")
    if expected_diff is not None:
        passed = str(expected_diff) == worktree_diff_sha256
        preconditions.append(
            CheckEvidence(
                "expected-worktree-diff",
                passed,
                f"expected={expected_diff} observed={worktree_diff_sha256}",
            )
        )

    if any(not check.passed for check in preconditions):
        return _receipt(
            request_id=request_id,
            outcome=VerificationOutcome.INDETERMINATE,
            base_head=base_head,
            changed_paths=changed_paths,
            worktree_diff_sha256=worktree_diff_sha256,
            post_worktree_diff_sha256=worktree_diff_sha256,
            worktree_unchanged=True,
            preconditions=tuple(preconditions),
            commands=(),
        )

    raw_commands = plan.get("commands")
    if not isinstance(raw_commands, list) or not raw_commands or not all(
        isinstance(item, str) and item for item in raw_commands
    ):
        preconditions.append(
            CheckEvidence(
                "verification-plan",
                False,
                "commands must be a non-empty JSON array of command IDs",
            )
        )
        return _receipt(
            request_id=request_id,
            outcome=VerificationOutcome.FAILED,
            base_head=base_head,
            changed_paths=changed_paths,
            worktree_diff_sha256=worktree_diff_sha256,
            post_worktree_diff_sha256=worktree_diff_sha256,
            worktree_unchanged=True,
            preconditions=tuple(preconditions),
            commands=(),
        )

    selected_registry = default_registry() if registry is None else registry
    command_evidence: list[CommandEvidence] = []
    for command_id in raw_commands:
        definition = selected_registry.get(command_id)
        if definition is None:
            command_evidence.append(
                _rejected_command(command_id, f"command id is not allowed by policy: {command_id}")
            )
            continue
        command_evidence.append(
            run_definition(root, definition, environment_source=environment_source)
        )

    try:
        _post_paths, post_worktree_diff = _git_attempt_evidence(root)
        post_worktree_diff_sha256 = _sha256(
            post_worktree_diff.encode("utf-8", errors="surrogateescape")
        )
        worktree_unchanged = post_worktree_diff_sha256 == worktree_diff_sha256
    except GitAdapterError:
        post_worktree_diff_sha256 = _EMPTY_SHA256
        worktree_unchanged = False

    outcomes = {command.outcome for command in command_evidence}
    if not worktree_unchanged or outcomes & {CommandOutcome.TIMEOUT, CommandOutcome.ERROR}:
        outcome = VerificationOutcome.INDETERMINATE
    elif outcomes & {CommandOutcome.FAIL, CommandOutcome.REJECTED}:
        outcome = VerificationOutcome.FAILED
    else:
        outcome = VerificationOutcome.VERIFIED

    return _receipt(
        request_id=request_id,
        outcome=outcome,
        base_head=base_head,
        changed_paths=changed_paths,
        worktree_diff_sha256=worktree_diff_sha256,
        post_worktree_diff_sha256=post_worktree_diff_sha256,
        worktree_unchanged=worktree_unchanged,
        preconditions=tuple(preconditions),
        commands=tuple(command_evidence),
    )
