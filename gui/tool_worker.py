# ReconCraft by Nirmal Chakraborty
# Copyright (c) 2025. All rights reserved.
# See LICENSE for details.

# ===================== Tool Install Worker + Safe Installer =====================

from PyQt5.QtCore import QThread, pyqtSignal
import os, sys, platform, shutil, subprocess, webbrowser
from pathlib import Path
from typing import Callable, Tuple, Optional, List
from core.installer_utils import safe_install_tool, get_plugin_install_meta, has_cmd, create_docker_shim
from gui.common_widgets import ElapsedTicker
# --------------------------- helper utilities ----------------------------------

from typing import Callable, List, Optional, Tuple
import os, sys, shutil, subprocess, threading, platform, time
from collections import deque

_INSTALLER_CANCEL_EVENT = threading.Event()
_INSTALLER_PROCS = set()
_INSTALLER_PROCS_LOCK = threading.Lock()
has_cmd_cache = {}

def has_cmd(cmd: str) -> bool:
    """
    Check if an executable is available on PATH (Windows-aware).
    Caches results to avoid repeated lookups.
    """
    try:
        if not isinstance(cmd, str) or not cmd.strip():
            return False
        key = cmd.strip().lower()
        if key in has_cmd_cache:
            return has_cmd_cache[key]
        found = shutil.which(cmd) is not None
        has_cmd_cache[key] = found
        return found
    except Exception:
        return False

def _emit(output_cb: Callable[[str], None], text: str):
    """
    Emit a single logical line to the callback, guarding against UI crashes.
    """
    try:
        s = "" if text is None else str(text)
        # Normalize to a single line (most UIs expect discrete lines)
        if s.endswith("\n"):
            s = s[:-1]
        output_cb(s)
    except Exception:
        # Intentionally swallow to avoid breaking installers on UI errors
        pass

def _run_cmd(args: List[str],
             output_cb: Callable[[str], None],
             cwd: Optional[str] = None,
             timeout: Optional[int] = None) -> Tuple[int, str]:
    """
    Run a command safely (no shell=True). Stream output to output_cb in real time.
    Returns (exit_code, combined_output).

    Implementation details:
      - Uses a background reader thread (prevents stdout deadlocks).
      - Enforces a real timeout (kills the process group on expiry).
      - Bounds in-memory output with a deque to avoid OOM from chatty tools.
    """
    if not isinstance(args, list) or not args:
        return 2, "runner error: empty args"

    if cwd and not os.path.isdir(cwd):
        return 2, f"runner error: cwd not found: {cwd}"

    # Windows: new process group so CTRL_BREAK can propagate if ever used
    _creationflags = 0
    if os.name == "nt":
        try:
            _creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        except Exception:
            _creationflags = 0
    try:
        # Start the process
        proc = subprocess.Popen(
            args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            creationflags=_creationflags,      # ← this must be the same name
            start_new_session=(os.name != "nt")
        )
        # track for cancellation
        try:
            with _INSTALLER_PROCS_LOCK:
                _INSTALLER_PROCS.add(proc)
        except Exception:
            pass
    except FileNotFoundError:
        return 127, f"command not found: {args[0]}"
    except Exception as e:
        return 1, f"runner error: {e}"

    # Collect output in a bounded buffer (keep last ~4 MB of text)
    # Assuming avg 120 chars/line -> ~35k lines ~= 4.2 MB
    max_lines = 35000
    buf = deque(maxlen=max_lines)

    done = threading.Event()

    def _reader():
        try:
            assert proc.stdout is not None
            for line in iter(proc.stdout.readline, ''):
                # Guard against None or binary glitches
                line = line.replace("\r\n", "\n").replace("\r", "\n")
                parts = line.split("\n")
                for p in parts:
                    if p == "" and line.endswith("\n") and parts.index(p) == len(parts)-1:
                        # trailing newline -> skip empty
                        continue
                    buf.append(p)
                    _emit(output_cb, p)
        except Exception as _e:
            # If reading fails, we still rely on timeout/return code
            pass
        finally:
            done.set()

    t = threading.Thread(target=_reader, daemon=True)
    t.start()

    start = time.time()
    code = None
    try:
        if timeout:
            # Wait until either reader finishes and process exits OR timeout fires
            while True:
                if proc.poll() is not None and done.is_set():
                    break
                if (time.time() - start) > timeout:
                    # Kill the process and break
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    code = 124
                    break
                                # cooperative cancel from UI
                try:
                    if _INSTALLER_CANCEL_EVENT.is_set():
                        try:
                            proc.terminate()
                        except Exception:
                            pass
                        code = 130  # standard "terminated" style
                        break
                except Exception:
                    pass

                time.sleep(0.05)
        # If we didn't timeout above, wait for process to exit cleanly
        if code is None:
            code = proc.wait()
    finally:
        # unregister from cancel tracking
        try:
            with _INSTALLER_PROCS_LOCK:
                _INSTALLER_PROCS.discard(proc)
        except Exception:
            pass  
        # Ensure reader terminates
        try:
            if proc.stdout:
                try:
                    proc.stdout.close()
                except Exception:
                    pass
        except Exception:
            pass
        done.set()
        t.join(timeout=1.0)

    combined = "\n".join(buf).strip()
    if code == 124:
        return 124, "command timed out"
    return code, combined

