"""CLI for RepoOps V0.3 policy-bounded verification commands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from repoops.verification import execute_verification_plan


def _load_plan(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("verification plan must be a JSON object")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path, help="Path inside the target local Git worktree")
    parser.add_argument("plan", type=Path, help="Path to a RepoOps V0.3 verification plan")
    parser.add_argument("--out", type=Path, help="Optional path for the verification receipt")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    receipt = execute_verification_plan(args.repository, _load_plan(args.plan))
    rendered = json.dumps(receipt.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if receipt.outcome.value == "VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
