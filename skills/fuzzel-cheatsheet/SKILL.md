---
name: fuzzel-cheatsheet
description: "Build a fuzzy-searchable cheatsheet menu (fuzzel/rofi/wofi/dmenu) for any application's keys, commands, or shortcuts, wired to a launcher or window-manager hotkey. Reflects the bindings the user actually has, merging their own config over upstream defaults, and converts a static reference image into an interactive searchable lookup. Use when the user asks to make, create, or build a cheatsheet, hotkey reference, shortcut lookup, or key-binding reference for an app (e.g. vim, vifm, tmux, zellij, fish, lazygit, btop, git, htop); when upgrading a static cheatsheet image into a searchable menu; or when wiring a searchable reference to a keybinding. Handles dumping live bindings when the app supports it, overlaying custom keymaps from the user's dotfiles, and fetching version-matched data when only a remote source exists. Triggers: 'cheatsheet for X', 'searchable keybindings', 'shortcut lookup', 'hotkey reference', 'interactive cheatsheet', 'my custom keybindings', 'make a fuzzel/rofi menu for X keys'."
---

# Fuzzel Cheatsheet

Announce at start: "I'm using the fuzzel-cheatsheet skill to build a searchable cheatsheet for an app."

Throughout, `<skill-dir>` is wherever this skill is installed (commonly `~/.claude/skills/fuzzel-cheatsheet` or `~/.agents/skills/fuzzel-cheatsheet`). Resolve it to an absolute path before running a bundled script.

## What this produces

A launcher hotkey (Hyprland submap by default) that opens a `fuzzel --dmenu` fuzzy-search menu of an app's keys/commands, fed from a TSV file. The picker is whichever of fuzzel/rofi/wofi/tofi/bemenu/dmenu the machine has, resolved once when the script is written. Two contracts:

- **Reference-only** (default, universal): search and read; selecting just closes. For apps you drive inside a TUI (vifm, vim, btop).
- **Execute-on-select** (only when the app exposes external IPC): selecting runs the action — each entry carries a command that a real runner dispatches (`hyprctl dispatch`, `tmux send-keys`, `i3-msg`) behind an allowlist of safe verbs. Do not fake execute — if no IPC, ship reference-only.

## Hard rules (these fail silently if skipped)

1. **The user's config outranks upstream defaults.** Defaults are the starting point, never the answer. Whenever data comes from docs rather than a live dump, find where *this* app keeps its customization, read it, and overlay it: add every custom binding, correct every default the user rebound, drop what they disabled. A sheet of pristine upstream keys looks complete and is wrong on exactly the keys its owner presses most. Each app hides its keymap somewhere different and in its own syntax — derive it from the app (its `--help`, its man page's FILES section, what a running instance has open, its introspection commands) rather than assuming a path. The discovery and overlay procedure: `references/data-sources.md` §2.
2. **Freshness before trust.** Never trust a pre-existing local cheatsheet file/image without confirming it matches the *installed* version. A cached asset is often stale (e.g. a `v0.13` image while `v0.14.4` is installed). Always get the installed version first and match the data source to it.
3. **Ground every entry, never from memory.** Author each TSV line from an authoritative source — the app's own binding dump, its `--help`/`man`, the user's config, or a version-matched official source. Plausible-from-memory keys are wrong often enough to make the sheet untrustworthy.
4. **The provenance comments are machine-read — keep their shape exact.** Every TSV starts with:
   ```
   # source: <app> <version> / <where it came from>
   # config: <path> @ <YYYY-MM-DD>
   ```
   `<app>` is the command you would run (`vifm`, `tmux`, `lazygit`), `<version>` a bare dotted number, one `# config:` line per user config consulted. The version line catches an app upgrade; the config lines catch a later rebind, which moves no version number and is otherwise undetectable forever.
5. **Write the chord the user presses.** Expand `<leader>`, `<prefix>`, `$mainMod` to their configured values before they reach the TSV — a placeholder in the key column makes the reader look up two things instead of one.
6. **Specialize the menu script to the installed picker and its version.** Resolve which picker is present and what that build supports (`fuzzel --version` + `--help`, the package changelog for when a flag landed), then write a script that calls that one picker with those flags. Never ship runtime picker dispatch or capability probing: the machine's picker does not change between invocations, and a fallback branch for a picker nobody has is code that is never exercised and never seen to be wrong.

## Workflow