def _is_linux():   return platform.system().lower() == "linux"
def _is_macos():   return platform.system().lower() == "darwin"
def _is_windows(): return platform.system().lower() == "windows"


# ----------------------------- package helpers ---------------------------------

def _pipx_install(tool: str, output_cb: Callable[[str], None]) -> Tuple[bool, str]:
    """Best practice for Python CLI tools: use pipx when available."""
    if not has_cmd("pipx"):
        return False, "pipx not found (recommended for Python CLIs). See https://pypa.github.io/pipx/"
    code, out = _run_cmd(["pipx", "install", tool], output_cb)
    if code == 0:
        return True, out or "OK"
    return False, out or "pipx install failed"

def _apt_install(pkg: str, output_cb: Callable[[str], None]) -> Tuple[bool, str]:
    """Do not attempt elevation here. If not root, return a clear instruction."""
    if not has_cmd("apt-get"):
        return False, "apt-get not found on this system"
    if hasattr(os, "geteuid"):
        try:
            if os.geteuid() != 0:
                return False, f"Requires root. Try: sudo apt-get update && sudo apt-get install -y {pkg}"
        except Exception:
            # On some restricted environments geteuid might fail; proceed without forcing root message.
            pass
    code_u, out_u = _run_cmd(["apt-get", "update"], output_cb)
    if code_u != 0:
        return False, out_u or "apt-get update failed"
    code_i, out_i = _run_cmd(["apt-get", "install", "-y", pkg], output_cb)
    if code_i == 0:
        return True, out_i or "OK"
    return False, out_i or "apt-get install failed"

def _brew_install(pkg: str, output_cb: Callable[[str], None]) -> Tuple[bool, str]:
    if not has_cmd("brew"):
        return False, "Homebrew not found. See https://brew.sh/"
    code, out = _run_cmd(["brew", "install", pkg], output_cb)
    if code == 0:
        return True, out or "OK"
    return False, out or "brew install failed"

def _choco_install(pkg: str, output_cb: Callable[[str], None]) -> Tuple[bool, str]:
    """Windows: Chocolatey is common. If missing, give a clear hint."""
    if not has_cmd("choco"):
        return False, "Chocolatey not found. Install from https://chocolatey.org/install"
    code, out = _run_cmd(["choco", "install", pkg, "-y", "--no-progress"], output_cb)
    if code == 0:
        return True, out or "OK"
    return False, out or "choco install failed"

def _go_install(module: str, output_cb: Callable[[str], None]) -> Tuple[bool, str]:
    if not has_cmd("go"):
        return False, "Go toolchain not found"
    mod = module if "@" in module else f"{module}@latest"
    code, out = _run_cmd(["go", "install", mod], output_cb)
    if code == 0:
        return True, out or "OK"
    return False, out or "go install failed"


# ---------------------------- safe installer callback --------------------------

