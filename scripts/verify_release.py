from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def verify(directory: Path, checksum_file: Path) -> list[str]:
    root = directory.expanduser().resolve()
    failures: list[str] = []
    for number, line in enumerate(checksum_file.read_text(encoding="ascii").splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split(None, 1)
        if len(parts) != 2 or len(parts[0]) != 64:
            failures.append(f"line {number}: malformed checksum entry")
            continue
        expected, name = parts[0].casefold(), parts[1].strip().lstrip("*")
        target = (root / name).resolve()
        if root not in target.parents or not target.is_file():
            failures.append(f"line {number}: missing or unsafe artifact {name}")
            continue
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if digest != expected:
            failures.append(f"line {number}: checksum mismatch for {name}")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify PlexMuxy release assets against SHA256SUMS.txt")
    parser.add_argument("directory", type=Path)
    parser.add_argument("--checksums", type=Path)
    args = parser.parse_args()
    checksums = args.checksums or args.directory / "SHA256SUMS.txt"
    failures = verify(args.directory, checksums)
    if failures:
        raise SystemExit("\n".join(failures))
    print("All release artifact checksums are valid.")


if __name__ == "__main__":
    main()
