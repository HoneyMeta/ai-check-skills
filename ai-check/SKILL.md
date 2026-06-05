---
name: AI-check
description: Generate reference AI-writing-rate reports for Word/DOCX files and, after explicit user confirmation, apply AI-assisted revisions to a new DOCX. Use when the user asks to check Chinese or academic AI-writing rate, create an AI-rate PDF/HTML report, or reduce AI-writing style based on that report.
---

# AI-check

AI-check turns a DOCX into a reference AI-writing-rate report, then optionally helps revise
suspicious passages after the user confirms.

## Core Rules

- OpenCode Only: the assistant judges `aigcValue`, `verdict`, reasons, and rewrites. Bundled Python
  scripts only read/write DOCX, JSON, HTML/PDF, and deterministic text signals.
- Independent document pipeline: do not use LibreOffice, `soffice`, Office automation, DOCX-to-PDF
  rendering, or screenshot-based document rendering for AI-check reports. DOCX is read through
  `python-docx`; PDF is produced directly with `reportlab` as selectable text.
- Never claim alignment with CNKI, VIP, Turnitin, or any closed detector. Say the report is for
  reference.
- Do not modify the original DOCX in place. Write reports and rewritten DOCX files beside the source
  or under a user-provided output directory.
- Ask for confirmation before applying revisions to Word.
- Preserve facts, terminology, numbers, formulas, citation markers, and conclusion direction.

## Workflow

1. Run `scripts/ai_check.py scan <docx> --out <scan.json>` to extract chunks.
2. Judge chunks in order. Use each chunk's `traceFeatures.riskSignals` and
   `traceFeatures.mitigatingSignals` as evidence, but do not treat them as a score.
3. Save a results JSON with `chunkId`, `sensitivity`, `aigcValue`, `verdict`, `reason`, and
   `signals`.
4. Run `scripts/ai_check.py report <scan.json> <results.json> --out-dir <dir>` to generate an
   HTML report and a polished selectable-text PDF. The PDF layout is generated directly by
   `reportlab` with A4 pages, summary cards, a distribution chart, repeated table headers, and
   footer page numbers.
5. Show the report path and summary. Ask whether to revise the Word document.
6. If the user confirms, prepare a replacements JSON from the report and source chunks, then run
   `scripts/ai_rewrite_docx.py apply <docx> <replacements.json> --out <new.docx>`.

## Detection Guidance

- Initial sensitivity is `medium`.
- Do not include titles, keywords, table-of-contents entries, references, cover pages, declarations,
  or short metadata-like text in the final report.
- `aigcValue < 0.30` is recorded but not shown as a suspicious report fragment.
- High scores require concrete, revisable risks: template phrases, contribution-list style,
  uniformly smooth rhythm, dense connectors, generic value claims, missing boundaries, or weak
  source-specific evidence.
- Do not score high only because the writing is academic, technical, citation-heavy, or structurally
  orderly. Citations, model names, metrics, experiments, data, limitations, and concrete method
  details are mitigating signals.
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

## References

- Read `references/ai_rate_signals.md` for the shared risk/mitigation signal vocabulary.
- Read `references/report_format.md` when changing report output expectations.
