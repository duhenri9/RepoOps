from __future__ import annotations

import copy
from typing import Any

from repoops.github_adapter import GitHubApiError, GitHubClient, collect_github_evidence
from repoops.models import GitHubCheckState, GitHubEvidenceOutcome

REPO = "/repos/duhenri9/RepoOps"
PR = f"{REPO}/pulls/9"
FILES = f"{PR}/files?per_page=100&page=1"
HEAD = "1" * 40
BASE = "2" * 40


class FakeTransport:
    def __init__(
        self,
        routes: dict[str, object],
        sequences: dict[str, list[object]] | None = None,
    ) -> None:
        self.routes = routes
        self.sequences = sequences or {}
        self.calls: list[str] = []

    def get_json(self, path: str) -> object:
        self.calls.append(path)
        if path in self.sequences:
            values = self.sequences[path]
            if not values:
                raise GitHubApiError(f"fixture exhausted for {path}")
            return copy.deepcopy(values.pop(0))
        if path not in self.routes:
            raise GitHubApiError(f"fixture has no route for {path}")
        return copy.deepcopy(self.routes[path])


def pr_payload(head_sha: str = HEAD) -> dict[str, Any]:
    return {
        "id": 9009,
        "number": 9,
        "base": {"ref": "main", "sha": BASE},
        "head": {"ref": "feat/v04", "sha": head_sha},
    }


def base_routes(
    *,
    files: list[dict[str, Any]] | None = None,
    check_runs: list[dict[str, Any]] | None = None,
    statuses: list[dict[str, Any]] | None = None,
) -> dict[str, object]:
    return {
        REPO: {"id": 12345, "full_name": "duhenri9/RepoOps"},
        FILES: files
        if files is not None
        else [
            {
                "filename": "src/repoops/github_adapter.py",
                "status": "modified",
                "sha": "abc",
                "additions": 5,
                "deletions": 1,
                "changes": 6,
                "patch": "@@ -1 +1 @@",
            }
        ],
        f"{REPO}/commits/{HEAD}/check-runs?per_page=100": {
            "total_count": len(check_runs or [1]),
            "check_runs": check_runs
            if check_runs is not None
            else [
                {
                    "name": "ci",
                    "status": "completed",
                    "conclusion": "success",
                    "details_url": "https://example.invalid/check/1",
                    "app": {"slug": "github-actions"},
                }
            ],
        },
        f"{REPO}/commits/{HEAD}/status?per_page=100": {
            "state": "success",
            "statuses": statuses or [],
        },
    }


def plan(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "request_id": "v04-test",
        "repository": "duhenri9/RepoOps",
        "pull_request": 9,
        "expected_repository_id": 12345,
        "expected_head_sha": HEAD,
        "allowed_paths": ["src/", "tests/"],
        "required_checks": ["ci"],
    }
    value.update(overrides)
    return value


def transport_for(routes: dict[str, object], final_head: str = HEAD) -> FakeTransport:
    return FakeTransport(routes, {PR: [pr_payload(), pr_payload(final_head)]})


def test_complete_read_only_evidence_is_deterministic() -> None:
    first = collect_github_evidence(plan(), transport=transport_for(base_routes()))
    second = collect_github_evidence(plan(), transport=transport_for(base_routes()))

    assert first.outcome is GitHubEvidenceOutcome.COMPLETE
    assert first.check_summary is GitHubCheckState.PASSING
    assert first.repository_id == 12345
    assert first.head_sha == HEAD
    assert first.changed_paths == ("src/repoops/github_adapter.py",)
    assert not first.scope_violations
    assert first.receipt_sha256 == second.receipt_sha256
    assert first.changed_files_sha256 == second.changed_files_sha256


