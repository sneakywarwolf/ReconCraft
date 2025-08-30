# ReconCraft by Nirmal Chakraborty
# Copyright (c) 2025. All rights reserved.
# See LICENSE for details.

# ===================== core/report_exporter.py =====================
# Export CSV/HTML/PDF/JSON for a single run model

import csv
from typing import Dict, Any
import json as _json
import html  # <-- needed by _render_html (escapes)
from pathlib import Path  # <-- used by helper exporters and paths

try:
        from PyQt5.QtGui import QTextDocument
        from PyQt5.QtGui import QPagedPaintDevice
        from PyQt5.QtPrintSupport import QPrinter
except Exception:
        from PySide6.QtGui import QTextDocument
        from PySide6.QtGui import QPagedPaintDevice
        from PySide6.QtPrintSupport import QPrinter


def export_csv(model: Dict[str, Any], out_path: str) -> None:
    cols = [
        "scan_id", "run_id", "tool", "tool_version", "target", "asset", "location", "port", "service",
        "category", "severity", "score", "title", "evidence_snippet", "references", "started_at", "ended_at",
    ]
    run = model.get("run", {})
    defaults = {
        "scan_id": run.get("scan_id"),
        "run_id": run.get("run_id"),
        "tool": run.get("tool"),
        "tool_version": run.get("tool_version"),
        "target": (run.get("targets") or [None])[0],
        "started_at": run.get("started_at"),
        "ended_at": run.get("ended_at"),
    }
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for fi in model.get("findings", []):
            row = {**defaults,
                   "asset": fi.get("asset"),
                   "location": fi.get("location"),
                   "port": fi.get("port"),
                   "service": fi.get("service"),
                   "category": fi.get("category"),
                   "severity": fi.get("severity"),
                   "score": fi.get("score"),
                   "title": fi.get("title"),
                   "evidence_snippet": fi.get("evidence"),
                   "references": ",".join(fi.get("references", []) if isinstance(fi.get("references"), list) else [fi.get("references")] if fi.get("references") else []),
                   }
            w.writerow(row)


def _render_html(model: Dict[str, Any]) -> str:
    run = model.get("run", {})
    counts = model.get("counts", {})
    def esc(x):
        return html.escape(str(x)) if x is not None else ""
    # Build minimal HTML (standalone)
    html_head = """
    <html><head><meta charset='utf-8'>
    <style>
    body { font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; }
    .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
    .card { border: 1px solid #ddd; border-radius: 10px; padding: 12px; }
    .sev { display:inline-block; padding:2px 8px; border-radius: 999px; font-size: 12px; }
    .sev.critical { background:#7b1e1e; color:#fff; }
    .sev.high { background:#d32f2f; color:#fff; }
    .sev.medium { background:#f9a825; color:#000; }
    .sev.low { background:#0288d1; color:#fff; }
    .sev.info { background:#607d8b; color:#fff; }
    table { border-collapse: collapse; width: 100%; margin-top: 12px; }
    th, td { border: 1px solid #e5e5e5; padding: 6px 8px; font-size: 13px; vertical-align: top; }
    th { background: #fafafa; text-align: left; }
    code { background:#f5f5f5; padding:2px 4px; border-radius:4px; }
    </style>
    </head><body>
    """
    header = f"""
    <h2>ReconCraft Report — {esc(run.get('tool'))}</h2>
    <div class='cards'>
      <div class='card'><b>Target</b><br>{esc((run.get('targets') or [''])[0])}</div>
      <div class='card'><b>Run ID</b><br><code>{esc(run.get('run_id'))}</code></div>
      <div class='card'><b>Started</b><br>{esc(run.get('started_at'))}</div>
      <div class='card'><b>Ended</b><br>{esc(run.get('ended_at'))}</div>
      <div class='card'><b>Status</b><br>{esc(run.get('status'))} (exit {esc(run.get('exit_code'))})</div>
      <div class='card'><b>Severity</b><br>
        <span class='sev critical'>Critical: {counts.get('critical',0)}</span>
        <span class='sev high'>High: {counts.get('high',0)}</span>
        <span class='sev medium'>Medium: {counts.get('medium',0)}</span>
        <span class='sev low'>Low: {counts.get('low',0)}</span>
        <span class='sev info'>Info: {counts.get('info',0)}</span>
      </div>
    </div>
    """
    # Table rows
    rows = []
    for fi in model.get("findings", []):
        rows.append(f"""
        <tr>
          <td><span class='sev {esc((fi.get('severity') or '').lower())}'>{esc(fi.get('severity'))}</span></td>
          <td>{esc(fi.get('title'))}</td>
          <td>{esc(fi.get('asset'))}</td>
          <td>{esc(fi.get('location'))}</td>
          <td>{esc(fi.get('port'))}</td>
          <td>{esc(fi.get('service'))}</td>
          <td>{esc(fi.get('category'))}</td>
          <td><code>{esc(fi.get('evidence'))}</code></td>
        </tr>
        """)
    table = """
    <table>
      <thead><tr>
        <th>Severity</</th><th>Title</th><th>Asset</th><th>Location</th><th>Port</th><th>Service</th><th>Category</th><th>Evidence</th>
      </tr></thead>
      <tbody>
    """ + ("\n".join(rows) if rows else "<tr><td colspan='8'><i>No structured findings.</i></td></tr>") + """
      </tbody>
    </table>
    """
    return html_head + header + table + "</body></html>"


