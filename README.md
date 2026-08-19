# RepoOps

Evidence-driven software maintenance with bounded authority and verifiable completion.

RepoOps is an open-source engineering project exploring a simple but strict idea:

> a system that changes code must not be allowed to certify its own success without independent evidence.

The first vertical slice is intentionally narrow: a work request becomes a plan, a frozen acceptance contract, a bounded repository mutation and an evidence receipt with explicit `ACCEPTED`, `REJECTED` or `INDETERMINATE` semantics.

## Status

Early public foundation. The V0 implementation is being built in small, reviewable increments with deterministic offline fixtures and negative controls.

## Design principles

- Evidence before completion claims.
- Authority is explicit and scoped.
- Planning, execution, verification and acceptance are separate responsibilities.
- A model may recommend; it does not own acceptance.
- Failure and indeterminate states are first-class outputs.
- The core path must run without a paid model key.

## V0 target

```text
work request
    ↓
plan
    ↓
acceptance contract
    ↓
bounded mutation
    ↓
tests + diff + scope evidence
    ↓
evidence receipt
    ↓
ACCEPTED | REJECTED | INDETERMINATE
```

The repository will not claim autonomous software-engineer capability, arbitrary shell authority or production readiness beyond the mechanisms that are actually implemented and tested.

## Licence

Apache-2.0 planned for the public V0. Licence file will be added with the first implementation PR.
