"""Stable public data contracts for RepoOps evidence receipts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class Outcome(StrEnum):
    """Bounded acceptance state for one maintenance attempt."""

    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    INDETERMINATE = "INDETERMINATE"


class CommandOutcome(StrEnum):
    """Execution state for one policy-approved verification command."""

    PASS = "PASS"
    FAIL = "FAIL"
    TIMEOUT = "TIMEOUT"
    REJECTED = "REJECTED"
    ERROR = "ERROR"


class VerificationOutcome(StrEnum):
    """Aggregate verification state; this is evidence, not delivery acceptance."""

    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    INDETERMINATE = "INDETERMINATE"


class GitHubEvidenceOutcome(StrEnum):
    """Whether the declared GitHub observation was completed without stale/missing evidence."""

    COMPLETE = "COMPLETE"
    INDETERMINATE = "INDETERMINATE"


class GitHubCheckState(StrEnum):
    """Observed GitHub check/status state; it is not delivery acceptance."""

    PASSING = "PASSING"
    FAILING = "FAILING"
    PENDING = "PENDING"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class CheckEvidence:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class Receipt:
    schema: str
    request_id: str
    outcome: Outcome
    changed_paths: tuple[str, ...]
    scope_violations: tuple[str, ...]
    checks: tuple[CheckEvidence, ...]
    repository_before_sha256: str
    repository_after_sha256: str
    claim_boundary: str
    receipt_sha256: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["outcome"] = self.outcome.value
        return payload


@dataclass(frozen=True)
class GitReceipt:
    """Evidence for one bounded mutation attempt against a real local Git worktree."""

    schema: str
    request_id: str
    outcome: Outcome
    base_head: str
    dirty_before: tuple[str, ...]
    changed_paths: tuple[str, ...]
    scope_violations: tuple[str, ...]
    checks: tuple[CheckEvidence, ...]
    unified_diff: str
    unified_diff_sha256: str
    worktree_restored: bool
    claim_boundary: str
    receipt_sha256: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["outcome"] = self.outcome.value
        return payload


@dataclass(frozen=True)
class CommandEvidence:
    """Bounded evidence for one command definition resolved from a registry."""

    command_id: str
    definition_version: str
    definition_sha256: str
    outcome: CommandOutcome
    argv: tuple[str, ...]
    timeout_seconds: float
    exit_code: int | None
    stdout_preview: str
    stderr_preview: str
    stdout_sha256: str
    stderr_sha256: str
    stdout_truncated: bool
    stderr_truncated: bool
    environment: tuple[tuple[str, str], ...]
    evidence_sha256: str


@dataclass(frozen=True)
class VerificationReceipt:
    """Aggregate command evidence that deliberately does not claim delivery acceptance."""

    schema: str
    request_id: str
    outcome: VerificationOutcome
    base_head: str
    changed_paths: tuple[str, ...]
    worktree_diff_sha256: str
    post_worktree_diff_sha256: str
    worktree_unchanged: bool
    preconditions: tuple[CheckEvidence, ...]
    commands: tuple[CommandEvidence, ...]
    claim_boundary: str
    receipt_sha256: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["outcome"] = self.outcome.value
        for command in payload["commands"]:
            command["outcome"] = command["outcome"].value
        return payload


@dataclass(frozen=True)
class GitHubCheckEvidence:
    """One read-only check/status observation from GitHub."""

    name: str
    source: str
    status: str
    conclusion: str | None
    details_url: str | None
    state: GitHubCheckState
    evidence_sha256: str


@dataclass(frozen=True)
class GitHubEvidenceReceipt:
    """Read-only GitHub identity/evidence receipt; never a delivery-acceptance decision."""

    schema: str
    request_id: str
    outcome: GitHubEvidenceOutcome
    repository_full_name: str
    repository_id: int | None
    base_ref: str | None
    base_sha: str | None
    head_ref: str | None
    head_sha: str | None
    pull_request_number: int | None
    pull_request_id: int | None
    issue_number: int | None
    issue_id: int | None
    changed_paths: tuple[str, ...]
    changed_files_sha256: str
    checks: tuple[GitHubCheckEvidence, ...]
    check_summary: GitHubCheckState
    scope_violations: tuple[str, ...]
    stale: bool
    missing_evidence: tuple[str, ...]
    errors: tuple[str, ...]
    claim_boundary: str
    receipt_sha256: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["outcome"] = self.outcome.value
        payload["check_summary"] = self.check_summary.value
        for check in payload["checks"]:
            check["state"] = check["state"].value
        return payload
