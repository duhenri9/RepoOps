# RepoOps

Evidence-driven software maintenance with bounded authority and verifiable completion.

RepoOps is an open-source engineering project built around a strict idea:

> a system that changes code must not be allowed to certify its own success without independent evidence.

## V0

The first executable slice runs entirely offline over deterministic synthetic repositories. It separates mutation authority from acceptance and emits an evidence receipt with explicit `ACCEPTED`, `REJECTED` or `INDETERMINATE` semantics.

```text
work request
    ↓
acceptance contract
    ↓
bounded mutation
    ↓
scope + freshness + behavioural checks
    ↓
evidence receipt
    ↓
ACCEPTED | REJECTED | INDETERMINATE
```

### What V0 proves

- exact allowed-path authority;
- stale-state/precondition detection;
- deterministic in-memory mutation;
- independent post-change checks;
- repository before/after SHA-256 identities;
- deterministic receipt digest;
- a known-bad out-of-scope executor is rejected even when the visible behaviour passes;
- missing/stale evidence becomes `INDETERMINATE`, not a fabricated success.

### What V0 does not prove

- real Git or GitHub mutation;
- arbitrary test-command execution;
- LLM planning quality;
- repository-wide correctness;
- autonomous software engineering;
- production readiness.

## Run it

```bash
python -m pip install -e ".[dev]"
repoops fixtures/accepted.json
```

Prove the failure controls:

```bash
repoops fixtures/rejected-out-of-scope.json
repoops fixtures/indeterminate-stale-state.json
```

Non-accepted outcomes intentionally return exit code `2`.

## Evidence model

A V0 receipt contains:

- schema and request id;
- outcome;
- changed paths and scope violations;
- individual check evidence;
- before/after repository digests;
- explicit claim boundary;
- deterministic receipt SHA-256.

The digest identifies the receipt payload. It is not a digital signature or proof that the whole repository is correct.

## Design principles

- Evidence before completion claims.
- Authority is explicit and scoped.
- Planning, execution, verification and acceptance are separate responsibilities.
- A model may recommend; it does not own acceptance.
- Failure and indeterminate states are first-class outputs.
- The core path runs without a paid model key.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for acceptance ownership and the V0 authority model. The staged Git/GitHub roadmap is tracked in the canonical roadmap issue.

## Development

```bash
python -m compileall src
python -m pytest -q
python -m ruff check src tests
python -m ruff format --check src tests
python -m mypy src
```

CI additionally executes all three control fixtures and uploads their receipts as artifacts.

## Security

See [`SECURITY.md`](SECURITY.md). V0 does not execute arbitrary shell commands, access external repositories or call model providers.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). New authority surfaces or claim types should arrive with adversarial/negative controls.

## Licence

Apache-2.0.