def export_html(model: Dict[str, Any], out_path: str) -> None:
    html_str = _render_html(model)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_str)


def export_pdf(model: Dict[str, Any], out_path: str) -> None:
    # Render our HTML via QTextDocument → PDF
    doc = QTextDocument()
    doc.setHtml(_render_html(model))
    printer = QPrinter()
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(out_path)
    printer.setPageMargins(12, 12, 12, 12, QPagedPaintDevice.Millimeter)
    doc.print_(printer)


def export_json(model: Dict[str, Any], out_path: str) -> None:
    with open(out_path, "w", encoding="utf-8") as f:
        _json.dump(model, f, ensure_ascii=False, indent=2)


# ------------------------------------------------------------------
# Additional UI-agnostic helpers for the Reports tab "Export…" menu.
# These write into: <run_dir>/exports/  (auto-created if missing)
# ------------------------------------------------------------------

def _pp(p) -> Path:
    """Internal: normalize to Path."""
    return p if isinstance(p, Path) else Path(p)

def _ensure_exports_dir(run_dir: str | Path) -> Path:
    """Return <run_dir>/exports, creating it if missing."""
    exp = _pp(run_dir) / "exports"
    exp.mkdir(parents=True, exist_ok=True)
    return exp


def export_copy_raw(raw_path: str | Path, run_dir: str | Path, tool: str, run_id: str) -> Path:
    """
    Copy raw_<tool>.log to:
        <run_dir>/exports/<tool>_<run_id>.log
    """
    src = _pp(raw_path)
    out = _ensure_exports_dir(run_dir) / f"{tool}_{run_id}.log"
    out.write_text(src.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    return out


def export_raw_to_html(raw_text: str, run_dir: str | Path, tool: str, target: str, run_id: str) -> Path:
    """
    Save the given raw text as a minimal HTML page to:
        <run_dir>/exports/<tool>_<run_id>.html
    """
    html_doc = f"""<!doctype html>
<html><head><meta charset="utf-8">
<title>{html.escape(tool)} – {html.escape(run_id)}</title>
<style>
body {{ background:#0e0e0e; color:#d8d8d8; font-family:Consolas,'Fira Code',monospace; }}
pre  {{ white-space:pre-wrap; word-wrap:break-word; }}
h3   {{ margin:0 0 12px 0; }}
</style></head>
<body>
<h3>{html.escape(tool)} — {html.escape(target)} — {html.escape(run_id)}</h3>
<pre>{html.escape(raw_text or "")}</pre>
</body></html>"""
    out = _ensure_exports_dir(run_dir) / f"{tool}_{run_id}.html"
    out.write_text(html_doc, encoding="utf-8")
    return out


def export_findings_json(findings: list[dict] | None, run_dir: str | Path, run_id: str) -> Path:
    """
    Dump structured findings to:
        <run_dir>/exports/findings_<run_id>.json
    """
    out = _ensure_exports_dir(run_dir) / f"findings_{run_id}.json"
    out.write_text(_json.dumps(findings or [], ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def export_findings_csv(findings: list[dict] | None, run_dir: str | Path, run_id: str) -> Path:
    """
    Export structured findings to:
        <run_dir>/exports/findings_<run_id>.csv
    Columns: severity, title, asset, location, port, service, category, evidence
    """
    fields = ["severity", "title", "asset", "location", "port", "service", "category", "evidence"]
    out = _ensure_exports_dir(run_dir) / f"findings_{run_id}.csv"
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for row in (findings or []):
            w.writerow({k: (row.get(k, "") if isinstance(row, dict) else "") for k in fields})
    return out