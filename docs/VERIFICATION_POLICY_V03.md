# Verification command policy V0.3

RepoOps V0.3 introduces command execution as an explicit authority surface. The design goal is not to become a shell agent. It is to collect bounded, attributable verification evidence without allowing a request to construct arbitrary process execution.

## Core rule

A verification request selects a **stable command ID** from a trusted registry.

```text
request
  commands: ["repoops.pytest", "repoops.mypy"]
        ↓
trusted command registry
        ↓
exact argv + timeout + output bound + env allowlist
        ↓
process with shell=False
        ↓
stdout/stderr evidence + exit outcome
        ↓
pre/post Git-visible worktree identity
        ↓
VERIFIED | FAILED | INDETERMINATE
```

The request cannot provide an arbitrary executable, shell string or appended arguments.

## Default registry

V0.3 deliberately ships only read-oriented self-verification definitions:

- `repoops.pytest`
- `repoops.ruff-check`
- `repoops.ruff-format-check`
- `repoops.mypy`

Each definition has a version, exact `argv`, timeout, maximum preview size and environment allowlist. The complete definition is SHA-256 identified in the command evidence.

Adding a new command therefore changes policy and should be reviewed like code. It is not a runtime prompt decision.

## No shell expansion

Commands are started with `shell=False` and an argv list. A token such as:

```text
; touch marker
```

is passed as literal process data when it appears in a trusted definition. It is not interpreted by a shell. An executable control proves this behaviour.

This does **not** mean every executable is safe merely because `shell=False` is used. The registry remains the authority boundary.

## Freshness and worktree binding

Before command execution V0.3 records:

- Git repository root;
- exact `HEAD`;
- Git-visible changed paths;
- complete unified worktree diff SHA-256.

A plan may additionally require an exact expected base `HEAD` and/or expected worktree-diff digest. A mismatch becomes `INDETERMINATE` and no command is executed.

After commands finish, RepoOps captures the Git-visible diff again. If the digest changed, the aggregate verification becomes `INDETERMINATE` even when every command exited zero. Verification commands are not silently allowed to mutate the evidence target.

The worktree-side-effect check is intentionally **Git-visible**. Ignored filesystem artefacts are outside this V0.3 claim.

## Output bounding without losing stream identity

Stdout and stderr are sent to temporary files rather than collected without a bound in process memory.

For each stream RepoOps records:

- SHA-256 of the complete captured byte stream;
- a bounded UTF-8 preview;
- whether the preview was truncated.

The executable large-output control proves that a 4 KiB stream can have a 32-byte preview while its SHA-256 still identifies the complete captured stream.

The digest identifies bytes. It is not a signature or proof that the command was semantically correct.

## Environment policy and secret redaction

A command definition contains an explicit environment-key allowlist. The child does not automatically inherit the full parent environment.

Evidence redacts values for environment keys whose names look secret-bearing, including token, secret, password, API-key, private-key, credential and auth patterns. The same exact values are removed from argv evidence and stdout/stderr previews when encountered.

The secret-redaction control proves that a child can consume a token-like environment value while the raw value is absent from the JSON receipt and preview.

Raw stream SHA-256 is calculated over the captured bytes before preview redaction. This preserves stream identity without embedding the secret value itself in the receipt.

### Important limitation

Redaction is a defence-in-depth evidence rule, not a general data-loss-prevention claim. A secret transformed by the child before printing may no longer match the original value and therefore may not be recognised by exact-value replacement. Secret-bearing commands should not be added casually to the registry.

## Timeout semantics

Every command definition has a positive timeout. On timeout the direct child process is killed and the command outcome becomes `TIMEOUT`; the aggregate verification becomes `INDETERMINATE`.

V0.3 does not claim descendant-process-tree containment or daemon supervision. Background/daemon commands are outside the default policy and current claim boundary.

## Outcomes

### Command outcome

- `PASS` — process exited `0` within the bound.
- `FAIL` — process exited non-zero.
- `TIMEOUT` — the direct child exceeded its timeout.
- `REJECTED` — requested command ID was not in policy; no process was created for it.
- `ERROR` — bounded execution evidence could not be produced safely.

### Aggregate verification outcome

- `VERIFIED` — all resolved commands passed and the Git-visible worktree identity remained unchanged.
- `FAILED` — at least one command failed or was rejected and no stronger indeterminate condition occurred.
- `INDETERMINATE` — timeout/error, stale precondition or command-induced Git-visible worktree mutation prevents a safe verification claim.

## `VERIFIED` is not `ACCEPTED`

This distinction is architectural, not wording.

A command can prove that a declared check ran and returned a particular result. It cannot decide by itself that the requested product change is acceptable, inside authority, correctly scoped or ready to merge.

RepoOps therefore keeps V0.3 `VerificationReceipt` separate from the V0/V0.2 delivery acceptance receipts. A later orchestration layer may consume both forms of evidence, but it must preserve independent acceptance ownership.

## Executable controls

The V0.3 test/CI gate proves:

1. a deterministic allowed command produces stable evidence on an identical baseline;
2. non-zero exit becomes `FAIL`/`FAILED`;
3. an unknown command is `REJECTED` without process execution;
4. shell metacharacters remain literal argv data;
5. timeout becomes explicit `TIMEOUT`/`INDETERMINATE`;
6. oversized output has bounded preview plus complete-stream digest;
7. a secret-like environment value is redacted from receipt and preview;
8. a zero-exit command that changes Git-visible state makes verification `INDETERMINATE`;
9. stale expected Git identity blocks command execution;
10. the default CLI registry passes the repository's own pytest/Ruff/mypy gate in CI.

## Non-goals

V0.3 does not provide:

- arbitrary shell access;
- request-supplied executables or extra argv;
- package installation by default;
- network-capable commands in the default registry;
- privileged execution;
- process-tree sandboxing;
- background daemon management;
- GitHub mutation;
- commit or merge authority;
- repository-wide correctness certification.
