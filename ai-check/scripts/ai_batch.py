#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch mode: scan every paper in a folder, then report them all with one summary table.

    ai_batch.py scan <folder> --out-dir <dir> [--recursive] [--include-tables]
    (the assistant judges each <dir>/<id>.scan.json and saves <dir>/<id>.results.json)
    ai_batch.py report <dir> [--no-annotate]

The summary (HTML, CSV for Excel, JSON) lists every document with its reference AI rate, the section
that contributes most, the most frequent writing patterns and the number of repeated sentences. Like
the single-document report it is a writing-quality self-check, not a detector result.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from ai_check import OFFICIAL_SITE, SUPPORTED_SUFFIXES, generate_report, load_json, percent, scan_docx, write_json  # noqa: E402
from source_formats import _read_tex, _strip_latex_comments, latex_include_targets, latex_project_files  # noqa: E402

MANIFEST_NAME = "batch.json"
OUTPUT_MARKERS = (".AI-check-comments.", ".revised.", ".ai-check.")


def doc_id(rel: Path) -> str:
    """Stable, filesystem-safe id from the path relative to the batch folder (extension kept)."""
    raw = "__".join(rel.with_suffix("").parts) + "-" + rel.suffix.lstrip(".").lower()
    return re.sub(r"[^\w.-]+", "_", raw, flags=re.UNICODE).strip("_") or "document"


def included_tex_files(files: list[Path]) -> set[Path]:
    """.tex files that another .tex file in the batch pulls in (chapter files of a thesis).

    Files with \\documentclass are main files: their includes are followed exactly as the scanner
    does. Other .tex files only contribute includes that resolve next to themselves.
    """
    included: set[Path] = set()
    for path in files:
        if path.suffix.lower() != ".tex":
            continue
        try:
            content = _strip_latex_comments(_read_tex(path))
        except OSError:
            continue
        if "\\documentclass" in content:
            included.update(latex_project_files(path)[1:])
            continue
        for _start, _end, target, _name in latex_include_targets(content, path.parent, path.parent):
            if target is not None and target != path:
                included.add(target)
    return included


def collect_documents(folder: Path, out_dir: Path, recursive: bool = False) -> tuple[list[Path], list[dict[str, str]]]:
    folder = folder.resolve()
    out_dir = out_dir.resolve()
    pattern = "**/*" if recursive else "*"
    candidates = sorted(p.resolve() for p in folder.glob(pattern) if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES)
    skipped: list[dict[str, str]] = []
    kept: list[Path] = []
    for path in candidates:
        rel = path.relative_to(folder).as_posix()
        if out_dir == path.parent or out_dir in path.parents:
            continue  # our own output folder
        if path.name.startswith("~$"):
            skipped.append({"path": rel, "reason": "Word lock file"})
        elif any(marker in path.name for marker in OUTPUT_MARKERS):
            skipped.append({"path": rel, "reason": "AI-check output"})
        else:
            kept.append(path)
    chapters = included_tex_files(kept)
    documents = []
    for path in kept:
        if path in chapters:
            skipped.append({"path": path.relative_to(folder).as_posix(), "reason": "included by another .tex file (scanned as part of it)"})
        else:
            documents.append(path)
    return documents, skipped


def batch_scan(folder: Path, out_dir: Path, recursive: bool = False, include_tables: bool = False) -> dict[str, Any]:
    if not folder.is_dir():
        raise ValueError(f"not a folder: {folder}")
    out_dir.mkdir(parents=True, exist_ok=True)
    documents, skipped = collect_documents(folder, out_dir, recursive=recursive)
    entries = []
    for path in documents:
        rel = path.relative_to(folder.resolve())
        identifier = doc_id(rel)
        entry: dict[str, Any] = {
            "id": identifier,
            "file": rel.as_posix(),
            "sourcePath": str(path),
            "scanPath": str((out_dir / f"{identifier}.scan.json").resolve()),
            "resultsPath": str((out_dir / f"{identifier}.results.json").resolve()),
        }
        try:
            scan = scan_docx(path, include_tables=include_tables)
        except Exception as exc:  # one broken file must not stop the batch
            entry["error"] = str(exc)
            entries.append(entry)
            continue
        write_json(Path(entry["scanPath"]), scan)
        entry.update({"chunks": len(scan["chunks"]), "totalChars": scan["totalChars"], "title": scan["documentTitle"]})
        if scan.get("includedFiles"):
            entry["includedFiles"] = scan["includedFiles"]
        entries.append(entry)
    manifest = {
        "tool": "AI-check",
        "kind": "batch",
        "createdAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "folder": str(folder.resolve()),
        "outDir": str(out_dir.resolve()),
        "documents": entries,
        "skipped": skipped,
        "next": "Judge every chunk of each scanPath and save the results JSON to that document's resultsPath, then run: ai_batch.py report <outDir>",
    }
    write_json(out_dir / MANIFEST_NAME, manifest)
    return manifest


