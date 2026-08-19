"""Stable public data contracts for RepoOps V0."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class Outcome(StrEnum):
    """Bounded acceptance state for one maintenance attempt."""

    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    INDETERMINATE = "INDETERMINATE"


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
