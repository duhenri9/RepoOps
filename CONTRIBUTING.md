# Contributing

RepoOps welcomes small, evidence-backed contributions.

## Before opening a PR

1. Keep the change inside one clear problem statement.
2. State the claim your change is intended to support.
3. Add or update a negative control when the change creates a new failure mode.
4. Run the same gates as CI:

```bash
python -m pip install -e ".[dev]"
python -m compileall src
python -m pytest -q
python -m ruff check src tests
python -m ruff format --check src tests
python -m mypy src
```

5. Do not weaken an acceptance criterion merely to make a test pass.

## Design rule

Planning, mutation authority, execution, verification and acceptance are separate responsibilities. A contribution that collapses these boundaries should include an explicit architecture rationale and adversarial tests.

## Fixtures

Synthetic fixtures are intentionally public and deterministic. Do not submit customer repositories, private code, access tokens, production logs or other sensitive material as test data.

## Claims

Describe exactly what a mechanism proves and what remains unsupported. Avoid words such as `safe`, `secure`, `correct`, `production-ready` or `autonomous` unless the PR contains bounded evidence for that claim.
