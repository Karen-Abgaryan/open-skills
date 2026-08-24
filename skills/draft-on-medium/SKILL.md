---
name: draft-on-medium
description: "Create or update a Medium draft from a finished article .md by driving a real browser with Playwright — the user logs in by hand, then the agent creates the story, or opens an existing draft and revises only what changed, pastes the body as Medium-native formatting, uploads each local image in place with its caption and alt text, sets the topics, and hands back a shareable draft link. Use when asked to put an article on Medium, create or upload a Medium draft, update or re-sync an existing Medium draft after editing the article, publish-prep a post for Medium, transfer a markdown article to Medium, or get a Medium draft link for review."
---

# Draft on Medium

Announce at start: "I'm using the draft-on-medium skill to build a Medium draft from the article."

Takes an article that is already written as a local `.md` and reproduces it as a
Medium **draft** — never a published story. Medium retired its public write API,
so the transfer runs through the live editor in a Playwright-driven browser, with
the user performing the login themselves.

Throughout, `<skill-dir>` is wherever this skill is installed (commonly
`~/.claude/skills/draft-on-medium` or `~/.agents/skills/draft-on-medium`). Resolve
it to an absolute path before running a bundled script.

## Requirements

The script depends on tools this skill does not ship, and two of them fail
*silently* when absent:

| Tool | Used for | When missing |
| --- | --- | --- |
| `python3` (stdlib only) | conversion, every artifact read | CONVERT FAILs loudly |
| `magick` (ImageMagick 7) | image widths, cover thumbnail | the width check still prints `IMAGES PASS uniform width:` with an empty width list — never trust that PASS on a host without `magick` |
| `curl` + network | link and Medium reachability checks | reported as `SKIP no network`, indistinguishable from a down network — check the tool, not just the line |

Beyond the script, the run needs a Playwright MCP browser (every editor step)
and a vision tool or subagent for the two MANUAL image checks. A missing
browser or vision capability stops the run; it does not degrade it.

## Hard rules

- **Never click Publish.** The deliverable is a draft. Medium's top-bar Publish
  button is not a dialog — it navigates to a pre-publish page whose own Publish
  and Schedule buttons are one click from going live. Set topics through the `⋯`
  menu instead and that page never loads. If the user asks to go live, that is a
  separate, explicitly confirmed action.
- **Never authenticate on the user's behalf.** No typed emails, passwords or 2FA
  codes, no password managers, no "Sign in with …" clicks. Open the page, ask,
  stop.
- **Make no browser call at all during the login hop.** The federated callback
  URL carries a live `access_token` plus an `id_token` whose claims include the
  account's email, and every browser tool — `browser_wait_for` no less than
  `browser_snapshot` — returns the current URL in its result. Bare waits are not
  a safe poll: one that lands mid-hop writes the token into the transcript by
  itself. Ask the user to sign in, end the turn, and let their reply be the
  signal to resume.
- **Images never travel with the paste.** Medium will not fetch a local file out
  of pasted HTML. Each one is uploaded by hand at its marker, or it silently
  never appears and `⟦IMG-nn⟧` ships in the body text instead.
- **The first image uploaded becomes the preview image.** If the article's first
  image is not the right cover, settle that before uploading anything. Apply the
  cover test, aspect ratio included: an illustration cropped tight to its content
  can be a wide thin strip that reads perfectly inline and cannot survive the
  near-square crop a feed card applies. A strip-shaped first image means the
  cover is a separate asset, not the lead illustration.
- **A screenshot leak is unrecoverable.** A draft link is readable by anyone
  holding it. Leaked home paths, usernames, chat names or scrollback stop the run
  until the source image is fixed.
- **Confirm the editor loaded before asking anyone to log in.** Under a
  Cloudflare block Medium serves pages but 403s its own bundles, so the login
  succeeds and the editor then loads as an empty shell — the password gets spent
  on a run that cannot finish. The test is `[contenteditable]` count in the
  browser, not a curl status.

