---
name: fuzzel-cheatsheet
description: "Build a fuzzy-searchable cheatsheet menu (fuzzel/rofi/dmenu) for any application's keys, commands, or shortcuts, wired to a launcher or window-manager hotkey. Converts a static reference image into an interactive searchable lookup. Use when the user asks to make, create, or build a cheatsheet, hotkey reference, shortcut lookup, or key-binding reference for an app (e.g. vim, vifm, tmux, zellij, fish, lazygit, btop, git, htop); when upgrading a static cheatsheet image into a searchable menu; or when wiring a searchable reference to a keybinding. Handles dumping live bindings when the app supports it, and fetching version-matched data when only a remote source exists. Triggers: 'cheatsheet for X', 'searchable keybindings', 'shortcut lookup', 'hotkey reference', 'interactive cheatsheet', 'make a fuzzel/rofi menu for X keys'."
---

# Fuzzel Cheatsheet

Announce at start: "I'm using the fuzzel-cheatsheet skill to build a searchable cheatsheet for an app."

Throughout, `<skill-dir>` is wherever this skill is installed (commonly `~/.claude/skills/fuzzel-cheatsheet` or `~/.agents/skills/fuzzel-cheatsheet`). Resolve it to an absolute path before running a bundled script.

## What this produces

A launcher hotkey (Hyprland submap by default) that opens a `fuzzel --dmenu` fuzzy-search menu of an app's keys/commands, fed from a TSV file. Two contracts:

- **Reference-only** (default, universal): search and read; selecting just closes. For apps you drive inside a TUI (vifm, vim, btop).
- **Execute-on-select** (only when the app exposes external IPC): selecting runs the action — each entry carries a command that a real runner dispatches (`hyprctl dispatch`, `tmux send-keys`, `i3-msg`) behind an allowlist of safe verbs. Do not fake execute — if no IPC, ship reference-only.

## Hard rules (these fail silently if skipped)

1. **Freshness before trust.** Never trust a pre-existing local cheatsheet file/image without confirming it matches the *installed* version. A cached asset is often stale (e.g. a `v0.13` image while `v0.14.4` is installed). Always get the installed version first and match the data source to it. Details: `references/data-sources.md`.
2. **Ground every entry, never from memory.** Author each TSV line from an authoritative source — the app's own binding dump, its `--help`/`man`, or a version-matched official source. Plausible-from-memory keys are wrong often enough to make the sheet untrustworthy.
3. **The provenance comment is machine-read — keep its shape exact.** The first line of every TSV is:
   ```
   # source: <app> <version> / <where it came from>
   ```
   `<app>` is the command you would run (`vifm`, `tmux`, `lazygit`), `<version>` a bare dotted number. Anything looser still *looks* fine — the validator only checks that a `# source:` line exists — but `audit_versions.sh` then reports the sheet as `UNKNOWN` forever, so a future stale sheet is never flagged.

## Workflow

1. **Pick the contract** — reference-only, unless the app exposes external IPC (Hyprland `hyprctl`, tmux `send-keys`, i3/sway `i3-msg`).
2. **Acquire data** (read `references/data-sources.md`): prefer tiers in order — (1) app dumps its own bindings, (2) local help text, (3) version-matched remote, (4) curated fallback cross-checked against `--help`.
3. **Confirm freshness** against the installed version before writing anything.
4. **Write the TSV** — schema `category<TAB>key<TAB>description` (+ optional 4th `command` column for execute), with the rule-3 provenance line on top. See `references/menu-and-wiring.md`.
5. **Validate the data** — must pass:
   ```bash
   bash <skill-dir>/scripts/validate.sh <file.tsv>
   ```
6. **Build the menu** — copy `scripts/make_cheatsheet.sh`, point `DATA` at the TSV.
7. **Wire the hotkey** — bind the menu script in the window manager's config, keeping any static image on `Shift+<key>` as a visual fallback. See `references/menu-and-wiring.md`.
8. **Validate everything** — same wrapper, now with the menu script, then reload the WM config (Hyprland: `hyprctl reload`, must report `ok`) and test the hotkey:
   ```bash
   bash <skill-dir>/scripts/validate.sh <file.tsv> <menu-script.sh>
   ```
9. **Audit the other cheatsheets** — see below. Do this every run, after the new sheet passes.

## Wrap-up: audit the other cheatsheets

The sheet just built is current; the ones built months ago may not be. Before reporting done, run:

```bash
bash <skill-dir>/scripts/audit_versions.sh
```

It compares each searchable cheatsheet's recorded version against the installed app and prints `OK` / `DRIFT` / `STALE` / `UNKNOWN` / `N/A`. Then:

- Report `STALE` and `UNKNOWN` rows to the user as a **suggestion**, naming the app and both versions. Never rebuild another app's cheatsheet unprompted — that is outside the task as asked.
- `DRIFT` (patch-level only) is worth one line, not an action.
- Say nothing beyond a summary count when everything is `OK`.

Scope is searchable TSV cheatsheets, where provenance is recorded and reliable. Static cheatsheet *images* wired to neighbouring hotkeys are not audited — do not report on them as if they were checked.

## When to read which file

| Situation | Read |
| --- | --- |
| Deciding where the data comes from, confirming it's current, downloading or parsing a source | `references/data-sources.md` |
| TSV schema, building the menu script, wiring the hotkey, execute variant | `references/menu-and-wiring.md` |

A task running normally opens nothing — these are looked up only when the situation above arises.

## Bundled scripts

Invoke with `bash <path>` (no exec bit needed); resolve `<skill-dir>` to an absolute path first.

- `scripts/validate.sh <file.tsv> [menu-script.sh]` — the single validation entry point. Runs five checks: TSV schema (delegating to `validate_tsv.py`), `bash -n` on the menu script, its exec bit, `fuzzel`/`awk` on PATH, and that the WM binding exists and points at a real file. A check whose input is missing prints `SKIP`, never a silent pass; exits 1 if anything `FAIL`s. Point `HYPR_CONF` at the WM config in use, or expect `SKIP wiring` on a non-Hyprland setup.
- `scripts/audit_versions.sh [extra.tsv ...]` — the wrap-up audit. Scans `~/.config/*/cheatsheet.tsv` (override with `CHEATSHEET_GLOB`), resolves each app's installed version via `--version`/`-v`/package manager, prints the status table. Advisory: always exits 0.
- `scripts/make_cheatsheet.sh` — canonical reference-only fuzzel wrapper (env: `DATA`, `PROMPT`, `WIDTH`, `LINES`). Copy and rename per app; flags (`--match-mode=fzf --no-sort --hide-prompt`) are baked in so they don't drift.
- `scripts/validate_tsv.py` — the schema engine behind `validate.sh`. Call it directly only when debugging the validator itself.
