# Menu, schema & hotkey wiring

## Table of contents
1. TSV schema
2. Validation
3. The menu script
4. Searching keys only
5. Reference-only vs execute-on-select
6. Hotkey wiring
7. Layout conventions

## 1. TSV schema

Plain text, one entry per line, **tab-separated**:

| Column | Required | Meaning |
| --- | --- | --- |
| `category` | yes | grouping for ordering/clustering in the flat menu (e.g. `Navigation`) |
| `key` | yes | the key/chord as typed (e.g. `Ctrl-W H`, `dd`, `:pat`) |
| `description` | yes | short, imperative (e.g. `move pane to far left`) |
| `command` | no | for the execute variant only — the thing to run/send |

Rules:
- Blank lines and `#`-comment lines are ignored. The first lines are the provenance comments — `# source: <app> <version> / <where>` and one `# config:` line per user config consulted, both in the exact forms `audit_versions.sh` parses (see `data-sources.md`).
- Keys are written as the user presses them: `Ctrl-`, `Shift-`, `Alt-` prefixes; `{c}` for "any character"; keep them short. Leaders and prefixes are expanded, never left as `<leader>`.
- Bindings from the user's own config are merged in as ordinary rows, indistinguishable from defaults; a default the user has rebound is corrected in place rather than kept alongside.
- One row per key within a category — a duplicate means an overlay left both the default and the rebind in the sheet, and the validator rejects it.
- Keep descriptions terse — the menu is one line per entry.
- Order entries by category so related keys cluster when the picker preserves input order (`--no-sort`).

Example:
```
# source: vifm 0.14.4 / vifm-help.txt (~/.config/vifm/)
# config: ~/.config/vifm/vifmrc @ 2026-08-09
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
| `tsv` | wrong column count, empty/whitespace-only category, key or description, non-tab-separated rows, a duplicate key inside one category, a malformed `# source:`/`# config:` comment (`validate_tsv.py` does the work). Warns on a missing provenance comment, an unexpanded `<leader>`/`<prefix>`/`$mainMod`, a stray 5th field, and a key repeated across categories |
| `syntax` | the menu script is missing or `bash -n` rejects it |
| `deps` | none of the pickers named in the menu script is on PATH, or `awk` is missing |
| `wiring` | no binding for the script in `$WM_CONF`, or the bound path does not exist. Warns on Hyprland `bind` instead of `bindd` |
| `exec` | the menu script has no exec bit *and* the binding runs it directly. A binding of the form `bash <path>` passes without one; with no binding to read, the check reports `SKIP` rather than guessing |

A check with no input prints `SKIP` rather than passing quietly, so a partial run never reads as a clean one. Exit 1 means at least one `FAIL`; fix and re-run before shipping.

`WM_CONF` defaults to the first existing Hyprland, sway, i3 or niri config. Set it explicitly for anything else, or accept `SKIP wiring` and verify the binding by hand.

## 3. The menu script

`scripts/make_cheatsheet.sh` is the reference-only template in its fuzzel form. Per app, copy and rename it (`<bin-dir>/<app>-cheatsheet.sh`, e.g. `~/.local/bin/vifm-cheatsheet.sh`) and set:

| Env | Default | Meaning |
| --- | --- | --- |
| `DATA` | — (required) | TSV path; by convention `~/.config/<app>/cheatsheet.tsv` |
| `PROMPT` | `Cheatsheet` | menu prompt |
| `WIDTH` | `90` | menu width (%) |
| `LINES` | `25` | visible rows |
| `MODE` | `full` | `keys` restricts matching to the key column (section 4) |

Menu line format is fixed: `key - description   (Category)` — searchable by key, action, or category.

The copy needs no exec bit: every invocation goes through `bash <path>`, both from the shell and from the hotkey (section 6). That keeps the build clear of `chmod +x`, which an agent is often not permitted to run on a file it has just written.

**Specialize the script to the installed picker, at build time.** Resolve which picker is present and what version it is (`fuzzel --version`, `rofi -version`, `wofi --version`), then write a script that calls that one picker with the flags that build actually supports. No runtime picker dispatch, no capability probing, no fallback branches: the machine's picker does not change between invocations, so a branch for a picker that is not installed is dead code that nobody will ever notice is wrong.

| Picker | Flags | Column matching |
| --- | --- | --- |
| fuzzel | `--dmenu --prompt P --hide-prompt --width N --lines N --match-mode=fzf --no-sort` | `--with-nth` since 1.12, `--match-nth` since 1.14, `--accept-nth` since 1.12 |
| rofi | `-dmenu -i -matching fuzzy -p P -l N` | none |
| wofi | `--dmenu --insensitive --prompt P --lines N --width N%` | none |
| tofi | `--prompt-text "P: "` | none |
| bemenu / dmenu | `-i -p P -l N` | none |

