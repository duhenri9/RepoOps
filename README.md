# RepoOps

Evidence-driven software maintenance with bounded authority and verifiable completion.

RepoOps is an open-source engineering project built around a strict idea:

> a system that changes code must not be allowed to certify its own success without independent evidence.

## Architecture

```text
work request
    ↓
acceptance contract
    ↓
bounded mutation adapter
    ↓
policy-bounded verification evidence
    ↓
GitHub read-only identity/evidence
    ↓
independent acceptance
    ↓
ACCEPTED | REJECTED | INDETERMINATE
```

Planning, mutation, verification, remote evidence and acceptance are deliberately separate responsibilities. Git, a verification process, GitHub or a model can provide inputs or mechanisms; none of them silently owns the completion claim.

## V0 — deterministic evidence runtime

The offline V0 runs over synthetic in-memory repositories and proves the acceptance semantics before introducing filesystem/Git complexity.

It proves:

- exact allowed-path authority;
- stale-state/precondition detection;
- deterministic bounded mutation;
- independent post-change checks;
- before/after SHA-256 identities;
- deterministic receipt digest;
- an out-of-scope known-bad attempt is rejected even when visible behaviour passes;
- missing/stale evidence becomes `INDETERMINATE`, not fabricated success.

```bash
repoops fixtures/accepted.json
repoops fixtures/rejected-out-of-scope.json
repoops fixtures/indeterminate-stale-state.json
```

## V0.2 — real local Git worktree adapter

V0.2 applies the same bounded model to a **real local Git worktree** without granting Git, shell commands or an LLM acceptance authority.

It adds executable evidence for:

- exact base `HEAD` identity;
- mandatory clean worktree/index precondition;
- safe repository-relative path validation;
- rejection of `..`, absolute, `.git` and symlink write paths;
- text replacement, delete and rename operations;
- SHA-256 preconditions/checks for binary rename/delete edge cases;
- real changed-path evidence from Git;
- real unified diff evidence, including binary diff form;
- a temporary Git index so the user's real index is never staged by RepoOps;
- failed post-change acceptance rollback to captured file snapshots;
- accepted changes left **uncommitted** for an external reviewer/authority;
- deterministic Git receipt identity for the same fixed baseline + plan.

```bash
repoops-git /path/to/local/repository fixtures/git-v02-accepted.json --out receipt.json
```

See [`docs/GIT_WORKTREE_V02.md`](docs/GIT_WORKTREE_V02.md).

## V0.3 — policy-bounded verification commands

V0.3 introduces process execution without turning RepoOps into an arbitrary shell agent.

A request may select only stable IDs from a trusted command registry. The registry owns the exact executable/argv, timeout, output bound and environment allowlist.

```text
verification request
        ↓
trusted command ID registry
        ↓
exact argv, shell=False
        ↓
bounded stdout/stderr evidence
        ↓
pre/post Git-visible worktree identity
        ↓
VERIFIED | FAILED | INDETERMINATE
```

The default V0.3 registry contains only read-oriented self-verification commands for RepoOps:

- `repoops.pytest`
- `repoops.ruff-check`
- `repoops.ruff-format-check`
- `repoops.mypy`

```bash
repoops-verify . fixtures/verification-v03-default.json --out verification.json
```

V0.3 records command-definition identity, exact argv, timeout, exit outcome, complete stdout/stderr SHA-256 identities, bounded previews, allowlisted/redacted environment evidence and pre/post Git-visible worktree identity.

The adversarial gate proves non-zero exit, unknown command, literal shell metacharacters, timeout, large-output bounding, secret redaction, command side effects and stale Git identity.

See [`docs/VERIFICATION_POLICY_V03.md`](docs/VERIFICATION_POLICY_V03.md).

## V0.4 — read-only GitHub evidence adapter

V0.4 adds remote repository evidence without granting RepoOps GitHub mutation authority.

```text
repository / PR / refs
        ↓
GET-only GitHub REST adapter
        ↓
repo ID + ref/PR identity
changed-file identity
check/status evidence
        ↓
final head recheck
        ↓
COMPLETE | INDETERMINATE
        ↓
separate acceptance authority
```

It records:

- exact `owner/name` plus stable GitHub repository ID;
- PR number/stable PR ID or explicit base/head refs;
- resolved base/head commit SHAs;
- optional issue/work-request identity;
- changed paths plus a deterministic SHA-256 identity over bounded file metadata;
- check runs and commit-status contexts without promoting failure/pending states;
- optional required-check evidence;
- explicit scope violations;
- final stale-head/base recheck;
- deterministic evidence receipt identity.

`COMPLETE` means the declared observation completed. It **does not** mean `ACCEPTED`, correct or safe to merge. A failing check can be complete evidence; a missing required check or moved head becomes `INDETERMINATE`.

```bash
GITHUB_TOKEN=... repoops-github \
  --repository owner/repo \
  --pr 123 \
  --expected-head <sha> \
  --out github-evidence.json
```

The token is optional for public repositories, is never written to the receipt, and the production transport exposes GET only. CI runs a live read-only observation of its own PR using explicit read permissions and `persist-credentials: false`.

See [`docs/GITHUB_EVIDENCE_V04.md`](docs/GITHUB_EVIDENCE_V04.md).

## Evidence model

RepoOps deliberately uses different evidence types for different authority surfaces:

- `repoops.receipt.v0` — synthetic bounded acceptance evidence;
- `repoops.git-receipt.v0.2` — real local Git mutation/acceptance evidence;
- `repoops.verification-receipt.v0.3` — policy-bounded command verification evidence;
- `repoops.github-evidence.v0.4` — read-only remote identity/check evidence.

**`VERIFIED` is not `ACCEPTED`, and `COMPLETE` is not `ACCEPTED`.** Evidence can support acceptance; it does not own acceptance.

Receipt digests identify bounded evidence payloads. They are not signatures and do not prove repository-wide correctness.

## What RepoOps still does not claim

- arbitrary user shell or request-supplied executables/argv;
- process-tree sandboxing or daemon supervision;
- package installation/network-capable commands in the default verification policy;
- GitHub issue/PR mutation;
- remote approval authentication;
- auto-commit or auto-merge;
- model planning quality;
- autonomous software engineering;
- production readiness;
- repository-wide correctness from a narrow request contract.

Those surfaces require their own gates and negative controls.

## Design principles

- Evidence before completion claims.
- Authority is explicit and scoped.
- Planning, execution, verification, remote observation and acceptance are separate responsibilities.
- A model may recommend; it does not own acceptance.
- A command may verify; it does not own acceptance.
- GitHub may report state; it does not own acceptance.
- Failure and indeterminate states are first-class outputs.
- The core path runs without a paid model key.
- New authority surfaces arrive only with executable adversarial controls.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and the canonical roadmap in issue #2.

## Development

```bash
python -m pip install -e ".[dev]"
python -m compileall src tools
python -m pytest -q
python -m ruff check src tests tools
python -m ruff format --check src tests tools
python -m mypy src
repoops-verify . fixtures/verification-v03-default.json
```

CI executes V0–V0.4 positive/negative controls, performs the live read-only GitHub identity probe on pull requests and uploads machine-readable receipts.

## Security

See [`SECURITY.md`](SECURITY.md). V0.4 does not expose a GitHub write transport. CI GitHub permissions are explicit read-only permissions.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Licence

Apache-2.0.