def _manifest_path(target: Path) -> Path:
    return target / MANIFEST_NAME if target.is_dir() else target


def batch_report(target: Path, annotate: bool = True) -> dict[str, Any]:
    manifest_path = _manifest_path(target)
    if not manifest_path.is_file():
        raise ValueError(f"no {MANIFEST_NAME} in {target}; run `ai_batch.py scan <folder> --out-dir {target}` first")
    manifest = load_json(manifest_path)
    out_dir = manifest_path.parent
    rows: list[dict[str, Any]] = []
    for entry in manifest.get("documents", []):
        row: dict[str, Any] = {"id": entry["id"], "file": entry["file"], "totalChars": entry.get("totalChars", 0)}
        results_path = Path(entry["resultsPath"])
        if entry.get("error"):
            row.update(status="error", note=entry["error"])
        elif not results_path.is_file():
            row.update(status="pending", note="no results JSON yet")
        else:
            try:
                summary = generate_report(Path(entry["scanPath"]), results_path, out_dir / entry["id"], annotate=annotate)
            except Exception as exc:
                row.update(status="error", note=str(exc))
            else:
                sections = summary.get("sectionBreakdown") or []
                row.update(
                    status="done",
                    aiRate=summary["aiRate"],
                    suspiciousAiRate=summary["suspiciousAiRate"],
                    suspiciousChars=summary["suspiciousChars"],
                    totalChars=summary["totalChars"],
                    fragments=summary["fragmentCount"],
                    topSection=f"{sections[0]['section']} ({percent(sections[0]['aiRate'])})" if sections else "",
                    topSignals=[item["signal"] for item in (summary.get("topSignals") or [])[:3]],
                    repeatedSentences=len(summary.get("internalRepetition") or []),
                    htmlPath=summary["htmlPath"],
                    pdfPath=summary["pdfPath"],
                    annotatedDocxPath=summary.get("annotatedDocxPath", ""),
                )
        rows.append(row)
    rows.sort(key=lambda r: (r["status"] != "done", -float(r.get("aiRate") or 0), r["file"]))

    done = [r for r in rows if r["status"] == "done"]
    total_chars = sum(int(r["totalChars"] or 0) for r in done)
    overall = sum(float(r["aiRate"]) * int(r["totalChars"] or 0) for r in done) / total_chars if total_chars else 0.0
    output = {
        "tool": "AI-check",
        "kind": "batch-summary",
        "createdAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "folder": manifest.get("folder"),
        "documents": len(rows),
        "reported": len(done),
        "pending": sum(1 for r in rows if r["status"] == "pending"),
        "errors": sum(1 for r in rows if r["status"] == "error"),
        "overallAiRate": round(overall, 4),
        "rows": rows,
        "skipped": manifest.get("skipped", []),
    }
    html_path = out_dir / "batch-summary.html"
    csv_path = out_dir / "batch-summary.csv"
    json_path = out_dir / "batch-summary.json"
    html_path.write_text(render_batch_html(output, out_dir), encoding="utf-8", newline="\n")
    write_batch_csv(csv_path, rows)
    output.update(summaryHtml=str(html_path.resolve()), summaryCsv=str(csv_path.resolve()), summaryJson=str(json_path.resolve()))
    write_json(json_path, output)
    return output


