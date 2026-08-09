# Data sources & freshness

## Table of contents
1. Acquisition tiers
2. Freshness — version match
3. Download techniques (throttled hosts)
4. Converting sources to text

## 1. Acquisition tiers

Try tiers in order; stop at the first that yields trustworthy, version-matched data.

| Tier | Source | Examples | How | Enables execute? |
| --- | --- | --- | --- | --- |
| **1 — app dumps its own bindings** (best: authoritative + always current) | the running app's IPC/CLI | Hyprland `hyprctl binds -j`; tmux `tmux list-keys -T prefix`; zellij `zellij setup --dump-aliases` / layout keybinds; i3/sway `i3-msg -t get_bindings`; git `git config --get-regexp '^alias\.'`; vifm `:map` (inside instance) | run the dump, parse JSON/lines to TSV | yes, if IPC exists (`hyprctl dispatch`, `tmux send-keys`) |
| **2 — local help text** | shipped docs | `<app> --help`, `man <app>`, `~/.config/<app>/help.txt` (e.g. vifm's), `/usr/share/doc/<app>`, info pages | read the key/command section, curate to TSV, ground each entry verbatim | no (reference) |
| **3 — no local source** | official remote, **version-matched** | app website / GitHub release assets / wiki | get installed ver → find the matching URL → download → extract text → curate | no |
| **4 — curated fallback** | agent knowledge | only when no authoritative source is reachable | author concise entries, then **cross-check every key against `--help`/man** before shipping | no |

Prefer text/JSON/HTML sources over images. Only OCR/parse an image if no text source exists (rare).

## 2. Freshness — version match

A pre-existing local cheatsheet is frequently stale (the vifm case: a `v0.13` image while the installed binary was `v0.14.4`). Always:

1. **Get the installed version** — `<app> --version` or `-v`. If that fails, the package manager:
   - Arch/Manjaro: `pacman -Q <pkg>`
   - Debian/Ubuntu: `dpkg -s <pkg> | grep Version` / `apt-cache policy <pkg>`
   - Fedora/RHEL: `rpm -q <pkg>`
   - Homebrew: `brew list --versions <pkg>`
   - from source / pipx / cargo: `<app> --version`; check the install prefix
2. **Match the data source to that version.** For tier-3 remotes, version is usually in the URL path (e.g. `vifm.info/releases/v0.14/...`) — pick the segment that matches the installed major.minor.
3. **Record provenance** in the TSV as the first line, in the exact form `# source: <app> <version> / <where>`:
   ```
   # source: vifm 0.14.4 / vifm-help.txt (~/.config/vifm/)
   # source: tmux 3.4 / tmux list-keys
   # source: lazygit 0.44.1 / https://github.com/jesseduffield/lazygit/blob/master/docs/keybindings/Keybindings_en.md
   ```
   `<app>` must be the runnable command name and `<version>` a bare dotted number: `audit_versions.sh` reads exactly those two tokens to decide whether the sheet has gone stale, and a freeform line leaves it permanently `UNKNOWN`. `validate.sh` warns when the comment is missing altogether.

Do not reuse a cached image whose version you cannot confirm.

## 3. Download techniques (throttled hosts)

Normal hosts: `curl -fL --connect-timeout 15 --max-time 90 -o <file> <url>` or `wget`.

**Throttled / DPI-killed host** — the TCP/TLS handshake succeeds but the connection transfers a small burst (~16 KB) then dies (curl shows bytes ticking at ~180 B/s; wget ends with "Read error ... Connection timed out"). Symptom: only one host affected, other downloads fine.

Fix — chunked resume, re-running until the size matches `Content-Length`:

```bash
# 1. get the expected size
curl -sIL <url> | grep -i content-length

# 2. resume in a loop; low --read-timeout makes each failed retry cycle fast
wget -c --tries=300 --waitretry=0 --read-timeout=5 --timeout=15 \
     -O <file> <url>
# (re-run the same command until it reports "... saved [N/N]")
```

Calibration: ~16 KB arrives per connection; with `--read-timeout=5` each cycle is ~6 s, so a 735 KB file finishes in ~50 retries (~5 min). Keep flags byte-identical across re-runs.

Always verify after download: `file <file>` (magic bytes) and byte size vs `Content-Length`.

## 4. Converting sources to text

- **PDF** → `pdftotext -layout <file> -` (keeps column layout; best for cheatsheet PDFs).
- **HTML** → a web-reader tool, or `pandoc -f html -t plain`.
- **PNG/image** → text extraction is OCR. Per house vision-dispatch rules, delegate image/OCR to a vision tool — do not attempt to read the image yourself. But first look harder for a text source (`.tex`, `.md`, wiki, man page); rendering/OCR of a cheatsheet image is a last resort.
- **man page** → `man <app> | col -bx` for clean text, then take the key/command section.
