#!/bin/bash
#
# Single validation entry point for a cheatsheet. Run it after writing the TSV
# (data only) and again after wiring the hotkey (everything).
#
# USAGE:
#   validate.sh <file.tsv> [menu-script.sh]
#
# Checks (a check whose input is absent is skipped, never silently dropped):
#   tsv     schema + provenance, via scripts/validate_tsv.py
#   syntax  bash -n on the menu script
#   exec    menu script is executable
#   deps    fuzzel and awk are on PATH
#   wiring  the menu script is bound in the WM config and the target exists
#
# Exit 0 when nothing failed; 1 otherwise. WARN never fails the run.

set -uo pipefail

SKILL_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
HYPR_CONF="${HYPR_CONF:-$HOME/.config/hypr/keybindings.conf}"

TSV="${1:-}"
MENU="${2:-}"

if [ -z "$TSV" ]; then
    echo "usage: validate.sh <file.tsv> [menu-script.sh]" >&2
    exit 2
fi

fails=0
checks=0

report() { # report <status> <name> <detail>
    printf '[%s]%*s%-7s %s\n' "$1" $((5 - ${#1})) "" "$2" "$3"
    # A WARN annotates the check that just ran; it is not a check of its own.
    [ "$1" = "WARN" ] || checks=$((checks + 1))
    [ "$1" = "FAIL" ] && fails=$((fails + 1))
    return 0
}

# --- tsv ---------------------------------------------------------------------
if tsv_out="$(python3 "$SKILL_DIR/scripts/validate_tsv.py" "$TSV" 2>&1)"; then
    ok_line="$(printf '%s\n' "$tsv_out" | grep -F '[OK]' | head -1)"
    report OK tsv "${ok_line##*"$TSV": }"
    case "$tsv_out" in
        *"[WARN]"*) report WARN tsv "no '# source: <app> <version> / <where>' comment — freshness unconfirmed" ;;
    esac
else
    report FAIL tsv "$(printf '%s' "$tsv_out" | tr '\n' ' ')"
fi

# --- menu script -------------------------------------------------------------
if [ -n "$MENU" ]; then
    menu_name="$(basename -- "$MENU")"
    if [ ! -f "$MENU" ]; then
        report FAIL syntax "$menu_name not found at $MENU"
    elif bash -n "$MENU" 2>/dev/null; then
        report OK syntax "$menu_name parses"
    else
        report FAIL syntax "$(bash -n "$MENU" 2>&1 | tr '\n' ' ')"
    fi

    if [ -x "$MENU" ]; then
        report OK exec "$menu_name is executable"
    else
        report FAIL exec "$menu_name is not executable (chmod +x)"
    fi
else
    report SKIP syntax "no menu script given — pass it once the script exists"
fi

# --- deps --------------------------------------------------------------------
missing=""
for dep in fuzzel awk; do
    command -v "$dep" >/dev/null 2>&1 || missing="$missing $dep"
done
if [ -z "$missing" ]; then
    report OK deps "fuzzel, awk present"
else
    report FAIL deps "not on PATH:$missing"
fi

# --- wiring ------------------------------------------------------------------
if [ -z "$MENU" ]; then
    report SKIP wiring "no menu script given"
elif [ ! -f "$HYPR_CONF" ]; then
    report SKIP wiring "$HYPR_CONF not present (non-Hyprland WM — verify the binding by hand)"
else
    bind_line="$(grep -F "$(basename -- "$MENU")" "$HYPR_CONF" | grep -E '^\s*bindd?\s*=' | head -1)"
    if [ -z "$bind_line" ]; then
        report FAIL wiring "no bind for $(basename -- "$MENU") in $HYPR_CONF"
    else
        # The bound path must resolve; $HOME/~ and $cs_path style vars are expanded.
        target="${bind_line##*exec, }"
        target="${target%%,*}"
        target="${target/#\~/$HOME}"
        target="${target//\$HOME/$HOME}"
        if [ -e "$target" ]; then
            report OK wiring "$(cut -d, -f1-3 <<<"$bind_line" | tr -s ' ') -> existing script"
        else
            report FAIL wiring "bound path does not exist: $target"
        fi
        case "$bind_line" in
            *bindd*) : ;;
            *) report WARN wiring "uses 'bind' not 'bindd' — no description in the bindings HUD" ;;
        esac
    fi
fi

# --- summary -----------------------------------------------------------------
if [ "$fails" -eq 0 ]; then
    printf '[PASS] %d checks\n' "$checks"
    exit 0
fi
printf '[FAIL] %d of %d checks failed\n' "$fails" "$checks" >&2
exit 1
