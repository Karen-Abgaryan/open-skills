#!/bin/bash
#
# Report which searchable cheatsheets have drifted from the installed app.
# Advisory only: it prints a table and always exits 0 — refreshing a stale
# sheet is the user's call, never an automatic rebuild.
#
# USAGE:
#   audit_versions.sh [extra.tsv ...]
#
# Scans ~/.config/*/cheatsheet.tsv (override the glob with CHEATSHEET_GLOB)
# plus any paths given as arguments.
#
# Version sources:
#   recorded   the '# source: <app> <version> / <where>' comment in the TSV
#   installed  <app> --version, then -v, then the package manager
#
# Status:
#   OK       recorded == installed
#   DRIFT    same major.minor, different patch — usually harmless
#   STALE    major.minor differs — the sheet predates the installed app
#   UNKNOWN  no parseable provenance comment, or the app version is unreadable
#   N/A      no local binary or package (web/GUI app; nothing to compare against)

set -uo pipefail

GLOB="${CHEATSHEET_GLOB:-$HOME/.config/*/cheatsheet.tsv}"

# First version-looking token in the first lines of output, e.g.
# "Version: 0.14.4" -> 0.14.4, "fuzzel version: 1.14.1 +cairo" -> 1.14.1
extract_version() {
    grep -oE '[0-9]+(\.[0-9]+)+' <<<"$1" | head -1
}

installed_version() {
    local app="$1" out=""
    if command -v "$app" >/dev/null 2>&1; then
        out="$("$app" --version 2>&1 | head -5)"
        [ -n "$(extract_version "$out")" ] || out="$("$app" -v 2>&1 | head -5)"
        [ -n "$(extract_version "$out")" ] && { extract_version "$out"; return 0; }
    fi
    # No usable --version: ask the package manager.
    for probe in "pacman -Q $app" "dpkg-query -W $app" "rpm -q $app" "brew list --versions $app"; do
        command -v "${probe%% *}" >/dev/null 2>&1 || continue
        out="$($probe 2>/dev/null | head -1)" || true
        [ -n "$(extract_version "$out")" ] && { extract_version "$out"; return 0; }
    done
    return 1
}

printf '%-34s %-10s %-10s %s\n' ASSET RECORDED INSTALLED STATUS
printf '%-34s %-10s %-10s %s\n' ---------------------------------- ---------- ---------- ------

shopt -s nullglob
candidates=()
for f in $GLOB "$@"; do
    [ -f "$f" ] && candidates+=("$f")
done
shopt -u nullglob

if [ "${#candidates[@]}" -eq 0 ]; then
    echo "(no cheatsheet TSVs found under $GLOB)"
    exit 0
fi

refresh=0
for tsv in "${candidates[@]}"; do
    # Display as <dir>/<file> so ~/.config/vifm/cheatsheet.tsv stays legible.
    label="$(basename -- "$(dirname -- "$tsv")")/$(basename -- "$tsv")"

    src_line="$(grep -im1 '^[[:space:]]*#[[:space:]]*source[[:space:]]*:' "$tsv")"
    src_body="${src_line#*:}"
    read -r app recorded _ <<<"$src_body"
    [ -n "${app:-}" ] || app="$(basename -- "$(dirname -- "$tsv")")"
    recorded="$(extract_version "${recorded:-}")"

    if installed="$(installed_version "$app")"; then
        :
    else
        installed=""
    fi

    if [ -z "$installed" ]; then
        status="N/A"
    elif [ -z "$recorded" ]; then
        status="UNKNOWN"
        refresh=$((refresh + 1))
    elif [ "$recorded" = "$installed" ]; then
        status="OK"
    else
        rec_mm="$(cut -d. -f1,2 <<<"$recorded")"
        ins_mm="$(cut -d. -f1,2 <<<"$installed")"
        if [ "$rec_mm" = "$ins_mm" ]; then
            status="DRIFT"
        else
            status="STALE"
            refresh=$((refresh + 1))
        fi
    fi

    printf '%-34s %-10s %-10s %s\n' "$label" "${recorded:--}" "${installed:--}" "$status"
done

echo
if [ "$refresh" -eq 0 ]; then
    echo "No cheatsheet needs a refresh."
else
    printf '%d cheatsheet(s) worth refreshing (STALE/UNKNOWN). Ask before rebuilding any.\n' "$refresh"
fi
exit 0
