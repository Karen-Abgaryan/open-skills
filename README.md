# Open Skills

A collection of skills for AI coding agents. Skills are packaged instructions and scripts that extend agent capabilities.

Skills follow the [Agent Skills](https://agentskills.io/) format.

[![skills.sh](https://skills.sh/b/Karen-Abgaryan/open-skills)](https://skills.sh/Karen-Abgaryan/open-skills)

## Available Skills

### draft-on-medium

Reproduces a finished Markdown article as a Medium **draft**, never a published story. Medium retired its public write API, so the transfer runs through the live editor in a Playwright-driven browser: the user performs the login themselves, the body is pasted as Medium-native blocks, each local image is uploaded in place with its caption and alt text, and the topics are set from the `⋯` menu so the pre-publish page never loads. Run against an article that already has a draft, it revises that draft in place rather than creating a duplicate story.

**Use when:**

- Putting a written article on Medium for review
- Re-syncing an existing Medium draft after editing the source file
- Getting a shareable draft link without publishing anything

### fuzzel-cheatsheet

Builds a fuzzy-searchable cheatsheet menu (fuzzel, rofi, dmenu) of an application's keys and commands, wired to a window-manager hotkey. Entries are grounded in the app's own binding dump or version-matched documentation, never written from memory, and the user's custom keymaps are merged over upstream defaults. Each sheet records the app version and the config files it was built from, so both an upgrade and a later rebind can be detected as staleness.

**Use when:**

- Building a cheatsheet, hotkey reference, or shortcut lookup for an app
- Turning a static cheatsheet image into a searchable menu
- Wiring a searchable key reference to a keybinding
- Making a reference that covers your own rebound keys, not just the defaults

### write-commit-msg

Drafts a commit message for currently-staged Git changes in a Conventional-Commits-inspired house style: past tense, passive voice, a short headline summary over a brief narrative description. Drafts the message text only — it never runs `git commit`.

**Use when:**

- Writing, generating, or suggesting a commit message for staged changes

## Installation

```bash
npx skills add Karen-Abgaryan/open-skills
```

## Skill Structure

Each skill contains:

- `SKILL.md` — Instructions for the agent
- `scripts/` — Helper scripts for automation (optional)
- `references/` — Supporting documentation (optional)
- `tests/` — Tests for helper scripts (optional)

## License

MIT
