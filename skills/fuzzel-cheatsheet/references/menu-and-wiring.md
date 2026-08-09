# Menu, schema & hotkey wiring

## Table of contents
1. TSV schema
2. Validation
3. The menu script
4. Reference-only vs execute-on-select
5. Hotkey wiring
6. Layout conventions

## 1. TSV schema

Plain text, one entry per line, **tab-separated**:

| Column | Required | Meaning |
| --- | --- | --- |
| `category` | yes | grouping for ordering/clustering in the flat menu (e.g. `Navigation`) |
| `key` | yes | the key/chord as typed (e.g. `Ctrl-W H`, `dd`, `:pat`) |
| `description` | yes | short, imperative (e.g. `move pane to far left`) |
| `command` | no | for the execute variant only — the thing to run/send |

Rules:
- Blank lines and `#`-comment lines are ignored. The first line is the provenance comment, in the exact form `# source: <app> <version> / <where>` — `audit_versions.sh` parses it (see `data-sources.md`).
- Keys are written as the user presses them: `Ctrl-`, `Shift-`, `Alt-` prefixes; `{c}` for "any character"; keep them short.
- Keep descriptions terse — the menu is one line per entry.
- Order entries by category so related keys cluster when fuzzel preserves input order (`--no-sort`).

Example:
```
# source: vifm 0.14.4 / vifm-help.txt (~/.config/vifm/)
Navigation	h	go up one directory
Navigation	l	enter directory or open file
Panes	Ctrl-W H	move pane to far left
File Ops	yy	yank (copy) files
```

## 2. Validation

One wrapper covers the whole build; run it twice, with more arguments as more exists:

```bash
bash <skill-dir>/scripts/validate.sh <file.tsv>                    # after step 4
bash <skill-dir>/scripts/validate.sh <file.tsv> <menu-script.sh>   # after step 7
```

| Check | Fails on |
| --- | --- |
| `tsv` | wrong column count, empty/whitespace-only category, key or description, non-tab-separated rows (`validate_tsv.py` does the work). Warns, without failing, when the `# source:` comment is missing |
| `syntax` | the menu script is missing or `bash -n` rejects it |
| `exec` | the menu script has no exec bit |
| `deps` | `fuzzel` or `awk` is not on PATH |
| `wiring` | no `bind`/`bindd` for the script in `$HYPR_CONF`, or the bound path does not exist. Warns on `bind` instead of `bindd` |

A check with no input prints `SKIP` rather than passing quietly, so a partial run never reads as a clean one. Exit 1 means at least one `FAIL`; fix and re-run before shipping.

On a non-Hyprland WM set `HYPR_CONF` to that config, or accept `SKIP wiring` and verify the binding by hand.

## 3. The menu script

`scripts/make_cheatsheet.sh` is the canonical reference-only wrapper. Per app, copy and rename it (`<bin-dir>/<app>-cheatsheet.sh`, e.g. `~/.local/bin/vifm-cheatsheet.sh`) and set:

| Env | Default | Meaning |
| --- | --- | --- |
| `DATA` | `~/.config/<app>/cheatsheet.tsv` | TSV path |
| `PROMPT` | app name | fuzzel prompt |
| `WIDTH` | `90` | menu width (%) |
| `LINES` | `25` | visible rows |

Menu line format is fixed: `key - description   (Category)` — searchable by key, action, or category. Fuzzel flags `--dmenu --match-mode=fzf --no-sort --hide-prompt` are baked in; do not change them ad hoc.

## 4. Reference-only vs execute-on-select

- **Reference-only** (default): selection is discarded (`>/dev/null`). Universal and safe. Use for any app driven inside a TUI (vifm, vim, btop, htop) and whenever there is no external IPC.
- **Execute-on-select**: only when the app exposes a real external control channel. Add the 4th `command` column, then have the wrapper feed the selected entry's command to the runner — `hyprctl dispatch` for Hyprland, `tmux send-keys` for tmux, `i3-msg` for i3/sway. Two requirements: keep an allowlist of accepted verbs so a malformed TSV line cannot execute something arbitrary, and cache the parsed data by mtime if the dump is expensive. Never ship an execute entry whose `command` field has no real runner — fall back to reference-only instead.

## 5. Hotkey wiring

**Hyprland** — bind the script, ideally inside a dedicated cheatsheet submap:

```
bindd = , F, Vifm cheat sheet, exec, ~/.local/bin/vifm-cheatsheet.sh
bindd = SHIFT, F, Vifm cheat sheet image, exec, feh $cs_path/vifm-v0.14-builtin-normal.png
```

- `bindd` (not `bind`) so the description shows in any bindings HUD.
- Keep the static image on `Shift+<key>` as a visual fallback (download it version-matched first; see `data-sources.md`).
- `$cs_path` is a variable defined at the top of the config, pointing at wherever cheatsheet images live.
- Reload after editing: `hyprctl reload` (must report `ok`).

**i3/Sway** — `bindsym <key> exec ~/.local/bin/<app>-cheatsheet.sh`. Use `rofi -dmenu` if that is the installed picker; its matching flags differ from fuzzel's (`-i`, `-matching fuzzy`), so adjust them rather than copying fuzzel's verbatim.

## 6. Layout conventions

Match whatever the setup already uses; when there is no precedent, these defaults keep the pieces findable:

| Piece | Default |
| --- | --- |
| Picker | `fuzzel` (Wayland), `rofi`/`dmenu` on X11 |
| Data | `~/.config/<app>/cheatsheet.tsv` — the path `audit_versions.sh` scans by default |
| Menu script | `~/.local/bin/<app>-cheatsheet.sh` |
| Images | one directory for all of them, exported as `$cs_path` in the WM config |
| Hotkey | a cheatsheet submap or prefix, one letter per app; image fallback on `Shift+<letter>` |

Example of one such layout: a `cheatsheet` submap opened with `SUPER, C`, with `F` bound to the vifm menu script and `SHIFT F` to the version-matched vifm image, data in `~/.config/vifm/cheatsheet.tsv`.

Keeping data at the default path matters beyond tidiness: `audit_versions.sh` globs `~/.config/*/cheatsheet.tsv`, so a sheet parked elsewhere is silently excluded from the staleness audit unless `CHEATSHEET_GLOB` is set to find it.
