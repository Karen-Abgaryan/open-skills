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
#   deps    the picker the menu script actually uses, plus awk, are on PATH
#   wiring  the menu script is bound in the WM config and the target exists
#   exec    menu script is executable — only required when the binding runs it
#           directly; `bash <path>` in the binding makes the exec bit irrelevant
#
# Env:
#   WM_CONF   window-manager config to check the binding in. Defaults to the
#             first of the Hyprland/sway/i3/niri configs that exists.
#             HYPR_CONF is still honoured for compatibility.
#
# Exit 0 when nothing failed; 1 otherwise. WARN never fails the run.

set -uo pipefail

SKILL_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

default_wm_conf() {
    local c
    for c in "$HOME/.config/hypr/keybindings.conf" \
             "$HOME/.config/hypr/hyprland.conf" \
             "$HOME/.config/sway/config" \
             "$HOME/.config/i3/config" \
             "$HOME/.config/niri/config.kdl"; do
        [ -f "$c" ] && { printf '%s' "$c"; return 0; }
    done
    printf '%s' "$HOME/.config/hypr/keybindings.conf"
}

WM_CONF="${WM_CONF:-${HYPR_CONF:-$(default_wm_conf)}}"

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
    # Forward every warning the validator raised, not just the first kind.
    while IFS= read -r warn_line; do
        [ -n "$warn_line" ] || continue
        report WARN tsv "${warn_line##*"$TSV": }"
    done < <(printf '%s\n' "$tsv_out" | grep -F '[WARN]')
else
    report FAIL tsv "$(printf '%s' "$tsv_out" | tr '\n' ' ')"
fi

# --- menu script -------------------------------------------------------------
picker=""
if [ -n "$MENU" ]; then
    menu_name="$(basename -- "$MENU")"
    if [ ! -f "$MENU" ]; then
        report FAIL syntax "$menu_name not found at $MENU"
    elif bash -n "$MENU" 2>/dev/null; then
        report OK syntax "$menu_name parses"
    else
        report FAIL syntax "$(bash -n "$MENU" 2>&1 | tr '\n' ' ')"
    fi

    # Check the picker the script actually calls: a rofi menu must not fail
    # because fuzzel happens to be absent.
    if [ -f "$MENU" ]; then
        for candidate in fuzzel rofi wofi tofi bemenu dmenu; do
            grep -qE "(^|[^-[:alnum:]])$candidate([^-[:alnum:]]|$)" "$MENU" &&
                picker="${picker:+$picker }$candidate"
        done
    fi
else
    report SKIP syntax "no menu script given — pass it once the script exists"
fi

# --- deps --------------------------------------------------------------------
# With no menu script yet there is nothing to read the picker from, so fall back
# to the skill's default.
[ -n "$picker" ] || picker="fuzzel"
missing=""
found=""
for dep in $picker; do
    if command -v "$dep" >/dev/null 2>&1; then
        found="${found:+$found, }$dep"
    else
        missing="$missing $dep"
    fi
done
if command -v awk >/dev/null 2>&1; then
    awk_present=1
else
    awk_present=0
    missing="$missing awk"
fi

# A script may name several pickers because it selects one at runtime, so one
# present picker plus awk is enough.
if [ -n "$found" ] && [ "$awk_present" -eq 1 ]; then
    report OK deps "present: $found, awk${missing:+ (absent:$missing)}"
else
    report FAIL deps "not on PATH:$missing"
fi

# --- wiring ------------------------------------------------------------------
# How the binding starts the script decides whether the exec bit matters below.
bind_mode="unknown"
if [ -z "$MENU" ]; then
    report SKIP wiring "no menu script given"
elif [ ! -f "$WM_CONF" ]; then
    report SKIP wiring "$WM_CONF not present — set WM_CONF, or verify the binding by hand"
else
    # Hyprland 'bind'/'bindd', sway/i3 'bindsym', niri 'spawn' inside a binds block.
    bind_line="$(grep -F "$(basename -- "$MENU")" "$WM_CONF" |
                 grep -E '(^|[^[:alnum:]])(bind[a-z]*|bindsym|spawn)([^[:alnum:]]|$)' | head -1)"
    if [ -z "$bind_line" ]; then
        report FAIL wiring "no binding for $(basename -- "$MENU") in $WM_CONF"
    else
        # Take the token ending in the script name, so trailing arguments, quotes
        # and commas elsewhere in the binding cannot corrupt the path.
        esc_name="$(basename -- "$MENU" | sed 's/[.[\*^$]/\\&/g')"
        target="$(grep -oE "[^ ,\"']*$esc_name" <<<"$bind_line" | head -1)"
        target="${target/#\~/$HOME}"
        target="${target//\$HOME/$HOME}"
        # An interpreter in front of the path (`exec, bash ~/…/x.sh`, niri's
        # `spawn "bash" "…"`) opens the file itself, so no exec bit is needed.
        if grep -qE "(^|[^-[:alnum:]])(bash|sh|zsh)[[:space:]\"',]+[^ ,\"']*$esc_name" <<<"$bind_line"; then
            bind_mode="interpreter"
        else
            bind_mode="direct"
        fi
        if [ -e "$target" ]; then
            report OK wiring "$(tr -s ' ' <<<"$bind_line" | cut -c1-60) -> existing script"
        else
            report FAIL wiring "bound path does not exist: $target"
        fi
        # Hyprland only: 'bindd' carries the description shown in a bindings HUD.
        case "$WM_CONF" in
            *hypr*)
                case "$bind_line" in
                    *bindd*) : ;;
                    *) report WARN wiring "uses 'bind' not 'bindd' — no description in the bindings HUD" ;;
                esac
                ;;
        esac
    fi
fi

# --- exec --------------------------------------------------------------------
# Runs after wiring because only the binding says whether the bit is needed.
if [ -n "$MENU" ] && [ -f "$MENU" ]; then
    if [ -x "$MENU" ]; then
        report OK exec "$menu_name is executable"
    elif [ "$bind_mode" = "interpreter" ]; then
        report OK exec "$menu_name has no exec bit — the binding runs it via an interpreter"
    elif [ "$bind_mode" = "direct" ]; then
        report FAIL exec "$menu_name is not executable and the binding runs it directly (chmod +x $MENU, or bind it as 'bash $MENU')"
    else
        report SKIP exec "$menu_name has no exec bit and no binding was read — needed only if the hotkey runs it directly"
    fi
fi

# --- summary -----------------------------------------------------------------
if [ "$fails" -eq 0 ]; then
    printf '[PASS] %d checks\n' "$checks"
    exit 0
fi
printf '[FAIL] %d of %d checks failed\n' "$fails" "$checks" >&2
exit 1