Confirm the flags against the installed build's `--help` rather than this table when a version is older than the ones above; the table records what the flags are for, not what every release accepts.

## 4. Searching keys only

By default the query matches the whole rendered line, so typing `w` also hits every description containing a w. Feeding the picker two columns — the rendered line, then the bare key — makes a key-only search possible:

```bash
MODE=keys bash ~/.local/bin/vifm-cheatsheet.sh
```

With fuzzel this is `--with-nth=1 --match-nth=2`: the full line is displayed, matching happens against the key alone. Only fuzzel ≥ 1.14 can do it; for any other picker, drop `MODE` from the script entirely rather than accepting a silent fall back to full-line matching.

Worth a second hotkey when an app has many keys sharing a description vocabulary (vim, vifm): `<key>` for the full menu, `Alt+<key>` for key-only lookup, with the same script and `MODE=keys`.

## 5. Reference-only vs execute-on-select

- **Reference-only** (default): selection is discarded (`>/dev/null`). Universal and safe. Use for any app driven inside a TUI (vifm, vim, btop, htop) and whenever there is no external IPC.
- **Execute-on-select**: only when the app exposes a real external control channel. Add the 4th `command` column, then have the wrapper feed the selected entry's command to the runner — `hyprctl dispatch` for Hyprland, `tmux send-keys` for tmux, `i3-msg` for i3/sway. Read the command back with fuzzel's `--accept-nth`, or re-look it up in the TSV by key; do not parse it out of the rendered display line. Two requirements: keep an allowlist of accepted verbs so a malformed TSV line cannot execute something arbitrary, and cache the parsed data by mtime if the dump is expensive. Never ship an execute entry whose `command` field has no real runner — fall back to reference-only instead.

## 6. Hotkey wiring

Bind the script through `bash`, never as a bare path: the exec bit then stops mattering, so a script written moments earlier fires on the first press without a `chmod +x` the environment may refuse.

**Hyprland** — bind the script, ideally inside a dedicated cheatsheet submap:

```
bindd = , F, Vifm cheat sheet, exec, bash ~/.local/bin/vifm-cheatsheet.sh
bindd = ALT, F, Vifm cheat sheet by key, exec, MODE=keys bash ~/.local/bin/vifm-cheatsheet.sh
bindd = SHIFT, F, Vifm cheat sheet image, exec, feh $cs_path/vifm-v0.14-builtin-normal.png
```

- `bindd` (not `bind`) so the description shows in any bindings HUD.
- Keep the static image on `Shift+<key>` as a visual fallback (download it version-matched first; see `data-sources.md`).
- `$cs_path` is a variable defined at the top of the config, pointing at wherever cheatsheet images live. `validate.sh` expands `~` and `$HOME` in a bound path but not config-local variables like this one, so an image bind is not checked for you.
- Reload after editing: `hyprctl reload` (must report `ok`).

**i3 / sway** — `bindsym <key> exec bash ~/.local/bin/<app>-cheatsheet.sh`; reload with `swaymsg reload` / `i3-msg reload`.

**niri** — inside the `binds` block: `Mod+Shift+F { spawn "bash" "/home/<user>/.local/bin/<app>-cheatsheet.sh"; }`. niri spawns the program without a shell, so each argument is separate and the path is absolute — a leading `~` reaches `bash` as a literal filename and the binding silently does nothing.

On any of these, the menu script is the one written for the picker installed on that machine (section 3); the wiring itself is the same whichever picker it calls.

## 7. Layout conventions

Match whatever the setup already uses; when there is no precedent, these defaults keep the pieces findable:

| Piece | Default |
| --- | --- |
| Picker | `fuzzel` (Wayland), `rofi`/`dmenu` on X11 — whichever is installed, resolved once when the script is written |
| Data | `~/.config/<app>/cheatsheet.tsv` — the path `audit_versions.sh` scans by default |
| Menu script | `~/.local/bin/<app>-cheatsheet.sh` |
| Images | one directory for all of them, exported as `$cs_path` in the WM config |
| Hotkey | a cheatsheet submap or prefix, one letter per app; key-only lookup on `Alt+<letter>`, image fallback on `Shift+<letter>` |

Example of one such layout: a `cheatsheet` submap opened with `SUPER, C`, with `F` bound to the vifm menu script and `SHIFT F` to the version-matched vifm image, data in `~/.config/vifm/cheatsheet.tsv`.

Keeping data at the default path matters beyond tidiness: `audit_versions.sh` globs `~/.config/*/cheatsheet.tsv`, so a sheet parked elsewhere is silently excluded from the staleness audit unless `CHEATSHEET_GLOB` is set to find it.