def try_install_tool_func(tool: str,
                          output_cb: Callable[[str], None],
                          install_hint: str = "",
                          install_url: str = "") -> Tuple[bool, str]:
    """
    Hardened installer used by ToolInstallWorker.

    Returns:
      (ok: bool, msg: str)

    Behavior:
      - Never uses shell=True
      - Never elevates privileges automatically
      - Emits live output via output_cb
      - PEP 668 friendly (does not 'pip install' into system Python)
    """
    hint = (install_hint or "").strip().lower()
    url  = (install_url or "").strip()

    # 0) Already installed?
    if has_cmd(tool):
        return True, f"OK: {tool} already present on PATH"

    # 1) Route by OS + hint
    if hint == "apt" and _is_linux():
        ok, msg = _apt_install(tool, output_cb)
        return ok, msg

    if hint == "brew" and _is_macos():
        ok, msg = _brew_install(tool, output_cb)
        return ok, msg

    if hint == "choco" and _is_windows():
        ok, msg = _choco_install(tool, output_cb)
        return ok, msg

    if hint == "pip":
        # For Python CLIs, prefer pipx; venv-based installs should be handled by requirements.txt, not here.
        ok, msg = _pipx_install(tool, output_cb)
        if ok:
            return True, msg
        # Provide explicit guidance if pipx is unavailable.
        return False, ("Use pipx (recommended) or install into your ReconCraft virtualenv via requirements.txt. "
                       "If you must install per-user: python -m pip install --user <package>")

    if hint == "go":
        mod = url if url else tool
        ok, msg = _go_install(mod, output_cb)
        return ok, msg

    if hint == "git":
        if url:
            _emit(output_cb, f"Clone and build from: {url}")
            return False, f"Manual git build required: {url}"
        return False, "No INSTALL_URL provided for git-based install"

    if hint == "manual":
        if url:
            _emit(output_cb, f"Install manually from: {url}")
            return False, f"Manual install required: {url}"
        return False, "Manual install requested but no INSTALL_URL provided"

    # (Optional) If your plugins use a 'docker' hint, direct the user explicitly.
    if hint == "docker":
        if url:
            _emit(output_cb, f"Use Docker image from: {url}")
        return False, "Run via Docker (configure a TOOL_ALIAS shim in your plugin so ReconCraft can call it)."

    # 2) Fallback guidance per platform
    if _is_linux():
        return False, (f"Unknown install method '{hint}'. "
                       f"Try your package manager, e.g.: sudo apt-get install -y {tool}")
    if _is_macos():
        return False, (f"Unknown install method '{hint}'. "
                       f"Try: brew install {tool}")
    if _is_windows():
        return False, (f"Unknown install method '{hint}'. "
                       f"Try: choco install {tool} -y")

    return False, "Unsupported OS or missing install hint"


# ------------------------------- worker class ----------------------------------

from PyQt5.QtCore import QThread, pyqtSignal
from pathlib import Path
import os, shutil, subprocess, platform, stat

