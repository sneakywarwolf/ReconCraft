# ReconCraft by Nirmal Chakraborty
# Copyright (c) 2025. All rights reserved.
# See LICENSE for details.


from pathlib import Path
import os, sys, shutil, subprocess, platform, stat, webbrowser
from typing import Callable, Optional, Tuple

# =============================================================================
# Small utilities
# =============================================================================

def has_cmd(cmd: str) -> bool:
    return shutil.which(cmd) is not None

def is_windows() -> bool:
    return platform.system().lower() == "windows"

def shims_dir() -> Path:
    p = Path.cwd() / ".rc_shims"
    p.mkdir(exist_ok=True)
    return p

def ensure_exec(path: Path):
    try:
        m = path.stat().st_mode
        path.chmod(m | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except Exception:
        pass

def run_cmd_stream(args, emit: Optional[Callable[[str], None]] = None) -> Tuple[int, str]:
    """
    Safe runner for argv or shell string (when shell=True).
    Used by compat layer when run_streamed is not injected.
    """
    shell = isinstance(args, str)
    try:
        p = subprocess.Popen(args,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT,
                             text=True,
                             shell=shell)
        buf = []
        for line in p.stdout:
            buf.append(line)
            if emit: emit(line.rstrip("\n"))
        rc = p.wait()
        out = "".join(buf)
        return rc, out
    except FileNotFoundError:
        if emit: emit(f"command not found: {args if isinstance(args, str) else args[0]}")
        return 127, ""
    except Exception as e:
        if emit: emit(f"error: {e}")
        return 1, str(e)

# =============================================================================
# Docker helpers (for new plugin template)
# =============================================================================

def create_docker_shim(alias: str, docker_run: str, emit: Callable[[str], None]) -> Optional[Path]:
    sd = shims_dir()
    try:
        if is_windows():
            p = sd / f"{alias}.cmd"
            p.write_text(f'@echo off\r\n{docker_run} %*\r\n', encoding="utf-8")
        else:
            p = sd / alias
            p.write_text(f"#!/usr/bin/env sh\nset -e\n{docker_run} \"$@\"\n", encoding="utf-8")
            ensure_exec(p)
        # Make visible immediately in current process
        os.environ["PATH"] = str(sd) + os.pathsep + os.environ.get("PATH", "")
        emit(f"🧩 Docker shim created: {p}")
        return p
    except Exception as e:
        emit(f"❌ Shim error: {e}")
        return None

def pull_image_if_mentioned(docker_run: str, emit: Callable[[str], None]):
    # Best-effort heuristic: last token that looks like an image (has '/' or ':')
    toks = docker_run.split()
    image = next((t for t in reversed(toks) if ("/" in t or ":" in t)), None)
    if image:
        emit(f"🐳 docker pull {image}")
        run_cmd_stream(["docker", "pull", image], emit)

# =============================================================================
# Native installers (used by both safe + compat flows)
# =============================================================================

def apt_install(pkg: str, emit) -> Tuple[bool, str]:
    # Preserve your previous sudo/root logic & messages
    is_root = False
    try:
        is_root = hasattr(os, "geteuid") and os.geteuid() == 0
    except Exception:
        is_root = False
    has_sudo = has_cmd("sudo")

    if is_root:
        cmd = ["apt", "install", "-y", pkg]
    elif has_sudo:
        cmd = ["sudo", "apt", "install", "-y", pkg]
    else:
        cmd = ["apt", "install", "-y", pkg]
        emit(
            f"⚠️ Not running as root and 'sudo' not available. "
            f"APT install may fail.\n💡 Try: sudo apt install -y {pkg}"
        )

    # Do an apt-get update first if we are root or have sudo; otherwise attempt install anyway
    if is_root:
        run_cmd_stream(["apt-get", "update"], emit)
    elif has_sudo:
        run_cmd_stream(["sudo", "apt-get", "update"], emit)

    rc, out = run_cmd_stream(cmd, emit)
    return (rc == 0, out if out else ("OK" if rc == 0 else "apt install failed"))

def brew_install(pkg: str, emit) -> Tuple[bool, str]:
    if not has_cmd("brew"): return False, "Homebrew not found (https://brew.sh)"
    rc, out = run_cmd_stream(["brew", "install", pkg], emit)
    return (rc == 0, out if out else ("OK" if rc == 0 else "brew install failed"))

def choco_install(pkg: str, emit) -> Tuple[bool, str]:
    if not has_cmd("choco"): return False, "Chocolatey not found (https://chocolatey.org/install)"
    rc, out = run_cmd_stream(["choco", "install", pkg, "-y"], emit)
    return (rc == 0, out if out else ("OK" if rc == 0 else "choco install failed"))

def pip_install(pkg: str, emit) -> Tuple[bool, str]:
    # Mirror your previous behavior: sys.executable -m pip install <pkg>
    rc, out = run_cmd_stream([sys.executable, "-m", "pip", "install", pkg], emit)
    return (rc == 0, out if out else ("OK" if rc == 0 else "pip install failed"))

def go_install(go_path: str, emit) -> Tuple[bool, str]:
    if not has_cmd("go"): return False, "Go not found (https://go.dev/dl/)"
    rc, out = run_cmd_stream(["go", "install", go_path], emit)
    return (rc == 0, out if out else ("OK" if rc == 0 else "go install failed"))

# =============================================================================
# New-template metadata reader
# =============================================================================

def get_plugin_install_meta(plugin) -> dict:
    """
    Reads fields from the final plugin template with sane fallbacks.
    """
    required_tool = getattr(plugin, "REQUIRED_TOOL", "")
    install_hint  = (getattr(plugin, "INSTALL_HINT", "manual") or "manual").strip().lower()
    install_url   = getattr(plugin, "INSTALL_URL", "") or ""
    executable    = getattr(plugin, "EXECUTABLE", "") or ""
    alias         = getattr(plugin, "TOOL_ALIAS", "") or ""
    docker_run    = getattr(plugin, "DOCKER_RUN", "") or ""
    runtime_name  = (alias or executable or required_tool).strip() or required_tool
    return {
        "required_tool": required_tool,
        "install_hint":  install_hint,
        "install_url":   install_url,
        "runtime_name":  runtime_name,
        "alias_name":    (alias or executable or required_tool),
        "docker_run":    docker_run,
        "executable":    executable or required_tool,
    }

# =============================================================================
# SAFE one-shot installer for a plugin module (preferred by ToolInstallWorker)
# =============================================================================

def safe_install_tool(plugin, emit: Callable[[str], None]) -> Tuple[bool, str]:
    """
    Single source of truth for installing ONE plugin/tool (new template).
    - Uses docker shim when INSTALL_HINT='docker' and DOCKER_RUN is provided.
    - For other hints, uses native installers above.
    - Avoids arbitrary shell strings except where necessary (docker pull is argv).
    """
    meta = get_plugin_install_meta(plugin)
    req  = meta["required_tool"] or "tool"
    hint = meta["install_hint"]
    url  = meta["install_url"]
    alias= meta["alias_name"]
    docker_run = meta["docker_run"]

    # already present?
    if has_cmd(alias) or has_cmd(req):
        return True, f"{alias or req} already present"

    if hint == "docker":
        if not has_cmd("docker"):
            return False, "Docker not found. Install Docker Engine/Desktop."
        if not docker_run:
            return False, "Plugin missing DOCKER_RUN."
        pull_image_if_mentioned(docker_run, emit)
        shim = create_docker_shim(alias, docker_run, emit)
        ok = bool(shim and shim.exists() and has_cmd(alias))
        return (ok, f"Shim created at {shim}" if ok else "Failed to create shim")

    if hint == "apt":    return apt_install(req, emit)
    if hint == "brew":   return brew_install(req, emit)
    if hint == "choco":  return choco_install(req, emit)
    if hint == "pip":    return pip_install(req, emit)
    if hint == "go":
        go_path = url or f"github.com/projectdiscovery/{req}/cmd/{req}@latest"
        if not url:
            emit(f"⚠️ No INSTALL_URL for Go tool '{req}', assuming ProjectDiscovery path: {go_path}")
        return go_install(go_path, emit)
    if hint == "git":
        return False, f"Manual git build required: {url or 'no URL provided'}"

    return False, f"Manual install: {url or req}"

# =============================================================================
# COMPAT: exact behavior of your old try_install_tool (single call)
# =============================================================================

def compat_try_install_tool(
    command_or_tool,
    output_func: Callable[[str], None],
    install_hint: Optional[str] = None,
    install_url: Optional[str] = None,
    max_attempts: int = 2,
    run_streamed: Optional[Callable[..., int]] = None
) -> str:
    """
    Mirrors your previous try_install_tool behavior (messages & flow),
    while sharing the same native helpers above.

    - If `command_or_tool` is a shell string with spaces, we stream it directly.
    - Otherwise we build the methods list (apt/brew/choco/go/pip/git) and try each with attempts.
    - Uses `run_streamed` if provided (your function from common_widget.py), else falls back to run_cmd_stream.
    """
    # choose a runner
    def _stream(cmd, emit, shell=False):
        if run_streamed:
            # old signature: run_streamed(cmd, output_func, shell=True/False)
            return run_streamed(cmd, emit, shell=shell)
        # fallback to local
        rc, _ = run_cmd_stream(cmd if shell else cmd, emit)
        return rc

    system = platform.system().lower()
    is_linux = (system == "linux")
    is_darwin = (system == "darwin")
    is_windows_sys = (system == "windows")

    # detect full shell command vs tool name
    is_shell_command = isinstance(command_or_tool, str) and " " in command_or_tool
    tool_bin = command_or_tool.strip().split()[0] if isinstance(command_or_tool, str) else str(command_or_tool)

    # 1) explicit full command (string) -> stream as-is
    if is_shell_command:
        output_func(f"⚙️ Executing: {command_or_tool}")
        try:
            rc = _stream(command_or_tool, output_func, shell=True)
            if rc == 0:
                output_func(f"✅ Successfully installed via: {command_or_tool}")
                return "installed"
            else:
                output_func(f"❌ Install failed (exit {rc}).")
                return "failed"
        except Exception as e:
            output_func(f"❌ Exception occurred: {e}")
            return "exception"

    # 2) Build methods list exactly like your old function
    methods = []

    # sudo/root detection (Linux only)
    is_root = False
    try:
        is_root = hasattr(os, "geteuid") and os.geteuid() == 0
    except Exception:
        is_root = False
    has_sudo = has_cmd("sudo")

    # apt
    if install_hint == "apt" or (is_linux and has_cmd("apt")):
        if is_root:
            cmd = ["apt", "install", "-y", tool_bin]
        elif has_sudo:
            cmd = ["sudo", "apt", "install", "-y", tool_bin]
        else:
            cmd = ["apt", "install", "-y", tool_bin]
            output_func(
                f"⚠️ Not running as root and 'sudo' not available. "
                f"APT install may fail.\n💡 Try: sudo apt install -y {tool_bin}"
            )
        # Do update first (best-effort), mirroring your behavior
        if is_root:
            methods.append(("apt", ["apt-get", "update"]))
        elif has_sudo:
            methods.append(("apt", ["sudo", "apt-get", "update"]))
        methods.append(("apt", cmd))

    # brew
    if install_hint == "brew" or (is_darwin and has_cmd("brew")):
        methods.append(("brew", ["brew", "install", tool_bin]))

    # choco
    if install_hint == "choco" or (is_windows_sys and has_cmd("choco")):
        methods.append(("choco", ["choco", "install", tool_bin, "-y"]))

    # go
    if install_hint == "go" or has_cmd("go"):
        if install_url:
            go_path = install_url
        else:
            go_path = f"github.com/projectdiscovery/{tool_bin}/cmd/{tool_bin}@latest"
            output_func(f"⚠️ No INSTALL_URL for Go tool '{tool_bin}', assuming ProjectDiscovery path: {go_path}")
        methods.append(("go", ["go", "install", go_path]))

    # pip (late)
    if install_hint == "pip" or install_hint is None:
        methods.append(("pip", [sys.executable, "-m", "pip", "install", tool_bin]))

    # git (string chain; shell=True)
    if install_hint == "git" and install_url:
        methods.append(("git", f"git clone {install_url} && cd {tool_bin} && sudo make install"))

    # 3) Try methods with attempts, preserve sudo prompt warning
    for method_name, cmd in methods:
        for attempt in range(1, max_attempts + 1):
            pretty = cmd if isinstance(cmd, str) else " ".join(cmd)
            output_func(f"🔁 Attempt {attempt} via {method_name}: {pretty}")

            if (isinstance(cmd, list) and "sudo" in cmd) or (isinstance(cmd, str) and "sudo " in cmd):
                output_func(
                    "🔑 Sudo password might be required!\n"
                    f"💡 Command: {pretty}\n"
                    "👉 Check your terminal for a password prompt.\n"
                    "⚠️ ReconCraft may appear frozen until input is received.\n"
                )

            try:
                rc = _stream(cmd, output_func, shell=isinstance(cmd, str))
                if rc == 0:
                    output_func(f"✅ {tool_bin} installed successfully via {method_name}.")
                    return "installed"
                else:
                    output_func(f"❌ {method_name} failed (exit {rc}).")
            except Exception as e:
                output_func(f"❌ {method_name} exception: {e}")

    # 4) Manual fallback
    output_func(f"⚠️ All install methods failed for '{tool_bin}'.")
    output_func("🔍 Opening browser for manual instructions…")
    try:
        webbrowser.open(f"https://www.google.com/search?q=install+{tool_bin}+tool")
    except Exception:
        output_func("🌐 Could not open browser — please search manually.")
    return "manual"