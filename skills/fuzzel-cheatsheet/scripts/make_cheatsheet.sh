#!/bin/bash
#
# Reference-only cheatsheet menu — the fuzzel form of the template.
#
# This is a starting point to specialize, not a script to ship as-is. Resolve
# the picker and its version on the target machine first, then keep only the
# flags that build supports; a menu script must call one picker with one set of
# flags. Per-picker flags and their minimum versions:
#   references/menu-and-wiring.md
#
# Requires fuzzel >= 1.12 (--with-nth); MODE=keys additionally needs 1.14
# (--match-nth). On an older fuzzel, drop --with-nth, pipe `cut -f1` into
# fuzzel, and delete MODE along with this note.
#
# Env:
#   DATA    TSV path (required)
#   PROMPT  menu prompt (default: Cheatsheet)
#   WIDTH   menu width % (default: 90)
#   LINES   visible rows (default: 25)
#   MODE    full (default) or keys — 'keys' matches the query against the key
#           column only, so searching 'd' does not hit every description
#           containing the letter d.

# No 'set -e': a picker exits non-zero when the menu is dismissed with Esc,
# which is a normal outcome for a reference menu, not a failure.
set -uo pipefail

DATA="${DATA:?DATA (TSV path) is required}"
PROMPT="${PROMPT:-Cheatsheet}"
WIDTH="${WIDTH:-90}"
LINES="${LINES:-25}"
MODE="${MODE:-full}"

if [ ! -r "$DATA" ]; then
    echo "[ERROR] cheatsheet data not found or unreadable: $DATA" >&2
    exit 1
fi

# Two tab-separated fields per line: the rendered menu line, then the bare key.
# fuzzel displays field 1 (--with-nth=1); MODE=keys points matching at field 2.
match_args=()
[ "$MODE" = keys ] && match_args=(--match-nth=2)

# Reference-only: discard the selection.
awk -F'\t' '
    /^[[:space:]]*#/ { next }
    NF >= 3 { printf "%-13s - %s   (%s)\t%s\n", $2, $3, $1, $2 }
' "$DATA" \
    | fuzzel --dmenu \
        --prompt "$PROMPT" \
        --hide-prompt \
        --width "$WIDTH" \
        --lines "$LINES" \
        --match-mode=fzf \
        --no-sort \
        --with-nth=1 \
        ${match_args[@]+"${match_args[@]}"} \
    >/dev/null

exit 0
