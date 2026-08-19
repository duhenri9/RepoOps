# Git worktree adapter V0.2

RepoOps V0.2 moves one layer outward from the deterministic in-memory V0 and proves that the same bounded authority/acceptance model can observe and mutate a **real local Git worktree** without turning Git itself into the acceptance authority.

## Boundary

The adapter:

- requires an existing local Git repository with a valid `HEAD`;
- requires the real index and worktree to be clean before mutation;
- captures the exact base `HEAD`;
- accepts only explicit repository-relative allowed paths;
- rejects absolute paths, `..`, `.git` and symlink write targets;
- supports bounded text replacement, deletion and rename;
- supports SHA-256 preconditions/checks for binary files;
- snapshots every touched path before mutation;
- generates real Git name-status and unified diff evidence using a **temporary index**;
- never stages the user's real index;
- rolls back its touched-path snapshots if post-mutation checks reject the attempt;
- leaves accepted changes uncommitted for an external reviewer/authority.

It does **not**:

- commit, push, fetch or contact a remote;
- execute request-supplied shell commands;
- decide merge authority;
- authenticate an approver;
- certify repository-wide correctness;
- replace the V0 acceptance engine with Git exit codes.

## Why a temporary index matters

`git diff HEAD` alone does not provide complete evidence for all untracked/renamed worktree changes. Staging into the user's real index would itself create a new authority/mutation surface.

V0.2 therefore creates a temporary `GIT_INDEX_FILE`, loads `HEAD` into it, stages the current worktree into that temporary index, and reads:

```text
git diff --cached --name-status -z --find-renames HEAD --
git diff --cached --binary --no-color --find-renames HEAD --
```

The real index remains unchanged.

## Outcome semantics

### `ACCEPTED`

- worktree was clean at start;
- all operation preconditions matched;
- every actual changed path was inside `allowed_paths`;
- every declared post-change check passed;
- the accepted changes remain uncommitted in the worktree.

### `REJECTED`

Examples:

- an operation requested a path outside bounded authority;
- a path attempted to escape the repository root;
- a post-change check failed;
- Git's actual changed-path evidence contained a path outside authority.

If mutation had already occurred before a rejection, V0.2 restores the captured touched-path snapshots and records `worktree_restored=true`.

### `INDETERMINATE`

Examples:

- worktree/index was already dirty;
- an expected-before identity did not match;
- repository/HEAD identity could not be established;
- Git evidence could not be collected safely;
- a targeted text file was non-UTF-8 without an explicit SHA-256 precondition.

RepoOps does not convert missing freshness/evidence into success.

## Binary edge case

V0.2 does not pretend arbitrary binary mutation is equivalent to text replacement. Binary files can be safely bounded for rename/delete using `expected_before_sha256`, and can be verified using a `sha256` check. A later gate can add a separately versioned binary-write contract if there is a real use case.

## Receipt

`repoops.git-receipt.v0.2` records:

- request id;
- acceptance outcome;
- base `HEAD`;
- dirty-state evidence captured before mutation;
- actual changed paths from Git;
- scope violations;
- post-change check evidence;
- complete unified diff;
- unified-diff SHA-256;
- whether a rejected/failed attempt was restored;
- explicit claim boundary;
- deterministic receipt SHA-256.

The receipt digest identifies the evidence payload. It is not a signature and is not proof that the whole repository is correct.

## CLI

```bash
repoops-git /path/to/local/repository fixtures/git-v02-accepted.json --out receipt.json
```

Accepted outcomes return `0`. `REJECTED` and `INDETERMINATE` return `2`.

## Executable controls

CI proves against real temporary Git repositories:

1. accepted text replacement + delete + text rename + binary rename;
2. dirty worktree fails closed before mutation;
3. out-of-scope operation is rejected before mutation;
4. parent-directory path escape is rejected and cannot touch the outside file;
5. failed post-change acceptance rolls the touched worktree back to clean state;
6. stale pre-state is `INDETERMINATE`;
7. the same fixed Git baseline + plan produces the same evidence receipt.
