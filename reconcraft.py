#!/usr/bin/env python3

import os
import subprocess
import argparse
import logging
import json
from datetime import datetime
from shutil import which
import importlib
import inspect

logging.basicConfig(
    format='[%(levelname)s] %(message)s',
    level=logging.INFO
)

report_data = {}

def read_ip_list(file_path):
    try:
        with open(file_path) as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logging.error(f"IP list file not found: {file_path}")
        return []

def check_tool_installed(tool_name):
    return which(tool_name) is not None

def run_command(command, raw_file):
    logging.info(f"Executing: {command}")
    full_path = os.path.join(RAW_DIR, raw_file)

    try:
        if isinstance(command, str):
            command = command.split()

        result = subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=180, text=True
        )

        with open(full_path, "w") as out:
            out.write(result.stdout)

        return full_path

    except subprocess.TimeoutExpired:
        logging.error(f"[!] Command timed out: {' '.join(command)}")
        return full_path

    except Exception as e:
        logging.error(f"[!] Command execution failed: {e}")
        return full_path


def extract_cves(raw_path, ip):
    cve_file = os.path.join(CVE_DIR, f"{ip}_cves.txt")
    found_cves = set()

    with open(raw_path, "r", errors="ignore") as raw, open(cve_file, "w") as out:
        for line in raw:
            if "CVE-" in line:
                cve_candidates = [word for word in line.strip().split() if "CVE-" in word]
                for cve in cve_candidates:
                    if cve not in found_cves:
                        found_cves.add(cve)
                        out.write(cve + "\n")
                        result = subprocess.getoutput(f'searchsploit {cve}')
                        out.write(result + "\n\n")

    return list(found_cves)

def list_available_plugins():
    plugin_dir = "plugins"
    if not os.path.isdir(plugin_dir):
        logging.error(f"Plugin directory '{plugin_dir}' not found.")
        return []
    plugins = []
    for filename in os.listdir(plugin_dir):
        if filename.endswith(".py") and not filename.startswith("__"):
            module_name = filename[:-3]
            try:
                module = importlib.import_module(f"plugins.{module_name}")
                desc = inspect.getdoc(module) or "No description provided."
                plugins.append((module_name, desc.split('\n')[0]))
            except Exception as e:
                plugins.append((module_name, f"Failed to load: {e}"))
    return plugins

def load_plugins(selected_plugins=None):
    plugins = []
    plugin_dir = "plugins"
    if not os.path.isdir(plugin_dir):
        logging.error(f"Plugin directory '{plugin_dir}' not found.")
        return plugins
    for filename in os.listdir(plugin_dir):
        if filename.endswith(".py") and not filename.startswith("__"):
            module_name = filename[:-3]
            if selected_plugins and module_name not in selected_plugins:
                continue
            try:
                module = importlib.import_module(f"plugins.{module_name}")
                if hasattr(module, "run"):
                    plugins.append(module)
                    logging.info(f"[+] Loaded plugin: {module_name}")
                else:
                    logging.warning(f"[!] Plugin '{module_name}' does not have a 'run(ip)' function.")
            except Exception as e:
                logging.error(f"[!] Failed to load plugin '{module_name}': {e}")
    return plugins

def scan_target(ip, plugins):
    logging.info(f"[>>>] Scanning: {ip}")
    report_data[ip] = {}
    for plugin in plugins:
        try:
            plugin.run(ip, RAW_DIR, BASE_DIR, run_command, check_tool_installed, extract_cves)
            report_data[ip][plugin.__name__] = "Completed"
        except Exception as e:
            report_data[ip][plugin.__name__] = f"Failed: {e}"
            logging.warning(f"[!] Plugin {plugin.__name__} failed for {ip}: {e}")

##Creates the internal structure inside that path: reports/ and logs/, and returns a dictionary of paths.
def prepare_scan_directories(base_path): 
    """
    Creates the standard directory structure under the given base path.
    Returns a dictionary with the paths.
    """
    os.makedirs(base_path, exist_ok=True)
    reports_path = os.path.join(base_path, "Sub-Reports")
    logs_path = os.path.join(base_path, "Logs")

    os.makedirs(reports_path, exist_ok=True)
    os.makedirs(logs_path, exist_ok=True)

    return {
        "base": base_path,
        "reports": reports_path,
        "logs": logs_path
    }


def main():
    
    """   global BASE_DIR, CVE_DIR, RAW_DIR, REPORT_DIR
    BASE_DIR = base_dir
    CVE_DIR = cve_dir
    RAW_DIR = raw_dir
    REPORT_DIR = report_dir
    """
    
    parser = argparse.ArgumentParser(description="ReconCraft - Active Reconnaissance Tool")
    parser.add_argument("-f", "--file", default="ip-list.txt", help="Path to file containing target IPs or domains")
    parser.add_argument("-p", "--plugins", help="Comma-separated list of plugins to run (e.g., nmap,nuclei,nikto)")
    parser.add_argument("--list-plugins", action="store_true", help="List all available plugins and exit")
    parser.add_argument("--create-plugin", help="Create a boilerplate plugin with the given name")
    args = parser.parse_args()

    if args.create_plugin:
        name = args.create_plugin.strip()
        path = os.path.join("plugins", f"{name}.py")
        if os.path.exists(path):
            print(f"[!] Plugin '{name}' already exists.")
        else:
            with open(path, "w") as f:
                f.write(f'''"""
            {name} - Describe what this plugin does.
            """

            def run(ip, raw_dir, base_dir, run_command, check_tool_installed, extract_cves):
                pass
            ''')

    if args.list_plugins:
        available = list_available_plugins()
        print("\n[+] Available Plugins:")
        for plugin, desc in sorted(available):
            print(f"  - {plugin:<15} : {desc}")
        return

    targets = read_ip_list(args.file)
    if not targets:
        logging.error("No targets to scan. Exiting.")
        return

    selected_plugins = args.plugins.split(",") if args.plugins else None
    plugins = load_plugins(selected_plugins)
    if not plugins:
        logging.error("No plugins loaded. Exiting.")
        return

    logging.info(f"[✓] Plugins loaded. Starting scans on {len(targets)} target(s)...")
    for ip in targets:
        scan_target(ip, plugins)

    report_path = os.path.join(REPORT_DIR, "report.json")
    with open(report_path, "w") as f:
        json.dump(report_data, f, indent=4)

    logging.info(f"\n[✓] All scans completed. Report saved at: {report_path}\n")

if __name__ == "__main__":
    main()