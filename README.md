# AI-check Skills

AI-check Skills is an open-source Codex/OpenCode-style skill for AI-rate detection report
generation, automated AI-writing reduction, and academic repetition/AI-writing style cleanup. It
can generate a polished, selectable-text AI-rate PDF/HTML report from a Word document, then help
reduce obvious AI-writing signals only after the user confirms the proposed revisions.

It is designed for researchers, students, editors, and AI coding assistants that need a transparent
and explainable workflow instead of a black-box detector.

![AI-check report preview](docs/assets/ai-check-report-preview.png)

## What It Does

- Reads `.docx` files and extracts body, abstract, and conclusion text.
- Splits long academic text into reviewable chunks.
- Detects explainable writing signals such as template phrases, dense connectors, generic claims,
  uniform rhythm, citation/detail mitigations, and method-specific evidence.
- Lets the active AI assistant judge `aigcValue`, verdict, reason, and signals in the visible
  conversation.
- Generates a polished AI-rate report as HTML and selectable-text PDF.
- Applies user-confirmed replacements to a new DOCX without modifying the original document.
- Supports Codex, Claude Code, OpenCode, and similar agent runtimes that can run local scripts.

## Independent DOCX/PDF Pipeline

AI-check Skills does not require LibreOffice, `soffice`, Microsoft Word automation, DOCX-to-PDF
rendering, or screenshot rendering.

- DOCX parsing and rewriting: `python-docx`
- PDF report generation: `reportlab`
- Deterministic signal extraction: bundled Python scripts

The scripts do not call AI models and do not produce a final AI probability by themselves. The AI
assistant remains responsible for judgment and rewriting so the user can see the reasoning.

## Install

```bash
python -m pip install python-docx reportlab
```

For tests:

```bash
python -m pip install pytest
```

## Repository Layout

```text
ai-check/
  SKILL.md
  agents/openai.yaml
  scripts/
    ai_check.py
    ai_rewrite_docx.py
  references/
    ai_rate_signals.md
    report_format.md
  assets/
    report_template.html
docs/
  assets/
    ai-check-report-preview.png
tests/
  test_ai_check.py
```

## Quick Start

Run a deterministic DOCX scan:

```bash
python ai-check/scripts/ai_check.py scan paper.docx --out work/scan.json
```

The scan output contains chunks and `traceFeatures`, but intentionally contains no final AI
probability. The assistant should judge each chunk and save a results JSON:

```json
{
  "documentTitle": "paper",
  "author": "unknown",
  "results": [
    {
      "chunkId": "chunk-0001",
      "sensitivity": "medium",
      "aigcValue": 0.62,
      "verdict": "suspicious",
      "reason": "模板化收束和泛化价值判断较明显，具体实验支撑不足",
      "signals": ["泛化套话", "连接词密集"]
    }
  ]
}
```

Generate the report:

```bash
python ai-check/scripts/ai_check.py report work/scan.json work/results.json --out-dir work/report
```

The report command writes:

- A polished selectable-text PDF
- An HTML report
- A summary JSON file

After the user confirms revisions, apply replacements to a new DOCX:

```bash
python ai-check/scripts/ai_rewrite_docx.py apply paper.docx work/replacements.json --out paper.ai-check.rewritten.docx
```

The original DOCX is never modified in place.

## Example Prompts

- `Use AI-check to generate an AI writing rate report for F:\papers\main.docx.`
- `根据 AI-check 报告，先给我看需要修改的片段和改写方案，确认后再写出新的 Word。`
- `只检测，不改 Word。`

## Safety Notes

- The report is for reference only.
- Do not claim that the result is equivalent to CNKI, VIP, Turnitin, or another closed detector.
- Preserve facts, terminology, formulas, numbers, citation markers, and conclusion direction during
  rewriting.
- If the source lacks evidence, do not invent experiments, data, cases, or citations. Lower the
  tone, add boundaries, or use existing source context instead.

## License

MIT

该功能是EasyIdea科研工作台的一小部分，欢迎下载使用 https://honeymeta.com/easyidea
