"""Parses lesson Markdown files into structured blocks the frontend renders with its own components.

Supported syntax (kept deliberately small):
  ---frontmatter---   key: value lines (topics comma-separated, sources separated by " · ")
  ## Title            starts a section          ### Title   sub-heading
  - item / 1. item    lists                     | a | b |   tables (first row = header)
  > [!tone] Title     callout (tip, warning, info, law, key); body may hold paragraphs and lists
  ::signs A.1a B.1    gallery of road signs (codes resolved by the content store)
  **bold**            inline emphasis (left to the renderer)
"""

import re
import unicodedata

LIST_RE = re.compile(r"^(-|\d+\.)\s+")
CALLOUT_RE = re.compile(r"^\[!(\w+)\]\s*(.*)$")
CALLOUT_TONES = {"tip", "warning", "info", "law", "key"}


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _is_block_start(line: str) -> bool:
    return bool(line.startswith(("#", ">", "|", "::")) or LIST_RE.match(line))


def parse_blocks(lines: list[str]) -> list[dict]:
    blocks: list[dict] = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            i += 1
            continue
        if line.startswith("### "):
            blocks.append({"type": "heading", "text": line[4:].strip()})
            i += 1
        elif line.startswith("::signs"):
            blocks.append({"type": "signs", "codes": line.split()[1:]})
            i += 1
        elif line.startswith(">"):
            chunk: list[str] = []
            while i < len(lines) and lines[i].startswith(">"):
                chunk.append(lines[i][1:].removeprefix(" ").rstrip())
                i += 1
            match = CALLOUT_RE.match(chunk[0])
            if match and match.group(1).lower() in CALLOUT_TONES:
                tone, title, body = match.group(1).lower(), match.group(2).strip(), chunk[1:]
            else:
                tone, title, body = "info", "", chunk
            blocks.append({"type": "callout", "tone": tone, "title": title, "blocks": parse_blocks(body)})
        elif line.startswith("|"):
            rows: list[list[str]] = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            blocks.append({"type": "table", "head": rows[0], "rows": rows[1:]})
        elif LIST_RE.match(line):
            ordered = line[0].isdigit()
            items: list[str] = []
            while i < len(lines) and LIST_RE.match(lines[i]) and lines[i][0].isdigit() == ordered:
                item = LIST_RE.sub("", lines[i]).strip()
                i += 1
                while i < len(lines) and lines[i].startswith("  ") and lines[i].strip():
                    item += " " + lines[i].strip()
                    i += 1
                items.append(item)
            blocks.append({"type": "list", "ordered": ordered, "items": items})
        else:
            para = [line.strip()]
            i += 1
            while i < len(lines) and lines[i].strip() and not _is_block_start(lines[i]):
                para.append(lines[i].strip())
                i += 1
            blocks.append({"type": "paragraph", "text": " ".join(para)})
    return blocks


def parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        raise ValueError("lesson is missing its frontmatter")
    _, raw, body = text.split("---", 2)
    meta: dict = {}
    for line in raw.strip().splitlines():
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    return meta, body


def parse_lesson(text: str) -> dict:
    meta, body = parse_frontmatter(text)
    sections: list[dict] = []
    intro: list[str] = []
    current: list[str] = intro
    for line in body.splitlines():
        if line.startswith("## "):
            title = line[3:].strip()
            current = []
            sections.append({"id": slugify(title), "title": title, "lines": current})
        else:
            current.append(line)
    if any(line.strip() for line in intro):
        raise ValueError(f"lesson {meta.get('slug')}: content must start with a '## ' section")
    return {
        "slug": meta["slug"],
        "order": int(meta["order"]),
        "title": meta["title"],
        "summary": meta["summary"],
        "icon": meta.get("icon", "book-open"),
        "topics": [t.strip() for t in meta.get("topics", "").split(",") if t.strip()],
        "minutes": int(meta.get("minutes", 5)),
        "free": meta.get("free", "false").lower() == "true",
        "sources": [s.strip() for s in meta.get("sources", "").split("·") if s.strip()],
        "sections": [{"id": s["id"], "title": s["title"], "blocks": parse_blocks(s["lines"])} for s in sections],
    }
