#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Apply user-confirmed AI-check replacements to a new DOCX file.

The script does not call AI. It only validates and applies replacement JSON
created by the assistant after the user has approved the changes.

Replacements are applied as a character-level diff inside the matched paragraph:
unchanged characters keep their original runs, so formatting (bold, superscript
citation marks, fonts), equations, images, fields and bookmarks elsewhere in the
paragraph survive. With ``--track-changes`` the edits are written as Word
revisions (w:ins / w:del) that can be accepted or rejected in Word.

Markdown (.md), LaTeX (.tex) and plain-text (.txt) sources are supported too: the
replacement is spliced into a copy of the file and a unified diff is written next to
it for review. LaTeX/Markdown markup such as cite/ref commands, $x$, links and
footnotes must survive every rewrite.
"""

from __future__ import annotations

import argparse
import copy
import difflib
import json
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from ai_check import iter_body_paragraph_elements, paragraph_units, w_tag  # noqa: E402
from source_formats import TEXT_SUFFIXES  # noqa: E402

XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
IGNORABLE_RE = re.compile(r"(?:\s| |​|‌|‍|⁠|⁣)")
MIN_EQUAL_RUN = 3  # equal stretches shorter than this between two edits are folded into one edit
REVISION_AUTHOR = "AI-check"


@dataclass
class Replacement:
    sourceText: str
    replacementText: str
    chunkId: str = ""
    reason: str = ""
    occurrence: int | None = None
    allowNumberChange: bool = False


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def normalize_replacements(payload: Any) -> list[Replacement]:
    raw = payload.get("replacements", payload) if isinstance(payload, dict) else payload
    if not isinstance(raw, list):
        raise ValueError("replacements JSON must be a list or an object with a replacements list")
    replacements: list[Replacement] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"replacement #{index} must be an object")
        source = str(item.get("sourceText") or item.get("source") or "").strip()
        replacement = str(item.get("replacementText") or item.get("replacement") or "").strip()
        if not source:
            raise ValueError(f"replacement #{index} missing sourceText")
        if not replacement:
            raise ValueError(f"replacement #{index} missing replacementText")
        occurrence = item.get("occurrence")
        replacements.append(
            Replacement(
                sourceText=source,
                replacementText=replacement,
                chunkId=str(item.get("chunkId") or "").strip(),
                reason=str(item.get("reason") or "").strip(),
                occurrence=int(occurrence) if occurrence is not None and str(occurrence).strip() else None,
                allowNumberChange=bool(item.get("allowNumberChange")),
            )
        )
    return replacements


def normalize_for_match(text: str) -> str:
    return IGNORABLE_RE.sub("", text or "")


CITATION_RE = re.compile(r"\[\d+(?:\s*[-–,，、]\s*\d+)*\]")


def citation_marks(text: str) -> set[str]:
    return set(CITATION_RE.findall(text or ""))


def validate_replacement_citations(item: Replacement) -> list[str]:
    required = citation_marks(item.sourceText)
    current = citation_marks(item.replacementText)
    missing = sorted(required - current)
    return missing


PROTECTED_MARKUP_RE = re.compile(
    r"\\(?:cite[a-zA-Z]*|parencite|textcite|autocite|ref|eqref|autoref|cref|Cref|label|url|href)\*?(?:\[[^\]]*\])*\{[^{}]*\}"
    r"|(?<![\\$])\$[^$\n]+\$"  # inline math
    r"|\[@[^\]]+\]|\[\^[^\]]+\]"  # pandoc citations, Markdown footnotes
    r"|!?\[[^\]]*\]\([^)]*\)"  # Markdown links and images
    r"|`[^`\n]+`"
)


def protected_markup(text: str) -> list[str]:
    return list(dict.fromkeys(PROTECTED_MARKUP_RE.findall(text or "")))


def validate_replacement_markup(item: Replacement) -> list[str]:
    """LaTeX/Markdown references, math, links and code must be carried over verbatim."""
    return [token for token in protected_markup(item.sourceText) if token not in item.replacementText]


def number_tokens(text: str) -> set[str]:
    # Citation keys and labels (\cite{li2023}) are not facts; markup is validated separately.
    return set(re.findall(r"\d+(?:\.\d+)?", CITATION_RE.sub(" ", PROTECTED_MARKUP_RE.sub(" ", text or ""))))


def validate_replacement_numbers(item: Replacement) -> list[str]:
    """Numbers are facts: a rewrite must keep every number of the source unless explicitly allowed."""
    if item.allowNumberChange:
        return []
    return sorted(number_tokens(item.sourceText) - number_tokens(item.replacementText), key=lambda n: (len(n), n))


# ---------------------------------------------------------------------------
# paragraph matching
# ---------------------------------------------------------------------------


def all_paragraphs(document: Any) -> list[Any]:
    return list(iter_body_paragraph_elements(document, include_tables=True))


def units_text(units: list[tuple[str, Any, int]]) -> str:
    return "".join(char for char, _element, _offset in units)


def locate_span(units: list[tuple[str, Any, int]], source: str) -> tuple[int, int] | None:
    """Return the [start, end) unit range matching ``source`` (exact first, then whitespace-insensitive)."""
    text = units_text(units)
    start = text.find(source)
    if start >= 0:
        return start, start + len(source)
    normalized_source = normalize_for_match(source)
    if not normalized_source:
        return None
    kept = [index for index, (char, _element, _offset) in enumerate(units) if not IGNORABLE_RE.match(char)]
    compact = "".join(units[index][0] for index in kept)
    found = compact.find(normalized_source)
    if found < 0:
        return None
    return kept[found], kept[found + len(normalized_source) - 1] + 1


def find_matches(document: Any, item: Replacement) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for paragraph_index, paragraph in enumerate(all_paragraphs(document)):
        units = paragraph_units(paragraph)
        text = units_text(units)
        if not text.strip():
            continue
        if locate_span(units, item.sourceText) is not None:
            matches.append(
                {
                    "paragraphIndex": paragraph_index,
                    "direct": item.sourceText in text,
                    "paragraphText": text,
                }
            )
    return matches


# ---------------------------------------------------------------------------
# run-level editing
# ---------------------------------------------------------------------------


def make_run(rpr: Any, text: str) -> Any:
    """A w:r with a copy of ``rpr`` holding ``text`` (tabs and line breaks become w:tab / w:br)."""
    from docx.oxml import OxmlElement  # type: ignore

    run = OxmlElement("w:r")
    if rpr is not None:
        run.append(copy.deepcopy(rpr))
    for piece in re.split(r"([\t\n])", text):
        if not piece:
            continue
        if piece == "\t":
            run.append(OxmlElement("w:tab"))
        elif piece == "\n":
            run.append(OxmlElement("w:br"))
        else:
            t = OxmlElement("w:t")
            t.text = piece
            t.set(XML_SPACE, "preserve")
            run.append(t)
    return run


def run_of(element: Any) -> Any:
    parent = element
    while parent is not None and parent.tag != w_tag("r"):
        parent = parent.getparent()
    return parent


def explode_run(run: Any, created: list[Any]) -> None:
    """Split a run into one run per visible character / non-text child so edits can address single characters."""
    parent = run.getparent()
    position = parent.index(run)
    rpr = run.find(w_tag("rPr"))
    pieces = []
    for child in list(run):
        if child.tag == w_tag("rPr"):
            continue
        if child.tag == w_tag("t"):
            pieces.extend(make_run(rpr, char) for char in (child.text or ""))
        else:
            piece = make_run(rpr, "")
            piece.append(copy.deepcopy(child))
            pieces.append(piece)
    parent.remove(run)
    for offset, piece in enumerate(pieces):
        parent.insert(position + offset, piece)
    created.extend(pieces)


def is_plain_run(run: Any, paragraph: Any) -> bool:
    """Ordinary body text: not a superscript/subscript mark and not inside a hyperlink or field wrapper."""
    rpr = run.find(w_tag("rPr"))
    if rpr is not None and rpr.find(w_tag("vertAlign")) is not None:
        return False
    return run.getparent() is paragraph


def coalesce_opcodes(opcodes: list[tuple[str, int, int, int, int]]) -> list[tuple[str, int, int, int, int]]:
    """Fold tiny unchanged stretches (a lone 的 or ，) between two edits into one edit, so the
    result reads as phrase-level changes instead of character confetti in Word's revision view."""
    merged: list[tuple[str, int, int, int, int]] = []
    index = 0
    while index < len(opcodes):
        tag, i1, i2, j1, j2 = opcodes[index]
        if tag == "equal":
            merged.append(opcodes[index])
            index += 1
            continue
        end_i, end_j = i2, j2
        cursor = index + 1
        while cursor < len(opcodes):
            next_tag, n_i1, n_i2, _n_j1, n_j2 = opcodes[cursor]
            if next_tag != "equal":
                end_i, end_j = n_i2, n_j2
                cursor += 1
            elif n_i2 - n_i1 < MIN_EQUAL_RUN and cursor + 1 < len(opcodes) and opcodes[cursor + 1][0] != "equal":
                end_i, end_j = opcodes[cursor + 1][2], opcodes[cursor + 1][4]
                cursor += 2
            else:
                break
        kind = "insert" if i1 == end_i else "delete" if j1 == end_j else "replace"
        merged.append((kind, i1, end_i, j1, end_j))
        index = cursor
    return merged


