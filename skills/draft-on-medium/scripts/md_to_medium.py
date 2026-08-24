#!/usr/bin/env python3
"""Convert an article .md into the artifacts needed to build a Medium draft.

Medium's editor has no markdown import. The reliable transfer path is a rich-text
paste, so this emits HTML restricted to the block types Medium's paste handler
understands, plus a manifest of the images that have to be uploaded by hand
(Medium will not fetch a local file out of pasted HTML).

Usage:
    md_to_medium.py ARTICLE.md [--outdir DIR]

Writes into DIR (default: /tmp/draft-on-medium-<slug>):
    body.html    rich text to put on the clipboard and paste into the editor
    body.txt     plain-text fallback for the same clipboard entry
    meta.json    title, subtitle, links, warnings
    images.json  ordered upload manifest: marker, absolute path, alt, caption
"""

import argparse
import html
import json
import os
import re
import sys

MARKER = "\u27e6IMG-{:02d}\u27e7"


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


# --- inline markup ---------------------------------------------------------

def inline(text):
    """Convert inline markdown to the subset of HTML Medium keeps on paste."""
    slots = []

    def stash(html_fragment):
        slots.append(html_fragment)
        return f"\x00{len(slots) - 1}\x00"

    # Code spans first: nothing inside them is markup.
    text = re.sub(
        r"`([^`]+)`",
        lambda m: stash(f"<code>{html.escape(m.group(1))}</code>"),
        text,
    )

    # Links before emphasis, so an underscore in a URL stays a underscore.
    def link(m):
        label, url = m.group(1), m.group(2)
        return stash(f'<a href="{html.escape(url, quote=True)}">{inline(label)}</a>')

    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, text)

    text = html.escape(text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*([^*]+)\*(?![\w*])", r"<em>\1</em>", text)
    text = re.sub(r"(?<![\w_])_([^_]+)_(?![\w_])", r"<em>\1</em>", text)

    return re.sub(r"\x00(\d+)\x00", lambda m: slots[int(m.group(1))], text)


def plain(text):
    """Strip markup for the text/plain clipboard flavour."""
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r"\1 (\2)", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"(?<![\w*])\*([^*]+)\*(?![\w*])", r"\1", text)
    return text


LINK_RE = re.compile(r"\[[^\]]+\]\((https?://[^)\s]+)\)")
BARE_URL_RE = re.compile(r"(?<![(\w])(https?://[^\s)>\]]*[^\s)>\].,;:!?'\"])")
IMAGE_RE = re.compile(r"^!\[([^\]]*)\]\(([^)\s]+)\)\s*$")
CAPTION_RE = re.compile(r"^\*([^*].*)\*$")


# --- tables ----------------------------------------------------------------

def render_table(rows, warnings):
    """Medium's editor has no table block. Render as an aligned monospace block."""
    widths = [0] * max(len(r) for r in rows)
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    if max(widths) > 30:
        warnings.append(
            "a table cell exceeds 30 characters; as a monospace block it will "
            "wrap badly on Medium — consider restructuring it as a list"
        )
    lines = ["  ".join(c.ljust(widths[i]) for i, c in enumerate(row)).rstrip() for row in rows]
    return lines


# --- block parsing ---------------------------------------------------------

