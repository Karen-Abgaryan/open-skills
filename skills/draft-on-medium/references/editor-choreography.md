# Medium editor choreography

Step-by-step browser work for building a draft. Read this before the first
`browser_*` call of a transfer.

Every selector below was taken from a working run against the live editor. They
are durable in a way accessibility labels are not: Medium's toolbar buttons carry
no `aria-label` at all, and its element refs go stale the moment the document
changes. Prefer, in order: `data-action`, `data-testid`, `aria-label`, then a
snapshot ref — and re-derive a ref immediately before using it.

Tool names appear bare (`browser_click`); the host adds its own prefix.

## Contents

- [1. Reachability](#1-reachability)
- [2. Login gate](#2-login-gate)
- [3. Open a new story](#3-open-a-new-story)
- [4. Title and subtitle](#4-title-and-subtitle)
- [5. Body paste](#5-body-paste)
- [6. Images at the markers](#6-images-at-the-markers)
- [7. Tags](#7-tags)
- [8. Share-draft link](#8-share-draft-link)
- [Selector table](#selector-table)
- [Troubleshooting](#troubleshooting)

## 1. Reachability

Cloudflare sometimes 403s `cdn-static-1.medium.com`, and when it does the editor
bundle never loads: `medium.com/new-story` returns 200, the page renders, and the
article is an empty shell. Confirm before asking anyone to log in.

The pre-flight `MEDIUM` line is a hint, not a verdict — curl gets challenged far
more readily than a real browser session, and a curl 403 has been observed while
the browser loaded the editor fine. Settle it in the browser:

```js
// browser_evaluate on medium.com/new-story
() => document.querySelectorAll('[contenteditable]').length
```

`2` means the editor is alive. `0` means it is not — read the console log for
`ERR_BLOCKED_BY_RESPONSE.NotSameOrigin` on `cdn-static-1.medium.com` to confirm,
report it, and stop. Do not retry in a loop; the block lifts on its own schedule.

## 2. Login gate

`browser_navigate` to `https://medium.com/me/stories/drafts`, then
`browser_snapshot`.

Signed in: the drafts list renders and the avatar carries the user's name.
Signed out: "Sign in" / "Get started" appear, the avatar reads "Unknown user",
and the "Write" link points at `/m/signin`.

If signed out, say this in chat and stop calling browser tools:

> A browser window is open on Medium's sign-in page. Log in there yourself —
> email link, Google, whichever you use. Tell me when you're through and I'll
> pick it up.

Then end the turn and wait for them to answer. Do not poll.

Polling is what leaks. `browser_wait_for` returns the page URL in its result
exactly as `browser_snapshot` does, so a bare wait is not the safe alternative it
looks like — one that happens to land during the federated hop captures the
callback verbatim. A Google sign-in ends on
`medium.com/m/callback/google#…access_token=…&id_token=…`: a bearer token valid
for an hour, alongside an `id_token` whose claims carry the account's email
address and Google user id. No browser call answers "are they done yet?" without
also taking that reading.

So the user's reply is the only signal. Issue no `browser_*` call between asking
them to sign in and hearing back. A sign-in link lands in a mail client and can
take a while; there is no timeout to manage, because nothing is running. When
they answer, resume with `browser_navigate` to
`https://medium.com/me/stories/drafts` and snapshot after that navigation — by
then the callback fragment is gone from the URL bar.

If a token reaches the transcript anyway, say so, point at
<https://myaccount.google.com/permissions>, and note that the transcript file on
disk keeps the value until it is scrubbed.

**Never** type an email, password, or 2FA code, never open a password manager,
and never click "Sign in with …". The login belongs to the human; the agent only
detects that it happened.

Sign-in that never seems to start is usually a window nobody can see. Before
handing over, confirm the browser is a real, mapped window — the compositor's own
client list is the check (`hyprctl clients -j` under Hyprland, `swaymsg -t
get_tree` under Sway, `wmctrl -l` under X11), and none of those touch the
browser. It may be stacked behind another window on a shared workspace; say which
workspace it is on.

A federated login can also complete at the provider and still leave Medium signed
out, when the CDN block ate the script that exchanges the token for a session.
Check reachability again before blaming the user's credentials.

## 3. Open a new story

`browser_navigate` to `https://medium.com/new-story`. The draft does not exist
server-side until the first keystroke; once it does, the URL becomes
`medium.com/p/<id>/edit`. Capture `<id>` — it is the draft's identity for the
rest of the run, and it survives every later navigation.

## 4. Title and subtitle

The editor starts with two blocks, placeholder `"Title\nTell your story…"`.

1. Click `[data-testid="editorTitleParagraph"]`, type the title.
2. Click `[data-testid="editorParagraphText"]`, type the subtitle.
3. Press `Home`, then `Shift+End` to select the subtitle line.
4. Click `button[data-action="h4"]`.

Step 4 is not optional. Typing into the second block leaves it a plain
`graf--p`; Medium only treats it as the story's subtitle once it is an `h4` with
`graf--subtitle`, which is what the toolbar's `h4` action applies. Verify:

```js
() => [...document.querySelectorAll('.js-postField .graf')]
  .slice(0, 2).map(n => n.className)
// expect graf--title on the first, graf--subtitle on the second
```

When the source article's H1 was replaced with a different title for Medium,
check that the file's H3 subtitle still adds something. A number-led title
frequently says exactly what the subtitle says, and the pair reads as a stutter.
Raise it rather than shipping the duplication.

## 5. Body paste

Medium has no markdown import, but its editor maps pasted rich text onto its own
blocks faithfully — headings, code, quote, lists, bold, italic, inline code and
links all survive. Put `body.html` on the clipboard as `text/html`, put the
cursor on an empty paragraph after the subtitle (`End`, then `Enter`), and paste:

```sh
wl-copy --type text/html < /tmp/draft-on-medium-<slug>/body.html
```

Then `browser_press_key` `ControlOrMeta+v`.

`wl-copy` backgrounds itself and serves the clipboard until it is replaced — do
not kill it before the paste. The clipboard belongs to the user: back it up first
(`wl-paste --type text/plain --no-newline > /tmp/clipboard-backup.txt`) and put
it back (`wl-copy < /tmp/clipboard-backup.txt`) once the paste has landed.

`--type text/html` advertises the same bytes under `text/plain` as well, so a
consumer that takes the plain flavour gets HTML source. Medium's handler prefers
`text/html`; literal `<p>` tags in the editor mean it did not.

This works because the browser is a real window on the same Wayland session as
the shell. A browser the agent launched itself frequently does not share that
clipboard even when it looks like an ordinary window: `Ctrl+V` lands nothing at
all, silently. One retry is enough to establish that.

When the clipboard is not shared — an agent-launched, headless or remote browser
— fall back to a synthetic paste event:

```js
// browser_evaluate, target = the editor's contenteditable body
(el) => {
  const dt = new DataTransfer();
  dt.setData('text/html', HTML);   // inline the body.html contents
  dt.setData('text/plain', TEXT);
  el.dispatchEvent(new ClipboardEvent('paste', {
    clipboardData: dt, bubbles: true, cancelable: true,
  }));
}
```

Verify against `meta.json` before going further:

```js
() => {
  const ed = document.querySelector('.js-postField[contenteditable="true"]');
  const kinds = {};
  ed.querySelectorAll('.graf').forEach(g => {
    const k = (g.className.match(/graf--(\w+)/) || [])[1] || '?';
    kinds[k] = (kinds[k] || 0) + 1;
  });
  return {
    kinds,
    markers: (ed.innerText.match(/⟦IMG-\d\d⟧/g) || []),
    links: ed.querySelectorAll('a').length,
    literalTags: /<p>|<h2>/.test(ed.innerText),
  };
}
```

Block count should be `meta.json`'s `blocks` plus two for title and subtitle,
every marker should appear exactly once, and `literalTags` must be false. If the
formatting was flattened, undo (`ControlOrMeta+z` until the body is empty) and
retry with the synthetic paste event before falling back to block-by-block typing.

One transformation is harmless and worth mentioning rather than fighting: links
are rewritten to `medium.com/r/?url=…`.

The other is not harmless. A fenced code block gets a guessed language label and
the guess is frequently wrong — a `bash` block holding an `npx` install command
has come back tagged `Auto (SQL)`, mislabelling the one line the article exists
to get readers to copy. Fix it in the editor rather than reporting it afterwards:
the language is a dropdown on the block itself. Check every fenced block, not
just the first, and re-check after any later edit that reflows the body.

## 6. Images at the markers

Medium will not fetch a local file out of pasted HTML, so each image is uploaded
at its marker. Work through `images.json` in order — the first image uploaded
also becomes the story's preview image.

Tag every marker paragraph once, up front, so each one can be addressed by a
stable selector even after the document shifts under earlier uploads:

```js
() => {
  const ed = document.querySelector('.js-postField[contenteditable="true"]');
  const out = [];
  ed.querySelectorAll('.graf').forEach(g => {
    const m = g.innerText.trim().match(/^⟦IMG-(\d\d)⟧$/);
    if (m) { g.setAttribute('data-imgslot', m[1]); out.push(m[1]); }
  });
  return out;
}
```

Then, for each entry:

1. `browser_click` `[data-imgslot="NN"]`.
2. `Home`, `Shift+End`, `Delete` — the paragraph must be genuinely empty, which
   is what makes Medium offer its insert control.
3. `browser_click` `[data-testid="editorAddButton"]`.
4. `browser_click` `button[aria-label="Add an image"]` — beware
   `button[aria-label="Add an image from Unsplash"]` sitting right beside it.
   A file chooser opens.
5. `browser_file_upload` with the entry's absolute `path`.
6. Caption: if the entry has one, `browser_type` into
   `figure.is-selected figcaption`; if not, `browser_press_key` `Escape`.
7. Alt: set it from the entry's `alt`. The control is `button[data-action="alt"]`
   on the figure's own menu, not the toolbar, and it exists only while the figure
   is `is-mediaFocused` — after typing a caption the focus sits on the
   `figcaption`, so click the figure's `img` again first. It opens an
   "Alternative text" dialog whose field is the `[contenteditable]` inside it;
   type, then Save. If this Medium build exposes no alt control at all, stop
   setting it and say so in the hand-back rather than leaving the caller to
   assume it landed.

Medium uploads and rehosts the file to `cdn-images-1.medium.com`. Confirm at the
end that no markers and no empty paragraphs remain:

```js
() => {
  const ed = document.querySelector('.js-postField[contenteditable="true"]');
  const grafs = [...ed.querySelectorAll('.graf')];
  return {
    markersLeft: (ed.innerText.match(/⟦IMG-\d\d⟧/g) || []),
    emptyParas: grafs.filter(g => g.tagName === 'P' && !g.innerText.trim()).length,
    figures: [...ed.querySelectorAll('figure')].map(f => ({
      host: (f.querySelector('img')?.src || '').split('/')[2],
      caption: f.className.includes('is-defaultValue')
        ? '(none)' : (f.querySelector('figcaption')?.innerText || '').trim(),
      alt: (f.querySelector('img')?.alt || '').trim(),
    })),
  };
}
```

A figure still carrying `is-defaultValue` has no caption — correct for entries
whose manifest caption is empty, a missed step for any other. An empty `alt` is
always a missed step: every manifest entry carries one.

The `alt` text and the caption are different fields doing different jobs. The
caption is the visible line beneath the image and carries the article's voice;
alt is what a screen reader and search see, and describes what the image shows
to someone who cannot see it. Set both. Alt comes out of the source file, where
the writer authored it deliberately — often under a house rule in the project's
style guide — so dropping it silently discards work someone did on purpose.

## 7. Tags

Use the `⋯` menu, **not** the Publish button:

1. `browser_click` the `⋯` button in the top bar (second button in the header;
   re-derive its ref from a fresh snapshot).
2. `browser_click` `button[data-action="show-tags-popover"]` ("Change topics").
3. `browser_type` each tag into `[role="combobox"]`, `Enter` after each.
4. `Escape` to close.

The combobox relabels itself from "Add a topic…" to "Add more topics…" after the
first tag, so address it by role rather than by name.

The top-bar **Publish** button does not open a modal — it *navigates* to
`/p/<id>/submission?…&submitType=publishing-post`, a full pre-publish page whose
`Publish` and `Schedule for later` buttons are one click from going live. The
tags popover reaches the same field without ever loading that page, which is why
it is the route. If something does land on the submission page, leave by its
`close` link or by navigating back to `/p/<id>/edit`.

Medium normalises tag capitalisation — "AI Agents" is stored as "Ai Agents".
Report the stored form, not the requested one.

Verify afterwards by reopening the popover and reading the chips back.

## 8. Share-draft link

`⋯` → `button[data-action="share-draft"]`. A popover appears reading "Copy and
send this link to someone and they'll be able to read your draft before you
publish", with the URL in a textbox:

```js
() => [...document.querySelectorAll('input')]
  .map(i => i.value).filter(v => (v || '').includes('medium.com'))
```

The link has the shape `https://medium.com/@user/slug-<postid>` and carries **no
`sk=` token** — that parameter belongs to friend links on published stories, not
to draft sharing. Do not promise one.

The popover shows the URL for manual copying rather than writing it to the
clipboard, so read it from the DOM as above.

## Selector table

| Target | Selector |
| --- | --- |
| Title block | `[data-testid="editorTitleParagraph"]` |
| Subtitle block | `[data-testid="editorParagraphText"]` |
| Insert (`+`) control | `[data-testid="editorAddButton"]` |
| Insert an image | `button[aria-label="Add an image"]` |
| Format toolbar | `button[data-action="…"]` — `bold`, `italic`, `link`, `h3`, `h4`, `cycle-quote`, `highlight` |
| `⋯` menu items | `button[data-action="…"]` — `share-draft`, `show-tags-popover`, `show-metadata-popover`, `show-image-picker-popover`, `show-post-submission`, `show-history-popover` |
| Editor body | `.js-postField[contenteditable="true"]` |
| Selected figure's caption | `figure.is-selected figcaption` |
| Figure alt-text control | `button[data-action="alt"]` — present only while the figure is `is-mediaFocused` |
| Tag input | `[role="combobox"]` |

Toolbar and menu buttons have **no accessible name** — they will not be findable
by label in a snapshot. `data-action` is the only reliable handle.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| Editor is an empty `<article>`; `[contenteditable]` count is 0 | The editor bundle never loaded. Check the console for `ERR_BLOCKED_BY_RESPONSE.NotSameOrigin` on `cdn-static-1.medium.com`. A Cloudflare block on the exit IP — report and stop, do not loop. |
| Login completes at the provider but Medium stays signed out | Same block, hitting `main-base.bundle…js` on the callback page — the script that exchanges the provider token for a Medium session. |
| `Ref … not found in the current page snapshot` | Refs die whenever the document changes, which every edit does. Switch to a `data-action` / `data-testid` selector. |
| Subtitle renders as body text | The `h4` action was never applied. Select the line and click `button[data-action="h4"]`. |
| Nothing appears after `Ctrl+V` | The browser is not sharing the Wayland clipboard, even though `wl-paste --list-types` shows `text/html`. Do not re-copy — go straight to the synthetic paste event. |
| Paste produced one long paragraph | Clipboard carried only `text/plain`. Confirm `wl-copy --type text/html` ran and was not superseded, then retry; else use the synthetic paste event. |
| Body shows literal `<p>` / `<h2>` tags | The editor took the plain flavour, which under `wl-copy --type text/html` is the HTML source. Undo, then use the synthetic paste event. |
| `wl-copy` not found | Session is not Wayland. Try `xclip -selection clipboard -t text/html -i`, else use the synthetic paste event. |
| File chooser never opens | The `+` control only appears on an empty line. Verify the marker paragraph is genuinely empty. |
| Uploaded image lands in the wrong place | The marker line was not cleared first, so the image was inserted after it. Undo, clear the line, retry. |
| Snapshot still shows sign-in after the user said they were done | Either the sign-in silently failed (see the CDN row above) or they finished in a different browser window. Say what the page shows and hand back; do not start polling, and never attempt the login. |
| A dialog appeared mid-run | Snapshot before reacting. Dismiss with `Escape` unless it is one you opened deliberately. |
