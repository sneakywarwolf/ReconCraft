

# Non-invasive helpers you can call from your existing ScanThread after a tool finishes

import json
from typing import Dict, Any


def write_run_manifest(path: str, *, scan_id: str, run_id: str, tool: str, tool_version: str | None,
                       targets: list[str], command: list[str], started_at: str, ended_at: str,
                       status: str, exit_code: int | None, raw_log_rel: str, findings_rel: str | None,
                       extra: Dict[str, Any] | None = None) -> None:
    data: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "scan_id": scan_id,
        "run_id": run_id,
        "tool": tool,
        "tool_version": tool_version,
        "targets": targets,
        "command": command,
        "started_at": started_at,
        "ended_at": ended_at,
        "status": status,
        "exit_code": exit_code,
        "artifacts": {
            "raw_log": raw_log_rel,
            "findings": findings_rel,
        },
        "counts": {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0},
    }
    if extra:
        data.update(extra)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)