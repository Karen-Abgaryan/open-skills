#!/usr/bin/env bash
# Pre-flight for a Medium draft transfer: runs every pre-transfer check that can
# be automated and prints one status line per check.
#
#   bash validate.sh ARTICLE.md [OUTDIR]
#
# Statuses: PASS, FAIL (blocks), WARN (report, keep going), SKIP (not runnable),
# MANUAL (needs a human or a vision tool — see the paths it prints).
# Exits non-zero if any check FAILs.

set -uo pipefail

ARTICLE="${1:-}"
if [ -z "$ARTICLE" ] || [ ! -f "$ARTICLE" ]; then
  echo "usage: validate.sh ARTICLE.md [OUTDIR]" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SLUG="$(basename "${ARTICLE%.*}")"
OUTDIR="${2:-/tmp/draft-on-medium-$SLUG}"
FAILED=0

status() { printf '%-10s %-9s %s\n' "$1" "$2" "$3"; [ "$2" = FAIL ] && FAILED=1; return 0; }

# --- 1. conversion ---------------------------------------------------------
CONV_OUT="$(python3 "$SCRIPT_DIR/md_to_medium.py" "$ARTICLE" --outdir "$OUTDIR" 2>&1)"
if [ $? -ne 0 ]; then
  status CONVERT FAIL "${CONV_OUT}"
  echo
  echo "conversion failed — nothing else can run"
  exit 1
fi
BLOCKS="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["blocks"])' "$OUTDIR/meta.json")"
status CONVERT PASS "$BLOCKS blocks -> $OUTDIR/body.html"

# --- 2. structure ----------------------------------------------------------
SUBTITLE="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["subtitle"])' "$OUTDIR/meta.json")"
if [ -n "$SUBTITLE" ]; then
  status STRUCTURE PASS "title + subtitle present"
else
  status STRUCTURE WARN "no H3 subtitle — an H3 under the title becomes Medium's subtitle"
fi

# --- 3. images -------------------------------------------------------------
IMG_COUNT="$(python3 -c 'import json,sys;print(len(json.load(open(sys.argv[1]))))' "$OUTDIR/images.json")"
if [ "$IMG_COUNT" -eq 0 ]; then
  status IMAGES SKIP "article references no images"
else
  MISSING=0
  GEOM=""
  while IFS= read -r p; do
    if [ ! -f "$p" ]; then
      status IMAGES FAIL "missing file: $p"
      MISSING=1
    else
      GEOM="$GEOM$(magick identify -format '%wx%h' "$p" 2>/dev/null)"$'\n'
    fi
  done < <(python3 -c 'import json,sys;[print(i["path"]) for i in json.load(open(sys.argv[1]))]' "$OUTDIR/images.json")
  if [ "$MISSING" -eq 0 ]; then
    UNIQ="$(printf '%s' "$GEOM" | sort -u | tr '\n' ' ')"
    # Width is the only dimension that has to match. Heights differ by design:
    # a capture cropped to its own content is legitimately a fraction of the
    # height of a fuller one — a three-result shot against a whole list.
    # Comparing whole geometries warned on every correctly cropped article.
    WIDTHS="$(printf '%s' "$GEOM" | sed 's/x.*//' | sort -u | grep -c .)"
    if [ "$WIDTHS" -gt 1 ]; then
      status IMAGES WARN "$IMG_COUNT files, mixed widths: $UNIQ (ragged column on Medium)"
    else
      status IMAGES PASS "$IMG_COUNT files, uniform width: $UNIQ"
    fi
  fi
fi

# --- 4. external links -----------------------------------------------------
LINKS="$(python3 -c 'import json,sys;[print(u) for u in json.load(open(sys.argv[1]))["links"]]' "$OUTDIR/meta.json")"
if [ -z "$LINKS" ]; then
  status LINKS SKIP "no external URLs"
elif ! curl -sS -m 5 -o /dev/null https://example.com 2>/dev/null; then
  status LINKS SKIP "no network"
else
  while IFS= read -r url; do
    CODE="$(curl -sSL -m 15 -o /dev/null -w '%{http_code}' -A 'Mozilla/5.0' "$url" 2>/dev/null)"
    case "$CODE" in
      2*|3*) status LINKS PASS "$CODE $url" ;;
      000)   status LINKS WARN "no response (may block automated requests): $url" ;;
      *)     status LINKS FAIL "$CODE $url" ;;
    esac
  done <<< "$LINKS"
fi

# --- 5. cover legibility ---------------------------------------------------
COVER="$(python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print(d[0]["path"] if d else "")' "$OUTDIR/images.json")"
if [ -z "$COVER" ] || [ ! -f "$COVER" ]; then
  status COVER SKIP "no cover candidate"
else
  THUMB="$OUTDIR/cover-200px.png"
  if magick "$COVER" -resize 200x "$THUMB" 2>/dev/null; then
    status COVER MANUAL "judge legibility at feed size: $THUMB"
  else
    status COVER WARN "could not downscale $COVER"
  fi
fi

# --- 6. leaked content -----------------------------------------------------
if [ "${IMG_COUNT:-0}" -eq 0 ]; then
  status LEAKS SKIP "no images to inspect"
else
  status LEAKS MANUAL "inspect each image for home paths, usernames, chat names, scrollback"
  python3 -c 'import json,sys;[print("           ", i["path"]) for i in json.load(open(sys.argv[1]))]' "$OUTDIR/images.json"
fi

# --- 7. medium reachability ------------------------------------------------
# Medium sits behind Cloudflare, which sometimes blocks the editor's JS bundle;
# when that happens the editor never initialises and there is nothing to drive.
# This is a hint only, never a gate: Cloudflare challenges a bare curl far more
# readily than a real browser session, so a 403 here has been observed while the
# browser loaded the editor perfectly. The authoritative check is in the browser
# — load the editor and count [contenteditable] nodes.
if ! curl -sS -m 5 -o /dev/null https://example.com 2>/dev/null; then
  status MEDIUM SKIP "no network"
else
  MCODE="$(curl -sS -m 15 -o /dev/null -w '%{http_code}' \
    -A 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36' \
    https://cdn-static-1.medium.com/ 2>/dev/null)"
  case "$MCODE" in
    403) status MEDIUM WARN "cdn-static-1.medium.com 403 to curl — inconclusive; confirm in the browser before believing it" ;;
    000) status MEDIUM WARN "no response from cdn-static-1.medium.com" ;;
    *)   status MEDIUM PASS "cdn-static-1.medium.com reachable ($MCODE)" ;;
  esac
fi

echo
if [ "$FAILED" -eq 1 ]; then
  echo "pre-flight: FAILURES above — resolve them before transferring"
  exit 1
fi
echo "pre-flight: no blocking failures; resolve MANUAL items before uploading"
