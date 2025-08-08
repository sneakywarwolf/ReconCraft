# ReconCraft by Nirmal Chakraborty
# Copyright (c) 2025. All rights reserved.
# See LICENSE for details.



import shutil
import os
import subprocess

def is_tool_installed(tool_bin, script_path=None, debug=False):
    """
    Checks if a CLI binary or script is installed and usable.
    - tool_bin: The CLI tool (e.g., 'amass', 'nmap').
    - script_path: If it's a custom script, provide its path.
    - debug: Print debug info if True.
    Returns True if found *and* runs with --version/-h, else False.
    """
    # 0. List of GUI tools that should NOT be launched!
    gui_tools = {"dirbuster", "burpsuite", "zenmap", "owasp-zap"}  # Expand as needed

    # 1. Check if the binary exists in PATH
    path = shutil.which(tool_bin.strip())
    if debug:
        print(f"[DEBUG] Checking {tool_bin!r}: shutil.which() result = {path!r}")
    if path:
        # 👉 For GUI tools, just check PATH (don't try to run with --version)
        if tool_bin.lower() in gui_tools:
            if debug:
                print(f"[DEBUG] {tool_bin!r} is a known GUI tool. Only checking PATH.")
            return True  # Only care if it's present

        # 2. Try running --version or -h to check if it's usable (CLI tools only)
        for flag in ['--version', '-v', '-h', '--help']:
            try:
                proc = subprocess.run(
                    [tool_bin, flag],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=3
                )
                if debug:
                    print(f"[DEBUG] Ran {tool_bin} {flag}: returncode={proc.returncode}")
                if proc.returncode == 0 or proc.returncode == 1:  # Some tools use 1 for help
                    return True
            except Exception as e:
                if debug:
                    print(f"[DEBUG] {tool_bin!r} {flag}: Exception: {e}")
                continue  # Try next flag
    # 3. For scripts, check if the script file exists
    if script_path:
        exists = os.path.isfile(script_path)
        if debug:
            print(f"[DEBUG] Checking for script {script_path!r}: exists = {exists}")
        if exists:
            return True
    return False
