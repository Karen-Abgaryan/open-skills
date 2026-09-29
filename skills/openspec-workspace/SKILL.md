---
name: openspec-workspace
description: "Use when OpenSpec work spans multiple repos, monorepo subfolders, or linked folders and cross-repo coordination must be resolved before any single repo acts — inspecting an OpenSpec workspace, binding a context store or initiative, deciding which repo owns a change, or splitting one initiative into separate repo-local changes. Triggers: opening an OpenSpec workspace, \"deliver X across repos A and B\", \"which repo should own this\", initiative/context-store coordination, multi-repo OpenSpec planning, starting work inside a linked repo (not a workspace) that may belong to an initiative, deciding whether a single-repo change needs cross-repo coordination. For work confined to one repo, use OpenSpec's `/opsx:*` workflow; when starting inside a repo that may join a cross-repo initiative, resolve coordination here first. Workspace and initiative flows are beta."
metadata:
  version: "1.0.0"
  updated: "2026-06-21"
---

# OpenSpec Workspace

Announce at start: "I'm using the openspec-workspace skill to coordinate multi-repo OpenSpec work."

## Beta caveat

Workspace and initiative flows are beta. Prefer plain commands, explicit paths,
and short status reports. Command behavior, state files, and JSON output are
evolving — do not build durable automation on top of them yet.

## Relationship to OpenSpec's own skills

OpenSpec installs its own per-change workflow skills and `/opsx:*` commands via
`openspec init` / `openspec update` (and `openspec workspace update --tools <agents>`
for the workspace root): explore, new/propose, continue, ff, apply, verify, sync,
archive, bulk-archive. Those — with `openspec instructions <artifact>` and
`openspec status <change>` — own authoring and the lifecycle of artifacts *inside one
repo*.

This skill does **not** replace them. It is the cross-repo coordination layer that
runs **before and around** them: resolve workspace / initiative / ownership context,
then hand each repo-local change off to OpenSpec's own `/opsx:*` workflow run in the
owning repo. Do not re-teach or duplicate the single-repo propose → apply → archive
flow here.

Two schemas ship (`openspec schemas`): `spec-driven` (default — one repo's
implementation change) and `workspace-planning` (cross-area planning artifacts).
Check `openspec schema which --all` for what a project resolves to. Choose
`workspace-planning` only when the deliverable is the cross-area *plan* itself — and
still create it as a change directory from a real repo/folder cwd, never the private
`.openspec-workspace/` view.

## Reference docs

Authoritative OpenSpec docs are bundled under `references/` (retrieved
2026-06-20 from `github.com/Fission-AI/OpenSpec/main/docs`). Read the relevant
one when this skill's summary is insufficient or behavior seems to have changed:

- `references/agent-cli-playbook.md` — agent-facing command playbook; read before running any non-trivial command sequence.
- `references/workspaces-user-guide.md` — the end-to-end human setup flow (store → initiative → open → explore → draft).
- `references/concepts.md` — full conceptual model (specs, changes, delta specs, artifacts, schemas, archive, coordination workspaces).

Re-fetch with `openspec --help` / `openspec <cmd> --help` for the exact args of the installed version, since these flows are beta and evolving.

## Core model

Use these concepts precisely and never collapse one into another:

| Concept | What it is | Where it lives |
|---------|-----------|----------------|
| **Workspace** | Private, machine-local *view* over linked repos/folders, opener state, and selected context. Not a repo. | `getGlobalDataDir()/workspaces/<name>/` with `.openspec-workspace/view.yaml`, generated `AGENTS.md`, and `<name>.code-workspace` |
| **Link** | Stable local name (`api`, `web`, `billing`, `checkout`) mapped to a repo or folder path | `view.yaml` `links:` |
| **Context store** | Durable, shared container for coordination metadata | A folder (managed local data dir by default), registered locally by id |
| **Initiative** | Durable cross-repo coordination thread inside a context store. Referenced as `<store>/<initiative>` | Files in the store: `requirements.md`, `design.md`, `decisions.md`, `questions.md`, `tasks.md` |
| **Change** | One repo-local implementation planning unit | The **owning repo** under `openspec/changes/<change-id>/` |
| **Specs** | Repo-local source of truth | The owning repo under `openspec/specs/` |

Two hard boundaries:
- **Workspace reasoning is cross-repo; change execution is repo-local.**
- Specs and changes live in the owning repo, never in workspace-local files or the context store.

## Operating rules

1. Opening a workspace does **not** mean coding should begin. Visibility ≠ commitment.
2. Never create specs or changes in the workspace folder or the context store.
3. Determine which linked repo *owns* each implementation concern before proposing a change. If ambiguous, ask.
4. Use one initiative to coordinate shared intent; use separate repo-local changes per implementation track, even within one initiative.
5. Run explore/propose and `new change` commands **from the owning repo as cwd**, not from the workspace root.
6. Do not assume the current directory is the owning repo — resolve it from links.
7. Do not invent initiatives, stores, or repo ownership. Inspect with `--json` or ask.
8. Preserve stable link names in reasoning and output.
9. After creating artifacts, report their **absolute paths** and the initiative link used.
10. If you start inside a linked repo without an opened workspace, reverse-map the repo's path against workspace `links:` to find any bound initiative **before** proposing a change — match by path, not by initiative name. If nothing links it and no contract/API/schema/migration crosses repos, treat the work as single-repo and use OpenSpec's `/opsx:*` flow.

