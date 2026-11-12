#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Plain-text readers for Markdown, LaTeX and TXT sources.

Each reader returns ``(text, metadata)`` where ``text`` holds one paragraph per line.
Headings are prefixed with ``HEADING_MARK`` so the chunker can treat unnumbered
headings ("## 研究背景", "\\section{Method}") as section titles.

Inline markup (``\\cite{..}``, ``$x$``, ``**bold**``, links) is kept verbatim on purpose:
the assistant copies ``sourceText`` from the scan, and the rewriter must find exactly
that text in the source file. Only non-prose blocks (code, tables, figures, display
math, bibliography) are dropped.
"""

from __future__ import annotations

import re
from pathlib import Path

HEADING_MARK = "\u0000H "
TEXT_SUFFIXES = {".md", ".markdown", ".tex", ".txt"}


def _join_wrapped(lines: list[str]) -> str:
    """Join hard-wrapped lines of one paragraph: CJK needs no space, Latin text does."""
    out = ""
    for line in (item.strip() for item in lines):
        if not line:
            continue
        if not out:
            out = line
        elif re.search(r"[A-Za-z0-9.,;:!?)\]\"'}$]$", out) and re.match(r"[A-Za-z0-9\"'(\[\\$]", line):
            out = f"{out} {line}"
        else:
            out = f"{out}{line}"
    return out


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

MD_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
MD_FENCE_RE = re.compile(r"^\s{0,3}(```|~~~)")
MD_LIST_RE = re.compile(r"^\s*(?:[-*+]|\d{1,3}[.)])\s+")
MD_TABLE_RE = re.compile(r"^\s*\|")
MD_IMAGE_ONLY_RE = re.compile(r"^\s*!\[[^\]]*\]\([^)]*\)\s*$")
MD_RULE_RE = re.compile(r"^\s{0,3}(?:-{3,}|\*{3,}|_{3,})\s*$")


def read_markdown_text(path: Path) -> tuple[str, dict[str, str]]:
    raw = path.read_text(encoding="utf-8-sig")
    metadata = {"title": "", "author": "", "subject": ""}
    front = re.match(r"^---\s*\n(.*?)\n---\s*\n", raw, re.S)
    if front:
        for key in ("title", "author"):
            found = re.search(rf"^{key}\s*:\s*['\"]?(.*?)['\"]?\s*$", front.group(1), re.M)
            if found:
                metadata[key] = found.group(1).strip()
        raw = raw[front.end():]
    raw = re.sub(r"<!--.*?-->", "", raw, flags=re.S)

    paragraphs: list[str] = []
    buffer: list[str] = []
    in_fence = False
    in_math = False

    def flush() -> None:
        if buffer:
            joined = _join_wrapped(buffer)
            if joined:
                paragraphs.append(joined)
            buffer.clear()

    for line in raw.splitlines():
        if MD_FENCE_RE.match(line):
            flush()
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.strip() == "$$":
            flush()
            in_math = not in_math
            continue
        if in_math or re.match(r"^\s*\$\$.*\$\$\s*$", line):
            continue
        heading = MD_HEADING_RE.match(line)
        if heading:
            flush()
            title = heading.group(2).strip()
            if title:
                if heading.group(1) == "#" and not metadata["title"] and not paragraphs:
                    metadata["title"] = title
                paragraphs.append(HEADING_MARK + title)
            continue
        if not line.strip() or MD_RULE_RE.match(line):
            flush()
            continue
        if MD_TABLE_RE.match(line) or MD_IMAGE_ONLY_RE.match(line):
            flush()
            continue
        if MD_LIST_RE.match(line):
            flush()
            buffer.append(MD_LIST_RE.sub("", line, count=1))
            continue
        buffer.append(re.sub(r"^\s{0,3}>\s?", "", line))
    flush()
    return "\n".join(paragraphs), metadata


# ---------------------------------------------------------------------------
# LaTeX
# ---------------------------------------------------------------------------

LATEX_SKIP_ENVS = (
    "figure", "table", "equation", "align", "gather", "multline", "eqnarray", "displaymath", "math",
    "tabular", "tabularx", "longtable", "lstlisting", "verbatim", "minted", "algorithm", "algorithmic",
    "tikzpicture", "comment", "thebibliography", "filecontents",
)
LATEX_HEADING_RE = re.compile(
    r"^\s*\\(?:part|chapter|section|subsection|subsubsection|paragraph)\*?\s*(?:\[[^\]]*\])?\s*\{(.*)\}\s*(.*)$"
)
LATEX_COMMAND_ONLY_RE = re.compile(r"^\s*(?:\\[A-Za-z@]+\*?(?:\[[^\]]*\])*(?:\{[^{}]*\})*\s*)+$")
LATEX_STOP_RE = re.compile(r"\\(?:bibliography|printbibliography|appendix)\b")


def _strip_latex_comments(text: str) -> str:
    return "\n".join(re.sub(r"(?<!\\)%.*$", "", line) for line in text.splitlines())


def _braced(text: str, command: str) -> str:
    found = re.search(rf"\\{command}\s*(?:\[[^\]]*\])?\s*\{{", text)
    if not found:
        return ""
    depth, start = 1, found.end()
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start:index]
    return ""


def _plain_latex(value: str) -> str:
    value = re.sub(r"\\(?:thanks|footnote)\s*\{[^{}]*\}", "", value)
    value = re.sub(r"\\\\|\\and\b", " ", value)
    value = re.sub(r"\\[A-Za-z]+\*?\s*(?:\[[^\]]*\])?", "", value)
    return re.sub(r"\s+", " ", value.replace("{", "").replace("}", "")).strip()


def read_latex_text(path: Path) -> tuple[str, dict[str, str]]:
    raw = _strip_latex_comments(path.read_text(encoding="utf-8-sig", errors="replace"))
    metadata = {
        "title": _plain_latex(_braced(raw, "title")),
        "author": _plain_latex(_braced(raw, "author")),
        "subject": "",
    }
    begin = raw.find("\\begin{document}")
    if begin >= 0:
        raw = raw[begin + len("\\begin{document}"):]
    end = raw.find("\\end{document}")
    if end >= 0:
        raw = raw[:end]
    # Display math never carries prose worth judging.
    raw = re.sub(r"\\\[.*?\\\]", "\n", raw, flags=re.S)
    raw = re.sub(r"\$\$.*?\$\$", "\n", raw, flags=re.S)

    paragraphs: list[str] = []
    buffer: list[str] = []
    skip_depth: list[str] = []

    def flush() -> None:
        if buffer:
            joined = _join_wrapped(buffer)
            if joined and not LATEX_COMMAND_ONLY_RE.match(joined):
                paragraphs.append(joined)
            buffer.clear()

    skip_env_re = re.compile(r"\\begin\{(" + "|".join(LATEX_SKIP_ENVS) + r")\*?\}")
    for line in raw.splitlines():
        if skip_depth:
            if re.search(r"\\end\{" + re.escape(skip_depth[-1]) + r"\*?\}", line):
                skip_depth.pop()
            continue
        if LATEX_STOP_RE.search(line):
            flush()
            break
        skip = skip_env_re.search(line)
        if skip:
            flush()
            before = line[: skip.start()].strip()
            if before and not LATEX_COMMAND_ONLY_RE.match(before):
                paragraphs.append(before)
            if not re.search(r"\\end\{" + re.escape(skip.group(1)) + r"\*?\}", line[skip.end():]):
                skip_depth.append(skip.group(1))
            continue
        if re.search(r"\\begin\{abstract\}", line):
            flush()
            paragraphs.append(HEADING_MARK + "Abstract")
            line = line.split("\\begin{abstract}", 1)[1]
        if re.search(r"\\end\{abstract\}", line):
            buffer.append(line.split("\\end{abstract}", 1)[0])
            flush()
            continue
        heading = LATEX_HEADING_RE.match(line)
        if heading:
            flush()
            title = _plain_latex(heading.group(1))
            if title:
                paragraphs.append(HEADING_MARK + title)
            if heading.group(2).strip():
                buffer.append(heading.group(2))
            continue
        if re.match(r"^\s*\\item\b", line):
            flush()
            buffer.append(re.sub(r"^\s*\\item\s*(?:\[[^\]]*\])?\s*", "", line))
            continue
        if not line.strip() or re.match(r"^\s*\\(?:begin|end)\{[^}]+\}\s*$", line) or re.match(r"^\s*\\par\s*$", line):
            flush()
            continue
        buffer.append(line)
    flush()
    return "\n".join(paragraphs), metadata


# ---------------------------------------------------------------------------
# Plain text
# ---------------------------------------------------------------------------


def read_plain_text(path: Path) -> tuple[str, dict[str, str]]:
    raw = path.read_text(encoding="utf-8-sig", errors="replace").replace("\r\n", "\n")
    blocks = re.split(r"\n\s*\n", raw)
    # Without blank lines every line is its own paragraph (typical for text copied from Word).
    if len(blocks) <= 1:
        paragraphs = [line.strip() for line in raw.splitlines() if line.strip()]
    else:
        paragraphs = [_join_wrapped(block.splitlines()) for block in blocks if block.strip()]
    return "\n".join(paragraphs), {"title": "", "author": "", "subject": ""}


def read_text_source(path: Path) -> tuple[str, dict[str, str]]:
    suffix = path.suffix.lower()
    if suffix in (".md", ".markdown"):
        return read_markdown_text(path)
    if suffix == ".tex":
        return read_latex_text(path)
    return read_plain_text(path)