class RevisionIds:
    def __init__(self, document: Any) -> None:
        ids = [0]
        for element in document.element.iter():
            value = element.get(w_tag("id"))
            if value is not None and value.lstrip("-").isdigit():
                ids.append(int(value))
        self.next_id = max(ids) + 1
        self.date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def wrapper(self, kind: str) -> Any:
        from docx.oxml import OxmlElement  # type: ignore

        element = OxmlElement(f"w:{kind}")
        element.set(w_tag("id"), str(self.next_id))
        element.set(w_tag("author"), REVISION_AUTHOR)
        element.set(w_tag("date"), self.date)
        self.next_id += 1
        return element


def mark_deleted(runs: list[Any], revisions: RevisionIds) -> Any:
    """Wrap runs in w:del (grouping adjacent siblings), turn their w:t into w:delText, return the last wrapper."""
    groups: list[list[Any]] = []
    for run in runs:
        if groups and groups[-1][-1].getnext() is run:
            groups[-1].append(run)
        else:
            groups.append([run])
    wrapper = None
    for group in groups:
        parent = group[0].getparent()
        wrapper = revisions.wrapper("del")
        parent.insert(parent.index(group[0]), wrapper)
        for run in group:
            wrapper.append(run)  # lxml moves the element
            for t in run.findall(w_tag("t")):
                t.tag = w_tag("delText")
            for instr in run.findall(w_tag("instrText")):
                instr.tag = w_tag("delInstrText")
    return wrapper


