#!/bin/bash
#
# Reference-only fuzzel cheatsheet menu. Copy per app and set DATA.
# See SKILL.md / references/menu-and-wiring.md.
#
# Env:
#   DATA    TSV path (required)
#   PROMPT  menu prompt (default: Cheatsheet)
#   WIDTH   menu width % (default: 90)
#   LINES   visible rows (default: 25)

set -euo pipefail

DATA="${DATA:?DATA (TSV path) is required}"
PROMPT="${PROMPT:-Cheatsheet}"
WIDTH="${WIDTH:-90}"
LINES="${LINES:-25}"

if [ ! -r "$DATA" ]; then
    echo "[ERROR] cheatsheet data not found or unreadable: $DATA" >&2
    exit 1
fi

# Reference-only: discard the selection. Line format is fixed so search keys
# match across apps; keep the fuzzel flags identical in every copy of this
# script so one app's menu never behaves differently from another's.
awk -F'\t' 'NF>=3 && $1 !~ /^#/ { printf "%-13s - %s   (%s)\n", $2, $3, $1 }' "$DATA" \
    | fuzzel --dmenu \
        --prompt "$PROMPT" \
        --hide-prompt \
        --width "$WIDTH" \
        --lines "$LINES" \
        --match-mode=fzf \
        --no-sort \
    >/dev/null

exit 0