## Workflow

### Entry point: workspace view vs. a linked repo

Determine how you arrived **before** Phase 1, because it changes how you resolve context:

- **From the workspace view** (cwd is the `.openspec-workspace/` folder, or you pass `--workspace <name>`): `workspace doctor` resolves it. Proceed to Phase 1 as written.
- **From inside a linked repo** (cwd is a repo and you did *not* open a workspace — the common case when work just "starts here"): `openspec workspace doctor` **will not resolve** from a repo cwd. First reverse-map this repo to any coordination context:

  ```bash
  openspec workspace list --json                       # all workspaces
  openspec workspace doctor --workspace <name> --json  # per workspace: read links: and bound context:
  openspec initiative list --json                      # corroborate active initiatives
  ```

  Scan each workspace's `links:` for a path equal to (or containing) your **cwd repo path**. **Match by path, not by initiative name** — an initiative that coordinates this repo may be named for the product, not the repo, so name-guessing misses it. (No first-class reverse-lookup exists yet — there is no `openspec workspace which --path`; until there is, scan `links:`. Worth requesting upstream.)

  - **A workspace links this repo and is bound to an initiative** → treat that initiative as the active coordination thread; tie your change to it in Phase 5 (`--initiative`). You do **not** need `openspec workspace open` to coordinate — binding the change from the repo cwd is enough; the workspace view is optional convenience.
  - **Nothing links this repo and no initiative covers it** → before concluding it is single-repo, apply the coordination litmus: does this change alter a contract, API, schema, event, or migration another repo consumes or produces, or need synchronized rollout? If yes and siblings are linked, surface the candidate cross-repo pairing (see Phase 1 "nothing bound") instead of siloing. If no → it is genuinely single-repo: step aside to OpenSpec's own `/opsx:*` per-change flow and do not manufacture a store or initiative.

### Phase 1 — Resolve context (always start here)

Use JSON for exact paths. Do not guess. (If you started inside a repo rather than
a workspace view, do the repo→coordination reverse-lookup above first.)

```bash
openspec context-store list --json
openspec initiative list --json
openspec initiative show <store>/<initiative> --json
openspec workspace doctor --json
openspec workspace doctor --workspace <name> --json
openspec schemas                       # which workflows exist (spec-driven, workspace-planning)
openspec schema which --all            # where each schema resolves from (bare `schema which` errors; pass --all or <name>)
```

Answer: What paths are linked? Which repos are relevant? Is an initiative
active? Is the request exploratory, planning, or implementation?

**If nothing is bound** (`context: null` with no context stores and no
initiatives): say so plainly — there is no selected initiative to resolve.
Then surface candidate cross-repo pairings by scanning each linked repo's
`openspec/changes/` for changes that are two halves of one effort, and ask
whether to create-and-bind an initiative or just explore read-only. Do not
invent a binding.

Workspace commands needing one workspace resolve it from cwd if inside a
workspace folder, else from `--workspace <name>`. With `--json` /
`--no-interactive`, an unresolved workspace fails with a structured error
instead of prompting.

### Phase 2 — Bind coordination context

If no initiative is active: ask whether to use an existing one or create a new
one; if the user named one, bind to it. If a store is needed but unspecified,
inspect available stores or ask.

**Decide where the store lives before creating it.** Ask the user; suggest the
managed default (`~/.local/share/openspec/context-stores/`, used when `--path`
is omitted) but offer a project-level path via `--path <dir>`. If project-level,
the store must sit **outside** any linked repo checkout (or be gitignored) — a
store created inside a repo would otherwise be committed, which violates the
"specs/changes repo-local, coordination metadata separate" boundary.

```bash
# Create a context store (agents pass inputs explicitly — no prompts)
openspec context-store setup <id> --no-init-git --json                 # managed data dir
openspec context-store setup <id> --path /path/to/store --init-git --json  # explicit location

# Relocate an existing store (no move command — do it by hand):
#   1. move the store folder (`.openspec-store/` + `initiatives/`) to the new path
#   2. openspec context-store unregister <id>   # forgets registration, keeps files
#   3. openspec context-store register <new-path>
# A registry-id binding survives the move; a path-selector binding does not.

# Create an initiative inside a store
openspec initiative create <id> --store <store-id> --title "Title" --summary "One line."
```

Then edit the initiative files in the store: `requirements.md`, `design.md`,
`decisions.md`, `questions.md`, `tasks.md`.

If an initiative is active, treat it as the single coordination thread and keep
all cross-repo planning aligned to it. Not every linked repo needs a change.