def merge_created_runs(paragraph: Any, created: list[Any]) -> None:
    """Re-join the single-character runs created during editing when their formatting is identical."""
    from lxml import etree  # type: ignore

    ours = set(created)  # holding the elements keeps their lxml proxies (and identities) alive

    def text_tag(run: Any) -> str | None:
        tags = {child.tag for child in run if child.tag != w_tag("rPr")}
        if len(tags) == 1 and tags <= {w_tag("t"), w_tag("delText")}:
            return tags.pop()
        return None

    def rpr_key(run: Any) -> bytes:
        rpr = run.find(w_tag("rPr"))
        return etree.tostring(rpr) if rpr is not None else b""

    for parent in [paragraph, *paragraph.iter()]:
        previous = None
        for child in list(parent):
            tag = text_tag(child) if child.tag == w_tag("r") and child in ours else None
            if tag and previous is not None and text_tag(previous) == tag and rpr_key(previous) == rpr_key(child):
                target = previous.findall(tag)[-1]
                for piece in child.findall(tag):
                    target.text = (target.text or "") + (piece.text or "")
                parent.remove(child)
                continue
            previous = child if tag else None


def apply_to_paragraph(
    paragraph: Any,
    source_text: str,
    replacement_text: str,
    revisions: RevisionIds | None = None,
) -> bool:
    units = paragraph_units(paragraph)
    span = locate_span(units, source_text)
    if span is None:
        return False
    start, end = span

    created: list[Any] = []
    affected = []
    for index in range(start, end):
        run = run_of(units[index][1])
        if run is not None and all(run is not seen for seen in affected):
            affected.append(run)
    for run in affected:
        explode_run(run, created)
    units = paragraph_units(paragraph)  # same text, now one run per character inside the span
    span_runs = [run_of(units[index][1]) for index in range(start, end)]
    original = units_text(units[start:end])

    def new_node(style_run: Any, text: str) -> Any:
        run = make_run(style_run.find(w_tag("rPr")) if style_run is not None else None, text)
        created.append(run)
        if revisions is None:
            return run
        wrapper = revisions.wrapper("ins")
        wrapper.append(run)
        return wrapper

    matcher = difflib.SequenceMatcher(None, original, replacement_text, autojunk=False)
    # Apply from the end so the runs before each edit are still untouched when it is applied.
    for kind, i1, i2, j1, j2 in reversed(coalesce_opcodes(matcher.get_opcodes())):
        if kind == "equal":
            continue
        new_text = replacement_text[j1:j2]
        if kind == "insert":
            prev_run = span_runs[i1 - 1] if i1 > 0 else None
            next_run = span_runs[i1] if i1 < len(span_runs) else None
            prefer_prev = prev_run is not None and (next_run is None or is_plain_run(prev_run, paragraph) or not is_plain_run(next_run, paragraph))
            node = new_node(prev_run if prefer_prev else next_run, new_text)
            if prefer_prev:
                prev_run.addnext(node)
            else:
                next_run.addprevious(node)
            continue
        doomed = span_runs[i1:i2]
        node = new_node(doomed[0], new_text) if kind == "replace" else None
        if revisions is not None:
            last_wrapper = mark_deleted(doomed, revisions)
            if node is not None:
                last_wrapper.addnext(node)  # deleted text first, then the inserted text
        else:
            if node is not None:
                doomed[0].addprevious(node)
            for run in doomed:
                run.getparent().remove(run)

    merge_created_runs(paragraph, created)
    return True


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Markdown / LaTeX / TXT sources
# ---------------------------------------------------------------------------


