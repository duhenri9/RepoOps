from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BINARY_PAYLOAD = bytes([0, 255, 1, 2])


def git(root: Path, *arguments: str, env: dict[str, str] | None = None) -> None:
    subprocess.run(["git", *arguments], cwd=root, env=env, check=True)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: create_git_fixture_repo.py PATH")
    root = Path(sys.argv[1])
    root.mkdir(parents=True, exist_ok=False)
    (root / "src").mkdir()
    (root / "docs").mkdir()
    (root / "assets").mkdir()
    (root / "src/service.py").write_text("VALUE = 'old'\n", encoding="utf-8")
    (root / "docs/obsolete.md").write_text("obsolete\n", encoding="utf-8")
    (root / "docs/guide-old.md").write_text("guide\n", encoding="utf-8")
    (root / "assets/blob.bin").write_bytes(BINARY_PAYLOAD)
    (root / "README.md").write_text("fixture repository\n", encoding="utf-8")

    git(root, "init", "-q")
    git(root, "config", "user.email", "repoops@example.invalid")
    git(root, "config", "user.name", "RepoOps Fixture")
    git(root, "add", "-A")
    environment = os.environ.copy()
    environment["GIT_AUTHOR_DATE"] = "2026-01-01T00:00:00+00:00"
    environment["GIT_COMMITTER_DATE"] = "2026-01-01T00:00:00+00:00"
    git(root, "commit", "-q", "-m", "fixture baseline", env=environment)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
