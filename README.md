# Open Skills

A collection of skills for AI coding agents. Skills are packaged instructions and scripts that extend agent capabilities.

Skills follow the [Agent Skills](https://agentskills.io/) format.

[![skills.sh](https://skills.sh/b/Karen-Abgaryan/open-skills)](https://skills.sh/Karen-Abgaryan/open-skills)

## Available Skills

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
