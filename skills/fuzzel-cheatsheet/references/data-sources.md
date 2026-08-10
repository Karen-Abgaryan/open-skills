# Data sources & freshness

## Table of contents
1. Acquisition tiers
2. The user's own bindings
3. Expanding prefixes and leaders
4. Freshness — version match and config match
5. Converting sources to text

## 1. Acquisition tiers

Try tiers in order; stop at the first that yields trustworthy, version-matched data.

| Tier | Source | Examples | How | Enables execute? |
| --- | --- | --- | --- | --- |
| **1 — app dumps its own bindings** (best: authoritative, current, and already reflects the user's rebinds) | the running app's IPC/CLI | Hyprland `hyprctl binds -j`; tmux `tmux list-keys -T prefix`; zellij `zellij setup --dump-config`; i3/sway `i3-msg -t get_bindings`; git `git config --get-regexp '^alias\.'`; vifm `:map` (inside instance) | run the dump, parse JSON/lines to TSV | yes, if IPC exists (`hyprctl dispatch`, `tmux send-keys`) |
| **2 — local help text or shipped UI definitions** | shipped docs and resources | `<app> --help`, `man <app>`, `~/.config/<app>/help.txt` (e.g. vifm's), `/usr/share/doc/<app>`, info pages; for a GUI app with no help text, the installed resource archive — Gecko `omni.ja`, Electron `app.asar`, a Qt `.rcc` — which carries the binding declarations themselves | read the key/command section; for an archive, unpack it and read the binding elements out of the UI definitions, resolving each one through the shipped locale files before it reaches the TSV | no (reference) |
| **3 — no local source** | official remote, **version-matched** | app website / GitHub release assets / wiki | get installed ver → find the matching URL → download → extract text → curate | no |
| **4 — curated fallback** | agent knowledge | only when no authoritative source is reachable | author concise entries, then **cross-check every key against `--help`/man** before shipping | no |

Prefer text/JSON/HTML sources over images. Only OCR/parse an image if no text source exists (rare).

Tiers 2–4 describe the app as shipped, not as the user runs it. Whenever data comes from one of them, section 2 is mandatory.

## 2. The user's own bindings

Defaults are the starting point, never the answer. A sheet built purely from upstream docs is wrong in two directions at once: it omits every key the user added, and it lists defaults the user has since rebound to something else. Both failures are invisible — the sheet looks complete.

Every app keeps its customization somewhere, in its own syntax, and no list of apps can be relied on to contain the one in front of you. Work it out from the app itself, in this order, stopping as soon as you have a config file and its binding syntax.

### 2.1 Locate the customization

1. **Ask the app.** Its own output names the file more often than not:
   ```bash
   <app> --help | grep -iE 'config|rc file|settings|keymap'
   man <app> | col -bx | sed -n '/^FILES/,/^[A-Z]/p'
   ```
   Some apps print their config path in `--version`, or accept `--config-file`/`--print-config`, which names the default in the error when the path is wrong.
2. **Ask a running instance** — authoritative when the docs are silent, because it reports what the app actually opened rather than what it documents:
   ```bash
   lsof -p "$(pgrep -n <app>)" | grep -vE '/(usr|proc|dev)/'
   ```
   For a config read once at startup, `strace -f -e trace=openat -o /tmp/t <app>` on a short run shows the same thing.
3. **Try the conventions**, in descending likelihood: `${XDG_CONFIG_HOME:-~/.config}/<app>/`, `~/.<app>rc`, `~/.<app>/`, `/etc/<app>/`. When nothing turns up:
   ```bash
   find ~ -maxdepth 3 -iname "*<app>*" -not -path '*/.cache/*' -not -path '*/.local/share/*'
   ```
4. **Look for an introspection command** before parsing anything — a binding dump is tier 1 and already merged. The app's `--help`, man page, or in-app help (`?`, `F1`, `:help`) will show it if it exists; the recurring shapes are a `list-*`/`show-*` subcommand, a `--dump-config`/`--print-config` flag, an IPC query, or a `:map`-style command inside the TUI.

### 2.2 Read the binding syntax out of the config

The verb differs per app but the vocabulary is small — grep the config for it and the surrounding comments usually explain the rest:

```bash
grep -inE '^\s*[a-z]*(map|bind|key|shortcut|hotkey)' <config>
```

Two things that quietly cost entries:

- **Follow includes.** `source`, `include`, `import`, `require`, a `conf.d/` directory: a user's real keymap is frequently in an included file rather than the top-level config, and the top-level one looks sparse and unmodified. Record every file you read as its own `# config:` line.
- **Resolve conditionals against this machine.** Definitions guarded by `if has('win')`, `if executable(...)`, a version test or a `$DISPLAY`/`$WAYLAND_DISPLAY` check belong in the sheet only when the condition holds here. Evaluate it (`command -v`, the environment) instead of importing every branch.

### 2.3 Overlay onto the upstream entries

1. Add each custom binding.
2. Replace the description of any default the user has rebound — a rebound key belongs to its new action, and may belong in a different category as a result.
3. Drop defaults the config disables (`<nop>`, `unbind`, `""`).
4. Merge without marking: a custom entry is written exactly like a default one. The sheet answers "what does this key do here", and the origin of a binding is not something the reader is looking up.
5. Record every config file read as a `# config:` line so the audit notices later edits (section 4).

### 2.4 Worked examples

These are the procedure's output for a few common apps — an illustration of what steps 2.1–2.2 produce, not a lookup table to consult first. An app absent from it is resolved exactly the same way.

| App | Introspection command | Customization found at |
| --- | --- | --- |
| tmux | `tmux list-keys -T prefix`, `tmux show-options -g prefix` | `~/.tmux.conf`, `~/.config/tmux/tmux.conf` |
| vim / neovim | `:verbose map` (names the defining file), `:command` | `~/.vimrc`, `~/.config/nvim/` + everything it `require`s |
| vifm | `:map`, `:command` inside a running instance | `~/.config/vifm/vifmrc` — `nnoremap`/`vnoremap`/`command!` |
| fish | `bind`, `abbr --show` | `~/.config/fish/config.fish`, `functions/` |
| zsh / bash | `bindkey`, `bind -p` | `~/.zshrc`, `~/.inputrc` |
| lazygit | — | `~/.config/lazygit/config.yml` → `keybinding:` |
| zellij | `zellij setup --dump-config` | `~/.config/zellij/config.kdl` → `keybinds` |
| kitty | `kitty +kitten show-config` | `~/.config/kitty/kitty.conf` → `map` |
| git | `git config --get-regexp '^alias\.'` | `~/.gitconfig` and its `[include]` files |
| Hyprland / sway / i3 | `hyprctl binds -j`, `i3-msg -t get_bindings` | the WM config and its sourced files |

## 3. Expanding prefixes and leaders

Write the chord the user actually presses. A row reading `<leader>ff` or `<prefix>c` is unusable — the reader has to look up two things instead of one, and the placeholder is often bound to something non-default:

- **vim/neovim** — resolve `mapleader`/`maplocalleader` (`:echo mapleader`, or the `let mapleader` line) and substitute it: `<leader>ff` with `mapleader = ","` becomes `,ff`.
- **tmux** — resolve the prefix (`tmux show-options -g prefix`, commonly rebound to `C-a`) and write it out: `C-a c`.
- **Window managers** — substitute `$mainMod`/`$mod`/`Mod4` with `Super`.

`validate_tsv.py` warns when an unexpanded placeholder survives into the key column.

## 4. Freshness — version match and config match

A pre-existing local cheatsheet is frequently stale (the vifm case: a `v0.13` image while the installed binary was `v0.14.4`). Two things go stale independently — the app, and the user's config — and the TSV records both.

1. **Get the installed version** — `<app> --version` or `-v`. If that fails, the package manager:
   - Arch/Manjaro: `pacman -Q <pkg>`
   - Debian/Ubuntu: `dpkg -s <pkg> | grep Version` / `apt-cache policy <pkg>`
   - Fedora/RHEL: `rpm -q <pkg>`
   - Homebrew: `brew list --versions <pkg>`
   - from source / pipx / cargo: `<app> --version`; check the install prefix
2. **Match the data source to that version.** For tier-3 remotes, version is usually in the URL path (e.g. `vifm.info/releases/v0.14/...`) — pick the segment that matches the installed major.minor.
3. **Record provenance** as the first lines of the TSV, in these exact forms:
   ```
   # source: <app> <version> / <where>
   # config: <path> @ <YYYY-MM-DD>
   ```
   ```
   # source: vifm 0.14.4 / vifm-help.txt (~/.config/vifm/)
   # config: ~/.config/vifm/vifmrc @ 2026-08-09
   # source: tmux 3.4 / tmux list-keys
   # config: ~/.tmux.conf @ 2026-08-09
   ```
   `<app>` must be the runnable command name and `<version>` a bare dotted number: `audit_versions.sh` reads exactly those two tokens to decide whether the sheet has gone stale. One `# config:` line per config file consulted, dated the day the sheet was built; the audit compares each file's mtime against that date and reports `CONFIG-DRIFT` when the config has moved on. Omit `# config:` only for an app with no user-configurable bindings at all.

`validate_tsv.py` fails on a malformed comment of either kind — a freeform line looks fine to a human while leaving the sheet permanently unauditable.

Do not reuse a cached image whose version you cannot confirm.

## 5. Converting sources to text

- **PDF** → `pdftotext -layout <file> -` (keeps column layout; best for cheatsheet PDFs).
- **HTML** → a web-reader tool, or `pandoc -f html -t plain`.
- **PNG/image** → text extraction is OCR. Per house vision-dispatch rules, delegate image/OCR to a vision tool — do not attempt to read the image yourself. But first look harder for a text source (`.tex`, `.md`, wiki, man page); rendering/OCR of a cheatsheet image is a last resort.
- **man page** → `man <app> | col -bx` for clean text, then take the key/command section.
