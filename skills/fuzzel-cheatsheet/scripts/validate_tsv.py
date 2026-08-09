#!/usr/bin/env python3
"""Validate a fuzzel-cheatsheet TSV file.

Fails loud on schema violations; warns on missing provenance. Exits 0 on success.

Schema: category<TAB>key<TAB>description[<TAB>command]
Lines starting with '#' are comments (provenance); blank lines are ignored.
"""
import argparse
import re
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a cheatsheet TSV.")
    parser.add_argument("tsv", help="path to the .tsv file")
    args = parser.parse_args()

    path = Path(args.tsv)
    if not path.is_file():
        print(f"[ERROR] not a file: {path}", file=sys.stderr)
        return 1

    errors: list[str] = []
    entries = 0
    categories: set[str] = set()
    has_provenance = False

    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        if raw.lstrip().startswith("#"):
            if re.match(r"\s*#\s*(source|version)\s*:", raw, re.IGNORECASE):
                has_provenance = True
            continue

        fields = raw.split("\t")
        if len(fields) < 3:
            errors.append(
                f"line {lineno}: expected >=3 tab-separated fields, got {len(fields)} "
                f"(use real TABs, not spaces): {raw!r}"
            )
            continue

        category, key, desc = fields[0].strip(), fields[1].strip(), fields[2].strip()
        if not key:
            errors.append(f"line {lineno}: empty key field: {raw!r}")
        if not desc:
            errors.append(f"line {lineno}: empty description field: {raw!r}")
        if not category:
            errors.append(f"line {lineno}: empty category field: {raw!r}")
        # Guard against the common mistake of spaces instead of tabs.
        if "\t" not in raw:
            errors.append(
                f"line {lineno}: no TAB separator found (did you use spaces?): {raw!r}"
            )

        if key and desc and category:
            entries += 1
            categories.add(category)

    if entries == 0:
        errors.append("no valid data entries found")

    if errors:
        print(f"[FAIL] {path} — {len(errors)} problem(s):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    if not has_provenance:
        print(
            f"[WARN] {path}: no '# source:' or '# version:' provenance comment — "
            "confirm data matches the installed app version.",
            file=sys.stderr,
        )

    print(f"[OK] {path}: {entries} entries, {len(categories)} categor(y/ies).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
