# ===================== core/file_conventions.py =====================
# Helpers to compute standardized on-disk paths for scan/run artifacts

import os
import uuid
from datetime import datetime, timezone

SCHEMA_VERSION = "1.0"


def iso_now():
    return datetime.now(timezone.utc).isoformat()


def ensure_dir(p: str):
    os.makedirs(p, exist_ok=True)
    return p


def scan_root(base_dir: str, scan_id: str, target_label: str) -> str:
    safe_label = target_label.replace(os.sep, "_").replace(" ", "_")[:64]
    return ensure_dir(os.path.join(base_dir, f"{scan_id}_{safe_label}"))


def run_dir(base_dir: str, scan_id: str, target_label: str, tool_name: str, run_id: str | None = None) -> str:
    rid = run_id or str(uuid.uuid4())
    tool_dir = ensure_dir(os.path.join(scan_root(base_dir, scan_id, target_label), tool_name.lower().replace(" ", "-")))
    return ensure_dir(os.path.join(tool_dir, rid))


def run_paths(base_dir: str, scan_id: str, target_label: str, tool_name: str, run_id: str | None = None):
    rd = run_dir(base_dir, scan_id, target_label, tool_name, run_id)
    return {
        "dir": rd,
        "raw_log": os.path.join(rd, "raw.log"),
        "run_json": os.path.join(rd, "run.json"),
        "findings_jsonl": os.path.join(rd, "findings.jsonl"),
        "extras": ensure_dir(os.path.join(rd, "extras")),
    }