# Changelog

## 0.4.0 (2026-11-22)

- Multi-file LaTeX theses: `scan main.tex` follows `\input`, `\include`, `\subfile`, `\import` and
  `\subimport` in reading order (cycle-safe, non-`.tex` inputs such as `.tikz` are not read) and lists
  `includedFiles` / `missingIncludes`.
- Rewrites across a LaTeX project: `ai_rewrite_docx.py apply main.tex … --out-dir <folder>` finds each
  sentence in whichever file holds it (`occurrence` counts in reading order), writes the project's
  `.tex` files to the folder and one `ai-check-changes.diff` for `git apply`. `--out-dir` also works for
  single Markdown/LaTeX/TXT files.
- Annotated Word copy: `report` on a DOCX also writes `<name>.AI-check-comments.docx` with one Word
  comment (reference value, reason, signals) on each flagged passage; the text is unchanged.
  `--no-annotate` skips it; `ai_check.py annotate` makes it on its own.
- Batch mode: `ai_batch.py scan <folder> --out-dir <dir> [--recursive]` and `ai_batch.py report <dir>`
  produce one report per paper plus `batch-summary.html` / `.csv` / `.json`. Word lock files, AI-check
  outputs and included chapter `.tex` files are skipped.
- Scripts write UTF-8 to stdout/stderr, so JSON with Chinese text no longer crashes on a non-Chinese
  Windows console or pipe.
- Requires python-docx 1.2+ (for Word comments).

## 0.3.0 (2026-11-12)

- Markdown, LaTeX and TXT input; safe text rewrites with a `.diff`.
- New writing-pattern signals, per-section breakdown, frequent patterns, in-document repetition.
- `compare` self-check for a revision.

## 0.2.0 (2026-10-08)

- Valid skill name, document-order scanning, formatting-safe DOCX rewrites, Word tracked changes.
