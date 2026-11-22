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


# \input{x}, \include{x}, \subfile{x}, \import{dir/}{x}, \subimport{dir/}{x} (also starred forms)
LATEX_INCLUDE_RE = re.compile(
    r"\\(input|include|subfile|import|subimport|inputfrom|subinputfrom|includefrom|subincludefrom)\*?\s*"
    r"(?:\{([^{}]*)\}\s*)?\{([^{}]+)\}"
)
LATEX_TWO_ARG_INCLUDES = {"import", "subimport", "inputfrom", "subinputfrom", "includefrom", "subincludefrom"}
LATEX_MAX_INCLUDE_DEPTH = 12


def _read_tex(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def resolve_latex_include(directory: Path, name: str) -> Path | None:
    """Resolve an include target the way LaTeX does: as given, then with .tex appended."""
    name = name.strip().strip('"')
    if not name:
        return None
    candidate = Path(name)
    if not candidate.is_absolute():
        candidate = directory / candidate
    for option in (candidate, candidate.with_name(candidate.name + ".tex")):
        if option.is_file():
            return option.resolve()
    return None


def latex_include_targets(content: str, base_dir: Path, file_dir: Path) -> list[tuple[int, int, Path | None, str]]:
    """(start, end, resolved path or None, raw name) for every include command in comment-free ``content``.

    \\input and \\include resolve against the main file's folder (LaTeX runs there), \\import{dir}{file}
    against ``dir``, and \\subimport / \\subfile against the including file's folder. Only .tex files (or
    names without an extension) are followed: \\input{fig.tikz} is not prose.
    """
    targets: list[tuple[int, int, Path | None, str]] = []
    for match in LATEX_INCLUDE_RE.finditer(content):
        command, folder, name = match.group(1), match.group(2), match.group(3)
        two_args = command in LATEX_TWO_ARG_INCLUDES
        if two_args != (folder is not None):
            continue
        suffix = Path(name.strip()).suffix.lower()
        if suffix and suffix != ".tex":
            continue
        if command in ("import", "inputfrom", "includefrom"):
            root = Path(folder.strip())
            directory = root if root.is_absolute() else base_dir / root
        elif two_args:
            directory = file_dir / folder.strip()
        elif command == "subfile":
            directory = file_dir
        else:
            directory = base_dir
        targets.append((match.start(), match.end(), resolve_latex_include(directory, name), name.strip()))
    return targets


def _document_body(content: str) -> str:
    """A \\subfile carries its own preamble and document environment; only the body is included."""
    begin = content.find("\\begin{document}")
    if begin < 0:
        return content
    body = content[begin + len("\\begin{document}"):]
    end = body.find("\\end{document}")
    return body[:end] if end >= 0 else body


def expand_latex_includes(path: Path, missing: list[str] | None = None, files: list[Path] | None = None) -> str:
    """Comment-free source of ``path`` with every included .tex file spliced in at its include command.

    ``files`` receives the main file and every included file in reading order; ``missing`` receives
    include targets that were not found. Include cycles and very deep nesting are cut off.
    """
    main = path.resolve()
    base_dir = main.parent
    files = files if files is not None else []
    missing = missing if missing is not None else []

    def expand(current: Path, stack: tuple[Path, ...]) -> str:
        if current not in files:
            files.append(current)
        content = _strip_latex_comments(_read_tex(current))
        out: list[str] = []
        last = 0
        for start, end, target, name in latex_include_targets(content, base_dir, current.parent):
            out.append(content[last:start])
            last = end
            if target is None:
                missing.append(name)
                continue
            if target in stack or len(stack) > LATEX_MAX_INCLUDE_DEPTH:
                continue
            body = expand(target, stack + (target,))
            if content.startswith("\\subfile", start):
                body = _document_body(body)
            out.append("\n" + body + "\n")  # an included file starts and ends a paragraph
        out.append(content[last:])
        return "".join(out)

    return expand(main, (main,))


def latex_project_files(path: Path) -> list[Path]:
    """The main .tex file followed by every .tex file it includes, in reading order."""
    files: list[Path] = []
    expand_latex_includes(path, files=files)
    return files


def latex_project_tree(path: Path) -> list[tuple[Path, tuple[int, ...]]]:
    """Every file of a LaTeX project with a sort key for reading order.

    The key is the chain of line numbers of the include commands that lead to the file (empty for the
    main file). A text position at ``line`` in that file sorts as ``key + (line, offset)``, so matches
    spread over several files can be put in the order a reader meets them.
    """
    main = path.resolve()
    base_dir = main.parent
    tree: list[tuple[Path, tuple[int, ...]]] = []

    def walk(current: Path, key: tuple[int, ...], stack: tuple[Path, ...]) -> None:
        if any(item == current for item, _key in tree):
            return
        tree.append((current, key))
        content = _strip_latex_comments(_read_tex(current))
        for start, _end, target, _name in latex_include_targets(content, base_dir, current.parent):
            if target is None or target in stack or len(stack) > LATEX_MAX_INCLUDE_DEPTH:
                continue
            walk(target, key + (content.count("\n", 0, start) + 1,), stack + (target,))

    walk(main, (), (main,))
    return tree


def _relative_label(item: Path, root: Path) -> str:
    try:
        return item.relative_to(root).as_posix()
    except ValueError:
        return str(item)


def read_latex_text(path: Path) -> tuple[str, dict[str, str]]:
    missing: list[str] = []
    files: list[Path] = []
    raw = expand_latex_includes(path, missing=missing, files=files)
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
    if len(files) > 1:
        root = path.resolve().parent
        metadata["includedFiles"] = [_relative_label(item, root) for item in files[1:]]
    if missing:
        metadata["missingIncludes"] = sorted(set(missing))
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