1. **Pick the contract** — reference-only, unless the app exposes external IPC (Hyprland `hyprctl`, tmux `send-keys`, i3/sway `i3-msg`).
2. **Acquire data** (read `references/data-sources.md`): prefer tiers in order — (1) app dumps its own bindings, (2) local help text, (3) version-matched remote, (4) curated fallback cross-checked against `--help`. Tier 1 wins partly because its output already includes the user's rebinds.
3. **Find and overlay the user's config** — establish how this app is customized (`data-sources.md` §2.1), follow whatever it includes, then merge. Mandatory for tiers 2–4, and worth a check even after a live dump (some apps dump defaults only). Custom entries go in as ordinary rows; a rebound default is corrected, not duplicated.
4. **Confirm freshness** against the installed version before writing anything.
5. **Write the TSV** — schema `category<TAB>key<TAB>description` (+ optional 4th `command` column for execute), with the rule-4 provenance lines on top. See `references/menu-and-wiring.md`.
6. **Validate the data** — must pass:
   ```bash
   bash <skill-dir>/scripts/validate.sh <file.tsv>
   ```
7. **Build the menu** — copy `scripts/make_cheatsheet.sh`, point `DATA` at the TSV, and specialize it per rule 6 to the picker actually installed.
8. **Wire the hotkey** — bind the menu script in the window manager's config, keeping any static image on `Shift+<key>` as a visual fallback. See `references/menu-and-wiring.md`.
9. **Validate everything** — same wrapper, now with the menu script, then reload the WM config (Hyprland: `hyprctl reload`, must report `ok`) and test the hotkey:
   ```bash
   bash <skill-dir>/scripts/validate.sh <file.tsv> <menu-script.sh>
   ```
10. **Audit the other cheatsheets** — see below. Do this every run, after the new sheet passes.

## Wrap-up: audit the other cheatsheets

The sheet just built is current; the ones built months ago may not be. Before reporting done, run:

```bash
bash <skill-dir>/scripts/audit_versions.sh
```

It compares each searchable cheatsheet's recorded version against the installed app, and each recorded config against that file's mtime, printing `OK` / `CONFIG-DRIFT` / `DRIFT` / `STALE` / `UNKNOWN` / `N/A`. Then:

- Report `STALE`, `CONFIG-DRIFT` and `UNKNOWN` rows to the user as a **suggestion**, naming the app and what moved. Never rebuild another app's cheatsheet unprompted — that is outside the task as asked.
- `DRIFT` (patch-level only) is worth one line, not an action.
- `N/A` means nothing could be verified; mention it only if the app clearly does have a local binary, which points at a wrong app token in that sheet's source comment.
- Say nothing beyond a summary count when everything is `OK`.

Scope is searchable TSV cheatsheets, where provenance is recorded and reliable. Static cheatsheet *images* wired to neighbouring hotkeys are not audited — do not report on them as if they were checked.

## When to read which file

| Situation | Read |
| --- | --- |
| Deciding where the data comes from, confirming it's current, downloading or parsing a source | `references/data-sources.md` |
| An app whose customization mechanism you have not established yet; a leader/prefix to resolve | `references/data-sources.md` §2–3 |
| TSV schema, building the menu script, wiring the hotkey, execute variant | `references/menu-and-wiring.md` |
| Making the menu search keys only, or targeting a picker other than fuzzel | `references/menu-and-wiring.md` §3–4 |

A task running normally opens nothing — these are looked up only when the situation above arises.

## Bundled scripts

Invoke with `bash <path>` (no exec bit needed); resolve `<skill-dir>` to an absolute path first.

- `scripts/validate.sh <file.tsv> [menu-script.sh]` — the single validation entry point. Runs five checks: TSV schema (delegating to `validate_tsv.py`), `bash -n` on the menu script, its exec bit, the picker that script actually calls plus `awk` on PATH, and that the WM binding exists and points at a real file. A check whose input is missing prints `SKIP`, never a silent pass; exits 1 if anything `FAIL`s. `WM_CONF` defaults to the first Hyprland/sway/i3/niri config present; point it at the config in use otherwise.
- `scripts/audit_versions.sh [extra.tsv ...]` — the wrap-up audit. Scans `~/.config/*/cheatsheet.tsv` (override with `CHEATSHEET_GLOB`), resolves each app's installed version via `--version`/`-v`/package manager, compares each recorded config's mtime, prints the status table. Advisory: always exits 0.
- `scripts/make_cheatsheet.sh` — the reference-only menu template in its fuzzel form (env: `DATA`, `PROMPT`, `WIDTH`, `LINES`, `MODE`). Copy, rename per app, and specialize to the installed picker; `references/menu-and-wiring.md` carries the flag set and minimum version per picker. `MODE=keys` restricts matching to the key column (fuzzel ≥ 1.14).
- `scripts/validate_tsv.py` — the schema engine behind `validate.sh`. Call it directly only when debugging the validator itself.
