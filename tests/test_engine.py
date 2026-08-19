from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from repoops.engine import execute_fixture
from repoops.models import Outcome

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def load(name: str) -> dict[str, Any]:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_happy_path_is_accepted() -> None:
    receipt = execute_fixture(load("accepted.json"))
    assert receipt.outcome is Outcome.ACCEPTED
    assert receipt.changed_paths == ("src/service.py",)
    assert not receipt.scope_violations
    assert all(check.passed for check in receipt.checks)


def test_out_of_scope_mutation_is_rejected_even_if_visible_check_passes() -> None:
    receipt = execute_fixture(load("rejected-out-of-scope.json"))
    assert receipt.outcome is Outcome.REJECTED
    assert receipt.scope_violations == (".github/workflows/ci.yml",)
    assert any(check.passed for check in receipt.checks)


def test_stale_state_is_indeterminate_not_accepted() -> None:
    receipt = execute_fixture(load("indeterminate-stale-state.json"))
    assert receipt.outcome is Outcome.INDETERMINATE
    assert any(check.name == "fresh-state-precondition" for check in receipt.checks)


def test_receipt_digest_is_deterministic() -> None:
    first = execute_fixture(load("accepted.json"))
    second = execute_fixture(load("accepted.json"))
    assert first.receipt_sha256 == second.receipt_sha256
    assert first.repository_before_sha256 == second.repository_before_sha256
    assert first.repository_after_sha256 == second.repository_after_sha256