def convert(md_path, outdir):
    src_dir = os.path.dirname(os.path.abspath(md_path))
    with open(md_path, encoding="utf-8") as fh:
        lines = fh.read().split("\n")

    title = subtitle = None
    body = []          # html fragments
    text_body = []     # plain-text fragments
    images = []
    warnings = []
    links = []

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # Fenced code -------------------------------------------------------
        if stripped.startswith("```"):
            i += 1
            code = []
            while i < n and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1
            escaped = html.escape("\n".join(code))
            body.append(f"<pre><code>{escaped}</code></pre>")
            text_body.append("\n".join(code))
            continue

        # Headings ----------------------------------------------------------
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            level, content = len(m.group(1)), m.group(2).strip()
            if level == 1 and title is None:
                title = plain(content).strip()
                i += 1
                continue
            if level == 3 and subtitle is None and not body:
                subtitle = plain(content).strip().strip("*").strip()
                i += 1
                continue
            # Medium offers two heading sizes; h2/h3 land on them respectively.
            tag = "h2" if level <= 2 else "h3"
            body.append(f"<{tag}>{inline(content)}</{tag}>")
            text_body.append(plain(content))
            links += LINK_RE.findall(content)
            i += 1
            continue

        # Images (+ optional italic caption on the next non-blank line) ------
        m = IMAGE_RE.match(stripped)
        if m:
            alt, rel = m.group(1), m.group(2)
            caption = ""
            j = i + 1
            while j < n and not lines[j].strip():
                j += 1
            if j < n:
                cap = CAPTION_RE.match(lines[j].strip())
                if cap:
                    caption = plain(cap.group(1)).strip()
                    i = j
            abs_path = rel if os.path.isabs(rel) else os.path.join(src_dir, rel)
            marker = MARKER.format(len(images) + 1)
            if rel.startswith(("http://", "https://")):
                warnings.append(f"image {rel} is remote; download it before uploading")
                abs_path = rel
            elif not os.path.isfile(abs_path):
                warnings.append(f"image file not found: {abs_path}")
            images.append(
                {
                    "marker": marker,
                    "index": len(images) + 1,
                    "path": abs_path,
                    "alt": alt,
                    "caption": caption,
                }
            )
            body.append(f"<p>{marker}</p>")
            text_body.append(marker)
            i += 1
            continue

        # Horizontal rule ---------------------------------------------------
        if re.fullmatch(r"(\*\s*){3,}|(-\s*){3,}|(_\s*){3,}", stripped):
            body.append("<hr>")
            text_body.append("---")
            i += 1
            continue

        # Blockquote --------------------------------------------------------
        if stripped.startswith(">"):
            quote = []
            while i < n and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip(">").strip())
                i += 1
            joined = " ".join(q for q in quote if q)
            body.append(f"<blockquote>{inline(joined)}</blockquote>")
            text_body.append(plain(joined))
            links += LINK_RE.findall(joined)
            continue

        # Table -------------------------------------------------------------
        if stripped.startswith("|") and i + 1 < n and re.fullmatch(
            r"\|[\s:\-|]+\|", lines[i + 1].strip()
        ):
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                row = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not re.fullmatch(r"[\s:\-]+", "".join(row)):
                    rows.append([plain(c) for c in row])
                i += 1
            rendered = render_table(rows, warnings)
            body.append("<pre><code>" + html.escape("\n".join(rendered)) + "</code></pre>")
            text_body.append("\n".join(rendered))
            continue

        # Lists ---------------------------------------------------------------
        m = re.match(r"^([-*+]|\d+\.)\s+(.*)$", stripped)
        if m:
            ordered = bool(re.match(r"^\d+\.$", m.group(1)))
            items = []
            while i < n:
                cur = lines[i].strip()
                lm = re.match(r"^([-*+]|\d+\.)\s+(.*)$", cur)
                if not lm:
                    break
                if bool(re.match(r"^\d+\.$", lm.group(1))) != ordered:
                    break
                items.append(lm.group(2).strip())
                i += 1
            tag = "ol" if ordered else "ul"
            body.append(
                f"<{tag}>" + "".join(f"<li>{inline(it)}</li>" for it in items) + f"</{tag}>"
            )
            for it in items:
                text_body.append(("- " if not ordered else "1. ") + plain(it))
                links += LINK_RE.findall(it)
            continue

        # Paragraph -----------------------------------------------------------
        para = []
        while i < n and lines[i].strip() and not re.match(
            r"^(#{1,6}\s|```|>|\||!\[|[-*+]\s|\d+\.\s)", lines[i].strip()
        ):
            para.append(lines[i].strip())
            i += 1
        joined = " ".join(para)
        body.append(f"<p>{inline(joined)}</p>")
        text_body.append(plain(joined))
        links += LINK_RE.findall(joined)
        for url in BARE_URL_RE.findall(joined):
            if url not in links:
                links.append(url)

    if title is None:
        die(f"{md_path}: no H1 title found — the first line must be '# Title'")
    if subtitle is None:
        warnings.append(
            "no H3 subtitle found; an H3 line directly under the title becomes "
            "the story's subtitle on Medium"
        )

    os.makedirs(outdir, exist_ok=True)
    body_html = (
        "<html><body>" + "\n".join(body) + "</body></html>"
    )
    with open(os.path.join(outdir, "body.html"), "w", encoding="utf-8") as fh:
        fh.write(body_html)
    with open(os.path.join(outdir, "body.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n\n".join(text_body) + "\n")
    with open(os.path.join(outdir, "images.json"), "w", encoding="utf-8") as fh:
        json.dump(images, fh, indent=2, ensure_ascii=False)
    meta = {
        "source": os.path.abspath(md_path),
        "title": title,
        "subtitle": subtitle or "",
        "blocks": len(body),
        "images": len(images),
        "links": links,
        "warnings": warnings,
    }
    with open(os.path.join(outdir, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, ensure_ascii=False)
    return meta, images, outdir


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("article")
    ap.add_argument("--outdir")
    args = ap.parse_args()

    if not os.path.isfile(args.article):
        die(f"no such file: {args.article}")
    slug = os.path.splitext(os.path.basename(args.article))[0]
    outdir = args.outdir or f"/tmp/draft-on-medium-{slug}"
    meta, images, outdir = convert(args.article, outdir)

    print(f"outdir:   {outdir}")
    print(f"title:    {meta['title']}")
    print(f"subtitle: {meta['subtitle'] or '(none)'}")
    print(f"blocks:   {meta['blocks']}   images: {meta['images']}   links: {len(meta['links'])}")
    for img in images:
        cap = f"  caption: {img['caption']}" if img["caption"] else ""
        print(f"  {img['marker']} -> {img['path']}{cap}")
    for w in meta["warnings"]:
        print(f"warning:  {w}")


if __name__ == "__main__":
    main()
