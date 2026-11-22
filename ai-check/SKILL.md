---
name: ai-check
description: Generate reference AI-writing-rate self-check reports for Word/DOCX, Markdown, LaTeX (including multi-file theses) or TXT papers (Chinese or English academic writing), with a per-section breakdown, frequent writing patterns, repeated sentences and a Word copy with one comment per flagged passage; check a whole folder of papers with one summary table; and, after explicit user confirmation, apply AI-assisted revisions to a new file (Word tracked changes for DOCX, a .diff for text sources). Use when the user asks to check a paper's AI-writing rate (AI率/AIGC率), create an AI-rate PDF/HTML report, reduce AI-writing style (降AI率) based on that report, or compare a revision with the original.
license: MIT
compatibility: Requires Python 3.10+ with python-docx>=1.2 and reportlab>=4. No LibreOffice, Word automation or network access needed.
---

# AI-check

AI-check turns a DOCX, Markdown (.md), LaTeX (.tex) or TXT paper into a reference AI-writing-rate
report, then optionally helps revise suspicious passages after the user confirms. Treat it as a
writing-quality self-check: the goal is specific, well-supported prose, not evading any detector.

## Core Rules

- Assistant-judged: you (the assistant) judge `aigcValue`, `verdict`, reasons, and rewrites in the
  visible conversation. Bundled Python scripts only read/write DOCX, JSON, HTML/PDF, and
  deterministic text signals; they never call a model or output a probability.
- Independent document pipeline: do not use LibreOffice, `soffice`, Office automation, DOCX-to-PDF
  rendering, or screenshot-based document rendering for AI-check reports. DOCX is read through
  `python-docx`; PDF is produced directly with `reportlab` as selectable text.
- Never claim alignment with CNKI, VIP, Wanfang, Turnitin, or any closed detector, and never promise
  that a revision will pass one. Say the report is for reference; schools choose their own platforms
  and thresholds.
- Do not modify the original file in place. Write reports and rewritten DOCX files beside the source
  or under a user-provided output directory (`ai_rewrite_docx.py` refuses `--out` equal to the source).
- Ask for confirmation before applying revisions to Word.
- Preserve facts, terminology, numbers, formulas, citation markers, and conclusion direction.

## Workflow

0. If `python-docx` (>= 1.2) or `reportlab` is missing, run `python -m pip install -U "python-docx>=1.2" "reportlab>=4"`.
1. Run `scripts/ai_check.py scan <file> --out <scan.json>` to extract chunks in document order.
   `<file>` may be `.docx`, `.md`, `.tex` or `.txt` (ask the user to save `.doc` as `.docx`). Word
   heading styles, Markdown `#` headings and LaTeX `\section{}` become section titles; code blocks,
   tables, figures, display math, references and acknowledgements (致谢) are skipped. Add
   `--include-tables` only if the user wants DOCX table text judged.
   The scan also lists `internalRepetition`: near-identical sentences that appear twice in the paper.
   For LaTeX, pass the main file (the one with `\documentclass`): `\input`, `\include`, `\subfile`,
   `\import` and `\subimport` are followed in reading order and the scan lists `includedFiles`. Tell the
   user about any `missingIncludes` (usually a wrong path or a chapter not saved yet).
2. Judge chunks in order. Use each chunk's `traceFeatures.riskSignals` and
   `traceFeatures.mitigatingSignals` as evidence, but do not treat them as a score.
3. Save a results JSON (one entry per judged chunk):

   ```json
   {"results": [{"chunkId": "chunk-0001", "sensitivity": "medium", "aigcValue": 0.62,
                 "verdict": "suspicious", "reason": "模板化收束，缺少方法边界", "signals": ["模板表达", "泛化套话"]}]}
   ```

   `aigcValue` is 0–1, `verdict` is `ai` / `suspicious` / `human`, `sensitivity` is `low` / `medium` / `high`.
4. Run `scripts/ai_check.py report <scan.json> <results.json> --out-dir <dir>` to generate an
   HTML report and a polished selectable-text PDF (A4, summary cards, distribution chart, per-section
   breakdown, frequent writing patterns, repeated sentences, repeated table headers, page numbers).
   For a DOCX source it also writes `<name>.AI-check-comments.docx`: a copy where every flagged passage
   carries a Word comment (批注) with the reference value, reason and signals, text unchanged
   (`annotatedDocxPath`; `--no-annotate` skips it). To make only that copy later, run
   `scripts/ai_check.py annotate <scan.json> <results.json> --out <copy.docx>`.
5. Show the report path and summary: overall rate, the 2-3 sections that contribute most
   (`sectionBreakdown`), the most frequent patterns (`topSignals`) and any repeated sentences. For
   DOCX, point to the annotated copy so the user can read each comment in Word. Ask whether to revise
   the document.
