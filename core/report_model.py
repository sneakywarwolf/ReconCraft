# ReconCraft by Nirmal Chakraborty
# Copyright (c) 2025. All rights reserved.
# See LICENSE for details.

# ===================== core/report_model.py =====================
# Load a single run (run.json + findings.jsonl) into a normalized in-memory model

import json
from typing import Dict, Any, List

SCHEMA_VERSION = "1.0"

def load_run_model(run_json_path: str, findings_path: str | None = None) -> Dict[str, Any]:
    model: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run": {},
        "findings": [],
        "counts": {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0},
    }
    try:
        with open(run_json_path, "r", encoding="utf-8") as f:
            model["run"] = json.load(f)
    except Exception:
        model["run"] = {}

    if findings_path:
        try:
            with open(findings_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        model["findings"].append(obj)
                        sev = (obj.get("severity") or "").lower()
                        if sev in model["counts"]:
                            model["counts"][sev] += 1
                    except Exception:
                        pass
        except FileNotFoundError:
            pass
    return model