## Workflow

### 1. Locate the article

Take the `.md` path from the user. Image paths inside it are resolved relative to
the article's own directory, so the file and its images travel together. If the
user named no file, list the candidates and ask which one.

If the project keeps a house style guide for articles — an `article-playbook.md`,
a writing section in `AGENTS.md` or `README.md`, a `docs/style.md` — read it
before the transfer. It governs title choice, cover selection and the
pre-publish checks, and it changes more often than this skill does. Where no such
file exists, the defaults stated below apply.

### 1a. New draft, or an update to one that exists?

Ask before opening the browser. An article that has already been through this
skill has a draft behind it, and that draft is revised in place: a second
transfer produces a duplicate story, leaves the original live at its own URL, and
strands the share link the user has already circulated.

If a draft exists, get its edit URL — `medium.com/p/<id>/edit`, or from
`medium.com/me/stories/drafts` — and open that instead of `new-story`. Skip the
title/subtitle/paste sequence entirely; an update is a diff, not a re-paste.
Compare the file against the draft and touch only what moved:

| What changed in the file | What to do in the editor |
| --- | --- |
| title or subtitle | click into the line, select it, retype |
| a paragraph, no inline formatting | select that paragraph alone and retype it |
| a span inside a paragraph that carries bold, italic or a link | do **not** retype the paragraph — retyping drops the inline markup. Set a DOM Range over the changed span alone and replace it with `document.execCommand('insertText', false, …)`, then reload the page and confirm both the new text and the surviving `<strong>` / `<a>` |
| an image's pixels | click the figure, delete it, re-upload at the same spot — the caption and alt do not survive the swap, so set both again |
| only a caption or alt | edit the field in place, no re-upload |
| topics | the `⋯` menu, exactly as for a new draft |

Re-uploading the *first* image re-triggers the preview-image rule below, so
re-check the cover after it. Then run the same verification sweep the
choreography uses after a fresh build: markers, empty paragraphs, figure hosts,
captions and alt.

### 2. Pre-flight

```sh
bash <skill-dir>/scripts/validate.sh <article.md>
```

One command, one status line per check: conversion, structure, image files,
external URLs, cover thumbnail, leak inspection, and a reachability hint. It
exits non-zero on a blocking failure — a missing image file, a dead URL — and
writes the transfer artifacts to `/tmp/draft-on-medium-<slug>/`:

| File | Use |
| --- | --- |
| `body.html` | rich text to paste into the editor |
| `body.txt` | plain-text clipboard fallback |
| `meta.json` | title, subtitle, block count, links, warnings |
| `images.json` | ordered upload manifest: marker, absolute path, alt, caption |
| `cover-200px.png` | the cover at feed size, for the legibility check |

Two checks report `MANUAL` because no script can settle them:

- **Cover legibility** — whether the subject still reads in `cover-200px.png`.
- **Leaked content** — every image in the manifest, checked for home paths,
  usernames, real names, chat titles, addresses and terminal scrollback bleeding
  through translucent windows. This applies to images the agent did not produce.

Both are image inspection. If the host's rules require image work to be
delegated, hand them to a vision-capable subagent or a vision MCP tool such as
`analyze_image` (the host prefix varies) rather than eyeballing them directly.

The `MEDIUM` line is a hint, not a gate. Cloudflare challenges curl far more
readily than a browser, and a curl 403 has been seen while the browser loaded the
editor perfectly — settle reachability in the browser, per the reference.

Report the pre-flight result as a short summary. A `WARN` is information; a
`FAIL` or a leak stops the run.

### 3. Confirm the metadata

Before opening the browser, put in front of the user:

- the title and subtitle the converter extracted
- the topics being proposed — Medium takes five, and the mix matters: broad ones
  carry distribution, narrow ones bring the right readers
- which image becomes the preview image

