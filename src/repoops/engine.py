"""Deterministic, fixture-backed RepoOps acceptance engine."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from repoops.models import CheckEvidence, Outcome, Receipt

CLAIM_BOUNDARY = (
    "This receipt proves only the bounded fixture mutation, scope checks and verification "
    "declared by this execution contract. It does not certify repository-wide correctness."
)


def _canonical_json(payload: object) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _repo_digest(repository: Mapping[str, str]) -> str:
    return hashlib.sha256(_canonical_json(dict(sorted(repository.items())))).hexdigest()


def _receipt_digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _run_check(repository: Mapping[str, str], check: Mapping[str, Any]) -> CheckEvidence:
    name = str(check["name"])
    kind = str(check["kind"])
    path = str(check["path"])
    expected = str(check.get("value", ""))

    if path not in repository:
        return CheckEvidence(name=name, passed=False, detail=f"missing path: {path}")

    content = repository[path]
    if kind == "contains":
        passed = expected in content
        return CheckEvidence(name=name, passed=passed, detail=f"contains({path})={passed}")
    if kind == "not_contains":
        passed = expected not in content
        return CheckEvidence(name=name, passed=passed, detail=f"not_contains({path})={passed}")
    if kind == "equals":
        passed = content == expected
        return CheckEvidence(name=name, passed=passed, detail=f"equals({path})={passed}")

    return CheckEvidence(name=name, passed=False, detail=f"unsupported check kind: {kind}")


def execute_fixture(fixture: Mapping[str, Any]) -> Receipt:
    """Execute one bounded fixture and return a deterministic evidence receipt.

    V0 intentionally operates over an in-memory synthetic repository. Real Git and GitHub
    adapters are later layers; acceptance ownership remains here.
    """

    request_id = str(fixture["request_id"])
    repository = {str(path): str(content) for path, content in dict(fixture["repository"]).items()}
    contract = dict(fixture["contract"])
    allowed_paths = {str(path) for path in contract["allowed_paths"]}
    operations = list(fixture["operations"])
    required_checks = list(contract["required_checks"])

    before_digest = _repo_digest(repository)
    changed_paths: list[str] = []
    scope_violations: list[str] = []
    stale_paths: list[str] = []

    for raw_operation in operations:
        operation = dict(raw_operation)
        path = str(operation["path"])
        if path not in allowed_paths:
            scope_violations.append(path)
            continue

        current = repository.get(path)
        expected_before = str(operation["expected_before"])
        if current is None or current != expected_before:
            stale_paths.append(path)
            continue

        repository[path] = str(operation["replacement"])
        changed_paths.append(path)

    checks = tuple(_run_check(repository, dict(check)) for check in required_checks)
    after_digest = _repo_digest(repository)

    if scope_violations:
        outcome = Outcome.REJECTED
    elif stale_paths:
        outcome = Outcome.INDETERMINATE
    elif all(check.passed for check in checks):
        outcome = Outcome.ACCEPTED
    else:
        outcome = Outcome.REJECTED

    if stale_paths:
        checks = (
            *checks,
            CheckEvidence(
                name="fresh-state-precondition",
                passed=False,
                detail="stale or missing path(s): " + ", ".join(sorted(stale_paths)),
            ),
        )

    unsigned: dict[str, Any] = {
        "schema": "repoops.receipt.v0",
        "request_id": request_id,
        "outcome": outcome.value,
        "changed_paths": sorted(changed_paths),
        "scope_violations": sorted(scope_violations),
        "checks": [
            {"name": check.name, "passed": check.passed, "detail": check.detail} for check in checks
        ],
        "repository_before_sha256": before_digest,
        "repository_after_sha256": after_digest,
        "claim_boundary": CLAIM_BOUNDARY,
    }

    return Receipt(
        schema="repoops.receipt.v0",
        request_id=request_id,
        outcome=outcome,
        changed_paths=tuple(sorted(changed_paths)),
        scope_violations=tuple(sorted(scope_violations)),
        checks=checks,
        repository_before_sha256=before_digest,
        repository_after_sha256=after_digest,
        claim_boundary=CLAIM_BOUNDARY,
        receipt_sha256=_receipt_digest(unsigned),
    )