class ToolInstallWorker(QThread):
    """
    Installs missing tools declared by plugins.
    - Honors new plugin fields: TOOL_ALIAS, EXECUTABLE, DOCKER_RUN
    - Supports: docker (shim), apt, brew, choco, pipx, go, git/manual (message)
    - Never uses shell=True and never auto-elevates.
    """
    progress = pyqtSignal(int)        # 0-100
    status   = pyqtSignal(str)        # status bar text
    output   = pyqtSignal(str)        # console log lines
    finished = pyqtSignal(bool)       # ✅ success flag (True=all installed, False=some failed)
    missing  = pyqtSignal(list)       # ✅ still-missing plugin names

    def __init__(self, missing_plugins, plugins):
        """
        :param missing_plugins: list[str] plugin module names to install
        :param plugins: dict[str, module] mapping plugin name -> imported module
        """
        super().__init__()
        self.to_install = list(missing_plugins or [])
        self.plugins = plugins or {}

    # === PATCH A: helpers inside ToolInstallWorker ===
    def _sudo_warmup_if_needed(self, planned_jobs):
        """
        Pre-cache sudo on Linux if any apt job will run and we are not root.
        Uses self.sudo_prompt() once if available. No change to installer helpers.
        """
        try:
            if os.name != "posix":
                return
            # any apt job planned?
            needs_apt = any((j.get("INSTALL_HINT") == "apt") for j in planned_jobs)
            if not needs_apt:
                return
            # root?
            if hasattr(os, "geteuid") and os.geteuid() == 0:
                return

            if not hasattr(self, "sudo_prompt") or not callable(self.sudo_prompt):
                # We cannot warm-up; apt may still prompt/ fail silently
                self.output.emit("⚠️  apt installs may require sudo but no sudo_prompt is configured.")
                return

            pw = self.sudo_prompt()  # prompt once
            if not pw:
                self.output.emit("⚠️  Skipping sudo warm-up (no password entered). apt may fail.")
                return

            # validate & cache sudo for this session (-v). Feed through stdin to avoid TTY prompt.
            proc = subprocess.run(
                ["sudo", "-S", "-v"],
                input=(pw + "\n").encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if proc.returncode == 0:
                self.output.emit("🔑 Sudo cached for apt operations.")
            else:
                self.output.emit("⚠️  Sudo warm-up failed; apt may fail. You can retry with correct password.")
        except Exception as e:
            self.output.emit(f"⚠️  Sudo warm-up error: {e!r}")

    def _verify_docker_shim(self, alias_name: str):
        """
        Quick one-shot check that the docker shim actually runs.
        We try '<alias> --version' or '-h' without breaking flow.
        """
        import subprocess, shutil
        try:
            exe = shutil.which(alias_name) or alias_name
            # try --version then -h
            for args in (["--version"], ["-h"]):
                p = subprocess.run([exe] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if p.returncode == 0:
                    return True
            return False
        except Exception:
            return False

    #Improved Cancel Support
    def request_cancel(self):
        """
        Signal the installer to cancel; terminate any running child processes.
        """
        try:
            _INSTALLER_CANCEL_EVENT.set()
        except Exception:
            pass
        # best-effort terminate whatever is running
        with _INSTALLER_PROCS_LOCK:
            procs = list(_INSTALLER_PROCS)
        for proc in procs:
            try:
                if os.name == "nt":
                    try:
                        proc.terminate()
                    except Exception:
                        pass
                else:
                    try:
                        proc.terminate()
                    except Exception:
                        pass
            except Exception:
                pass

    # ---------- main loop ----------
    def run(self):
        """
        Improved installer:
        - Pre-warm sudo once for apt (Linux)
        - Run pip/go in limited parallel (safe)
        - Verify docker shim after creation
        - Rich failure messages with INSTALL_URL
        - Preserve original emits (status/output/progress/missing/finished)
        """
         # reset cancel flag for this run
        try:
            _INSTALLER_CANCEL_EVENT.clear()
        except Exception:
            pass

        still_missing = []

        try:
            to_install = list(self.to_install or [])
            if not to_install:
                self.output.emit("🎉 All tools are already installed.")
                self.status.emit("✅ Nothing to install.")
                self.progress.emit(100)
                self.missing.emit([])
                self.finished.emit(True)
                return

            # ---------------- helpers (local) ----------------
            def _sudo_warmup_if_needed(jobs):
                try:
                    import os, subprocess
                    # Linux only; if any apt job; and not root
                    if os.name != "posix":
                        return
                    if not any(((getattr(self.plugins.get(pn), "INSTALL_HINT", "") or "").strip().lower() == "apt") for pn in jobs):
                        return
                    if hasattr(os, "geteuid") and os.geteuid() == 0:
                        return

                    if not hasattr(self, "sudo_prompt") or not callable(self.sudo_prompt):
                        self.output.emit("⚠️  apt installs may require sudo but no sudo_prompt is configured.")
                        return

                    pw = self.sudo_prompt()  # prompt once
                    if not pw:
                        self.output.emit("⚠️  Skipping sudo warm-up (no password entered). apt may fail.")
                        return

                    proc = subprocess.run(
                        ["sudo", "-S", "-v"],
                        input=(pw + "\n").encode("utf-8"),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    if proc.returncode == 0:
                        self.output.emit("🔑 Sudo cached for apt operations.")
                    else:
                        self.output.emit("⚠️  Sudo warm-up failed; apt may fail. You can retry with correct password.")
                except Exception as e:
                    self.output.emit(f"⚠️  Sudo warm-up error: {e!r}")

            def _verify_docker_shim(shim_path, alias_name):
                """
                Try running the new shim to ensure it actually works.
                Uses module-level _run_cmd which returns (rc, out).
                """
                try:
                    candidates = []
                    try:
                        if shim_path:
                            sp = str(shim_path)
                            candidates.append([sp, "--version"])
                            candidates.append([sp, "-h"])
                    except Exception:
                        pass
                    if alias_name:
                        candidates.append([alias_name, "--version"])
                        candidates.append([alias_name, "-h"])

                    for cmd in candidates:
                        rc, _out = _run_cmd(cmd, self.output.emit, timeout=15)
                        if rc == 0:
                            return True
                    return False
                except Exception:
                    return False

            # Partition hints for limited parallelism (avoid assuming new helpers)
            def _hint_of(pn):
                pl = self.plugins.get(pn)
                return (getattr(pl, "INSTALL_HINT", "manual") or "manual").strip().lower()

            serial_set   = {"apt", "brew", "choco", "docker", "git", "manual", ""}
            parallel_set = {"pip", "go"}  # safe-only; do not assume _git_install exists

            serial_items   = [pn for pn in to_install if _hint_of(pn) in serial_set]
            parallel_items = [pn for pn in to_install if _hint_of(pn) in parallel_set]

            total = len(to_install)
            done_count = 0

            # Warm up sudo once if needed
            _sudo_warmup_if_needed(to_install)

            # Core installer for one plugin (reuses your existing helpers/flow)
            def _install_one(plugin_name):
                plugin = self.plugins.get(plugin_name)
                if not plugin:
                    self.output.emit(f"⚠️ Plugin '{plugin_name}' not found; skipping.")
                    return False, "plugin not found"

                required_tool = getattr(plugin, "REQUIRED_TOOL", plugin_name)
                install_hint  = (getattr(plugin, "INSTALL_HINT", "manual") or "manual").strip().lower()
                install_url   = getattr(plugin, "INSTALL_URL", "") or ""
                alias_name    = (
                    getattr(plugin, "TOOL_ALIAS", "").strip()
                    or getattr(plugin, "EXECUTABLE", "").strip()
                    or required_tool
                )
                docker_run    = getattr(plugin, "DOCKER_RUN", "") or ""

                self.status.emit(f"⚙ Installing {plugin_name}…")
                self.output.emit(f"🔽 method: {install_hint}")

                # Already present?
                if has_cmd(alias_name) or has_cmd(required_tool):
                    self.output.emit(f"✅ {plugin_name} already available as '{alias_name or required_tool}'.")
                    return True, "already present"

                ok, msg = False, "not attempted"

                # ---- docker path (shim) ----
                if install_hint == "docker":
                    if not has_cmd("docker"):
                        ok, msg = False, "Docker not found. Install Docker Engine/Desktop."
                    elif not docker_run:
                        ok, msg = False, "Plugin missing DOCKER_RUN."
                    else:
                        # Best-effort: infer image from docker_run and pull it
                        image = None
                        for t in reversed(docker_run.split()):
                            if "/" in t or ":" in t:
                                image = t
                                break
                        if image:
                            self.output.emit(f"🐳 docker pull {image}")
                            try:
                                _rc, _ = _run_cmd(["docker", "pull", image], self.output.emit)
                            except Exception:
                                pass
                        from core.installer_utils import create_docker_shim
                        shim_path = create_docker_shim(alias_name, docker_run, self.output.emit)
                        ok = bool(shim_path and shim_path.exists())
                        if ok:
                            # Verify shim actually runs
                            if not _verify_docker_shim(shim_path, alias_name):
                                ok = False
                                msg = "Shim failed verification"
                            else:
                                msg = f"Shim created at {shim_path}"
                        else:
                            msg = "Failed to create shim"

                # ---- apt / brew / choco / pip / go / git / manual ----
                elif install_hint == "apt":
                    ok, msg = _apt_install(required_tool, self.output.emit)
                elif install_hint == "brew":
                    ok, msg = _brew_install(required_tool, self.output.emit)
                elif install_hint == "choco":
                    ok, msg = _choco_install(required_tool, self.output.emit)
                elif install_hint == "pip":
                    ok, msg = _pipx_install(required_tool, self.output.emit)
                elif install_hint == "go":
                    mod = getattr(plugin, "INSTALL_URL", "") or required_tool
                    ok, msg = _go_install(mod, self.output.emit)

                elif install_hint == "git":
                    # Keep your previous behavior (manual)
                    ok, msg = False, f"Manual git build required: {install_url or 'no URL provided'}"
                else:  # manual or unknown
                    ok, msg = False, f"Manual install: {install_url or required_tool}"

                # Verify installation result
                path_ok = (has_cmd(alias_name) or has_cmd(required_tool))

                if ok and path_ok:
                    self.output.emit(f"✅ {plugin_name} installed ({alias_name or required_tool}).")
                    return True, msg
                else:
                    # Stronger guidance using INSTALL_URL if we have it
                    self.output.emit(f"❌ {plugin_name} failed: {msg}")
                    if install_url:
                        self.output.emit(f"   ↳ Refer: {install_url}")
                    return False, msg

            # --------------- run serial jobs ---------------
            for pn in serial_items:
                ok, _msg = _install_one(pn)
                if not ok:
                    still_missing.append(pn)
                done_count += 1
                self.progress.emit(int(100 * done_count / total))

            # --------------- run parallel-safe jobs (pip/go) ---------------
            if parallel_items:
                self.output.emit(f"🧵 Running {len(parallel_items)} parallel installs (pip/go)...")
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(parallel_items))) as ex:
                    futmap = {ex.submit(_install_one, pn): pn for pn in parallel_items}
                    for fut in concurrent.futures.as_completed(futmap):
                        pn = futmap[fut]
                        ok, _msg = fut.result()
                        if not ok:
                            still_missing.append(pn)
                        done_count += 1
                        self.progress.emit(int(100 * done_count / total))

            # Ensure progress bar completes visually
            self.progress.emit(100)

            # --------------- summary + final emits ---------------
            if still_missing:
                succeeded = total - len(still_missing)
                self.output.emit(f"✅ Installed: {succeeded} / {total}")
                self.output.emit(f"⚠️ Failed: {len(still_missing)} → {', '.join(still_missing)}")
                self.status.emit("⚠️ Some tools could not be installed. See logs.")
                self.missing.emit(still_missing)
                self.finished.emit(False)
            else:
                self.status.emit("✅ All missing tools installed.")
                self.missing.emit([])
                self.finished.emit(True)

        except Exception as e:
            self.output.emit(f"[installer] error: {e}")
            self.status.emit("⚠️ Installer encountered an unexpected error.")
            self.progress.emit(100)
            self.missing.emit(still_missing)
            self.finished.emit(False)


# ToolCheckWorker checks if required tools are installed.
class ToolCheckWorker(QThread):
    progress = pyqtSignal(int)        # For progress bar
    status = pyqtSignal(str)          # For status bar
    output = pyqtSignal(str)          # For output console
    finished = pyqtSignal(list)       # Emit missing tools at end

    def __init__(self, plugins, is_tool_installed_func):
        super().__init__()
        self.plugins = plugins
        self.is_tool_installed = is_tool_installed_func

    def run(self):
        total = len(self.plugins)
        missing_tools = []
        for i, (plugin_name, plugin_module) in enumerate(self.plugins.items()):
            
            # prefer alias -> executable -> required tool
            runtime_name = (
                getattr(plugin_module, "TOOL_ALIAS", "").strip()
                or getattr(plugin_module, "EXECUTABLE", "").strip()
                or getattr(plugin_module, "REQUIRED_TOOL", plugin_name)
            )

            if shutil.which(runtime_name) is None:
                missing_tools.append(plugin_name)
                self.output.emit(f"❌ {plugin_name}: '{runtime_name}' not found on PATH.")
            else:
                self.output.emit(f"✅ {plugin_name}: '{runtime_name}' found.")

            self.status.emit(f"Checking {plugin_name}...")
            self.progress.emit(int(100 * (i + 1) / total))

        if missing_tools:
            self.output.emit("\n⚠️ Missing: " + ", ".join(missing_tools))
        else:
            self.output.emit("\n🎉 All dynamically loaded tools are installed!")

        self.status.emit("Check Tools Complete.")
        self.finished.emit(missing_tools)
        self.progress.emit(100)