### Phase 3 — Map initiative → repo-local changes

For each affected repo, decide whether it needs a change, name it by repo-local
scope, keep it narrow, and tie it to the shared initiative. Example:

```
initiative: team-context/billing-launch
  billing repo  → change: add-billing-api
  checkout repo → change: add-checkout-billing-ui
```

### Phase 4 — Explore before implementing

Summarize affected links, initiative intent, and inter-repo dependencies
(contracts, APIs, migrations, rollout coupling). Propose change boundaries.
**If the user has not asked to implement, stop after exploration/planning.**

### Phase 5 — Create the change from the owning repo

Set the owning repo as cwd, then:

```bash
openspec new change <change-id> --initiative <store>/<initiative>
# optional: --store <id> | --store-path <path> | --areas <link-names>
# --schema spec-driven (default; one repo's implementation) | --schema workspace-planning (cross-area plan)
```

Do not ask the user to type this and do not run it from a workspace root. If you
only know the workspace, resolve the linked repo path first. After creation,
report absolute file paths and the initiative link. Then author artifacts and run
apply/verify/archive through OpenSpec's own per-change workflow (`/opsx:*`, or
`openspec instructions`/`openspec status`) in that repo — this skill stops at wiring
the change to its initiative.

## Opening / linking a workspace

```bash
openspec workspace setup --no-interactive --name <name> --link /repos/api --link web=/repos/web
openspec workspace list                # or: openspec workspace ls
openspec workspace link <name=path>    # records existing paths only; never clones/creates
openspec workspace relink <name> <new-path>
```

`workspace link`/`relink` record existing folders only. Linked paths need no
repo-local `openspec/` state to participate in planning. Opening and binding a
workspace to an initiative is covered next.

### Binding an initiative to a workspace

The binding is the `context:` block in `.openspec-workspace/view.yaml`. The
supported command to set it is `workspace open --initiative`, which persists the
binding **and** launches an opener — there is no persist-only mode.

- Selector forms are mutually exclusive: `--initiative <store>/<id>` **or**
  `--initiative <id> --store <store>`, never both (combining them errors
  `context_store_selector_conflict`).
- `open` always *attempts to launch* the opener (editor or agent), even with
  `--no-interactive --json` (verified: it fails with `workspace_opener_launch_failed`
  rather than binding quietly). `--prepare-only` is Unsupported (reserved for a
  future context/query command). Do not assume any flag suppresses the launch.

So there are two paths:

1. **Human / fresh entry** — open the workspace in an editor or agent:
   ```bash
   openspec workspace open --initiative <store>/<initiative> --editor
   openspec workspace open --initiative <store>/<initiative> --agent claude
   ```
2. **Agent already inside the workspace** — `open` would spawn a nested opener
   (and fail), so record the binding by writing the documented `context:` block
   into `.openspec-workspace/view.yaml`, then verify:
   ```yaml
   context:
     kind: initiative
     store:
       id: <store-id>
       selector:
         kind: registry        # registry id stays portable; use kind: path + path for path-selected stores
         id: <store-id>
     initiative:
       id: <initiative-id>
   ```
   ```bash
   openspec workspace doctor --workspace <name> --json   # confirms context resolves
   ```
   This is the one schema-bounded write this skill sanctions (reversible via
   `context: null`); it does not loosen the "metadata is not the source of truth"
   rule. Upstream lacks a non-launching `bind`/`use` command — worth requesting.

```bash
openspec workspace open                # uses stored opener (launches it)
openspec workspace update --workspace <name> --tools claude,codex  # refresh local guidance/skills
```

## Output structure

When responding inside a workspace flow, structure the answer as:

1. Active context (store / initiative / workspace)
2. Affected links/repos (by stable name)
3. Proposed repo-local changes
4. Dependencies and risks
5. Next action

## Ask vs. proceed

**Ask** when unclear: which linked repo owns a capability; whether an initiative
exists; which store to use; where a new context store should live (managed
default vs. project-level path); whether the request is exploration or
implementation; whether one initiative should split into multiple changes.

**Don't ask** when: the user named the initiative and target repo; links and
active context are already clear; or implementation in a known repo is
explicitly requested.

## Do not promise (not yet supported)

Never imply OpenSpec will do these in this beta — it does not:
- Auto sync, pull, push, or conflict handling
- Cloning repos; creating branches, worktrees, or submodules
- Workspace-level apply, verify, or archive
- Progress dashboards
- Enforced edit boundaries (so do not edit every linked repo just because it is visible)

## Safety constraints

Never: treat workspace metadata as the source of truth for system behavior;
store implementation artifacts in workspace-local files or the context store;
merge separately-owned repos into one synthetic change; start coding in all
linked repos because they are visible; assume initiative context implies edit
permission.

Always: keep specs and changes repo-local; keep initiative coordination
cross-repo; distinguish exploration from implementation; maintain explicit
ownership boundaries.
