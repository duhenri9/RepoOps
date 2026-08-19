"""RepoOps command-line interface."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from repoops.engine import execute_fixture


def _load_fixture(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("fixture must be a JSON object")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path, help="Path to a RepoOps V0 JSON fixture")
    parser.add_argument("--out", type=Path, help="Optional path for the evidence receipt")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    receipt = execute_fixture(_load_fixture(args.fixture))
    rendered = json.dumps(receipt.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if receipt.outcome.value == "ACCEPTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
