# ReconCraft by Nirmal Chakraborty
# Copyright (c) 2025. All rights reserved.
# See LICENSE for details.

"""
Headless (GUI-free) execution engine for ReconCraft plugins.

Why this module exists
----------------------
ReconCraft plugins are already decoupled from the PyQt GUI: every plugin's
``run()`` receives its execution helpers (``run_command``,
``check_tool_installed``, ``extract_cves``) as *parameters*. ``ScanThread``
(core/scan_thread.py) is merely one provider of those helpers, wired to Qt
signals and a Qt thread.

This module provides an equivalent, **PyQt-free** provider so the very same
plugins can be driven from a CLI, an MCP server, or any automation context —
without importing PyQt5 and without modifying ``ScanThread``, the GUI, or any
plugin. It intentionally mirrors ``ScanThread``'s behaviour:

* identical PATH-based ``check_tool_installed`` semantics,
* the same on-disk layout
  ``<report_root>/All Reports/<target>/<tool>/<run_id>/raw_<tool>.log``
  (plus ``formatted/``, ``exports/`` per run and an empty ``machine/`` under
  the scan root),
* the same profile handling (Aggressive/Normal/Passive/Custom), the same
  ``{{target}}``/``{target}`` substitution, and the same ``DISABLED`` skip
  rules.

Nothing here changes existing GUI functionality; it only reuses the plugin
contract from a different entry point.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Event, Lock
from typing import Callable, Dict, List, Optional

from core.plugin_loader import discover_plugins

# Profile keys as defined by plugin DEFAULT_ARGS dictionaries.
_PROFILE_KEYMAP = {
    "aggressive": "Aggressive",
    "normal": "Normal",
    "passive": "Passive",
    "custom": "Custom",
}
VALID_PROFILES = ("Aggressive", "Normal", "Passive", "Custom")


def _norm(s: str) -> str:
    """Filesystem-safe key. Mirrors ScanThread._norm exactly."""
    s = (s or "").strip().lower()
    return "".join(ch if (ch.isalnum() or ch in "-_.") else "_" for ch in s).strip("_")


@dataclass
class RunResult:
    """Structured outcome of a single (tool, target) execution."""

    tool: str
    target: str
    profile: str
    ok: bool
    skipped: bool = False
    message: str = ""
    command: str = ""
    output: str = ""
    output_path: Optional[str] = None
    exit_code: Optional[int] = None
    started_at: str = ""
    finished_at: str = ""
    logs: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "tool": self.tool,
            "target": self.target,
            "profile": self.profile,
            "ok": self.ok,
            "skipped": self.skipped,
            "message": self.message,
            "command": self.command,
            "output": self.output,
            "output_path": self.output_path,
            "exit_code": self.exit_code,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "logs": self.logs,
        }


class HeadlessRunner:
    """
    Drives ReconCraft plugins without any Qt dependency.

    Parameters
    ----------
    report_root_folder:
        Root of a scan output tree (equivalent to ScanThread.report_root_folder).
        The standard ``All Reports/<target>/<tool>/<run_id>/`` layout is created
        beneath it, so outputs are interoperable with the GUI's Reports tab.
    default_timeout:
        Per-command wall-clock timeout in seconds. ``None`` disables the timeout
        (matching the GUI, which has no per-command timeout). Defaults to None to
        preserve GUI-identical behaviour; callers such as the MCP server may set
        a sane bound.
    """

    def __init__(
        self,
        report_root_folder: str,
        default_timeout: Optional[float] = None,
    ) -> None:
        self.report_root_folder = report_root_folder
        self.default_timeout = default_timeout
        self.plugin_map: Dict[str, object] = discover_plugins(verbose=False)

        self.cancel_event = Event()
        self._procs: set = set()
        self._procs_lock = Lock()

        # Per-run context, mirrors ScanThread._active_run_ctx usage.
        self._active_run_ctx: dict = {}
        self._last_run_paths: dict = {}
        self._current_timeout: Optional[float] = default_timeout

    # ------------------------------------------------------------------ #
    # Discovery / metadata
    # ------------------------------------------------------------------ #
    def available_tools(self) -> List[str]:
        return sorted(self.plugin_map.keys())

    def tool_metadata(self, tool: str) -> dict:
        """Return install metadata + supported profiles for a plugin."""
        module = self.plugin_map.get(tool)
        if module is None:
            raise KeyError(f"Unknown tool: {tool!r}")

        info: dict = {}
        get_info = getattr(module, "get_install_info", None)
        if callable(get_info):
            try:
                info = dict(get_info() or {})
            except Exception as exc:  # pragma: no cover - defensive
                info = {"error": f"get_install_info failed: {exc}"}

        default_args = dict(getattr(module, "DEFAULT_ARGS", {}) or {})
        runtime_name = (
            info.get("alias_name")
            or info.get("exec_name")
            or getattr(module, "REQUIRED_TOOL", tool)
        )
        return {
            "name": tool,
            "required_tool": getattr(module, "REQUIRED_TOOL", tool),
            "runtime_name": runtime_name,
            "install_hint": info.get("install_hint", getattr(module, "INSTALL_HINT", "")),
            "install_url": info.get("install_url", getattr(module, "INSTALL_URL", "")),
            "docker_run": info.get("docker_run", getattr(module, "DOCKER_RUN", "")),
            "profiles": {k: default_args.get(k, "") for k in default_args},
            "installed": self.check_tool_installed(runtime_name),
        }

    def all_metadata(self) -> List[dict]:
        return [self.tool_metadata(t) for t in self.available_tools()]

    # ------------------------------------------------------------------ #
    # Plugin helper callbacks (passed into plugin.run)
    # ------------------------------------------------------------------ #
    def check_tool_installed(self, tool_name: str) -> bool:
        """PATH executability check. Mirrors ScanThread.check_tool_installed."""
        if not tool_name:
            return False
        return any(
            os.access(os.path.join(path, tool_name), os.X_OK)
            for path in os.environ.get("PATH", "").split(os.pathsep)
            if path
        )

    def extract_cves(self, filepath: str, ip: str) -> None:
        """Placeholder, kept for plugin-call compatibility (ScanThread parity)."""
        return None

    def run_command(self, cmd_list, outfile_name, output_callback=None) -> str:
        """
        Execute a command, stream output to a raw log, and return its path.

        Faithful, Qt-free port of ScanThread.run_command: same directory layout,
        same process-group handling and cooperative cancel, with the addition of
        an optional wall-clock timeout.
        """
        scan_root = Path(self.report_root_folder)
        all_reports_root = scan_root / "All Reports"
        all_reports_root.mkdir(parents=True, exist_ok=True)
        (scan_root / "machine").mkdir(parents=True, exist_ok=True)

        tool_name = Path(cmd_list[0]).name
        if tool_name.lower().endswith(".exe"):
            tool_name = tool_name[:-4]
        tool_key = _norm(tool_name)

        ctx = self._active_run_ctx or {}
        target_key = ctx.get("target")
        if not target_key:
            tail = (outfile_name or "").split("_", 1)[-1]
            target_key = _norm(tail) or "target"

        run_id = ctx.get("run_id") or datetime.now().strftime("%Y%m%d_%H%M%S")

        run_dir = all_reports_root / target_key / tool_key / run_id
        (run_dir / "formatted").mkdir(parents=True, exist_ok=True)
        (run_dir / "exports").mkdir(parents=True, exist_ok=True)
        run_dir.mkdir(parents=True, exist_ok=True)
        out_path = str(run_dir / f"raw_{tool_key}.log")

        command_str = " ".join(cmd_list)
        if output_callback:
            output_callback(f"🟢 Running: {command_str}")

        aborted = False
        timed_out = False
        ret: Optional[int] = None
        deadline = None
        if self._current_timeout and self._current_timeout > 0:
            deadline = time.time() + self._current_timeout

        try:
            creationflags = 0
            preexec_fn = None
            if os.name == "nt":
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
            else:
                preexec_fn = os.setsid

            with open(out_path, "w", encoding="utf-8") as f:
                proc = subprocess.Popen(
                    cmd_list,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                    creationflags=creationflags,
                    preexec_fn=preexec_fn,
                )
                with self._procs_lock:
                    self._procs.add(proc)

                # Watchdog thread: enforces cancel + timeout independently of
                # stdout activity (a process can block after emitting output, so
                # the read loop alone cannot guarantee termination). Flags are
                # shared via a mutable holder.
                state = {"aborted": False, "timed_out": False, "stop": Event()}

                def _watchdog() -> None:
                    while not state["stop"].wait(0.2):
                        # Check triggers before liveness: an external cancel()
                        # may already have terminated the process, and we still
                        # need to record why it died.
                        if self.cancel_event.is_set():
                            state["aborted"] = True
                            self._terminate(proc)
                            return
                        if deadline and time.time() > deadline:
                            state["timed_out"] = True
                            self._terminate(proc)
                            return
                        if proc.poll() is not None:
                            return

                from threading import Thread

                watcher = Thread(target=_watchdog, daemon=True)
                watcher.start()

                last_log = time.time()
                try:
                    if proc.stdout is not None:
                        for line in iter(proc.stdout.readline, ""):
                            f.write(line)
                            if output_callback and (time.time() - last_log) > 0.25:
                                last_log = time.time()
                                output_callback(line.rstrip())
                            if state["aborted"] or state["timed_out"]:
                                break
                finally:
                    ret = proc.wait()
                    state["stop"].set()
                    watcher.join(timeout=1)

                aborted = state["aborted"]
                timed_out = state["timed_out"]
                if aborted and output_callback:
                    output_callback("⏹️ Aborted by user.")
                elif timed_out and output_callback:
                    output_callback(f"⏱️ Timed out after {self._current_timeout}s.")

                with self._procs_lock:
                    self._procs.discard(proc)
                if not (aborted or timed_out) and output_callback:
                    output_callback(f"✅ Finished: {command_str} (Exit code: {ret})")
                    if ret != 0:
                        output_callback(
                            f"⚠️ Warning: Tool exited with code {ret}. "
                            "Check the output file for errors."
                        )
        except FileNotFoundError:
            if output_callback:
                output_callback(f"❌ Not found on PATH: {cmd_list[0]}")
        except Exception as exc:  # pragma: no cover - defensive parity with GUI
            if output_callback:
                output_callback(f"❌ Error running: {command_str}")
                output_callback(str(exc))

        self._last_run_paths[(tool_key, target_key)] = {"path": out_path, "ts": time.time()}
        # Stash exit status for the caller (RunResult enrichment).
        self._active_run_ctx["_exit_code"] = ret
        self._active_run_ctx["_aborted"] = aborted
        self._active_run_ctx["_timed_out"] = timed_out
        return out_path

    def _terminate(self, proc: "subprocess.Popen") -> None:
        try:
            if os.name == "nt":
                try:
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                except Exception:
                    pass
                proc.terminate()
            else:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except Exception:
                    pass
                proc.terminate()
        except Exception:
            pass

    def cancel(self) -> None:
        """Cooperatively cancel a running command (best effort)."""
        self.cancel_event.set()
        with self._procs_lock:
            procs = list(self._procs)
        for p in procs:
            self._terminate(p)

    # ------------------------------------------------------------------ #
    # Argument / profile resolution (mirrors ScanThread.run_tool)
    # ------------------------------------------------------------------ #
    def _resolve_args(
        self,
        module,
        tool: str,
        target: str,
        profile: str,
        custom_args: Optional[str],
    ):
        """
        Return (replaced_args, skip_message_or_None).

        A non-None second element means "skip without treating it as a hard
        error" (Custom disabled / empty), matching GUI semantics.
        """
        default_args = dict(getattr(module, "DEFAULT_ARGS", {}) or {})
        low = (profile or "Normal").strip().lower()
        profile_key = _PROFILE_KEYMAP.get(low, profile)

        if profile_key == "Custom":
            raw_template = (custom_args or "").strip()
            if not raw_template:
                # Fall back to the plugin's own Custom template if present.
                raw_template = (default_args.get("Custom") or "").strip()
            if not raw_template or raw_template.upper() == "DISABLED":
                return None, f"⚠ Custom disables: {tool} (skipped for {target})."
            replaced = raw_template.replace("{{target}}", target).replace("{target}", target)
            return replaced, None

        template = default_args.get(profile_key, "")
        if isinstance(template, str) and template.upper() == "DISABLED":
            return None, f"[!] {tool} is disabled for {profile_key} mode. Skipping {target}."
        replaced = template.replace("{{target}}", target).replace("{target}", target)
        return replaced, None

    # ------------------------------------------------------------------ #
    # Public: run a single (tool, target)
    # ------------------------------------------------------------------ #
    def run_tool(
        self,
        tool: str,
        target: str,
        profile: str = "Normal",
        custom_args: Optional[str] = None,
        timeout: Optional[float] = ...,  # sentinel: use default_timeout
        output_callback: Optional[Callable[[str], None]] = None,
    ) -> RunResult:
        """
        Execute one plugin against one target and return a RunResult.

        This reproduces ScanThread.run_tool + run_tool_and_save semantics but
        returns structured data instead of emitting Qt signals.
        """
        started = datetime.now()
        logs: List[str] = []

        def _cb(line: str) -> None:
            logs.append(line)
            if output_callback:
                output_callback(line)

        result = RunResult(
            tool=tool,
            target=target,
            profile=profile,
            ok=False,
            started_at=started.isoformat(),
            logs=logs,
        )

        module = self.plugin_map.get(tool)
        if module is None:
            result.message = f"Tool '{tool}' is not supported."
            result.finished_at = datetime.now().isoformat()
            return result

        replaced_args, skip_msg = self._resolve_args(module, tool, target, profile, custom_args)
        if skip_msg is not None:
            result.skipped = True
            result.ok = True  # skip is not a hard failure (GUI parity)
            result.message = skip_msg
            result.finished_at = datetime.now().isoformat()
            return result

        run_id = started.strftime("%Y%m%d_%H%M%S")
        tool_key = _norm(tool)
        target_key = _norm(target)
        raw_dir = os.path.join(
            self.report_root_folder, "All Reports", target_key, tool_key, run_id
        )
        os.makedirs(raw_dir, exist_ok=True)
        os.makedirs(os.path.join(raw_dir, "formatted"), exist_ok=True)
        os.makedirs(os.path.join(raw_dir, "exports"), exist_ok=True)

        self.cancel_event.clear()
        self._current_timeout = self.default_timeout if timeout is ... else timeout
        self._active_run_ctx = {"tool": tool_key, "target": target_key, "run_id": run_id}

        plugin_run = getattr(module, "run", None)
        if not callable(plugin_run):
            result.message = f"Plugin '{tool}' has no callable run()."
            result.finished_at = datetime.now().isoformat()
            return result

        result.command = replaced_args
        aborted = False
        timed_out = False

        try:
            output = plugin_run(
                target,
                raw_dir,
                self.report_root_folder,
                self.run_command,
                self.check_tool_installed,
                self.extract_cves,
                replaced_args,
                _cb,
            )
        except subprocess.CalledProcessError as exc:
            result.message = f"{tool} failed for {target}: {exc.output}"
            result.finished_at = datetime.now().isoformat()
            return result
        except Exception as exc:
            result.message = f"{tool} crashed for {target}: {exc}"
            result.finished_at = datetime.now().isoformat()
            return result
        finally:
            ctx = self._active_run_ctx or {}
            result.exit_code = ctx.get("_exit_code")
            aborted = bool(ctx.get("_aborted")) or self.cancel_event.is_set()
            timed_out = bool(ctx.get("_timed_out"))
            self._active_run_ctx = {}

        # A killed subprocess (cancel/timeout) is a failure regardless of what
        # the plugin returned, since the plugin cannot observe the kill.
        if aborted or timed_out:
            rec = self._last_run_paths.get((tool_key, target_key))
            result.output_path = rec.get("path") if rec else None
            try:
                if result.output_path and Path(result.output_path).is_file():
                    result.output = Path(result.output_path).read_text(
                        encoding="utf-8", errors="replace"
                    )
            except Exception:
                pass
            result.ok = False
            result.skipped = False
            result.message = (
                "Aborted by user."
                if aborted
                else f"Timed out after {self._current_timeout}s."
            )
            result.finished_at = datetime.now().isoformat()
            return result

        # Interpret plugin return value, mirroring ScanThread.run_tool_and_save.
        had_error = False
        text_output = ""
        if isinstance(output, tuple):
            msg, had_error = output
            text_output = msg if isinstance(msg, str) else str(msg)
        elif isinstance(output, str):
            text_output = output
        elif output is None:
            had_error = True
        else:
            text_output = str(output)

        # If the plugin returned a path, resolve it to file contents + path.
        resolved_path = None
        if isinstance(text_output, str):
            p = Path(text_output.strip()) if text_output.strip() else None
            if p and p.is_file():
                resolved_path = str(p)
                try:
                    text_output = p.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass

        if resolved_path is None:
            rec = self._last_run_paths.get((tool_key, target_key))
            if rec and Path(rec.get("path", "")).is_file():
                resolved_path = rec["path"]

        result.output = text_output or ""
        result.output_path = resolved_path
        result.finished_at = datetime.now().isoformat()

        if had_error:
            result.ok = False
            if not result.message:
                result.message = f"{tool} reported an error for {target}."
        else:
            result.ok = True
            result.message = f"{tool} finished for {target}."
        return result


def new_scan_root(base_dir: str, label: str = "mcp") -> str:
    """
    Create and return a fresh scan-root folder under ``base_dir``, named like
    the GUI's scan folders so results land in the same Reports structure.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = _norm(label) or "scan"
    root = os.path.join(base_dir, f"Scan Results", f"{ts}_{safe}")
    os.makedirs(os.path.join(root, "All Reports"), exist_ok=True)
    os.makedirs(os.path.join(root, "machine"), exist_ok=True)
    return root
