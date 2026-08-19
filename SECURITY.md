# Security policy

RepoOps is experimental software that may eventually mediate repository mutations and diagnostic command execution. Treat every authority surface as security-sensitive.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting when available. Do not open a public issue containing live credentials, private repository contents, exploit payloads against third-party systems or other sensitive data.

If private reporting is unavailable, open a minimal public issue asking for a private contact path without including exploit details.

## V0 security boundary

The current V0:

- operates only on synthetic in-memory repository fixtures;
- does not clone or mutate external repositories;
- does not execute arbitrary shell commands;
- does not call model providers;
- does not auto-merge or deploy;
- fails closed on out-of-scope paths and stale pre-state.

Future Git, shell, GitHub and model adapters must preserve the separation between planning, mutation authority, execution, verification and acceptance.

## Not a security certification

A green RepoOps receipt is evidence about one declared acceptance contract. It is not a security review, code audit or proof that a repository is correct or safe.
