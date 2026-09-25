# ReconCraft by Nirmal Chakraborty
# Copyright (c) 2025. All rights reserved.
# See LICENSE for details.

"""
Headless batch controller.

Previously this module imported a top-level ``reconcraft`` module that does not
exist in the project, so every symbol here raised ``ModuleNotFoundError`` on
import and the module was dead. It is now a thin, working batch API layered on
``core.headless_runner.HeadlessRunner`` — a GUI-free way to run several plugins
across several targets programmatically. It does not touch the PyQt GUI or
``ScanThread``.
"""

from __future__ import annotations

import json
import logging
from typing import Callable, Dict, List, Optional

from core.headless_runner import HeadlessRunner, new_scan_root


def scan_targets(
    targets: List[str],
    selected_plugins: List[str],
    status_callback: Optional[Callable[[str], None]] = None,
    save_to_path: Optional[str] = None,
    profile: str = "Normal",
    output_dir: str = "cli_runs",
    custom_args_map: Optional[Dict[str, str]] = None,
    timeout: Optional[float] = None,
) -> Dict:
    """
    Run ``selected_plugins`` against each target and return a structured report.

    Args:
        targets: hosts / IPs / URLs to scan.
        selected_plugins: plugin names to run (must exist in ``plugins/``).
        status_callback: optional progress sink, called with status strings.
        save_to_path: if set, the returned report is also written here as JSON.
        profile: Aggressive | Normal | Passive | Custom.
        output_dir: base directory for a new scan-root folder.
        custom_args_map: per-tool arg templates used when ``profile='Custom'``.
        timeout: optional per-command wall-clock timeout (seconds).

    Returns:
        ``{"scan_root": str, "results": [RunResult.to_dict(), ...]}``.
    """
    scan_root = new_scan_root(output_dir, label="batch")
    runner = HeadlessRunner(report_root_folder=scan_root, default_timeout=timeout)

    available = set(runner.available_tools())
    unknown = [p for p in selected_plugins if p not in available]
    if unknown:
        logging.warning("Unknown plugins skipped: %s", ", ".join(unknown))
        if status_callback:
            status_callback(f"[!] Unknown plugins skipped: {', '.join(unknown)}")

    custom_map = dict(custom_args_map or {})
    report: Dict = {"scan_root": scan_root, "results": []}

    for target in targets:
        if status_callback:
            status_callback(f"[>>>] Scanning: {target}")
        for plugin in selected_plugins:
            if plugin not in available:
                continue
            result = runner.run_tool(
                tool=plugin,
                target=target,
                profile=profile,
                custom_args=custom_map.get(plugin),
                timeout=timeout,
            )
            report["results"].append(result.to_dict())
            if status_callback:
                status_callback(f"    - {plugin}: {result.status or ('ok' if result.ok else 'error')}")
        if status_callback:
            status_callback(f"[✓] Completed: {target}")

    if save_to_path:
        with open(save_to_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=4)

    return report
