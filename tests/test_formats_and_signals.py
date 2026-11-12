from __future__ import annotations

import json
from pathlib import Path

from docx import Document

from test_ai_check import ai_check, ai_rewrite, write_replacements


ABSTRACT_CN = "本文针对低信噪比条件下的水声目标识别问题，提出一种多尺度特征融合方法，在公开数据集上准确率达到 92.4% [3]。"
REPEATED = "实验表明所提方法在低信噪比条件下仍能保持稳定的识别性能，且推理开销较小。"

MARKDOWN = f"""---
title: 水声目标识别研究
author: 张三
---

# 水声目标识别研究

## 摘要

{ABSTRACT_CN}

## 研究背景

传统水声目标识别技术主要依赖人工设计的特征描述符和浅层分类器[4]，
在复杂海况下泛化能力有限。综上所述，{REPEATED}

```python
print("代码块里的文字不应该被扫描，综上所述")
```

| 表头 | 综上所述这一格不应被扫描 |
| --- | --- |

- 列表项：本文采用 [Smith 的数据集](https://example.org) 与 `librosa` 提取特征，并说明了适用范围。

## 结论

{REPEATED}

## 致谢

感谢导师在论文写作过程中给予的悉心指导和帮助，感谢实验室同学的支持与鼓励。
"""

LATEX = r"""\documentclass{article}
\title{Robust Acoustic Target Recognition}
\author{Jane Doe \and John Roe}
\begin{document}
\maketitle
\begin{abstract}
We study underwater acoustic target recognition under low signal-to-noise ratio
and report 92.4\% accuracy on the public dataset \cite{li2023}.
\end{abstract}

\section{Introduction}
% a comment that mentions In conclusion and must be ignored
In today's rapidly evolving landscape, acoustic sensing plays a pivotal role in
maritime safety. It is worth noting that prior work \cite{wang2022} relies on
hand-crafted features, as shown in Fig.~\ref{fig:pipeline}.

\begin{figure}[t]
  \centering
  \caption{In conclusion this caption must be skipped}
\end{figure}

\begin{equation}
  y = Wx + b
\end{equation}

\section*{Method}
We restrict the model to $n = 3$ scales and evaluate on 1,200 recordings.

\bibliography{refs}
\section{Appendix text after bibliography should be ignored}
\end{document}
"""


def test_markdown_scan_uses_headings_and_skips_non_prose(tmp_path):
    source = tmp_path / "paper.md"
    source.write_text(MARKDOWN, encoding="utf-8")
    scan = ai_check.scan_docx(source)
    texts = "\n".join(chunk["text"] for chunk in scan["chunks"])
    assert scan["sourceFormat"] == "md"
    assert scan["documentTitle"] == "水声目标识别研究"
    assert scan["author"] == "张三"
    assert "代码块" not in texts and "这一格" not in texts
    assert "感谢导师" not in texts, "acknowledgements are not judged as academic prose"
    sections = {chunk["sectionType"] for chunk in scan["chunks"]}
    assert {"abstract", "body", "conclusion"} <= sections
    assert any(chunk["sectionTitle"] == "研究背景" for chunk in scan["chunks"])
    # hard-wrapped CJK lines are joined without a stray space
    assert "浅层分类器[4]，在复杂海况下" in texts


def test_latex_scan_keeps_markup_and_drops_floats(tmp_path):
    source = tmp_path / "paper.tex"
    source.write_text(LATEX, encoding="utf-8")
    scan = ai_check.scan_docx(source)
    texts = "\n".join(chunk["text"] for chunk in scan["chunks"])
    assert scan["documentTitle"] == "Robust Acoustic Target Recognition"
    assert "Jane Doe" in scan["author"]
    assert "caption must be skipped" not in texts and "Wx + b" not in texts
    assert "a comment that mentions" not in texts
    assert "after bibliography" not in texts
    assert "\\cite{wang2022}" in texts, "inline markup stays verbatim so rewrites can find it"
    assert scan["chunks"][0]["sectionType"] == "abstract"
    intro = next(chunk for chunk in scan["chunks"] if chunk["sectionTitle"] == "Introduction")
    features = intro["traceFeatures"]
    assert any("In today" in signal for signal in features["riskSignals"])
    assert "具体证据:引用编号" in features["mitigatingSignals"]


def test_new_llm_pattern_signals():
    cn = ai_check.scan_trace_features("这不是简单的技术升级，而是范式的转变。人工智能在其中扮演着关键角色，为后续研究提供了新的思路。")
    assert {"模板表达:不是而是反转句", "模板表达:扮演角色套语", "模板表达:提供新思路收束"} <= set(cn.riskSignals)

    openers = ai_check.scan_trace_features("本文提出一种方法。本文构建了一个数据集。本文设计了对比实验。本文验证了方法效果。该方法显著提升了识别性能。")
    assert "句首重复:本文" in openers.riskSignals
    assert "效果表述缺少数据" in openers.riskSignals

    quantified = ai_check.scan_trace_features("该方法将识别准确率显著提升了 3.2 个百分点，推理时间降低到 12 ms。")
    assert "效果表述缺少数据" not in quantified.riskSignals

    en = ai_check.scan_trace_features(
        "It's not just a tool, it's a paradigm shift. In the realm of acoustics, this serves as a testament to progress."
    )
    assert any("not just" in signal for signal in en.riskSignals)
    assert any("realm" in signal for signal in en.riskSignals)


def test_internal_repetition_finds_reused_sentences(tmp_path):
    source = tmp_path / "paper.md"
    source.write_text(MARKDOWN, encoding="utf-8")
    scan = ai_check.scan_docx(source)
    pairs = scan["internalRepetition"]
    assert len(pairs) == 1
    assert pairs[0]["similarity"] >= 0.8
    assert pairs[0]["first"]["sectionTitle"] == "研究背景"
    assert REPEATED.rstrip("。") in pairs[0]["second"]["text"]


