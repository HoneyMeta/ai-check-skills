"""v0.4: multi-file LaTeX projects, annotated Word copies, folder batches."""

from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from docx import Document
from docx.oxml.ns import qn

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "ai-check" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load_module(name: str, path: Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ai_check = load_module("ai_check", SCRIPTS / "ai_check.py")
ai_rewrite = load_module("ai_rewrite_docx", SCRIPTS / "ai_rewrite_docx.py")
source_formats = load_module("source_formats", SCRIPTS / "source_formats.py")
docx_annotate = load_module("docx_annotate", SCRIPTS / "docx_annotate.py")

INTRO = "近年来，深度学习在水声目标识别中扮演着至关重要的角色，为该领域提供了新的思路。"
METHOD = "本文提出的方法在 ShipsEar 数据集上把准确率从 71.2% 提高到 78.4%~\\cite{ships}。"
SHARED = "该结论在不同信噪比下保持一致。"


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def make_latex_project(root: Path) -> Path:
    write(root / "preamble.tex", "\\usepackage{amsmath}\n% \\input{never}\n")
    write(root / "chapters" / "intro.tex", f"\\chapter{{绪论}}\n{INTRO}\n\n{SHARED}\n\\input{{chapters/sub/detail}}\n")
    write(root / "chapters" / "sub" / "detail.tex", "\\section{研究现状}\n传统方法依赖人工设计的特征描述符和浅层分类器。\n")
    write(root / "chapters" / "method.tex", f"\\chapter{{方法}}\n{METHOD}\n\n{SHARED}\n\\input{{figures/plot.tikz}}\n")
    write(root / "figures" / "plot.tikz", "\\draw (0,0) -- (1,1); 这不是正文，也不应该被读取。\n")
    write(root / "appendix.tex", "\\chapter{附录}\n附录正文不参与检测。\n")
    return write(
        root / "main.tex",
        "\\documentclass{ctexbook}\n\\input{preamble}\n\\title{水声目标识别研究}\n\\begin{document}\n\\maketitle\n"
        "\\include{chapters/intro}\n% \\include{chapters/old}\n\\include{chapters/method}\n\\include{chapters/missing}\n"
        "\\appendix\n\\input{appendix}\n\\end{document}\n",
    )


# ---------------------------------------------------------------------------
# LaTeX projects
# ---------------------------------------------------------------------------


def test_latex_scan_follows_input_and_include_in_reading_order(tmp_path):
    main = make_latex_project(tmp_path / "thesis")
    text, meta = source_formats.read_latex_text(main)
    assert text.index("扮演着") < text.index("人工设计") < text.index("ShipsEar")
    assert "这不是正文" not in text, "non-.tex inputs must not be read"
    assert "附录正文" not in text, "reading still stops at \\appendix"
    assert meta["includedFiles"] == ["preamble.tex", "chapters/intro.tex", "chapters/sub/detail.tex", "chapters/method.tex", "appendix.tex"]
    assert meta["missingIncludes"] == ["chapters/missing"]
    scan = ai_check.scan_docx(main)
    assert scan["includedFiles"][1] == "chapters/intro.tex"
    titles = {chunk["sectionTitle"] for chunk in scan["chunks"]}
    assert {"绪论", "方法"} <= titles


def test_latex_include_cycles_and_subfiles(tmp_path):
    write(tmp_path / "a.tex", "甲文件的正文内容足够长，可以作为一个段落参与检测。\n\\input{b}\n")
    write(tmp_path / "b.tex", "乙文件的正文内容也足够长，同样可以作为段落参与检测。\n\\input{a}\n")
    write(tmp_path / "parts" / "c.tex", "\\documentclass[../main.tex]{subfiles}\n\\begin{document}\n丙文件是一个 subfile，只有正文部分会被并入主文档。\n\\end{document}\n")
    main = write(tmp_path / "main.tex", "\\documentclass{article}\n\\begin{document}\n\\input{a}\n\\subfile{parts/c}\n结尾段落。\n\\end{document}\n")
    text, meta = source_formats.read_latex_text(main)
    assert text.count("甲文件") == 1 and text.count("乙文件") == 1
    assert "丙文件是一个 subfile" in text and "结尾段落" in text
    assert "documentclass" not in text
    assert meta["includedFiles"] == ["a.tex", "b.tex", "parts/c.tex"]


def test_rewrite_latex_project_into_out_dir_with_one_patch(tmp_path):
    main = make_latex_project(tmp_path / "thesis")
    replacements = write(
        tmp_path / "r.json",
        json.dumps(
            {
                "replacements": [
                    {"chunkId": "c1", "sourceText": INTRO, "replacementText": "近年来，深度学习方法被越来越多地用于水声目标识别。"},
                    {"chunkId": "c2", "sourceText": SHARED, "replacementText": "在 0 dB 到 10 dB 的信噪比下，该结论保持一致。", "occurrence": 2},
                    {"chunkId": "c3", "sourceText": METHOD, "replacementText": "本文方法在 ShipsEar 数据集上把准确率提高到 78.4%~\\cite{ships}。"},
                ]
            },
            ensure_ascii=False,
        ),
    )
    preview = ai_rewrite.dry_run(main, replacements)
    assert preview["projectFiles"][0] == "main.tex"
    assert [item["matchCount"] for item in preview["items"]] == [1, 2, 1]
    assert preview["items"][1]["matches"][1]["file"] == "chapters/method.tex"
    assert preview["items"][2]["willApply"] is False and preview["items"][2]["missingNumbers"] == ["71.2"]

    with pytest.raises(ValueError, match="--out-dir"):
        ai_rewrite.apply_replacements(main, replacements, tmp_path / "main.revised.tex")
    with pytest.raises(ValueError, match="must not be the folder"):
        ai_rewrite.apply_replacements(main, replacements, None, out_dir=main.parent)

    out = tmp_path / "revised"
    result = ai_rewrite.apply_replacements(main, replacements, None, out_dir=out)
    assert result["appliedCount"] == 2 and result["skippedCount"] == 1
    assert result["changedFiles"] == ["chapters/intro.tex", "chapters/method.tex"]
    assert {entry["file"] for entry in result["applied"]} == {"chapters/intro.tex", "chapters/method.tex"}
    method = (out / "chapters" / "method.tex").read_text(encoding="utf-8")
    assert "0 dB 到 10 dB" in method and SHARED not in method
    assert SHARED in (out / "chapters" / "intro.tex").read_text(encoding="utf-8"), "occurrence 2 is the second one in reading order"
    assert (out / "main.tex").exists() and (out / "chapters" / "sub" / "detail.tex").exists()
    assert INTRO in (tmp_path / "thesis" / "chapters" / "intro.tex").read_text(encoding="utf-8"), "originals untouched"
    patch = (out / "ai-check-changes.diff").read_text(encoding="utf-8")
    assert "--- a/chapters/intro.tex" in patch and "+++ b/chapters/method.tex" in patch and "main.tex" not in patch

    # the revised copy is a complete project again: compare can follow its includes
    comparison = ai_check.compare_scans(ai_check.scan_docx(main), ai_check.scan_docx(out / "main.tex"))
    assert comparison["after"]["chunks"] == comparison["before"]["chunks"]


def test_single_text_files_still_work_and_accept_out_dir(tmp_path):
    source = write(tmp_path / "paper.md", f"# 引言\n\n{INTRO}\n")
    replacements = write(
        tmp_path / "r.json",
        json.dumps({"replacements": [{"sourceText": INTRO, "replacementText": "深度学习方法被越来越多地用于水声目标识别。"}]}, ensure_ascii=False),
    )
    single = ai_rewrite.apply_replacements(source, replacements, tmp_path / "paper.revised.md")
    assert single["appliedCount"] == 1 and single["diffPath"].endswith("paper.revised.md.diff")
    into_dir = ai_rewrite.apply_replacements(source, replacements, None, out_dir=tmp_path / "out")
    assert (tmp_path / "out" / "paper.md").read_text(encoding="utf-8").endswith("深度学习方法被越来越多地用于水声目标识别。\n")
    assert into_dir["changedFiles"] == ["paper.md"]


# ---------------------------------------------------------------------------
# Annotated Word copy
# ---------------------------------------------------------------------------

FLAGGED = "综上所述，该方法具有重要意义，为后续研究提供了新的思路。"
CLEAN = "实验在 ShipsEar 数据集上进行，准确率为 78.4%，比基线高 7.2 个百分点[4]。"


def make_docx(path: Path) -> Path:
    document = Document()
    document.add_paragraph("1 绪论", style="Heading 1")
    first = document.add_paragraph()
    first.add_run("开头保留不动的句子，长度足够被扫描到。").bold = True
    first.add_run("综上所述，该方法具有重要意义，")
    first.add_run("为后续研究提供了新的思路。").italic = True
    document.add_paragraph(CLEAN)
    document.add_paragraph("2 结论", style="Heading 1")
    document.add_paragraph("本文方法在多个场景中发挥着关键作用，助力水声目标识别迈上新台阶，具有广阔的应用前景。")
    document.save(str(path))
    return path


def commented_text(path: Path) -> dict[str, str]:
    """Text covered by each comment id, read back from the saved file."""
    body = Document(str(path)).element.body
    open_ids: set[str] = set()
    out: dict[str, str] = {}
    for element in body.iter():
        if element.tag == qn("w:commentRangeStart"):
            open_ids.add(element.get(qn("w:id")))
        elif element.tag == qn("w:commentRangeEnd"):
            open_ids.discard(element.get(qn("w:id")))
        elif element.tag == qn("w:t"):
            for comment_id in open_ids:
                out[comment_id] = out.get(comment_id, "") + (element.text or "")
    return out


def results_for(scan: dict, values: dict[str, float]) -> list:
    payload = []
    for chunk in scan["chunks"]:
        for needle, value in values.items():
            if needle in chunk["text"]:
                payload.append(
                    {"chunkId": chunk["chunkId"], "aigcValue": value, "verdict": "suspicious" if value < 0.7 else "ai", "reason": "模板化收束", "signals": ["模板表达", "泛化套话"]}
                )
                break
    return ai_check.normalize_results({"results": payload})


def test_annotated_copy_puts_comments_on_exactly_the_flagged_text(tmp_path):
    source = make_docx(tmp_path / "paper.docx")
    before = [p.text for p in Document(str(source)).paragraphs]
    scan = ai_check.scan_docx(source)
    # chunk 1 spans two paragraphs (the flagged closer and the data sentence), chunk 2 is the conclusion
    results = results_for(scan, {"综上所述": 0.62, "广阔的应用前景": 0.81})
    result = docx_annotate.annotate_docx(source, scan, results, tmp_path / "paper.AI-check-comments.docx")
    assert result["commentCount"] == 2 and result["unanchored"] == []

    out = tmp_path / "paper.AI-check-comments.docx"
    document = Document(str(out))
    assert [p.text for p in document.paragraphs] == before, "the text must not change"
    comments = list(document.comments)
    assert len(comments) == 2
    assert comments[0].author == "AI-check"
    assert "62.0%" in comments[0].text and "原因：模板化收束" in comments[0].text and "不是知网" in comments[0].text
    assert "81.0%" in comments[1].text and "不是知网" not in comments[1].text
    covered = commented_text(out)
    assert sorted(covered.values()) == sorted(
        ["开头保留不动的句子，长度足够被扫描到。" + FLAGGED + CLEAN, "本文方法在多个场景中发挥着关键作用，助力水声目标识别迈上新台阶，具有广阔的应用前景。"]
    )
    # formatting of the untouched runs survives the split
    runs = document.paragraphs[1].runs
    assert any(r.bold and r.text.startswith("开头保留") for r in runs)
    assert any(r.italic and "新的思路" in r.text for r in runs)
    assert source.read_bytes() != out.read_bytes()


def test_annotation_splits_runs_at_fragment_boundaries():
    document = Document()
    paragraph = document.add_paragraph()
    paragraph.add_run("前缀文字。中间需要标注的句子。后缀")
    p = paragraph._p
    units = ai_check.paragraph_units(p)
    text = "".join(c for c, _e, _o in units)
    start = text.index("中间")
    end = text.index("后缀")
    docx_annotate.split_before_unit(p, end)
    docx_annotate.split_before_unit(p, start)
    runs = ["".join(t.text for t in r.findall(qn("w:t"))) for r in p.findall(qn("w:r"))]
    assert runs == ["前缀文字。", "中间需要标注的句子。", "后缀"]
    docx_annotate.split_before_unit(p, 0)
    assert len(p.findall(qn("w:r"))) == 3


def test_report_writes_annotated_docx_by_default(tmp_path):
    source = make_docx(tmp_path / "paper.docx")
    scan = ai_check.scan_docx(source)
    scan_path = write(tmp_path / "scan.json", json.dumps(scan, ensure_ascii=False))
    payload = [{"chunkId": c["chunkId"], "aigcValue": 0.66, "verdict": "suspicious", "reason": "套话", "signals": []} for c in scan["chunks"] if "综上所述" in c["text"]]
    results_path = write(tmp_path / "results.json", json.dumps({"results": payload}, ensure_ascii=False))
    output = ai_check.generate_report(scan_path, results_path, tmp_path / "report")
    assert output["annotatedDocxPath"].endswith("paper.AI-check-comments.docx") and output["annotatedComments"] == 1
    assert output["annotateError"] == ""
    skipped = ai_check.generate_report(scan_path, results_path, tmp_path / "report2", annotate=False)
    assert skipped["annotatedDocxPath"] == ""


# ---------------------------------------------------------------------------
# Batch mode
# ---------------------------------------------------------------------------

ai_batch = load_module("ai_batch", SCRIPTS / "ai_batch.py")


def make_batch_folder(root: Path) -> Path:
    (root / "nested").mkdir(parents=True, exist_ok=True)
    make_docx(root / "张三.docx")
    make_docx(root / "nested" / "李四.docx")
    write(root / "notes.md", f"# 引言\n\n{INTRO}\n\n本文在第三章给出了完整的实验设置和误差分析，所有数字均来自表 3。\n")
    make_latex_project(root / "thesis")
    write(root / "~$张三.docx", "lock")
    write(root / "old.AI-check-comments.docx", "previous output")
    return root


def test_batch_scan_skips_chapters_lock_files_and_outputs(tmp_path):
    folder = make_batch_folder(tmp_path / "papers")
    manifest = ai_batch.batch_scan(folder, tmp_path / "out", recursive=True)
    files = [entry["file"] for entry in manifest["documents"]]
    assert files == ["nested/李四.docx", "notes.md", "thesis/main.tex", "张三.docx"]
    reasons = {item["path"]: item["reason"] for item in manifest["skipped"]}
    assert reasons["~$张三.docx"] == "Word lock file"
    assert reasons["old.AI-check-comments.docx"] == "AI-check output"
    assert reasons["thesis/chapters/intro.tex"].startswith("included by another .tex")
    thesis = next(entry for entry in manifest["documents"] if entry["file"] == "thesis/main.tex")
    assert "chapters/method.tex" in thesis["includedFiles"]
    assert all(Path(entry["scanPath"]).is_file() for entry in manifest["documents"])
    flat = ai_batch.batch_scan(folder, tmp_path / "out-flat")
    assert "nested/李四.docx" not in [entry["file"] for entry in flat["documents"]]


def test_batch_report_builds_summary_table(tmp_path):
    folder = make_batch_folder(tmp_path / "papers")
    out = tmp_path / "out"
    manifest = ai_batch.batch_scan(folder, out, recursive=True)
    for entry in manifest["documents"]:
        if entry["file"] == "notes.md":
            continue  # left pending on purpose
        scan = json.loads(Path(entry["scanPath"]).read_text(encoding="utf-8"))
        value = 0.72 if entry["file"] == "张三.docx" else 0.4
        payload = [{"chunkId": c["chunkId"], "aigcValue": value, "verdict": "suspicious", "reason": "模板化", "signals": ["模板表达"]} for c in scan["chunks"]]
        write(Path(entry["resultsPath"]), json.dumps({"results": payload}, ensure_ascii=False))

    summary = ai_batch.batch_report(out)
    assert summary["documents"] == 4 and summary["reported"] == 3 and summary["pending"] == 1
    rows = summary["rows"]
    assert rows[0]["file"] == "张三.docx" and rows[-1]["status"] == "pending"
    assert rows[0]["aiRate"] > rows[1]["aiRate"]
    assert rows[0]["annotatedDocxPath"].endswith("张三.AI-check-comments.docx")
    assert 0 < summary["overallAiRate"] < 1
    page = Path(summary["summaryHtml"]).read_text(encoding="utf-8")
    assert "批量自查汇总" in page and "批注版 Word" in page and "不代表知网" in page and "待判断" in page
    assert 'href="' + rows[0]["id"] + "/" in page, "report links are relative so the folder can be zipped and shared"
    with open(summary["summaryCsv"], encoding="utf-8-sig", newline="") as handle:
        table = list(csv.reader(handle))
    assert table[0][0] == "文件 / file" and table[1][0] == "张三.docx" and table[1][2].endswith("%")
    assert len(table) == 5


def test_batch_cli_round_trip(tmp_path):
    folder = tmp_path / "papers"
    write(folder / "a.md", f"# 引言\n\n{INTRO}\n")
    script = SCRIPTS / "ai_batch.py"
    env_run = lambda *args: subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True, encoding="utf-8")
    scanned = env_run("scan", str(folder), "--out-dir", str(tmp_path / "out"))
    assert scanned.returncode == 0, scanned.stderr
    assert json.loads(scanned.stdout)["documents"][0]["id"] == "a-md"
    reported = env_run("report", str(tmp_path / "out"))
    assert reported.returncode == 0, reported.stderr
    assert json.loads(reported.stdout)["pending"] == 1
    missing = env_run("report", str(tmp_path / "nowhere"))
    assert missing.returncode == 1 and "batch.json" in missing.stderr
