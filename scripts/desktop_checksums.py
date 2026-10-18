"""Generate a deterministic checksum manifest for the actual release assets."""

import hashlib
from pathlib import Path
import re
import sys


def manifest(root: Path) -> str:
    files = sorted(p for p in root.iterdir() if p.suffix in {".dmg", ".zip", ".exe"})
    if not files:
        raise ValueError("NO_DESKTOP_INSTALLERS")
    source = root / "SOURCE_COMMIT.txt"
    if source.is_symlink() or not re.fullmatch(r"[a-f0-9]{40}\n?", source.read_text()):
        raise ValueError("INVALID_SOURCE_COMMIT")
    rows = []
    for path in sorted([*files, source]):
        if path.is_symlink() or not re.fullmatch(r"[A-Za-z0-9_.-]+", path.name):
            raise ValueError("INVALID_RELEASE_ASSET")
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        rows.append(f"{digest}  {path.name}\n")
    return "".join(rows)


if __name__ == "__main__":
    directory = Path(sys.argv[1])
    (directory / "SHA256SUMS.txt").write_text(
        manifest(directory), encoding="utf-8", newline="\n"
    )
