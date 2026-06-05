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
