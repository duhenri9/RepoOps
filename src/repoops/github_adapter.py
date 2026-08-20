"""Read-only GitHub identity and check evidence adapter for RepoOps V0.4."""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any, Protocol, cast
from urllib.parse import quote

from repoops.models import (
    GitHubCheckEvidence,
    GitHubCheckState,
    GitHubEvidenceOutcome,
    GitHubEvidenceReceipt,
)

CLAIM_BOUNDARY = (
    "V0.4 proves only read-only GitHub identity, changed-file and check/status observation "
    "for the declared repository/ref/PR request. COMPLETE does not mean the change is accepted, "
    "correct or safe to merge. The adapter performs GET requests only and owns no mutation or "
    "delivery-acceptance authority."
)
MAX_PAGES = 20
PER_PAGE = 100


class GitHubApiError(RuntimeError):
    """Bounded transport/API failure that becomes indeterminate evidence."""


class GitHubReadTransport(Protocol):
    """Minimal GET-only transport used by both the real client and deterministic controls."""

    def get_json(self, path: str) -> object:
        """Return decoded JSON for one API path without mutating remote state."""


class GitHubClient:
    """Small GitHub REST client exposing only GET operations."""

    def __init__(self, token: str | None = None, timeout_seconds: float = 10.0) -> None:
        self._token = token
        self._timeout_seconds = timeout_seconds
        self._base_url = "https://api.github.com"

    def get_json(self, path: str) -> object:
        if not path.startswith("/"):
            raise GitHubApiError("API path must start with /")
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "RepoOps-V0.4-read-evidence",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        request = urllib.request.Request(
            f"{self._base_url}{path}", headers=headers, method="GET"
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                data = response.read()
        except urllib.error.HTTPError as error:
            raise GitHubApiError(f"GitHub HTTP {error.code} for {path}") from error
        except urllib.error.URLError as error:
            raise GitHubApiError(f"GitHub transport error for {path}: {error.reason}") from error
        try:
            return cast(object, json.loads(data.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise GitHubApiError(f"GitHub returned invalid JSON for {path}") from error


def _canonical_json(payload: object) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _sha256(payload: object) -> str:
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _expect_dict(value: object, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GitHubApiError(f"{context} was not a JSON object")
    return cast(dict[str, Any], value)


def _expect_list(value: object, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise GitHubApiError(f"{context} was not a JSON array")
    return cast(list[Any], value)


def _required_str(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _optional_str(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string when present")
    return value


def _optional_int(payload: Mapping[str, Any], key: str) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{key} must be a positive integer when present")
    return value


def _string_tuple(payload: Mapping[str, Any], key: str) -> tuple[str, ...]:
    raw = payload.get(key, [])
    if not isinstance(raw, list):
        raise ValueError(f"{key} must be an array of strings")
    values: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item:
            raise ValueError(f"{key} must contain only non-empty strings")
        values.append(item)
    return tuple(values)


def _repo_path(repository: str) -> str:
    parts = repository.split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError("repository must use owner/name form")
    return "/repos/" + "/".join(quote(part, safe="") for part in parts)


def _string(payload: Mapping[str, Any], key: str, context: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise GitHubApiError(f"{context}.{key} is missing")
    return value


def _integer(payload: Mapping[str, Any], key: str, context: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise GitHubApiError(f"{context}.{key} is missing")
    return value


def _nested_dict(payload: Mapping[str, Any], key: str, context: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise GitHubApiError(f"{context}.{key} is missing")
    return cast(dict[str, Any], value)


def _ref_sha(transport: GitHubReadTransport, repository_path: str, ref: str) -> str:
    encoded = quote(ref, safe="")
    payload = _expect_dict(
        transport.get_json(f"{repository_path}/git/ref/heads/{encoded}"),
        f"ref {ref}",
    )
    obj = _nested_dict(payload, "object", f"ref {ref}")
    return _string(obj, "sha", f"ref {ref}.object")


def _paged_pr_files(
    transport: GitHubReadTransport, repository_path: str, pr_number: int
) -> tuple[list[dict[str, Any]], bool]:
    files: list[dict[str, Any]] = []
    for page in range(1, MAX_PAGES + 1):
        payload = _expect_list(
            transport.get_json(
                f"{repository_path}/pulls/{pr_number}/files?per_page={PER_PAGE}&page={page}"
            ),
            "pull request files",
        )
        page_files = [_expect_dict(item, "pull request file") for item in payload]
        files.extend(page_files)
        if len(page_files) < PER_PAGE:
            return files, True
    return files, False


def _compare_files(
    transport: GitHubReadTransport, repository_path: str, base_sha: str, head_sha: str
) -> tuple[list[dict[str, Any]], bool]:
    payload = _expect_dict(
        transport.get_json(f"{repository_path}/compare/{base_sha}...{head_sha}"),
        "compare response",
    )
    raw_files = payload.get("files")
    if not isinstance(raw_files, list):
        raise GitHubApiError("compare response did not include files")
    files = [_expect_dict(item, "compare file") for item in raw_files]
    return files, True


def _file_identity(files: list[dict[str, Any]]) -> tuple[tuple[str, ...], str]:
    paths: set[str] = set()
    identities: list[dict[str, Any]] = []
    for item in files:
        filename = _string(item, "filename", "changed file")
        paths.add(filename)
        previous = item.get("previous_filename")
        if isinstance(previous, str) and previous:
            paths.add(previous)
        patch = item.get("patch")
        patch_sha256 = hashlib.sha256(patch.encode()).hexdigest() if isinstance(patch, str) else None
        identities.append(
            {
                "filename": filename,
                "previous_filename": previous if isinstance(previous, str) else None,
                "status": item.get("status"),
                "sha": item.get("sha"),
                "additions": item.get("additions"),
                "deletions": item.get("deletions"),
                "changes": item.get("changes"),
                "patch_sha256": patch_sha256,
            }
        )
    identities.sort(key=lambda item: (str(item["filename"]), str(item["previous_filename"])))
    return tuple(sorted(paths)), _sha256(identities)


def _state_for_check_run(status: str, conclusion: str | None) -> GitHubCheckState:
    if status != "completed":
        return GitHubCheckState.PENDING
    if conclusion in {"success", "neutral", "skipped"}:
        return GitHubCheckState.PASSING
    if conclusion in {
        "failure",
        "cancelled",
        "timed_out",
        "action_required",
        "startup_failure",
        "stale",
    }:
        return GitHubCheckState.FAILING
    return GitHubCheckState.UNKNOWN


def _state_for_status(state: str) -> GitHubCheckState:
    if state == "success":
        return GitHubCheckState.PASSING
    if state in {"failure", "error"}:
        return GitHubCheckState.FAILING
    if state == "pending":
        return GitHubCheckState.PENDING
    return GitHubCheckState.UNKNOWN


def _check_evidence(
    *,
    name: str,
    source: str,
    status: str,
    conclusion: str | None,
    details_url: str | None,
    state: GitHubCheckState,
) -> GitHubCheckEvidence:
    unsigned = {
        "name": name,
        "source": source,
        "status": status,
        "conclusion": conclusion,
        "details_url": details_url,
        "state": state.value,
    }
    return GitHubCheckEvidence(
        name=name,
        source=source,
        status=status,
        conclusion=conclusion,
        details_url=details_url,
        state=state,
        evidence_sha256=_sha256(unsigned),
    )


def _collect_checks(
    transport: GitHubReadTransport, repository_path: str, head_sha: str
) -> tuple[tuple[GitHubCheckEvidence, ...], bool]:
    check_payload = _expect_dict(
        transport.get_json(f"{repository_path}/commits/{head_sha}/check-runs?per_page={PER_PAGE}"),
        "check-runs response",
    )
    raw_runs = check_payload.get("check_runs")
    if not isinstance(raw_runs, list):
        raise GitHubApiError("check-runs response did not include check_runs")

    status_payload = _expect_dict(
        transport.get_json(f"{repository_path}/commits/{head_sha}/status?per_page={PER_PAGE}"),
        "combined-status response",
    )
    raw_statuses = status_payload.get("statuses")
    if not isinstance(raw_statuses, list):
        raise GitHubApiError("combined-status response did not include statuses")

    checks: list[GitHubCheckEvidence] = []
    for raw in raw_runs:
        item = _expect_dict(raw, "check run")
        name = _string(item, "name", "check run")
        status = _string(item, "status", "check run")
        conclusion_value = item.get("conclusion")
        conclusion = conclusion_value if isinstance(conclusion_value, str) else None
        app = item.get("app")
        source = "check-run"
        if isinstance(app, dict):
            slug = cast(dict[str, Any], app).get("slug")
            if isinstance(slug, str) and slug:
                source = f"check-run:{slug}"
        details_value = item.get("details_url")
        details = details_value if isinstance(details_value, str) else None
        checks.append(
            _check_evidence(
                name=name,
                source=source,
                status=status,
                conclusion=conclusion,
                details_url=details,
                state=_state_for_check_run(status, conclusion),
            )
        )

    for raw in raw_statuses:
        item = _expect_dict(raw, "commit status")
        name = _string(item, "context", "commit status")
        state_value = _string(item, "state", "commit status")
        target_value = item.get("target_url")
        target = target_value if isinstance(target_value, str) else None
        checks.append(
            _check_evidence(
                name=name,
                source="commit-status",
                status=state_value,
                conclusion=state_value,
                details_url=target,
                state=_state_for_status(state_value),
            )
        )

    checks.sort(key=lambda item: (item.name, item.source, item.status, item.conclusion or ""))
    total_count = check_payload.get("total_count")
    check_runs_complete = not isinstance(total_count, int) or total_count <= len(raw_runs)
    statuses_complete = len(raw_statuses) < PER_PAGE
    return tuple(checks), check_runs_complete and statuses_complete


def _check_summary(checks: tuple[GitHubCheckEvidence, ...]) -> GitHubCheckState:
    states = {item.state for item in checks}
    if GitHubCheckState.FAILING in states:
        return GitHubCheckState.FAILING
    if GitHubCheckState.PENDING in states:
        return GitHubCheckState.PENDING
    if GitHubCheckState.UNKNOWN in states:
        return GitHubCheckState.UNKNOWN
    if checks:
        return GitHubCheckState.PASSING
    return GitHubCheckState.UNKNOWN


def _path_allowed(path: str, allowed_paths: tuple[str, ...]) -> bool:
    if not allowed_paths:
        return True
    for allowed in allowed_paths:
        if allowed.endswith("/") and path.startswith(allowed):
            return True
        if path == allowed:
            return True
    return False


def collect_github_evidence(
    plan: Mapping[str, Any],
    *,
    transport: GitHubReadTransport | None = None,
    token: str | None = None,
) -> GitHubEvidenceReceipt:
    """Collect bounded read-only GitHub evidence without making an acceptance decision."""

    request_id = _required_str(plan, "request_id")
    repository = _required_str(plan, "repository")
    repository_path = _repo_path(repository)
    expected_repository_id = _optional_int(plan, "expected_repository_id")
    expected_head_sha = _optional_str(plan, "expected_head_sha")
    pr_number = _optional_int(plan, "pull_request")
    issue_number = _optional_int(plan, "issue")
    requested_base_ref = _optional_str(plan, "base_ref")
    requested_head_ref = _optional_str(plan, "head_ref")
    allowed_paths = _string_tuple(plan, "allowed_paths")
    required_checks = _string_tuple(plan, "required_checks")
    client: GitHubReadTransport = transport or GitHubClient(token=token)

    repository_id: int | None = None
    base_ref: str | None = requested_base_ref
    base_sha: str | None = None
    head_ref: str | None = requested_head_ref
    head_sha: str | None = None
    pull_request_id: int | None = None
    issue_id: int | None = None
    changed_paths: tuple[str, ...] = ()
    changed_files_sha256 = _sha256([])
    checks: tuple[GitHubCheckEvidence, ...] = ()
    stale = False
    missing_evidence: list[str] = []
    errors: list[str] = []

    try:
        repo_payload = _expect_dict(client.get_json(repository_path), "repository response")
        observed_full_name = _string(repo_payload, "full_name", "repository")
        repository_id = _integer(repo_payload, "id", "repository")
        if observed_full_name != repository:
            errors.append(
                f"repository identity mismatch: requested {repository}, observed {observed_full_name}"
            )
        if expected_repository_id is not None and repository_id != expected_repository_id:
            errors.append(
                "repository id mismatch: "
                f"expected {expected_repository_id}, observed {repository_id}"
            )

        files: list[dict[str, Any]]
        file_coverage_complete: bool
        if pr_number is not None:
            pr_payload = _expect_dict(
                client.get_json(f"{repository_path}/pulls/{pr_number}"),
                "pull request response",
            )
            pull_request_id = _integer(pr_payload, "id", "pull request")
            base = _nested_dict(pr_payload, "base", "pull request")
            head = _nested_dict(pr_payload, "head", "pull request")
            base_ref = _string(base, "ref", "pull request.base")
            base_sha = _string(base, "sha", "pull request.base")
            head_ref = _string(head, "ref", "pull request.head")
            head_sha = _string(head, "sha", "pull request.head")
            files, file_coverage_complete = _paged_pr_files(client, repository_path, pr_number)
        else:
            if base_ref is None or head_ref is None:
                raise ValueError("base_ref and head_ref are required when pull_request is absent")
            base_sha = _ref_sha(client, repository_path, base_ref)
            head_sha = _ref_sha(client, repository_path, head_ref)
            files, file_coverage_complete = _compare_files(
                client, repository_path, base_sha, head_sha
            )

        if expected_head_sha is not None and head_sha != expected_head_sha:
            errors.append(f"head SHA mismatch: expected {expected_head_sha}, observed {head_sha}")
        if not file_coverage_complete:
            missing_evidence.append("changed-file pagination exceeded V0.4 bound")
        changed_paths, changed_files_sha256 = _file_identity(files)

        if issue_number is not None:
            issue_payload = _expect_dict(
                client.get_json(f"{repository_path}/issues/{issue_number}"),
                "issue response",
            )
            issue_id = _integer(issue_payload, "id", "issue")
            observed_issue_number = _integer(issue_payload, "number", "issue")
            if observed_issue_number != issue_number:
                errors.append(
                    f"issue identity mismatch: expected {issue_number}, observed {observed_issue_number}"
                )

        if head_sha is None:
            raise GitHubApiError("head SHA could not be resolved")
        checks, check_coverage_complete = _collect_checks(client, repository_path, head_sha)
        if not check_coverage_complete:
            missing_evidence.append("check/status pagination exceeded V0.4 bound")

        observed_check_names = {item.name for item in checks}
        for required in required_checks:
            if required not in observed_check_names:
                missing_evidence.append(f"required check missing: {required}")

        if pr_number is not None:
            final_pr = _expect_dict(
                client.get_json(f"{repository_path}/pulls/{pr_number}"),
                "final pull request response",
            )
            final_head = _nested_dict(final_pr, "head", "final pull request")
            final_base = _nested_dict(final_pr, "base", "final pull request")
            stale = (
                _string(final_head, "sha", "final pull request.head") != head_sha
                or _string(final_base, "sha", "final pull request.base") != base_sha
            )
        else:
            if head_ref is None:
                raise GitHubApiError("head ref could not be resolved")
            stale = _ref_sha(client, repository_path, head_ref) != head_sha
    except GitHubApiError as error:
        errors.append(str(error))

    scope_violations = tuple(
        sorted(path for path in changed_paths if not _path_allowed(path, allowed_paths))
    )
    summary = _check_summary(checks)
    outcome = (
        GitHubEvidenceOutcome.INDETERMINATE
        if stale or errors or missing_evidence
        else GitHubEvidenceOutcome.COMPLETE
    )

    unsigned: dict[str, Any] = {
        "schema": "repoops.github-evidence.v0.4",
        "request_id": request_id,
        "outcome": outcome.value,
        "repository_full_name": repository,
        "repository_id": repository_id,
        "base_ref": base_ref,
        "base_sha": base_sha,
        "head_ref": head_ref,
        "head_sha": head_sha,
        "pull_request_number": pr_number,
        "pull_request_id": pull_request_id,
        "issue_number": issue_number,
        "issue_id": issue_id,
        "changed_paths": changed_paths,
        "changed_files_sha256": changed_files_sha256,
        "checks": [
            {
                "name": item.name,
                "source": item.source,
                "status": item.status,
                "conclusion": item.conclusion,
                "details_url": item.details_url,
                "state": item.state.value,
                "evidence_sha256": item.evidence_sha256,
            }
            for item in checks
        ],
        "check_summary": summary.value,
        "scope_violations": scope_violations,
        "stale": stale,
        "missing_evidence": tuple(sorted(missing_evidence)),
        "errors": tuple(sorted(errors)),
        "claim_boundary": CLAIM_BOUNDARY,
    }
    return GitHubEvidenceReceipt(
        schema="repoops.github-evidence.v0.4",
        request_id=request_id,
        outcome=outcome,
        repository_full_name=repository,
        repository_id=repository_id,
        base_ref=base_ref,
        base_sha=base_sha,
        head_ref=head_ref,
        head_sha=head_sha,
        pull_request_number=pr_number,
        pull_request_id=pull_request_id,
        issue_number=issue_number,
        issue_id=issue_id,
        changed_paths=changed_paths,
        changed_files_sha256=changed_files_sha256,
        checks=checks,
        check_summary=summary,
        scope_violations=scope_violations,
        stale=stale,
        missing_evidence=tuple(sorted(missing_evidence)),
        errors=tuple(sorted(errors)),
        claim_boundary=CLAIM_BOUNDARY,
        receipt_sha256=_sha256(unsigned),
    )
