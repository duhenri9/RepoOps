# Security policy

RepoOps is experimental software that mediates increasingly sensitive repository authority surfaces. Treat every mutation, process-execution and remote-identity boundary as security-sensitive.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting when available. Do not open a public issue containing live credentials, private repository contents, exploit payloads against third-party systems or other sensitive data.

If private reporting is unavailable, open a minimal public issue asking for a private contact path without including exploit details.

## Current security boundary

RepoOps separates four currently implemented surfaces:

- **V0** — deterministic synthetic acceptance evidence;
- **V0.2** — bounded local Git worktree mutation with path authority, freshness checks and rollback;
- **V0.3** — trusted-ID verification commands with exact argv, `shell=False`, timeout, bounded output evidence and environment redaction;
- **V0.4** — read-only GitHub repository/PR/ref/check observation.

### V0.4 GitHub boundary

The production GitHub transport exposes GET only. It does not implement POST, PATCH, PUT or DELETE operations.

The CLI may read `GITHUB_TOKEN` from the environment for authentication. The token is never included in receipts or logs by RepoOps. CI grants explicit read permissions only and keeps checkout credentials non-persistent.

V0.4 fails closed as `INDETERMINATE` when required remote evidence is missing, the expected repository/head identity mismatches, or the observed head/base moves while evidence is being collected.

A failing or pending GitHub check is preserved as failing/pending evidence; RepoOps does not promote it to success. Conversely, a `COMPLETE` GitHub evidence receipt is not delivery acceptance and does not certify that GitHub or a third-party check is trustworthy.

## Explicitly unavailable authority

The current public implementation does not:

- accept arbitrary request-supplied shell commands;
- install packages or run privileged commands in the default verification policy;
- create/edit GitHub issues or pull requests;
- comment, request review or change remote refs;
- commit, push or merge automatically;
- authenticate human approval authority;
- call model providers in the core path;
- claim repository-wide correctness or security certification.

Any future GitHub write surface requires its own gate with exact target identity, expected-head/ref preconditions, minimal permissions and adversarial controls.

## Not a security certification

A green RepoOps receipt is evidence about one declared contract or observation boundary. It is not a security review, code audit or proof that a repository is correct or safe.
