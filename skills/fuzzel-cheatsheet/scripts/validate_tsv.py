#!/usr/bin/env python3
"""Validate a fuzzel-cheatsheet TSV file.

Fails loud on schema violations; warns on missing provenance. Exits 0 on success.

Schema: category<TAB>key<TAB>description[<TAB>command]
Lines starting with '#' are comments (provenance); blank lines are ignored.
"""
import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

# audit_versions.sh reads exactly these two shapes. A line that looks close
# enough to a human but does not parse leaves the sheet unauditable forever,
# so a malformed comment is an error rather than a warning.
SOURCE_RE = re.compile(r"^\s*#\s*source\s*:\s*(\S+)\s+(\d+(?:\.\d+)+)\s*/\s*(\S.*)$", re.I)
CONFIG_RE = re.compile(r"^\s*#\s*config\s*:\s*(\S.*?)\s*@\s*(\d{4}-\d{2}-\d{2})\s*$", re.I)
SOURCE_FORM = "# source: <app> <version> / <where>"
CONFIG_FORM = "# config: <path> @ <YYYY-MM-DD>"

# Placeholders that are meaningful in a config file but useless in a cheatsheet:
# the reader needs the chord they actually press.
PLACEHOLDERS = ("<leader>", "<localleader>", "<prefix>", "$mainmod", "$mod", "mod4")

# A key still carrying a symbolic reference — a DTD entity, a shell expansion,
# an unexpanded token — reads as a chord to the validator and as nonsense to the
# user. The named PLACEHOLDERS above cover the forms seen so far; this catches
# the shape.
UNRESOLVED = re.compile(r"&[\w.-]+;|\$\{[^}]+\}|<[a-z][a-z-]*>")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a cheatsheet TSV.")
    parser.add_argument("tsv", help="path to the .tsv file")
    args = parser.parse_args()

    path = Path(args.tsv)
    if not path.is_file():
        print(f"[ERROR] not a file: {path}", file=sys.stderr)
        return 1

    errors: list[str] = []
    warnings: list[str] = []
    entries = 0
    categories: set[str] = set()
    has_source = False
    has_config = False
    seen: dict[tuple[str, str], int] = {}
    key_categories: defaultdict[str, set[str]] = defaultdict(set)

    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        if raw.lstrip().startswith("#"):
            if re.match(r"\s*#\s*source\s*:", raw, re.IGNORECASE):
                if SOURCE_RE.match(raw):
                    has_source = True
                else:
                    errors.append(
                        f"line {lineno}: provenance comment does not parse; "
                        f"expected '{SOURCE_FORM}' with a bare dotted version: {raw!r}"
                    )
            elif re.match(r"\s*#\s*config\s*:", raw, re.IGNORECASE):
                if CONFIG_RE.match(raw):
                    has_config = True
                else:
                    errors.append(
                        f"line {lineno}: config comment does not parse; "
                        f"expected '{CONFIG_FORM}': {raw!r}"
                    )
            elif re.match(r"\s*#\s*version\s*:", raw, re.IGNORECASE):
                errors.append(
                    f"line {lineno}: '# version:' is not read by the staleness audit; "
                    f"use '{SOURCE_FORM}': {raw!r}"
                )
            continue

        fields = raw.split("\t")
        if len(fields) < 3:
            errors.append(
                f"line {lineno}: expected >=3 tab-separated fields, got {len(fields)} "
                f"(use real TABs, not spaces): {raw!r}"
            )
            continue
        if len(fields) > 4:
            warnings.append(
                f"line {lineno}: {len(fields)} fields — everything past the 4th is "
                f"dropped; a stray TAB in the description is the usual cause: {raw!r}"
            )

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

        lowered = key.lower()
        for placeholder in PLACEHOLDERS:
            if placeholder in lowered:
                warnings.append(
                    f"line {lineno}: key contains the placeholder '{placeholder}' — "
                    f"expand it to the chord actually configured: {key!r}"
                )
                break

        if UNRESOLVED.search(key):
            errors.append(
                f"line {lineno}: key '{key}' contains an unresolved reference — "
                f"resolve it against the source's locale/config files before shipping"
            )

        if key and desc and category:
            # An overlaid custom binding that shadows a default lands here: two
            # rows claim the same key, and only one of them is what the app does.
            previous = seen.get((category, key))
            if previous is not None:
                errors.append(
                    f"line {lineno}: duplicate key {key!r} in category {category!r} "
                    f"(first seen on line {previous}) — the later binding usually "
                    "wins; keep one row"
                )
            else:
                seen[(category, key)] = lineno
            key_categories[key].add(category)
            entries += 1
            categories.add(category)

    for key, cats in sorted(key_categories.items()):
        if len(cats) > 1:
            warnings.append(
                f"key {key!r} appears in {len(cats)} categories "
                f"({', '.join(sorted(cats))}) — fine for different modes, "
                "a conflict otherwise"
            )

    if entries == 0:
        errors.append("no valid data entries found")

    if errors:
        print(f"[FAIL] {path} — {len(errors)} problem(s):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    if not has_source:
        warnings.append(
            f"no '{SOURCE_FORM}' comment — freshness unconfirmed, and the sheet "
            "stays UNKNOWN in the staleness audit"
        )
    if not has_config:
        warnings.append(
            f"no '{CONFIG_FORM}' comment — a later rebind in the user's config "
            "will never be flagged"
        )

    for w in warnings:
        print(f"[WARN] {path}: {w}", file=sys.stderr)

    print(f"[OK] {path}: {entries} entries, {len(categories)} categor(y/ies).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
