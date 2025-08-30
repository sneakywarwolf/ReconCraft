#!/usr/bin/env python3
# ReconCraft by Nirmal Chakraborty
# Copyright (c) 2025. All rights reserved.
# See LICENSE for details.
"""
ReconCraft installer & launcher

- Creates a virtual environment in .venv/
- Installs dependencies from requirements.txt
- Immediately launches ReconCraft (main.py) in that venv

Usage:
    python install.py
"""

import os, sys, subprocess, venv
import venv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
VENV_DIR = BASE_DIR / ".venv"
REQ_FILE = BASE_DIR / "requirements.txt"


def run(cmd, **kwargs):
    print(f"[*] Running: {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, **kwargs)
    if result.returncode != 0:
        sys.exit(result.returncode)


def create_venv():
    if VENV_DIR.exists():
        print("[*] Virtual environment already exists. Skipping creation.")
    else:
        print("[*] Creating virtual environment in .venv/")
        venv.EnvBuilder(with_pip=True).create(str(VENV_DIR))

    # 🔎 Safety check: verify the venv's Python exists
    py_name = "python.exe" if os.name == "nt" else "python"
    py_exe = VENV_DIR / ("Scripts" if os.name == "nt" else "bin") / py_name
    if not py_exe.exists():
        print(f"[-] Could not find expected Python interpreter in venv: {py_exe}")
        sys.exit(1)
    else:
        print(f"[*] Verified venv interpreter: {py_exe}")


def install_deps():
    print("[*] Installing dependencies from requirements.txt]")
    py_name = "python.exe" if os.name == "nt" else "python"
    py_exe = VENV_DIR / ("Scripts" if os.name == "nt" else "bin") / py_name
    if not REQ_FILE.exists():
        print("[-] requirements.txt not found!")
        sys.exit(1)

    try:
        subprocess.check_call([str(py_exe), "-m", "pip", "install", "--upgrade", "pip"])
    except subprocess.CalledProcessError as e:
        print(f"[!] pip upgrade failed (non-fatal): rc={e.returncode}")
    subprocess.check_call([str(py_exe), "-m", "pip", "install", "-r", str(REQ_FILE)])



def launch_app():
    py_name = "python.exe" if os.name == "nt" else "python"
    py_exe = VENV_DIR / ("Scripts" if os.name == "nt" else "bin") / py_name
    main_file = BASE_DIR / "main.py"

    if not py_exe.exists():
        print(f"[-] venv interpreter not found: {py_exe}")
        sys.exit(1)
    if not main_file.exists():
        print(f"[-] main.py not found: {main_file}")
        sys.exit(1)

    print("\n✅ Installation complete! Launching ReconCraft with:")
    print(f"  {py_exe} {main_file}\n")

    if os.name == "nt":
        # On Windows, spawn a new detached process and exit the installer.
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        try:
            subprocess.Popen(
                [str(py_exe), str(main_file)],
                cwd=str(BASE_DIR),
                creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                close_fds=True,
            )
        except Exception as e:
            print(f"[!] Failed to launch GUI: {e}")
            sys.exit(1)
        sys.exit(0)
    else:
        # On Linux/macOS, replace current process
        os.execv(str(py_exe), [str(py_exe), str(main_file)])

def main():
    create_venv()
    install_deps()
    launch_app()


if __name__ == "__main__":
    main()
