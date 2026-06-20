#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# ///
"""Validate a write-commit-msg house-style commit message.

Reads a commit message from stdin or a file, checks it against the
write-commit-msg style rules (header shape, type allowlist, scope regex,
summary/body word limits, forbidden AI/bot attribution), and reports.

Exit codes:
  0  message is valid
  1  message is invalid (details below)
  2  usage error (bad flag or unreadable file)

Output:
  stdout always contains a single-line JSON object:
    {"ok": true}
    {"ok": false, "errors": [{"code": "...", "message": "...", "fix": "..."}]}
  stderr (only on failure) contains a human-readable bullet list.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import List, Dict

ALLOWED_TYPES = (
    "feat", "fix", "impr", "docs", "chore", "test",
    "build", "ci", "style", "revert", "perf", "refactor",
)

SCOPE_RE = re.compile(r"^[a-z0-9][a-z0-9._/-]*$")
HEADER_RE = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[^()\s]+)\))?: (?P<summary>.+)$")

AI_PATTERNS = (
    re.compile(
        r"\b(?:claude|anthropic|chatgpt|openai|copilot|cursor|gemini|sonnet|opus|"
        r"haiku|llama|mistral|deepseek|qwen)\b",
        re.I,
    ),
    re.compile(r"\bgpt-?\d", re.I),
    re.compile(
        r"co-?authored-by:\s*"
        r"(?:claude|gpt|chatgpt|copilot|bot|ai|llm|gemini|sonnet|opus|haiku)",
        re.I,
    ),
    re.compile(
        r"\b(?:generated|written|authored|assisted)\s+(?:by|with)\s+"
        r"(?:an?\s+)?"
        r"(?:ai|claude|gpt|copilot|bot|llm|model|assistant|gemini|coding\s+agent)\b",
        re.I,
    ),
    re.compile(r"\bAI\s+(?:assistant|agent)\b", re.I),
    re.compile(r"\bcoding\s+agent\b", re.I),
)


def word_count(text: str) -> int:
    return len(text.split())


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="validate.py",
        description="Validate a write-commit-msg house-style commit message.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exit codes:\n"
            "  0  message is valid\n"
            "  1  message is invalid (see stdout JSON / stderr bullets)\n"
            "  2  usage error\n\n"
            "Examples:\n"
            "  uv run scripts/validate.py < MSG\n"
            "  uv run scripts/validate.py --summary-max 10 --file MSG\n"
        ),
    )
    parser.add_argument(
        "--summary-max", type=int, default=8, metavar="N",
        help="max words in the summary (default: 8)",
    )
    parser.add_argument(
        "--body-max", type=int, default=30, metavar="N",
        help="max words in the description body (default: 30)",
    )
    parser.add_argument(
        "--file", default="-", metavar="PATH",
        help='read message from PATH; "-" means stdin (default)',
    )
    return parser.parse_args(argv)


def read_message(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError as exc:
        sys.stderr.write(f"validate.py: cannot read {path}: {exc}\n")
        sys.exit(2)


def validate(msg: str, summary_max: int, body_max: int) -> List[Dict[str, str]]:
    errors: List[Dict[str, str]] = []

    if not msg.strip():
        errors.append({
            "code": "empty",
            "message": "empty commit message",
            "fix": "write a non-empty message before piping into the validator",
        })
        return errors

    lines = msg.split("\n")
    header = lines[0]
    match = HEADER_RE.match(header)
    if not match:
        errors.append({
            "code": "header_malformed",
            "message": "first line must match `<type>[(scope)]: <summary>`",
            "fix": "rewrite the first line as e.g. `feat(api): added thing`",
        })
    else:
        type_ = match.group("type")
        scope = match.group("scope")
        summary = match.group("summary")
        if type_ not in ALLOWED_TYPES:
            errors.append({
                "code": "type_disallowed",
                "message": f"type `{type_}` is not allowed",
                "fix": f"use one of: {', '.join(ALLOWED_TYPES)}",
            })
        if scope is not None and not SCOPE_RE.match(scope):
            errors.append({
                "code": "scope_invalid",
                "message": (
                    f"scope `{scope}` must be lowercase letters/digits with only "
                    "`-`, `_`, `.`, `/` separators"
                ),
                "fix": "rename the scope to use only [a-z0-9._/-]",
            })
        sw = word_count(summary)
        if sw > summary_max:
            errors.append({
                "code": "summary_too_long",
                "message": f"summary has {sw} words (max {summary_max})",
                "fix": f"shorten the summary, or pass --summary-max {sw}",
            })

    if len(lines) >= 2 and lines[1].strip():
        errors.append({
            "code": "missing_blank_line",
            "message": "second line must be empty",
            "fix": "insert a blank line between the summary and the description",
        })

    if len(lines) >= 3:
        body = "\n".join(lines[2:])
        if body.strip():
            bw = word_count(body)
            if bw > body_max:
                errors.append({
                    "code": "body_too_long",
                    "message": f"body has {bw} words (max {body_max})",
                    "fix": f"shorten the description, or pass --body-max {bw}",
                })

    for pat in AI_PATTERNS:
        m = pat.search(msg)
        if m:
            errors.append({
                "code": "ai_attribution",
                "message": f"AI/bot attribution detected: `{m.group(0)}`",
                "fix": "remove all references to AI tools, models, or coding agents",
            })
            break

    return errors


def main(argv=None) -> int:
    args = parse_args(argv)
    msg = read_message(args.file)
    errors = validate(msg, args.summary_max, args.body_max)
    if errors:
        json.dump({"ok": False, "errors": errors}, sys.stdout)
        sys.stdout.write("\n")
        sys.stderr.write("commit message validation failed:\n")
        for err in errors:
            sys.stderr.write(f"  - {err['message']}\n")
        return 1
    json.dump({"ok": True}, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