def is_text_source(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES


def read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def find_text_spans(content: str, source: str) -> list[tuple[int, int]]:
    """All non-overlapping spans of ``source`` in ``content``: exact first, then ignoring whitespace."""
    spans: list[tuple[int, int]] = []
    start = content.find(source)
    while start >= 0:
        spans.append((start, start + len(source)))
        start = content.find(source, start + len(source))
    if spans:
        return spans
    needle = normalize_for_match(source)
    if not needle:
        return []
    kept = [index for index, char in enumerate(content) if not IGNORABLE_RE.match(char)]
    compact = "".join(content[index] for index in kept)
    found = compact.find(needle)
    while found >= 0:
        spans.append((kept[found], kept[found + len(needle) - 1] + 1))
        found = compact.find(needle, found + len(needle))
    return spans


def line_of(content: str, offset: int) -> int:
    return content.count("\n", 0, offset) + 1


def validate_item(item: Replacement) -> tuple[list[str], list[str], list[str]]:
    return validate_replacement_citations(item), validate_replacement_numbers(item), validate_replacement_markup(item)


def dry_run_text(source: Path, replacements_path: Path) -> dict[str, Any]:
    content = read_text_file(source)
    items = []
    for item in normalize_replacements(load_json(replacements_path)):
        spans = find_text_spans(content, item.sourceText)
        missing_citations, missing_numbers, missing_markup = validate_item(item)
        unique = len(spans) == 1 or (item.occurrence is not None and 1 <= item.occurrence <= len(spans))
        items.append(
            {
                "chunkId": item.chunkId,
                "matchCount": len(spans),
                "missingCitations": missing_citations,
                "missingNumbers": missing_numbers,
                "missingMarkup": missing_markup,
                "willApply": unique and not missing_citations and not missing_numbers and not missing_markup,
                "matches": [{"line": line_of(content, start)} for start, _end in spans[:5]],
            }
        )
    return {
        "sourcePath": str(source.resolve()),
        "replacementPath": str(replacements_path.resolve()),
        "total": len(items),
        "applicable": sum(1 for item in items if item["willApply"]),
        "items": items,
    }


def skip_reason(item: Replacement, match_count: int) -> str:
    missing_citations, missing_numbers, missing_markup = validate_item(item)
    if missing_citations:
        return f"missing citation marks: {', '.join(missing_citations)}"
    if missing_markup:
        return f"missing LaTeX/Markdown markup: {', '.join(missing_markup)}"
    if missing_numbers:
        return f"missing numbers: {', '.join(missing_numbers)} (set allowNumberChange only if the user approved it)"
    if not match_count:
        return "sourceText not found"
    if item.occurrence is not None and (item.occurrence < 1 or item.occurrence > match_count):
        return "occurrence out of range"
    if item.occurrence is None and match_count > 1:
        return "sourceText matched multiple places; set occurrence to apply deterministically"
    return ""


def apply_text(source: Path, replacements_path: Path, output: Path) -> dict[str, Any]:
    original = read_text_file(source)
    content = original
    applied, skipped = [], []
    for item in normalize_replacements(load_json(replacements_path)):
        spans = find_text_spans(content, item.sourceText)
        reason = skip_reason(item, len(spans))
        if reason:
            skipped.append({"chunkId": item.chunkId, "reason": reason})
            continue
        start, end = spans[(item.occurrence or 1) - 1]
        content = content[:start] + item.replacementText + content[end:]
        applied.append({"chunkId": item.chunkId, "line": line_of(content, start)})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8", newline="")
    diff_path = output.with_name(output.name + ".diff")
    diff = difflib.unified_diff(
        original.splitlines(keepends=True), content.splitlines(keepends=True), fromfile=source.name, tofile=output.name
    )
    diff_path.write_text("".join(diff), encoding="utf-8", newline="")
    return {
        "sourcePath": str(source.resolve()),
        "outputPath": str(output.resolve()),
        "diffPath": str(diff_path.resolve()),
        "replacementPath": str(replacements_path.resolve()),
        "trackChanges": False,
        "appliedCount": len(applied),
        "skippedCount": len(skipped),
        "applied": applied,
        "skipped": skipped,
        "note": "Text source rewritten into a new file; review the .diff (or use git diff / latexdiff) before final use.",
    }


def open_document(path: Path) -> Any:
    try:
        from docx import Document  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on optional package
        raise RuntimeError("python-docx is required: python -m pip install python-docx") from exc
    return Document(str(path))


def dry_run(source_docx: Path, replacements_path: Path) -> dict[str, Any]:
    if is_text_source(source_docx):
        return dry_run_text(source_docx, replacements_path)
    document = open_document(source_docx)
    replacements = normalize_replacements(load_json(replacements_path))
    items = []
    for item in replacements:
        matches = find_matches(document, item)
        missing_citations = validate_replacement_citations(item)
        missing_numbers = validate_replacement_numbers(item)
        missing_markup = validate_replacement_markup(item)
        unique = len(matches) == 1 or (item.occurrence is not None and 1 <= item.occurrence <= len(matches))
        items.append(
            {
                "chunkId": item.chunkId,
                "matchCount": len(matches),
                "missingCitations": missing_citations,
                "missingNumbers": missing_numbers,
                "missingMarkup": missing_markup,
                "willApply": unique and not missing_citations and not missing_numbers and not missing_markup,
                "matches": matches[:5],
            }
        )
    return {
        "sourcePath": str(source_docx.resolve()),
        "replacementPath": str(replacements_path.resolve()),
        "total": len(items),
        "applicable": sum(1 for item in items if item["willApply"]),
        "items": items,
    }


def apply_replacements(
    source_docx: Path,
    replacements_path: Path,
    output_docx: Path,
    dry_run_only: bool = False,
    track_changes: bool = False,
) -> dict[str, Any]:
    preview = dry_run(source_docx, replacements_path)
    if dry_run_only:
        return preview
    if output_docx.resolve() == source_docx.resolve():
        raise ValueError("--out must be a new file; AI-check never modifies the original DOCX in place")
    if is_text_source(source_docx):
        if output_docx.suffix.lower() != source_docx.suffix.lower():
            raise ValueError(f"--out must keep the source extension {source_docx.suffix}")
        return apply_text(source_docx, replacements_path, output_docx)

    replacements = normalize_replacements(load_json(replacements_path))
    skipped = []
    applied = []
    output_docx.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_docx, output_docx)
    document = open_document(output_docx)
    revisions = RevisionIds(document) if track_changes else None

    for item in replacements:
        missing = validate_replacement_citations(item)
        if missing:
            skipped.append({"chunkId": item.chunkId, "reason": f"missing citation marks: {', '.join(missing)}"})
            continue
        missing_numbers = validate_replacement_numbers(item)
        if missing_numbers:
            skipped.append(
                {
                    "chunkId": item.chunkId,
                    "reason": f"missing numbers: {', '.join(missing_numbers)} (set allowNumberChange only if the user approved it)",
                }
            )
            continue
        missing_markup = validate_replacement_markup(item)
        if missing_markup:
            skipped.append({"chunkId": item.chunkId, "reason": f"missing LaTeX/Markdown markup: {', '.join(missing_markup)}"})
            continue

        matches = find_matches(document, item)
        if not matches:
            skipped.append({"chunkId": item.chunkId, "reason": "sourceText not found"})
            continue
        if item.occurrence is not None and (item.occurrence < 1 or item.occurrence > len(matches)):
            skipped.append({"chunkId": item.chunkId, "reason": "occurrence out of range"})
            continue
        if item.occurrence is None and len(matches) > 1:
            skipped.append({"chunkId": item.chunkId, "reason": "sourceText matched multiple paragraphs; set occurrence to apply deterministically"})
            continue

        target_index = matches[(item.occurrence or 1) - 1]["paragraphIndex"]
        paragraph = all_paragraphs(document)[target_index]
        if not apply_to_paragraph(paragraph, item.sourceText, item.replacementText, revisions):
            skipped.append({"chunkId": item.chunkId, "reason": "replacement failed"})
            continue
        applied.append({"chunkId": item.chunkId, "paragraphIndex": target_index})

    document.save(str(output_docx))
    return {
        "sourcePath": str(source_docx.resolve()),
        "outputPath": str(output_docx.resolve()),
        "replacementPath": str(replacements_path.resolve()),
        "trackChanges": track_changes,
        "appliedCount": len(applied),
        "skippedCount": len(skipped),
        "applied": applied,
        "skipped": skipped,
        "note": (
            "Edits are written as Word tracked changes by AI-check; review and accept/reject them in Word."
            if track_changes
            else "Only the changed characters were rewritten; the rest of each paragraph keeps its runs and formatting. Review the output DOCX before final use."
        ),
    }


