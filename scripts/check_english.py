from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HAN_RANGES = (
    (0x2E80, 0x2EFF),
    (0x2F00, 0x2FDF),
    (0x3005, 0x3007),
    (0x3021, 0x3029),
    (0x3038, 0x303B),
    (0x31C0, 0x31EF),
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0x16FE2, 0x16FE3),
    (0x16FF0, 0x16FF1),
    (0x20000, 0x2EE5F),
    (0x2F800, 0x2FA1F),
    (0x30000, 0x3347F),
)
ESCAPE = re.compile(
    r"\\(?:u\{([0-9a-fA-F]{1,6})\}|u([0-9a-fA-F]{4})|U([0-9a-fA-F]{8}))"
)
BINARY_SUFFIXES = {
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".woff",
    ".woff2",
    ".zip",
}
LOCK_NAMES = {"uv.lock", "package-lock.json"}


def contains_han(text: str) -> bool:
    return any(start <= ord(char) <= end for char in text for start, end in HAN_RANGES)


def maintained(path: Path) -> bool:
    if path.name in LOCK_NAMES or path.suffix.lower() in BINARY_SUFFIXES:
        return False
    if path.parts[0] in {"data", "reports"}:
        return path.name == "README.md"
    return True


def findings(text: str):
    for number, line in enumerate(text.splitlines(), 1):
        if contains_han(line):
            yield number, "Han characters"
            continue
        decoded = ESCAPE.sub(decode_escape, line)
        decoded = decoded.encode("utf-16", "surrogatepass").decode(
            "utf-16", "surrogatepass"
        )
        if contains_han(decoded):
            yield number, "Unicode-escaped Han characters"


def decode_escape(match: re.Match) -> str:
    codepoint = int(next(group for group in match.groups() if group), 16)
    return chr(codepoint) if codepoint <= 0x10FFFF else match.group()


def annotation_escape(value: str) -> str:
    for before, after in (
        ("%", "%25"),
        ("\r", "%0D"),
        ("\n", "%0A"),
        (",", "%2C"),
        (":", "%3A"),
    ):
        value = value.replace(before, after)
    return value


def scan(root: Path) -> int:
    paths = subprocess.check_output(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
    ).split(b"\0")
    failed = False
    count = 0
    for raw in sorted(set(paths) - {b""}):
        path = Path(os.fsdecode(raw))
        if not maintained(path) or not (root / path).is_file():
            continue
        count += 1
        issues = []
        if contains_han(str(path)):
            issues.append((1, "Han characters in file name"))
        try:
            issues.extend(findings((root / path).read_text(encoding="utf-8")))
        except UnicodeError:
            issues.append((1, "Maintained text must use UTF-8"))
        for line, reason in issues:
            failed = True
            name = annotation_escape(str(path))
            print(
                f"::error file={name},line={line},title=English-only policy::{reason}"
            )
    print(
        f"English-only scan: {count} maintained files; {'FAIL' if failed else 'PASS'}"
    )
    return int(failed)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reject Han characters in maintained repository text."
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    return scan(parser.parse_args().root.resolve())


if __name__ == "__main__":
    sys.exit(main())
