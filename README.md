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
independent acceptance
    ↓
ACCEPTED | REJECTED | INDETERMINATE
```

Planning, mutation, verification and acceptance are deliberately separate responsibilities. Git, a verification process, GitHub or a model can provide inputs or mechanisms; none of them silently owns the completion claim.

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

V0.3 records:

- command ID + definition version + definition SHA-256;
- exact argv evidence;
- timeout and exit outcome;
- SHA-256 of complete captured stdout/stderr byte streams;
- bounded output previews plus explicit truncation state;
- allowlisted environment evidence with secret-like values redacted;
- exact base `HEAD` and Git-visible changed paths;
- pre/post unified worktree-diff SHA-256;
- whether verification left Git-visible worktree state unchanged;
- deterministic command/receipt identities where the underlying evidence is deterministic.

### V0.3 adversarial controls

The executable gate proves:

- a deterministic allowed command can produce stable evidence on the same baseline;
- non-zero exit becomes `FAIL`, never success;
- an unknown/disallowed ID is rejected before process creation;
- shell metacharacters remain literal argv data because no shell expansion is used;
- timeout is explicit and aggregate verification becomes `INDETERMINATE`;
- oversized output is preview-bounded while the complete captured stream still has a digest;
- a token-like environment value can be consumed by the child without appearing raw in receipt/preview evidence;
- a zero-exit command that changes Git-visible worktree state makes verification `INDETERMINATE`;
- stale expected Git identity blocks command execution.

See [`docs/VERIFICATION_POLICY_V03.md`](docs/VERIFICATION_POLICY_V03.md).

## Evidence model

RepoOps deliberately uses different evidence types for different authority surfaces:

- `repoops.receipt.v0` — synthetic bounded acceptance evidence;
- `repoops.git-receipt.v0.2` — real local Git mutation/acceptance evidence;
- `repoops.verification-receipt.v0.3` — policy-bounded command verification evidence.

**`VERIFIED` is not `ACCEPTED`.** A command result can support acceptance; it does not own acceptance.

Receipt digests identify bounded evidence payloads. They are not signatures and do not prove repository-wide correctness.

## What RepoOps still does not claim

- arbitrary user shell or request-supplied executables/argv;
- process-tree sandboxing or daemon supervision;
- package installation/network-capable commands in the default policy;
- GitHub issue/PR mutation;
- remote authority/authentication;
- auto-commit or auto-merge;
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
- A command may verify; it does not own acceptance.
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

CI executes V0, V0.2 and V0.3 positive/negative controls and uploads machine-readable receipts.

## Security

See [`SECURITY.md`](SECURITY.md). V0.3 does not accept request-supplied shell commands and the default command policy contains no network/installation/privileged command surface.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Licence

Apache-2.0.
