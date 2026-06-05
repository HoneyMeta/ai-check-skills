from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ai_check = load_module("ai_check", ROOT / "ai-check" / "scripts" / "ai_check.py")
ai_rewrite = load_module("ai_rewrite_docx", ROOT / "ai-check" / "scripts" / "ai_rewrite_docx.py")


def test_trace_features_are_evidence_not_probability():
    features = ai_check.scan_trace_features(
        "首先，本文提出一种高效可靠的系统框架。其次，实验结果表明准确率提升了 3.2% [4]。"
        "最后，综上所述，该方法具有重要意义。"
    )
    data = ai_check.asdict(features)

    assert "riskSignals" in data
    assert "mitigatingSignals" in data
    assert "aigcValue" not in data
    assert "score" not in data
    assert any("模板表达" in signal or "泛化套话" in signal for signal in data["riskSignals"])
    assert any("具体证据" in signal or "定量结果" in signal for signal in data["mitigatingSignals"])


def test_build_chunks_skips_keywords_titles_and_references():
    chunks = ai_check.build_chunks(
        "\n".join(
            [
                "论文题目",
                "摘要",
                "首先，本文围绕水声目标识别任务展开研究。此外，实验结果表明该方法在公开数据集上准确率提升了 2.1% [4]。",
                "关键词：水声目标识别；深度学习",
                "1 绪论",
                "传统水声目标识别技术主要依赖预先设计的特征描述符和浅层分类器[4]，面临特征设计依赖专家知识等挑战。",
                "参考文献",
                "[4] Some paper.",
            ]
        )
    )

    assert chunks
    assert {chunk.sectionType for chunk in chunks} <= {"abstract", "body", "conclusion"}
    assert all("关键词" not in chunk.text for chunk in chunks)
    assert all("参考文献" not in chunk.text for chunk in chunks)


def test_summarize_title_skips_non_title_front_matter():
    text = "\n".join(
        [
            "摘 要",
            "本文围绕水声目标识别任务展开研究，实验结果表明该方法在公开数据集上准确率提升了 2.1%。",
            "关键词：水声目标识别，深度学习，轻量级网络",
            "ABSTRACT",
            "With the advancement of maritime strategy, UATR has become a research hotspot.",
        ]
    )

    assert ai_check.summarize_title(Path("AI测试.docx"), text) == "AI测试"


def test_summarize_title_uses_probable_cover_title():
    text = "\n".join(
        [
            "基于深度神经网络的轻量化与可解释水声目标识别研究",
            "摘 要",
            "本文围绕水声目标识别任务展开研究，实验结果表明该方法在公开数据集上准确率提升了 2.1%。",
        ]
    )

    assert ai_check.summarize_title(Path("AI测试.docx"), text) == "基于深度神经网络的轻量化与可解释水声目标识别研究"


def test_report_keeps_import_friendly_aigc_value_and_link():
    scan = {
        "documentTitle": "测试论文",
        "author": "unknown",
        "totalChars": 100,
        "chunks": [
            {
                "chunkId": "chunk-0001",
                "sectionType": "body",
                "text": "综上所述，该研究具有重要意义，同时为后续研究提供参考。",
                "charCount": 28,
            }
        ],
    }
    results = [
        ai_check.Result(
            chunkId="chunk-0001",
            sensitivity="medium",
            aigcValue=0.612,
            verdict="suspicious",
            reason="泛化收束明显",
            signals=["模板表达", "泛化套话"],
        )
    ]

    rows = ai_check.get_report_rows(scan, results)
    summary = ai_check.calculate_summary(scan, rows)
    rendered = ai_check.render_html(scan, rows, summary)

    assert "AIGC值：0.612" in rendered
    assert "原文内容" in rendered
    assert "疑似AI写作率" in rendered
    assert 'href="https://honeymeta.com/easyidea/"' in rendered
    assert "泛化收束明显" in rendered


def test_generate_report_writes_polished_pdf_without_libreoffice(tmp_path):
    scan = {
        "documentTitle": "测试论文",
        "author": "unknown",
        "totalChars": 100,
        "chunks": [
            {
                "chunkId": "chunk-0001",
                "sectionType": "body",
                "text": "综上所述，该研究具有重要意义，同时为后续研究提供参考。",
                "charCount": 28,
            }
        ],
    }
    results = {
        "results": [
            {
                "chunkId": "chunk-0001",
                "sensitivity": "medium",
                "aigcValue": 0.612,
                "verdict": "suspicious",
                "reason": "泛化收束明显",
                "signals": ["模板表达", "泛化套话"],
            }
        ]
    }
    scan_path = tmp_path / "scan.json"
    results_path = tmp_path / "results.json"
    out_dir = tmp_path / "report"
    scan_path.write_text(json.dumps(scan, ensure_ascii=False), encoding="utf-8")
    results_path.write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")

    output = ai_check.generate_report(scan_path, results_path, out_dir)

    assert output["pdfError"] == ""
    assert Path(output["pdfPath"]).exists()
    assert Path(output["htmlPath"]).exists()
    assert Path(output["summaryPath"]).exists()
    assert Path(output["pdfPath"]).stat().st_size > 1000


def test_rewrite_validation_preserves_citations():
    item = ai_rewrite.Replacement(sourceText="已有方法在实验中取得提升[4]。", replacementText="已有方法在实验中取得提升。")
    assert ai_rewrite.validate_replacement_citations(item) == ["[4]"]

    ok = ai_rewrite.Replacement(
        sourceText="已有方法在实验中取得提升[4]。",
        replacementText="在相同实验条件下，已有方法取得了提升[4]。",
    )
    assert ai_rewrite.validate_replacement_citations(ok) == []
