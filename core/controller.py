# ReconCraft by Nirmal Chakraborty
# Copyright (c) 2025. All rights reserved.
# See LICENSE for details.

from reconcraft import read_ip_list, load_plugins, scan_target, report_data
import logging
import json
import os
from core.plugin_loader import discover_plugins

def scan_targets(targets, selected_plugins, status_callback=None, save_to_path=None):
    plugins = discover_plugins(selected_plugins)
    if not plugins:
        logging.error("No plugins loaded.")
        return

    for ip in targets:
        if status_callback:
            status_callback(f"[>>>] Scanning: {ip}")
        scan_target(ip, plugins)
        if status_callback:
            status_callback(f"[✓] Completed: {ip}")

    if save_to_path:
        with open(save_to_path, "w") as f:
            json.dump(report_data, f, indent=4)

    return report_data