The title in the file is not automatically the title for Medium. A project often
carries a plain descriptive H1 in the repo and a sharper, number-led variant for
a feed; if the style guide says so, or the H1 reads as the plain variant, raise
it rather than typing the file's title by default. When the title does change,
re-check the subtitle against the new title *and* against the opening
paragraphs. A subtitle must add something the title does not, and must not
repeat a line the reader is about to meet in the body — that second collision is
the one that survives review, reading as a stutter the moment the reader arrives
at the paragraph it came from.

### 4. Build the draft

On an update this step is the table in 1a instead; take only the login,
image-upload, tags and verification passages from the choreography, and never
navigate to `new-story`.

Read `references/editor-choreography.md` and follow it. In outline: confirm the
editor loads, wait out the login, open `medium.com/new-story`, type the title,
type the subtitle and apply the `h4` action to it, paste `body.html` from the
clipboard, upload each image at its marker with its caption, set the topics from
the `⋯` menu, then read the share-draft link out of its popover.

Medium's toolbar and menu buttons carry no accessible name, and element refs go
stale on every edit. Target `data-action` and `data-testid` attributes; the
reference has the full selector table.

### 5. Hand back

Report the share-draft link, the edit URL (`medium.com/p/<id>/edit`), and
anything that did not survive the transfer cleanly: a table rendered as a
monospace block, a topic Medium re-cased, an alt field this Medium build gave no
way to set. On an update, report instead what was touched and what was
deliberately left alone. Do not publish, and do not offer to.

### 6. Offer to clear the browser profile

The login outlives the run. Playwright MCP drives a real browser against a
persistent profile directory, so the session cookies the user created in step 4
stay on disk — and a federated sign-in leaves the provider's cookies there too,
which is a whole Google or Facebook account session, not a Medium-only one. Each
new browser build gets its own profile, so the old ones accumulate unnoticed
beside the current one.

Once the link is handed back, ask whether to clear it, and state the cost in the
same breath: **clearing means the next run starts signed out and needs the login
hop again.** That trade is the user's to make — one may prefer a warm profile for
a draft they will revise tomorrow, another may not want an account session parked
in a cache directory. Clear nothing without an answer.

If they say yes, delete the profile directories. Locate them rather than assuming
a path; on a Linux host they have been `~/.cache/ms-playwright-mcp/` with one
`mcp-<channel>-<hash>/` directory per browser build. Deleting those directories
is the entire cleanup — nothing in the article, the draft, or the transfer
artifacts depends on them.

## Reference

Read on trigger, not on schedule. A run that goes normally opens only
`editor-choreography.md`.

| Trigger | File |
| --- | --- |
| about to make the first `browser_*` call | `references/editor-choreography.md` |
| paste came out unformatted, an upload failed, a ref went stale | `references/editor-choreography.md`, troubleshooting table |
| a construct is missing from the draft, or the converter mangled a block | `scripts/md_to_medium.py` — the mapping is the code |

## Markdown that Medium cannot hold

The converter maps what maps and degrades the rest. Say which of these happened,
so the loss is a decision rather than a surprise:

- **Tables** become an aligned monospace block. A cell over 30 characters raises
  a warning, because it will wrap into something unreadable — restructure it as a
  list in the source instead.
- **Two heading levels.** `##` and `###` land on Medium's large and small title;
  anything deeper collapses into the small one.
- **Footnotes, raw HTML blocks and nested lists** have no Medium equivalent and
  flatten into paragraphs.

Medium also rewrites on its own account: links become `medium.com/r/?url=…` and
topics get title-cased ("AI Agents" is stored as "Ai Agents"). Both are
unavoidable, so mention them and move on. A fenced code block is also given a
guessed language label, and that one is not unavoidable — it is a dropdown on
the block, the guess is often wrong, and a wrong label sits on the exact line
readers are meant to copy. Correct it during the run.
