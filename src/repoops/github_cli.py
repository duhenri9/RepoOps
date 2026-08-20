"""CLI for RepoOps V0.4 read-only GitHub evidence collection."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from repoops.github_adapter import collect_github_evidence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, help="GitHub repository in owner/name form")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--pr", type=int, help="Pull request number to observe")
    target.add_argument("--refs", action="store_true", help="Observe explicit base/head branch refs")
    parser.add_argument("--base-ref", help="Base branch when --refs is used")
    parser.add_argument("--head-ref", help="Head branch when --refs is used")
    parser.add_argument("--issue", type=int, help="Optional issue/work-request identity")
    parser.add_argument("--expected-repository-id", type=int)
    parser.add_argument("--expected-head", dest="expected_head_sha")
    parser.add_argument("--allowed-path", action="append", default=[])
    parser.add_argument("--required-check", action="append", default=[])
    parser.add_argument("--request-id", default="repoops-github-v04")
    parser.add_argument("--out", type=Path, help="Optional JSON receipt path")
    return parser


def _plan(args: argparse.Namespace) -> dict[str, Any]:
    if args.refs and (not args.base_ref or not args.head_ref):
        raise ValueError("--refs requires --base-ref and --head-ref")
    payload: dict[str, Any] = {
        "request_id": args.request_id,
        "repository": args.repository,
        "allowed_paths": list(args.allowed_path),
        "required_checks": list(args.required_check),
    }
    if args.pr is not None:
        payload["pull_request"] = args.pr
    else:
        payload["base_ref"] = args.base_ref
        payload["head_ref"] = args.head_ref
    if args.issue is not None:
        payload["issue"] = args.issue
    if args.expected_repository_id is not None:
        payload["expected_repository_id"] = args.expected_repository_id
    if args.expected_head_sha:
        payload["expected_head_sha"] = args.expected_head_sha
    return payload


def main() -> int:
    args = build_parser().parse_args()
    try:
        receipt = collect_github_evidence(_plan(args), token=os.environ.get("GITHUB_TOKEN"))
    except ValueError as error:
        raise SystemExit(str(error)) from error
    rendered = json.dumps(receipt.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if receipt.outcome.value == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