def test_report_has_section_breakdown_patterns_and_repetition(tmp_path):
    source = tmp_path / "paper.md"
    source.write_text(MARKDOWN, encoding="utf-8")
    scan_path = tmp_path / "scan.json"
    ai_check.write_json(scan_path, ai_check.scan_docx(source))
    scan = ai_check.load_json(scan_path)
    results = [
        {"chunkId": chunk["chunkId"], "aigcValue": 0.8 if chunk["sectionTitle"] == "研究背景" else 0.4, "verdict": "suspicious", "reason": "测试"}
        for chunk in scan["chunks"]
    ]
    results_path = tmp_path / "results.json"
    results_path.write_text(json.dumps({"results": results}, ensure_ascii=False), encoding="utf-8")
    output = ai_check.generate_report(scan_path, results_path, tmp_path / "out")
    assert output["sectionBreakdown"][0]["section"] == "研究背景"
    assert output["internalRepetition"]
    html_text = Path(output["htmlPath"]).read_text(encoding="utf-8")
    assert "章节分布" in html_text and "前后重复表述" in html_text and "高频写作模式" in html_text
    assert output["pdfPath"], output["pdfError"]


def test_text_rewrite_handles_wrapped_lines_and_writes_diff(tmp_path):
    source = tmp_path / "paper.md"
    source.write_text(MARKDOWN, encoding="utf-8")
    source_text = "传统水声目标识别技术主要依赖人工设计的特征描述符和浅层分类器[4]，在复杂海况下泛化能力有限。"
    replacement = "早期的水声目标识别多用人工特征加浅层分类器[4]，换到复杂海况时效果明显下降。"
    plan = write_replacements(tmp_path / "r.json", [{"chunkId": "c1", "sourceText": source_text, "replacementText": replacement}])
    preview = ai_rewrite.dry_run(source, plan)
    assert preview["applicable"] == 1 and preview["items"][0]["matches"][0]["line"] > 1
    out = tmp_path / "paper.revised.md"
    result = ai_rewrite.apply_replacements(source, plan, out)
    assert result["appliedCount"] == 1, result
    revised = out.read_text(encoding="utf-8")
    assert replacement in revised and "浅层分类器[4]，\n" not in revised
    assert source.read_text(encoding="utf-8") == MARKDOWN, "source must stay untouched"
    assert "+早期的水声目标识别" in Path(result["diffPath"]).read_text(encoding="utf-8")


def test_text_rewrite_rejects_dropped_latex_markup(tmp_path):
    source = tmp_path / "paper.tex"
    source.write_text(LATEX, encoding="utf-8")
    source_text = r"It is worth noting that prior work \cite{wang2022} relies on hand-crafted features, as shown in Fig.~\ref{fig:pipeline}."
    plan = write_replacements(
        tmp_path / "r.json",
        [
            {"chunkId": "bad", "sourceText": source_text, "replacementText": "Prior work relies on hand-crafted features."},
            {
                "chunkId": "good",
                "sourceText": source_text,
                "replacementText": r"Prior work \cite{wang2022} still uses hand-crafted features (Fig.~\ref{fig:pipeline}).",
            },
        ],
    )
    result = ai_rewrite.apply_replacements(source, plan, tmp_path / "paper.revised.tex")
    assert result["appliedCount"] == 1
    assert result["skipped"][0]["chunkId"] == "bad"
    assert "\\cite{wang2022}" in result["skipped"][0]["reason"]


def test_compare_reports_signal_changes_and_lost_citations(tmp_path):
    before = tmp_path / "before.txt"
    after = tmp_path / "after.txt"
    before.write_text(
        "综上所述，本文提出的方法具有重要意义，为相关研究提供了新的思路[2]。\n\n"
        "随着人工智能的快速发展，水声识别扮演着越来越重要的角色，具有广阔的应用前景[3]。",
        encoding="utf-8",
    )
    after.write_text(
        "本文方法在 3 个数据集上的结果说明，它适合低信噪比场景，但对长时序信号仍有不足。\n\n"
        "水声识别近年开始引入深度模型，本文只讨论舰船辐射噪声这一类目标。",
        encoding="utf-8",
    )
    report = ai_check.compare_scans(ai_check.scan_docx(before), ai_check.scan_docx(after))
    assert report["after"]["riskSignalTotal"] < report["before"]["riskSignalTotal"]
    assert any(change["signal"].startswith("模板表达:综上所述") and change["after"] == 0 for change in report["signalChanges"])
    assert any("引用标记" in warning for warning in report["warnings"])


def test_docx_heading_styles_become_section_titles(tmp_path):
    document = Document()
    document.add_heading("研究背景", level=1)
    document.add_paragraph("传统水声目标识别技术主要依赖人工设计的特征描述符和浅层分类器[4]，在复杂海况下泛化能力有限。")
    document.add_heading("致谢", level=1)
    document.add_paragraph("感谢导师在论文写作过程中给予的悉心指导和帮助，感谢实验室同学的支持与鼓励。")
    source = tmp_path / "styled.docx"
    document.save(str(source))
    scan = ai_check.scan_docx(source)
    assert [chunk["sectionTitle"] for chunk in scan["chunks"]] == ["研究背景"]


def test_unsupported_extension_is_explained(tmp_path):
    source = tmp_path / "paper.doc"
    source.write_bytes(b"\xd0\xcf\x11\xe0")
    try:
        ai_check.scan_docx(source)
    except ValueError as exc:
        assert ".docx" in str(exc)
    else:
        raise AssertionError("expected ValueError")
