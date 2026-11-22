#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Write a copy of the DOCX with one Word comment (批注) per flagged passage.

The comment sits on the flagged sentences themselves and carries the assistant's reference value,
reason and signals, so a student can work through the report inside Word. The text of the document
is not changed: runs are only split at the start and end of each flagged passage so the comment can
cover exactly that text. Needs python-docx >= 1.2 (comments support).
"""

from __future__ import annotations

import copy
import shutil
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from ai_check import REPORT_MIN_VALUE, get_report_rows, iter_body_paragraph_elements, paragraph_units, percent, w_tag  # noqa: E402
from ai_rewrite_docx import XML_SPACE, locate_span, run_of  # noqa: E402

COMMENT_AUTHOR = "AI-check"
COMMENT_INITIALS = "AC"
VERDICT_LABELS = {"ai": "高 / ai", "suspicious": "疑似 / suspicious", "human": "低 / human"}
DISCLAIMER = "说明：AI-check 写作质量自查的参考意见，不是知网、维普、Turnitin 等平台的检测结果。"


def _content_children(run: Any) -> list[Any]:
    return [child for child in run if child.tag != w_tag("rPr")]


def split_before_unit(paragraph: Any, index: int) -> None:
    """Make the character at ``index`` the first character of its run (no-op if it already is)."""
    from docx.oxml import OxmlElement  # type: ignore

    units = paragraph_units(paragraph)
    if index <= 0 or index >= len(units):
        return
    _char, element, offset = units[index]
    run = run_of(element)
    if run is None:
        return
    children = _content_children(run)
    if element not in children:  # e.g. w:t nested deeper than the run; leave it alone
        return
    position = children.index(element)
    if element.tag == w_tag("t") and offset > 0:
        text = element.text or ""
        element.text = text[:offset]
        element.set(XML_SPACE, "preserve")
        tail = OxmlElement("w:t")
        tail.text = text[offset:]
        tail.set(XML_SPACE, "preserve")
        moving = [tail, *children[position + 1 :]]
    elif position == 0:
        return
    else:
        moving = children[position:]
    new_run = OxmlElement("w:r")
    rpr = run.find(w_tag("rPr"))
    if rpr is not None:
        new_run.append(copy.deepcopy(rpr))
    for child in moving:
        new_run.append(child)  # lxml moves the element
    run.addnext(new_run)


def _locate(paragraphs: list[Any], text: str, start: int) -> tuple[int, int, int] | None:
    order = list(range(start, len(paragraphs))) + list(range(0, start))
    for index in order:
        span = locate_span(paragraph_units(paragraphs[index]), text)
        if span is not None:
            return index, span[0], span[1]
    return None


def comment_lines(result: Any, first: bool) -> list[str]:
    lines = [f"AI-check 参考值 {percent(result.aigcValue)}（{VERDICT_LABELS.get(result.verdict, result.verdict)}）"]
    if result.reason.strip():
        lines.append(f"原因：{result.reason.strip()}")
    signals = [signal.strip() for signal in result.signals if signal.strip()]
    if signals:
        lines.append(f"信号：{'、'.join(signals)}")
    if first:
        lines.append(DISCLAIMER)
    return lines


def annotate_docx(source: Path, scan: dict[str, Any], results: list[Any], output: Path) -> dict[str, Any]:
    try:
        from docx import Document  # type: ignore
        from docx.text.run import Run  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on optional package
        raise RuntimeError("python-docx is required: python -m pip install \"python-docx>=1.2\"") from exc
    if source.suffix.lower() != ".docx":
        raise ValueError("annotated copies are only made for .docx sources")
    if output.resolve() == source.resolve():
        raise ValueError("the annotated copy must be a new file; AI-check never modifies the original DOCX")

    rows = get_report_rows(scan, results)
    groups: list[dict[str, Any]] = []
    for row in rows:
        chunk_id = str(row["chunk"].get("chunkId") or "")
        if groups and groups[-1]["chunkId"] == chunk_id:
            groups[-1]["fragments"].append(row["text"])
        else:
            groups.append({"chunkId": chunk_id, "result": row["result"], "fragments": [row["text"]]})

    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, output)
    document = Document(str(output))
    if not hasattr(document, "add_comment"):
        raise RuntimeError("python-docx >= 1.2 is required for Word comments: python -m pip install -U \"python-docx>=1.2\"")
    paragraphs = list(iter_body_paragraph_elements(document, include_tables=True))

    annotated, unanchored = [], []
    cursor = 0
    for group in groups:
        first = _locate(paragraphs, group["fragments"][0], cursor)
        if first is None:
            unanchored.append(group["chunkId"])
            continue
        last = _locate(paragraphs, group["fragments"][-1], first[0]) if len(group["fragments"]) > 1 else first
        if last is None or last[0] < first[0] or (last[0] == first[0] and last[2] <= first[1]):
            last = first
        first_p, start, _ = first
        last_p, _, end = last
        # split the later boundary first so the earlier unit index stays valid
        split_before_unit(paragraphs[last_p], end)
        split_before_unit(paragraphs[first_p], start)
        first_units = paragraph_units(paragraphs[first_p])
        last_units = paragraph_units(paragraphs[last_p])
        first_run = run_of(first_units[start][1])
        last_run = run_of(last_units[end - 1][1])
        if first_run is None or last_run is None:
            unanchored.append(group["chunkId"])
            continue
        lines = comment_lines(group["result"], first=not annotated)
        comment = document.add_comment(
            [Run(first_run, None), Run(last_run, None)], text=lines[0], author=COMMENT_AUTHOR, initials=COMMENT_INITIALS
        )
        for line in lines[1:]:
            comment.add_paragraph(line)
        annotated.append({"chunkId": group["chunkId"], "aigcValue": group["result"].aigcValue, "paragraphIndex": first_p})
        cursor = last_p

    document.save(str(output))
    return {
        "annotatedPath": str(output.resolve()),
        "commentCount": len(annotated),
        "minValue": REPORT_MIN_VALUE,
        "annotated": annotated,
        "unanchored": unanchored,
        "note": "Each flagged passage carries a Word comment by AI-check; the document text itself is unchanged.",
    }
