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
independent scope + freshness + behavioural evidence
    ↓
evidence receipt
    ↓
ACCEPTED | REJECTED | INDETERMINATE
```

Planning, mutation, verification and acceptance are deliberately separate responsibilities. Git, GitHub or a model can provide inputs or mechanisms; none of them silently owns the completion claim.

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

### V0.2 negative controls

CI proves that:

- a dirty worktree becomes `INDETERMINATE` before mutation;
- an out-of-scope requested path is rejected before mutation;
- `../` path escape cannot touch a file outside the repository;
- stale expected-before identity becomes `INDETERMINATE`;
- a deliberately failing post-change check returns `REJECTED` and restores the worktree;
- rename/delete/binary edge cases remain inside the same evidence model.

See [`docs/GIT_WORKTREE_V02.md`](docs/GIT_WORKTREE_V02.md).

## Evidence model

V0 emits `repoops.receipt.v0` for the synthetic runtime.

V0.2 emits `repoops.git-receipt.v0.2` with:

- request id and outcome;
- exact base `HEAD`;
- dirty-state evidence;
- actual changed paths and scope violations;
- independent check evidence;
- complete unified diff + SHA-256;
- rollback/restoration state;
- explicit claim boundary;
- deterministic receipt SHA-256.

Receipt digests identify the bounded evidence payload. They are not signatures and do not prove repository-wide correctness.

## What RepoOps still does not claim

- arbitrary verification-command execution;
- GitHub issue/PR mutation;
- remote authority/authentication;
- auto-merge;
- model planning quality;
- autonomous software engineering;
- production readiness;
- repository-wide correctness from a narrow request contract.

Those surfaces require their own gates and negative controls.

## Design principles

- Evidence before completion claims.
- Authority is explicit and scoped.
- Planning, execution, verification and acceptance are separate responsibilities.
- A model may recommend; it does not own acceptance.
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
```

CI executes both V0 and V0.2 positive/negative controls and uploads machine-readable receipts.

## Security

See [`SECURITY.md`](SECURITY.md). V0.2 never executes request-supplied shell commands, commits, pushes or contacts a remote.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Licence

Apache-2.0.