CSV_COLUMNS = [
    ("file", "文件 / file"),
    ("status", "状态 / status"),
    ("aiRate", "AI率（参考）/ AI rate"),
    ("suspiciousAiRate", "疑似比例 / suspicious share"),
    ("totalChars", "总字数 / chars"),
    ("fragments", "疑似片段 / fragments"),
    ("topSection", "最需修改章节 / top section"),
    ("topSignals", "高频写作模式 / top patterns"),
    ("repeatedSentences", "前后重复 / repeated"),
    ("htmlPath", "报告 / report"),
    ("note", "备注 / note"),
]


def write_batch_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    # utf-8-sig so Excel opens Chinese text correctly
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([label for _key, label in CSV_COLUMNS])
        for row in rows:
            values = []
            for key, _label in CSV_COLUMNS:
                value = row.get(key, "")
                if key in ("aiRate", "suspiciousAiRate") and value != "":
                    value = percent(float(value))
                elif isinstance(value, list):
                    value = "、".join(value)
                values.append(value)
            writer.writerow(values)


STATUS_TEXT = {"done": "已出报告", "pending": "待判断", "error": "出错"}


def render_batch_html(summary: dict[str, Any], out_dir: Path) -> str:
    def link(path: str, label: str) -> str:
        if not path:
            return ""
        try:
            href = Path(path).resolve().relative_to(out_dir.resolve()).as_posix()
        except ValueError:
            href = Path(path).resolve().as_uri()
        return f'<a href="{html.escape(href)}">{html.escape(label)}</a>'

    body = []
    for row in summary["rows"]:
        rate = float(row.get("aiRate") or 0)
        level = "high" if rate >= 0.3 else "medium" if rate >= 0.15 else "low"
        links = " · ".join(filter(None, [link(row.get("htmlPath", ""), "HTML"), link(row.get("pdfPath", ""), "PDF"), link(row.get("annotatedDocxPath", ""), "批注版 Word")]))
        body.append(
            "<tr>"
            f"<td class=\"file\">{html.escape(row['file'])}</td>"
            f"<td>{STATUS_TEXT.get(row['status'], row['status'])}</td>"
            f"<td class=\"num {level if row['status'] == 'done' else ''}\">{percent(rate) if row['status'] == 'done' else '-'}</td>"
            f"<td class=\"num\">{row.get('totalChars') or '-'}</td>"
            f"<td class=\"num\">{row.get('fragments', '-')}</td>"
            f"<td>{html.escape(row.get('topSection') or '-')}</td>"
            f"<td>{html.escape('、'.join(row.get('topSignals') or []) or '-')}</td>"
            f"<td class=\"num\">{row.get('repeatedSentences', '-')}</td>"
            f"<td>{links or html.escape(row.get('note', ''))}</td>"
            "</tr>"
        )
    skipped = "".join(f"<li>{html.escape(item['path'])}：{html.escape(item['reason'])}</li>" for item in summary.get("skipped", []))
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>AI-check 批量自查汇总</title>
<style>
  :root {{ --fg:#202124; --muted:#5f6368; --line:#d9d9d9; --head:#f7f7f7; --bg:#ffffff; --accent:#4b89dc; --high:#d93025; --medium:#b06000; --low:#188038; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --fg:#e8eaed; --muted:#9aa0a6; --line:#3c4043; --head:#2a2b2e; --bg:#1f2023; --high:#f28b82; --medium:#fdd663; --low:#81c995; }} }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--fg); font: 13px/1.6 "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", Arial, sans-serif; }}
  main {{ max-width: 1200px; margin: 0 auto; padding: 24px 16px 40px; }}
  h1 {{ font-size: 22px; margin: 0 0 6px; }}
  .meta {{ color: var(--muted); margin-bottom: 16px; }}
  .cards {{ display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 18px; }}
  .card {{ border: 1px solid var(--line); border-radius: 6px; padding: 10px 14px; min-width: 130px; }}
  .card strong {{ display: block; font-size: 20px; }}
  .wrap {{ overflow-x: auto; border: 1px solid var(--line); border-radius: 6px; }}
  table {{ border-collapse: collapse; width: 100%; min-width: 900px; }}
  th, td {{ border-bottom: 1px solid var(--line); padding: 7px 9px; text-align: left; vertical-align: top; }}
  th {{ background: var(--head); color: var(--muted); font-weight: 600; white-space: nowrap; }}
  td.file {{ word-break: break-all; max-width: 260px; }}
  td.num {{ white-space: nowrap; text-align: right; }}
  td.high {{ color: var(--high); font-weight: 700; }} td.medium {{ color: var(--medium); font-weight: 700; }} td.low {{ color: var(--low); font-weight: 700; }}
  a {{ color: var(--accent); }}
  .notes {{ color: var(--muted); margin-top: 18px; }}
</style>
</head>
<body>
<main>
<h1>AI-check 批量自查汇总</h1>
<div class="meta">{html.escape(str(summary.get('folder') or ''))} · {html.escape(summary['createdAt'])}</div>
<section class="cards">
  <div class="card"><strong>{summary['documents']}</strong>文档</div>
  <div class="card"><strong>{summary['reported']}</strong>已出报告</div>
  <div class="card"><strong>{summary['pending']}</strong>待判断</div>
  <div class="card"><strong>{percent(summary['overallAiRate'])}</strong>按字数加权的整体 AI 率（参考）</div>
</section>
<div class="wrap"><table>
<thead><tr><th>文件</th><th>状态</th><th>AI率（参考）</th><th>总字数</th><th>疑似片段</th><th>最需修改的章节</th><th>高频写作模式</th><th>前后重复</th><th>报告</th></tr></thead>
<tbody>
{''.join(body)}
</tbody>
</table></div>
{f'<p class="notes">未单独检测的文件：</p><ul class="notes">{skipped}</ul>' if skipped else ''}
<section class="notes">
<p>说明：AI 率由当前 AI 助手逐段判断后汇总，仅作写作质量自查参考，不代表知网、维普、Turnitin 或其他平台的检测结果。按 AI 率从高到低排序。</p>
<p>EasyIdea：<a href="{OFFICIAL_SITE}">{OFFICIAL_SITE}</a></p>
</section>
</main>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def command_scan(args: argparse.Namespace) -> int:
    manifest = batch_scan(Path(args.folder), Path(args.out_dir), recursive=args.recursive, include_tables=args.include_tables)
    brief = {
        "manifest": str((Path(args.out_dir) / MANIFEST_NAME).resolve()),
        "documents": [
            {key: entry.get(key) for key in ("id", "file", "chunks", "totalChars", "scanPath", "resultsPath", "error") if entry.get(key) is not None}
            for entry in manifest["documents"]
        ],
        "skipped": manifest["skipped"],
        "next": manifest["next"],
    }
    print(json.dumps(brief, ensure_ascii=False, indent=2))
    return 0


def command_report(args: argparse.Namespace) -> int:
    output = batch_report(Path(args.batch_dir), annotate=not args.no_annotate)
    brief = {key: output[key] for key in ("documents", "reported", "pending", "errors", "overallAiRate", "summaryHtml", "summaryCsv", "summaryJson")}
    brief["rows"] = [{key: row.get(key) for key in ("file", "status", "aiRate", "topSection", "note") if row.get(key) is not None} for row in output["rows"]]
    print(json.dumps(brief, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI-check batch mode: scan a folder of papers, then report them with one summary table")
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan", help="scan every .docx/.md/.tex/.txt paper in a folder")
    scan.add_argument("folder")
    scan.add_argument("--out-dir", required=True, help="where scans, results, reports and the summary go")
    scan.add_argument("--recursive", action="store_true", help="also scan sub-folders")
    scan.add_argument("--include-tables", action="store_true", help="also scan text inside DOCX tables")
    scan.set_defaults(func=command_scan)
    report = sub.add_parser("report", help="render every document that has a results JSON, plus batch-summary.html/.csv/.json")
    report.add_argument("batch_dir", help="the --out-dir of the batch scan (or its batch.json)")
    report.add_argument("--no-annotate", action="store_true", help="do not write annotated Word copies")
    report.set_defaults(func=command_report)
    return parser


def use_utf8_output() -> None:
    """JSON and help text contain Chinese; never crash on a cp1252/cp437 console or pipe."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # pragma: no cover - replaced or detached streams
            pass


def main(argv: list[str] | None = None) -> int:
    use_utf8_output()
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:
        print(f"AI-check batch error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