6. If the user confirms, prepare a replacements JSON from the report and source chunks:

   ```json
   {"replacements": [{"chunkId": "chunk-0001", "sourceText": "原文中的一句或一段（逐字复制）",
                      "replacementText": "改写后的文字", "reason": "去掉模板化收束"}]}
   ```

   `sourceText` must be copied verbatim from the chunk text (whitespace and line-wrap differences are
   tolerated). Add `"occurrence": N` when the same text appears in several paragraphs. For a
   repeated-sentence pair, ask the user which copy to keep and rephrase or shorten the other.
7. Run `scripts/ai_rewrite_docx.py dry-run <file> <replacements.json>` and fix every item whose
   `willApply` is false (not found, ambiguous, missing citation marks, numbers, or LaTeX/Markdown
   markup such as `\cite{..}`, `\ref{..}`, `$x$`, links and footnotes).
8. DOCX: run `scripts/ai_rewrite_docx.py apply <docx> <replacements.json> --out <new.docx> --track-changes`
   so the user can accept or reject each edit in Word. Omit `--track-changes` only if the user wants
   a clean copy. Only the changed characters are rewritten; formatting, superscript citations,
   equations, images and fields elsewhere in the paragraph are preserved.
   Markdown/LaTeX/TXT: run the same `apply` with `--out <new.md|new.tex|new.txt>` (same extension);
   it writes the new file plus `<new file>.diff` for review.
   LaTeX main file that includes chapter files: use `--out-dir <folder>` instead of `--out`. Matches are
   searched in every included file (dry-run shows `file` per match; `occurrence` counts in reading
   order), every project `.tex` file is written under the folder at its relative path, and all edits
   go into one `ai-check-changes.diff` that `git apply` accepts in the project folder.
9. Run `scripts/ai_check.py compare <original> <revised> --out <compare.json>` and show the user the
   signal changes and every `warnings` entry (more uniform rhythm, new template phrases, lost
   citations, large deletions). Fix flagged items before calling the revision done. Say that this is
   a script self-check, not a detector score.

## Batch Mode (a folder of papers)

Use when the user wants several documents checked at once (a class's theses, chapters saved as
separate Word files, several drafts):

1. `scripts/ai_batch.py scan <folder> --out-dir <dir> [--recursive]` scans every `.docx/.md/.tex/.txt`
   file and writes `<dir>/<id>.scan.json` plus `<dir>/batch.json`. Word lock files (`~$…`), AI-check
   outputs and `.tex` chapter files included by a main file are skipped (listed under `skipped`).
2. Judge each document's chunks exactly as above and save `<dir>/<id>.results.json` (the path is
   `resultsPath` in the scan output). Large batches can be done in several sessions; documents
   without results stay `pending`.
3. `scripts/ai_batch.py report <dir>` renders each judged document into `<dir>/<id>/` (HTML, PDF,
   annotated DOCX) and writes `batch-summary.html`, `batch-summary.csv` (opens in Excel) and
   `batch-summary.json`, sorted by reference AI rate. Show the summary path and the top rows.

## Detection Guidance

- Initial sensitivity is `medium`.
- Do not include titles, keywords, table-of-contents entries, references, cover pages, declarations,
  or short metadata-like text in the final report.
- `aigcValue < 0.30` is recorded but not shown as a suspicious report fragment.
- High scores require concrete, revisable risks: template phrases, contribution-list style,
  uniformly smooth rhythm, dense connectors, generic value claims or buzzwords (赋能/助力/至关重要,
  "pivotal", "underscore", "delve"), stacked dashes, "不是…而是…" / "not just X, it's Y" reframing,
  "扮演…角色", "为…提供了新的思路" closers, the same sentence opener again and again (句首重复),
  strong effect claims with no number (效果表述缺少数据), missing boundaries, or weak source-specific
  evidence.
- Do not score high only because the writing is academic, technical, citation-heavy, or structurally
  orderly. Citations, model names, metrics, statistics, experiments, data, limitations, and concrete
  method details are mitigating signals.
- For `aigcValue >= 0.70`, include at least two risk signals and explain why mitigating signals do
  not fully offset them.

## Revision Guidance

- Read the report reason/signals and convert them into rewrite goals.
- Medium rewriting should remove the actual risk signals rather than making text smoother and more
  templated.
- For generic value claims, lower the tone and add boundaries from the source context.
- For contribution-list style, vary sentence rhythm and integrate claims into local context.
- For dense connectors or uniform rhythm, reduce obvious connectors and allow natural variation.
- If the source lacks evidence, do not invent evidence. Use limitation, scope, or author-choice
  language instead.
- For `效果表述缺少数据`, use the numbers the paper already reports for that result, or soften the
  claim. Never invent a number.
- Do not add typos, slang, filler or random rewording to look "human"; that lowers quality and is not
  the goal.
- Keep every citation marker and every number. The rewrite script skips replacements that drop a
  citation such as `[4]` or a number such as `2.1`; set `"allowNumberChange": true` on an item only
  when the user explicitly approved changing that number.

## References

- Read `references/ai_rate_signals.md` for the shared risk/mitigation signal vocabulary.
- Read `references/report_format.md` when changing report output expectations.
