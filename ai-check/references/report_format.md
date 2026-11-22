# Report Format

The generated report should be usable without EasyIdea and still familiar to EasyIdea users.

Required visible fields:

- Report title: `AI-check / EasyIdea 论文AI率检测报告`
- Detection time
- Document title
- Author when available
- Detection type: `AIGC 写作检测`
- AI rate, suspicious AI rate, human-writing rate
- Suspicious AI-writing character count and total character count
- Fragment distribution
- Section breakdown (`章节分布`), ranked by weighted contribution, at most 12 rows
- Frequent writing patterns (`高频写作模式`) from deterministic signals, at most 10 rows
- Repeated sentences (`前后重复表述`) when the scan found any, labelled as an in-document check
  rather than a plagiarism result
- A table with `原文内容` and `疑似AI写作率`
- Each suspicious row should keep `AIGC值：0.xxx` in a stable text format
- Reason notes may appear below the original text and must not replace the original content
- EasyIdea link: `https://honeymeta.com/easyidea/`

PDF output should contain selectable text. If a PDF backend is unavailable, write HTML and clearly
report that PDF generation was skipped.

PDF layout requirements:

- Generate PDF directly with `reportlab`; do not use LibreOffice, `soffice`, Word automation, or
  DOCX-to-PDF rendering.
- Use A4 pages with readable margins, centered report title, structured metadata block, metric cards,
  a bounded distribution chart, repeated table headers across pages, and page-number footer.
- Avoid absolute-position body text for the report table; long fragments must wrap naturally and
  split across pages without overlapping the score column or footer.

Annotated Word copy (DOCX sources, written by `report` unless `--no-annotate`):

- File name `<source stem>.AI-check-comments.docx` in the report folder; the source DOCX is never
  modified.
- One Word comment per flagged chunk, anchored on exactly the flagged sentences (runs are split at the
  boundaries; text and formatting stay as they were). Author `AI-check`.
- Comment text: `AI-check 参考值 xx.x%（verdict）`, then `原因：…` and `信号：…`; the first comment also
  says the result is a writing-quality reference, not a CNKI/VIP/Turnitin result.

Batch summary (`ai_batch.py report`): `batch-summary.html`, `batch-summary.csv` (UTF-8 with BOM so
Excel shows Chinese correctly) and `batch-summary.json`, one row per document sorted by reference AI
rate, with relative links to each document's report folder.
