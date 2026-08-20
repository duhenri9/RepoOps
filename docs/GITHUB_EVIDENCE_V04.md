# GitHub read/evidence adapter V0.4

RepoOps V0.4 adds a deliberately read-only GitHub boundary. Its job is to observe exact repository/ref/PR/check evidence and preserve uncertainty. It does **not** mutate GitHub and it does not own delivery acceptance.

## Authority boundary

```text
request contract
      ↓
GitHub read adapter
      ↓
repository identity
ref / PR identity
changed-file identity
check + status evidence
stale-state recheck
      ↓
COMPLETE | INDETERMINATE
      ↓
separate acceptance authority
```

`COMPLETE` means only that the declared observation completed without a stale identity, transport failure or required-evidence gap. It does not mean the PR is correct, safe, approved or ready to merge.

## Read-only transport

The production client exposes one transport method: `GET` JSON from `https://api.github.com`.

There is no POST, PATCH, PUT or DELETE method in the V0.4 transport. The CLI reads `GITHUB_TOKEN` only when present and never writes the token into a receipt. CI grants only explicit read permissions:

- `contents: read`
- `checks: read`
- `issues: read`
- `pull-requests: read`
- `statuses: read`

Repository checkout keeps `persist-credentials: false`.

## Identity evidence

A PR observation records:

- requested `owner/name`;
- stable GitHub repository ID;
- pull request number and stable PR ID;
- base ref + resolved SHA;
- head ref + resolved SHA;
- optional issue number + stable issue ID;
- optional expected repository ID;
- optional expected head SHA.

A ref observation records explicit base/head branch refs and resolves both to exact SHAs before comparing them.

A repository-ID or expected-head mismatch makes the observation `INDETERMINATE`.

## Changed-file identity

For a PR the adapter reads the paginated changed-file API. For explicit refs it uses the compare API.

The receipt stores the sorted changed-path set and a SHA-256 identity over bounded per-file metadata:

- current filename;
- previous filename for renames;
- status;
- blob SHA when GitHub provides it;
- additions/deletions/change counts;
- SHA-256 of the patch text when GitHub provides a patch.

The raw patch is not persisted in the V0.4 GitHub receipt. This keeps the evidence small while retaining a reproducible identity for the observed changed-file response.

Pagination is bounded. If configured coverage exceeds the V0.4 bound, the result is `INDETERMINATE` rather than silently partial.

## Scope evidence

A plan can declare exact paths or directory prefixes ending in `/`.

Changed files outside that set are recorded under `scope_violations`. The GitHub adapter still does not convert this into delivery `REJECTED` or `ACCEPTED`; it reports the fact for the separate acceptance layer.

Renames include both the old and new paths in scope evidence.

## Checks and commit statuses

V0.4 reads both GitHub check runs and legacy/commit status contexts for the resolved head SHA.

Each observation is preserved as:

- name;
- source (`check-run:<app>` or `commit-status`);
- raw status;
- raw conclusion where present;
- details/target URL where present;
- normalized evidence state;
- SHA-256 evidence identity.

Normalized states are:

- `PASSING`
- `FAILING`
- `PENDING`
- `UNKNOWN`

The adapter deliberately does not turn a failing check into `INDETERMINATE`: a failing check can be perfectly complete evidence. Likewise, a pending check remains pending. Missing **required** check evidence is different: that means the declared evidence set is incomplete, so the receipt becomes `INDETERMINATE`.

## Stale-state control

PR mode reads the PR identity before collecting files/checks and reads it again afterwards. If base or head SHA moved, `stale=true` and the receipt becomes `INDETERMINATE`.

Ref mode resolves the head ref again after evidence collection and applies the same rule.

This prevents an observation from claiming a stable identity when the evidence was assembled across different heads.

## Deterministic controls

The test suite includes controls for:

1. complete passing evidence with stable receipt identity;
2. failing and pending checks preserved exactly rather than promoted;
3. required-check evidence missing -> `INDETERMINATE`;
4. head moves between first and final observation -> stale + `INDETERMINATE`;
5. wrong repository ID -> `INDETERMINATE`;
6. out-of-scope changed path preserved explicitly without the adapter inventing acceptance;
7. missing API evidence -> `INDETERMINATE`;
8. explicit base/head ref resolution and compare identity;
9. production client exposes no write method.

CI additionally performs a live read-only observation of the PR running the gate. It binds the observed repository ID, PR number and head SHA to the GitHub event values.

## Claim boundary

V0.4 does not:

- create or edit issues;
- create or update pull requests;
- comment or request review;
- commit, push, merge or change refs;
- authenticate human approval authority;
- prove that a check itself is trustworthy;
- prove repository-wide correctness;
- convert `COMPLETE` GitHub evidence into delivery `ACCEPTED`.

Any future GitHub write surface requires a separate gate with exact target identity, expected-head/ref preconditions, minimal permissions and adversarial controls. Auto-merge is explicitly outside the first mutation gate.
