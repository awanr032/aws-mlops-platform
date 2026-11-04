"""Split a Markdown manual into chunks that each remember which manual and section they came from.

Each section (## or ### heading) becomes one chunk; long sections are split on paragraph
boundaries, repeating the last paragraph of one chunk at the start of the next (overlap), so a
fact that spans a paragraph break is not cut in half. No AWS code here.
"""

from __future__ import annotations

import re

HEADING = re.compile(r"^(#{1,4})\s+(.*\S)\s*$")
MAX_CHARS = 1200


def _paragraphs(lines: list[str]) -> list[str]:
    text = "\n".join(lines).strip()
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _pack(paragraphs: list[str], max_chars: int) -> list[str]:
    """Group paragraphs into pieces of at most max_chars, with one paragraph of overlap."""
    pieces, current = [], []
    for para in paragraphs:
        if current and len("\n\n".join(current + [para])) > max_chars:
            pieces.append("\n\n".join(current))
            current = [current[-1]] if len(current[-1]) < max_chars // 2 else []
        current.append(para)
    if current:
        pieces.append("\n\n".join(current))
    return pieces


def chunk_markdown(text: str, source: str, max_chars: int = MAX_CHARS) -> list[dict]:
    """Return chunks: {id, source, title, section, text}. The first '# ' heading is the title."""
    title, section = source, "Introduction"
    sections: list[tuple[str, list[str]]] = []
    lines: list[str] = []

    for line in text.splitlines():
        match = HEADING.match(line)
        if not match:
            lines.append(line)
            continue
        level, heading = len(match.group(1)), match.group(2)
        if level == 1:
            title = heading
            continue
        sections.append((section, lines))
        section, lines = heading, []
    sections.append((section, lines))

    chunks = []
    for name, body in sections:
        for piece in _pack(_paragraphs(body), max_chars):
            chunks.append({"id": f"{source}#{len(chunks) + 1}", "source": source,
                           "title": title, "section": name, "text": piece})
    return chunks


def embedding_text(chunk: dict) -> str:
    """What gets embedded: the text plus its manual and section, so 'bearing housing bolts'
    in the pump manual is distinguishable from bearing text in the gearbox manual."""
    return f"{chunk['title']}\nSection: {chunk['section']}\n\n{chunk['text']}"
