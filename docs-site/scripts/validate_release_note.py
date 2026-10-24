from __future__ import annotations

import re
import sys
from pathlib import Path


TAG_PATTERN = re.compile(r"agents-v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")
RELEASE_DIRECTORY = (
    Path(__file__).resolve().parents[2] / "docs-site" / "cms" / "release-notes"
)


def validate_release_note(tag: str, release_directory: Path = RELEASE_DIRECTORY) -> Path:
    if TAG_PATTERN.fullmatch(tag) is None:
        raise ValueError(f"Invalid agent release tag: {tag!r}")

    note_path = release_directory / f"{tag}.md"
    if not note_path.is_file():
        raise ValueError(f"Add {note_path.as_posix()} before publishing this release.")

    content = note_path.read_text(encoding="utf-8")
    if re.search(r"(?m)^#\s+\S", content) is None:
        raise ValueError(f"{note_path.as_posix()} needs a title.")

    summary = next(
        (
            line.strip()
            for line in content.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ),
        "",
    )
    if len(summary) < 20:
        raise ValueError(f"{note_path.as_posix()} needs a useful summary.")
    return note_path


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: validate_release_note.py agents-vMAJOR.MINOR.PATCH", file=sys.stderr)
        return 2
    try:
        note_path = validate_release_note(sys.argv[1])
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    print(f"Validated release documentation: {note_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
