#!/bin/bash
#
# Report which searchable cheatsheets have drifted from the installed app or
# from the user's own keybinding config. Advisory only: it prints a table and
# always exits 0 — refreshing a stale sheet is the user's call, never an
# automatic rebuild.
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
#   config     each '# config: <path> @ <YYYY-MM-DD>' comment in the TSV
#
# Status:
#   OK            recorded == installed, and no config is newer than its date
#   CONFIG-DRIFT  the app matches, but a keybinding config changed since the
#                 sheet was built — rebinds may be missing or wrong
#   DRIFT         same major.minor, different patch — usually harmless
#   STALE         major.minor differs — the sheet predates the installed app
#   UNKNOWN       no parseable provenance comment, or the app version is unreadable
#   N/A           no local binary or package: either a web/GUI app with nothing
#                 to compare against, or a wrong app token in the source comment

set -uo pipefail

GLOB="${CHEATSHEET_GLOB:-$HOME/.config/*/cheatsheet.tsv}"

# First version-looking token in the first lines of output, e.g.
# "Version: 0.14.4" -> 0.14.4, "fuzzel version: 1.14.1 +cairo" -> 1.14.1
extract_version() {
    grep -oE '[0-9]+(\.[0-9]+)+' <<<"$1" | head -1
}

# An app that does not understand --version can open its TUI and hang the audit,
# so every probe is time-boxed and gets no stdin.
probe() {
    if command -v timeout >/dev/null 2>&1; then
        timeout 5 "$@" </dev/null 2>&1
    else
        "$@" </dev/null 2>&1
    fi
}

installed_version() {
    local app="$1" out=""
    if command -v "$app" >/dev/null 2>&1; then
        out="$(probe "$app" --version | head -5)"
        [ -n "$(extract_version "$out")" ] || out="$(probe "$app" -v | head -5)"
        [ -n "$(extract_version "$out")" ] && { extract_version "$out"; return 0; }
    fi
    # No usable --version: ask the package manager.
    for probe_cmd in "pacman -Q $app" "dpkg-query -W $app" "rpm -q $app" "brew list --versions $app"; do
        command -v "${probe_cmd%% *}" >/dev/null 2>&1 || continue
        out="$(probe $probe_cmd | head -1)" || true
        [ -n "$(extract_version "$out")" ] && { extract_version "$out"; return 0; }
    done
    return 1
}

# Echoes one "<path> (<recorded> -> <actual>)" per config that changed after the
# sheet was built. A rebind never moves the app version, so this is the only
# signal that a sheet has gone wrong while still matching the installed release.
config_drift() {
    local tsv="$1" line body path recorded actual
    while IFS= read -r line; do
        body="${line#*:}"
        path="${body%@*}"
        recorded="${body##*@}"
        # Trim surrounding whitespace.
        path="$(sed 's/^[[:space:]]*//; s/[[:space:]]*$//' <<<"$path")"
        recorded="$(sed 's/^[[:space:]]*//; s/[[:space:]]*$//' <<<"$recorded")"
        [ -n "$path" ] && [ -n "$recorded" ] || continue
        path="${path/#\~/$HOME}"
        if [ ! -e "$path" ]; then
            printf '%s (recorded %s, now missing)\n' "$path" "$recorded"
            continue
        fi
        actual="$(date -r "$path" +%F 2>/dev/null)" || continue
        # ISO dates compare correctly as strings.
        [[ "$actual" > "$recorded" ]] && printf '%s (%s -> %s)\n' "$path" "$recorded" "$actual"
    done < <(grep -i '^[[:space:]]*#[[:space:]]*config[[:space:]]*:' "$tsv")
    return 0
}

printf '%-30s %-10s %-10s %s\n' ASSET RECORDED INSTALLED STATUS
printf '%-30s %-10s %-10s %s\n' ------------------------------ ---------- ---------- ------------

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
unverifiable=0
notes=()
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

    drifted="$(config_drift "$tsv")"

    if [ -z "$installed" ]; then
        status="N/A"
        unverifiable=$((unverifiable + 1))
        notes+=("$label: no binary or package named '$app' — a web/GUI app, or a wrong app token in the '# source:' line")
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

    # A changed config outranks a patch-level version difference: the rebind is
    # what actually makes the sheet wrong.
    if [ -n "$drifted" ] && [ "$status" != "STALE" ] && [ "$status" != "UNKNOWN" ]; then
        status="CONFIG-DRIFT"
        refresh=$((refresh + 1))
    fi
    if [ -n "$drifted" ]; then
        while IFS= read -r d; do
            [ -n "$d" ] && notes+=("$label: config changed — $d")
        done <<<"$drifted"
    fi

    printf '%-30s %-10s %-10s %s\n' "$label" "${recorded:--}" "${installed:--}" "$status"
done

echo
for n in ${notes[@]+"${notes[@]}"}; do
    echo "  $n"
done
[ "${#notes[@]}" -gt 0 ] && echo

if [ "$refresh" -eq 0 ]; then
    echo "No cheatsheet needs a refresh."
else
    printf '%d cheatsheet(s) worth refreshing (STALE/UNKNOWN/CONFIG-DRIFT). Ask before rebuilding any.\n' "$refresh"
fi
[ "$unverifiable" -gt 0 ] &&
    printf '%d sheet(s) could not be verified at all (N/A) — check the app token in their source comment.\n' "$unverifiable"
exit 0
