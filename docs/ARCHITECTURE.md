# RepoOps V0 architecture

RepoOps separates five responsibilities that are often collapsed in coding-agent systems:

```text
request
  ↓
planning/recommendation
  ↓
mutation authority
  ↓
execution
  ↓
verification
  ↓
acceptance
```

V0 implements the last four responsibilities over a deterministic synthetic repository fixture. A future model planner can be added without changing who owns acceptance.

## Acceptance ownership

The executor cannot declare its own work complete. `execute_fixture` derives the final state from independent contract evidence:

- requested mutation paths must be explicitly allowlisted;
- every mutation must match its declared pre-state;
- required checks execute after the mutation attempt;
- any scope violation forces `REJECTED`;
- stale/missing pre-state forces `INDETERMINATE`;
- only a clean scope and all passing checks can produce `ACCEPTED`.

## Why an in-memory repository first

The first gate isolates the acceptance mechanism from Git, GitHub, shell execution and LLM-provider behaviour. This makes the evidence semantics deterministic and easy to falsify with negative controls.

The next adapter layer will map a real Git worktree into the same contract without moving acceptance authority into Git or an LLM.

## Evidence receipt

Each receipt records:

- schema and request id;
- bounded outcome;
- changed paths;
- scope violations;
- check evidence;
- before/after repository SHA-256 digests;
- explicit claim boundary;
- deterministic receipt SHA-256.

The digest is an integrity identifier for the receipt payload, not a signature or proof of repository correctness.

## Threat/authority model

V0 explicitly protects against three failure classes:

1. **false completion** — a visible check passes while an unauthorised file was also touched;
2. **stale execution** — an operation was prepared for a repository state that no longer exists;
3. **unsupported verification** — unknown checks fail closed instead of being silently ignored.

V0 does not run arbitrary shell commands and does not access external repositories. Those are future authority surfaces and require their own policy contract.
