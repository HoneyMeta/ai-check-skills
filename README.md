# AI-check Skills

AI-check Skills 是一个面向 Codex、Claude Code、OpenCode 等 AI 编程助手的开源 Skill，用于
Word/DOCX、Markdown、LaTeX 论文的 AI 率自查报告、降低 AI 写作痕迹、前后重复表述清理与确认后改写。
它是写作质量自查工具：帮你找到模板化、空泛、缺数据的句子并改具体，不承诺"通过"任何检测平台。

> 该功能是 [EasyIdea 科研工作台](https://honeymeta.com/easyidea) 的一小部分。如果你需要完整
> 的论文写作、DOCX 工作台、报告导入、标注修改、批量审阅和一键采纳/放弃能力，欢迎下载使用：
> https://honeymeta.com/easyidea

![AI-check report preview](docs/assets/ai-check-report-preview.png?v=20260628)

## 功能亮点

- 支持 `.docx`、`.md`、`.tex`、`.txt`：按文档顺序读取摘要、正文、结论（DOCX 含内容控件里的段落，
  表格默认跳过；Markdown 跳过代码块和表格；LaTeX 跳过注释、图表环境、公式环境和参考文献）。
- 识别 Word 标题样式、Markdown `#` 标题、LaTeX `\section{}`，不带编号的标题也能分章节；致谢不计入检测。
- 支持中文与英文论文。
- 自动切分长文本，生成适合 AI 助手逐段判断的 chunk。
- 提取可解释的 AI 写作风险信号，例如模板化表达、连接词密集、泛化套话、句式节奏过于均匀，
  以及近年大模型常见的"赋能/助力/至关重要"、破折号堆叠、英文 delve / pivotal / underscore 等用语。
- v0.3 新增信号："不是……而是……"反转句、"扮演着……角色"、"为……提供了新的思路"式收尾、
  同一开头词反复出现（句首重复，如"本文……本文……本文……"）、"显著提升"但整句没有数据
  （效果表述缺少数据）；英文 "It's not just X, it's Y"、"In the realm of"、"serves as a testament"、
  foster / leverage / holistic 等。每个信号都只是证据，不直接等于分数。
- 同时记录缓和信号，例如引用编号、实验指标、模型/方法名、领域方法细节和定量结果支撑。
- 由当前 AI 助手在可见对话中判断 `aigcValue`、verdict、reason 和 signals，脚本本身不黑箱打分。
- 生成美观、可选择文本的 AI 率检测 PDF/HTML 报告，包含：
  - **章节分布**：每个章节的字数、疑似字数和章节 AI 率，按对全文的贡献排序，先改哪章一目了然；
  - **高频写作模式**：全文最常出现的风险信号及示例片段，便于一次性改掉写作习惯；
  - **前后重复表述**：同一篇论文里几乎相同的句子（如摘要原样搬进结论、各章小结重复绪论）。
    这只是同文自比，不是知网/维普查重结果。
- 在用户确认后，将改写方案写入新的 DOCX，不会原地修改原文档；只改动有变化的字符，
  原段落的加粗、上标引用、公式、图片、域代码都会保留。
- 可选以 **Word 修订（Track Changes）** 形式写入，在 Word 里逐条接受/拒绝。
- Markdown/LaTeX/TXT 改写写入新文件，同时生成 `.diff` 供审阅；LaTeX 的 `\cite{}`、`\ref{}`、`$x$`，
  Markdown 的链接、脚注、行内代码必须原样保留。
- 改写校验：丢失引用编号（如 `[4]`）、数字（如 `2.1`）或上述标记的替换会被拒绝。
- 改写后自查（`compare`）：对比改写前后的信号数量、句式均匀片段、引用标记数和字数；
  如果改写把文字改得更"顺"更模板化、丢了引用或删了大段内容，会给出警告。
- 支持 Codex、Claude Code、OpenCode，以及其他能运行本地脚本的 agent runtime。

## 独立 DOCX/PDF 管线

AI-check Skills 不依赖 LibreOffice、`soffice`、Microsoft Word 自动化、DOCX 转 PDF 渲染或截图渲染。

- DOCX 解析和写回：`python-docx`
- PDF 报告生成：`reportlab`
- 确定性信号提取：仓库内置 Python 脚本

脚本不会调用 AI 模型，也不会自行输出最终 AI 概率。AI 助手负责逐段判断与改写，用户可以看到判断依据。

## 安装

在 Claude Code、Codex、OpenCode、Cursor、GitHub Copilot 等 AI 编程助手中直接发送：

```text
帮我安装 https://github.com/HoneyMeta/ai-check-skills
```

安装完成后，重启客户端让新安装的 skill 生效。
也可以手动用通用的 skills 安装器：`npx skills add HoneyMeta/ai-check-skills`，或把 `ai-check/` 文件夹
复制到所用客户端的 skills 目录，例如 `~/.claude/skills/`（Claude Code）、`~/.agents/skills/` 或项目内
`.agents/skills/`（Codex、Gemini CLI 等支持 Agent Skills 标准的客户端）、`~/.config/opencode/skills/`（OpenCode）。
各客户端的目录以其官方文档为准。

依赖（Python 3.10+，缺少时 AI 会按 SKILL.md 自动安装）：

```bash
python -m pip install "python-docx>=1.1" "reportlab>=4"
```

## 目录结构

```text
ai-check/
  SKILL.md
  agents/openai.yaml
  scripts/
    ai_check.py          # scan / report / compare / features
    ai_rewrite_docx.py   # dry-run / apply（DOCX、Markdown、LaTeX、TXT）
    source_formats.py    # Markdown / LaTeX / TXT 读取
  references/
    ai_rate_signals.md
    report_format.md
docs/
  assets/
    ai-check-report-preview.png
tests/
  test_ai_check.py
  test_formats_and_signals.py
```

## 快速开始

在 AI 编程助手中发送：

```text
使用 ai-check-skills 帮我为 XXXX（文档路径）生成 AI率检测报告
```

例如：

```text
使用 ai-check-skills 帮我为 F:\papers\main.docx 生成 AI率检测报告
使用 ai-check-skills 帮我检查 F:\papers\thesis\main.tex 的 AI 写作痕迹
```

AI 助手会读取文档，生成可解释的片段信号，并输出：

- 可选择文本的 PDF 报告
- HTML 报告
- summary JSON

如果需要继续降 AI 率，可以在报告生成后让 AI 助手先列出改写方案；用户确认后再写入新的 DOCX。
原始 DOCX 不会被原地修改。

## 示例提示词

- `使用 ai-check-skills 帮我为 F:\papers\main.docx 生成 AI率检测报告`
- `根据 AI-check 报告，先给我看需要修改的片段和改写方案，确认后再写出新的 Word。`
- `确认后用修订模式写入新的 Word，我要在 Word 里逐条接受。`
- `只检测，不改 Word。`
- `把改写后的 main.revised.docx 和原文对比一下，看看改写有没有引入新的套话或丢引用。`
- `报告里的前后重复表述，帮我看看哪一处该保留、哪一处该改写。`

## 注意事项

- 报告仅供参考。
- 不要宣称结果等同于知网、维普、万方、Turnitin 或其他闭源检测平台；各平台结果本身就可能相差很大，
  学校用哪个平台、阈值是多少，以学校正式通知为准。
- 本工具不保证改写后能通过任何平台的检测，也不应以"规避检测"为目标。不要为了"像人写的"故意加错字、口语或无意义改写。
- 改写时应保留事实、术语、公式、数字、引用编号和结论方向。
- 如果原文缺少证据，不要编造实验、数据、案例或引用；应降低语气、补充边界，或使用已有上下文。

## License

MIT

## English

AI-check Skills is an open-source agent skill (Codex, Claude Code, OpenCode, …) for AI-writing
self-check reports, AI-writing style reduction, and cleanup of repeated sentences in academic papers.
It reads Word/DOCX, Markdown, LaTeX or TXT, generates a polished, selectable-text PDF/HTML report, and
applies confirmed revisions to a new file only after user approval. It is a writing-quality tool: it
points at template-like, vague or unsupported sentences so you can make them specific. It does not
promise to pass any detector.

This project is a small part of [EasyIdea Research Workbench](https://honeymeta.com/easyidea). For a
full research-writing workflow with a live DOCX workbench, report import, annotations, batch review,
and one-click accept/reject, download EasyIdea: https://honeymeta.com/easyidea

### Highlights

- Reads `.docx`, `.md`, `.tex` and `.txt` in document order (DOCX content controls included, tables
  skipped by default; Markdown code blocks/tables and LaTeX comments, floats, display math and the
  bibliography are skipped). Word heading styles, Markdown `#` headings and LaTeX `\section{}` become
  section titles, and acknowledgements are excluded. Works for Chinese and English papers.
- Splits long academic text into reviewable chunks.
- Extracts explainable AI-writing signals such as template phrases, dense connectors, generic
  claims, and uniform sentence rhythm. New in v0.3: "不是…而是…" / "It's not just X, it's Y"
  reframing, "扮演…角色" and "provides new ideas" closers, repeated sentence openers, strong effect
  claims with no number in the sentence, and more English LLM vocabulary (foster, leverage, holistic…).
- Keeps mitigating evidence such as citations, metrics, method names, domain details, and
  quantitative results.
- Lets the active AI assistant judge `aigcValue`, verdict, reason, and signals in the visible
  conversation.
- Generates a polished AI-rate report as HTML and selectable-text PDF, with a per-section breakdown
  ranked by contribution, the most frequent writing patterns, and repeated sentences inside the same
  paper (an in-document check, not a plagiarism check).
- Applies user-confirmed replacements to a new DOCX without modifying the original document. Only the
  changed characters are rewritten, so bold text, superscript citations, equations, images and fields
  survive; `--track-changes` writes the edits as Word revisions you can accept or reject.
- Markdown/LaTeX/TXT rewrites go to a new file plus a `.diff`; `\cite{}`, `\ref{}`, `$x$`, links and
  footnotes must survive.
- Rejects rewrites that drop a citation marker such as `[4]`, a number such as `2.1`, or that markup.
- `compare` checks a revision against the original: signal counts, uniform-rhythm passages, citation
  marks and length, with warnings when a rewrite becomes more template-like or loses citations.
- Supports Codex, Claude Code, OpenCode, and similar agent runtimes that can run local scripts.

### Independent Pipeline

AI-check Skills does not require LibreOffice, `soffice`, Microsoft Word automation, DOCX-to-PDF
rendering, or screenshot rendering.

- DOCX parsing and rewriting: `python-docx`
- PDF report generation: `reportlab`
- Deterministic signal extraction: bundled Python scripts

The scripts do not call AI models and do not produce a final AI probability by themselves. The AI
assistant remains responsible for judgment and rewriting so the user can see the reasoning.

### Install

Ask your AI coding assistant (Claude Code, Codex, OpenCode, Cursor, GitHub Copilot, …):

```text
Install https://github.com/HoneyMeta/ai-check-skills
```

Restart the assistant afterwards so the new skill is loaded. To install manually, use the cross-agent
skills installer `npx skills add HoneyMeta/ai-check-skills`, or copy the `ai-check/` folder into your
client's skills directory, e.g. `~/.claude/skills/` (Claude Code), `~/.agents/skills/` or a project's
`.agents/skills/` (Codex, Gemini CLI and other Agent Skills clients), `~/.config/opencode/skills/`
(OpenCode). Check your client's docs for the exact path. Dependencies (Python 3.10+):
`python -m pip install "python-docx>=1.1" "reportlab>=4"`.

### Quick Start

Send a prompt like:

```text
Use ai-check-skills to generate an AI-rate report for C:\papers\main.docx.
```

For Chinese workflows, you can use:

```text
使用 ai-check-skills 帮我为 XXXX（文档路径）生成 AI率检测报告
```

The assistant will scan the DOCX, produce an explainable PDF/HTML report, and only write a rewritten
DOCX after you approve the replacement plan.

### Safety Notes

- The report is for reference only.
- Do not claim that it is equivalent to CNKI, VIP, Wanfang, Turnitin, or another closed detector.
  Those platforms often disagree with each other; your school decides which one and which threshold apply.
- It does not guarantee passing any detector and should not be used to evade one. Do not add typos,
  slang or random rewording to look "human".
- Preserve facts, terminology, formulas, numbers, citation markers, and conclusion direction during
  rewriting.
- If the source lacks evidence, do not invent experiments, data, cases, or citations.