def command_dry_run(args: argparse.Namespace) -> int:
    output = dry_run(Path(args.docx), Path(args.replacements_json))
    if args.out_json:
        write_json(Path(args.out_json), output)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def command_apply(args: argparse.Namespace) -> int:
    output = apply_replacements(
        Path(args.docx),
        Path(args.replacements_json),
        Path(args.out),
        dry_run_only=False,
        track_changes=args.track_changes,
    )
    if args.out_json:
        write_json(Path(args.out_json), output)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply user-confirmed AI-check replacements to a new DOCX/Markdown/LaTeX/TXT file")
    sub = parser.add_subparsers(dest="command", required=True)

    dry = sub.add_parser("dry-run", help="validate replacement matching without writing DOCX")
    dry.add_argument("docx")
    dry.add_argument("replacements_json")
    dry.add_argument("--out-json")
    dry.set_defaults(func=command_dry_run)

    apply = sub.add_parser("apply", help="apply replacements to a new DOCX")
    apply.add_argument("docx")
    apply.add_argument("replacements_json")
    apply.add_argument("--out", required=True, help="new output path with the same extension (must differ from the source)")
    apply.add_argument("--out-json", help="write apply summary JSON")
    apply.add_argument("--track-changes", action="store_true", help="DOCX only: write edits as Word tracked changes (w:ins/w:del)")
    apply.set_defaults(func=command_apply)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:
        print(f"AI-check rewrite error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