def test_failing_and_pending_checks_are_preserved_not_promoted() -> None:
    routes = base_routes(
        check_runs=[
            {
                "name": "lint",
                "status": "completed",
                "conclusion": "failure",
                "details_url": None,
                "app": {"slug": "github-actions"},
            },
            {
                "name": "tests",
                "status": "in_progress",
                "conclusion": None,
                "details_url": None,
                "app": {"slug": "github-actions"},
            },
        ]
    )
    receipt = collect_github_evidence(
        plan(required_checks=["lint", "tests"]), transport=transport_for(routes)
    )

    assert receipt.outcome is GitHubEvidenceOutcome.COMPLETE
    assert receipt.check_summary is GitHubCheckState.FAILING
    states = {item.name: item.state for item in receipt.checks}
    assert states == {"lint": GitHubCheckState.FAILING, "tests": GitHubCheckState.PENDING}


def test_missing_required_check_is_indeterminate() -> None:
    receipt = collect_github_evidence(
        plan(required_checks=["ci", "security"]), transport=transport_for(base_routes())
    )
    assert receipt.outcome is GitHubEvidenceOutcome.INDETERMINATE
    assert receipt.missing_evidence == ("required check missing: security",)


def test_moved_head_between_reads_is_stale_and_indeterminate() -> None:
    moved = "3" * 40
    receipt = collect_github_evidence(plan(), transport=transport_for(base_routes(), moved))
    assert receipt.outcome is GitHubEvidenceOutcome.INDETERMINATE
    assert receipt.stale is True
    assert receipt.head_sha == HEAD


def test_wrong_repository_identity_fails_closed() -> None:
    receipt = collect_github_evidence(
        plan(expected_repository_id=99999), transport=transport_for(base_routes())
    )
    assert receipt.outcome is GitHubEvidenceOutcome.INDETERMINATE
    assert any("repository id mismatch" in error for error in receipt.errors)


def test_out_of_scope_file_remains_explicit_evidence_not_acceptance() -> None:
    routes = base_routes(
        files=[
            {
                "filename": ".github/workflows/ci.yml",
                "status": "modified",
                "sha": "def",
                "additions": 1,
                "deletions": 0,
                "changes": 1,
                "patch": "+permissions: write-all",
            }
        ]
    )
    receipt = collect_github_evidence(plan(), transport=transport_for(routes))
    assert receipt.outcome is GitHubEvidenceOutcome.COMPLETE
    assert receipt.scope_violations == (".github/workflows/ci.yml",)
    assert "acceptance" in receipt.claim_boundary.lower()


def test_missing_api_evidence_is_indeterminate() -> None:
    routes = base_routes()
    del routes[f"{REPO}/commits/{HEAD}/status?per_page=100"]
    receipt = collect_github_evidence(plan(), transport=transport_for(routes))
    assert receipt.outcome is GitHubEvidenceOutcome.INDETERMINATE
    assert any("no route" in error for error in receipt.errors)


def test_refs_mode_resolves_both_refs_and_compare_identity() -> None:
    base_ref_path = f"{REPO}/git/ref/heads/main"
    head_ref_path = f"{REPO}/git/ref/heads/feat%2Fv04"
    compare_path = f"{REPO}/compare/{BASE}...{HEAD}"
    routes = base_routes()
    routes[base_ref_path] = {"object": {"sha": BASE}}
    routes[head_ref_path] = {"object": {"sha": HEAD}}
    routes[compare_path] = {
        "files": [
            {
                "filename": "src/repoops/github_adapter.py",
                "status": "modified",
                "sha": "abc",
                "additions": 5,
                "deletions": 1,
                "changes": 6,
                "patch": "@@ -1 +1 @@",
            }
        ]
    }
    transport = FakeTransport(routes, {head_ref_path: [{"object": {"sha": HEAD}}, {"object": {"sha": HEAD}}]})
    receipt = collect_github_evidence(
        plan(
            pull_request=None,
            base_ref="main",
            head_ref="feat/v04",
            required_checks=["ci"],
        ),
        transport=transport,
    )
    assert receipt.outcome is GitHubEvidenceOutcome.COMPLETE
    assert receipt.base_sha == BASE
    assert receipt.head_sha == HEAD


def test_real_client_exposes_no_write_method() -> None:
    client = GitHubClient()
    assert hasattr(client, "get_json")
    assert not hasattr(client, "post_json")
    assert not hasattr(client, "patch_json")
    assert not hasattr(client, "delete_json")
