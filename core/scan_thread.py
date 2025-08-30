# ReconCraft by Nirmal Chakraborty
# Copyright (c) 2025. All rights reserved.
# See LICENSE for details.



from PyQt5.QtCore import QThread, pyqtSignal
import os, sys, time, subprocess, threading, signal
import concurrent.futures
import importlib
from core.plugin_loader import discover_plugins
from pathlib import Path
from core.file_conventions import run_paths
from datetime import datetime
from threading import Event, Lock

        

class ScanThread(QThread):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    status_signal = pyqtSignal(str)

    def __init__(self,
                targets,
                tools,
                report_root_folder,
                scan_mode="Normal",
                # --- NEW (optional; safe defaults) ---
                profile_mode=None,
                custom_args_map=None):
        super().__init__()
        self.scan_mode = scan_mode     # storing the scanning mode (kept)
        self.targets = targets
        self.tools = tools
        self.report_root_folder = report_root_folder
        self.total_tasks = len(targets) * len(tools)
        self.completed_tasks = 0
        self.plugin_map = discover_plugins()
        self.cancel_event = threading.Event()   # <- allows Abort to signal cancellation
        self._cancel = Event()      # ✅ cooperative cancel flag
        self._procs = set()         # ✅ track live subprocess.Popen objects
        self._procs_lock = Lock()


        # --- NEW: runtime profile + flattened custom args (no impact if not provided) ---
        # If caller doesn't pass profile_mode, we mirror scan_mode. Everything is lowercase internally.
        self.profile_mode = (profile_mode or scan_mode or "Normal").lower()
        # Flattened dict like {"nmap": "-sn {{target}}", "httpx": "…"}
        self.custom_args_map = dict(custom_args_map or {})



    def get_all_tools(self):
        """
        Returns the list of dynamically loaded plugin tools only.
        """
        return list(self.plugin_map.keys())

    def request_cancel(self):
        # set flag so workers stop asap
        self._cancel.set()
        try:
            # trip the shared event used by run_command() cooperative checks
            self.cancel_event.set()
        except Exception:
            pass
        # kill any running processes quickly
        with self._procs_lock:
            procs = list(self._procs)
        for p in procs:
            try:
                p.terminate() if os.name == "nt" else p.send_signal(signal.SIGTERM)
            except Exception:
                pass


    def run(self):
        
        error_occurred = False # Flag to track if any error occurred
        os.makedirs(self.report_root_folder, exist_ok=True)
        # Creating a subfolder for all reports
        all_reports_dir = os.path.join(self.report_root_folder, "All Reports")
        os.makedirs(all_reports_dir, exist_ok=True)
        # Prepare for future MCP/AI (folder only; no writes yet)
        #machine_dir = os.path.join(self.report_root_folder, "machine")
        #os.makedirs(machine_dir, exist_ok=True)
        self.log_signal.emit(f"⚙ Launching tools on {len(self.targets)} target(s)...")

        if self.cancel_event.is_set():
            self.log_signal.emit("⏹️ Scan aborted before start.")
            self.finished_signal.emit("done_error")
            return
        
        import concurrent.futures  # ensure available in scope
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = []

            # 👉 Schedule all (tool × target) jobs
            for target in self.targets:
                if self.cancel_event.is_set():
                    break
                for tool in self.tools:
                    if self.cancel_event.is_set():
                        break
                    # target_folder is not used anymore by the writer; keep signature
                    futures.append(executor.submit(self.run_tool_and_save, tool, target, None))

            # If cancel was requested during submission, cancel queued immediately
            if self.cancel_event.is_set():
                for f in futures:
                    f.cancel()
                self.log_signal.emit("⏹️ Cancelling remaining tasks…")
                try:
                    executor.shutdown(cancel_futures=True)  # Python 3.9+
                except TypeError:
                    executor.shutdown()
            else:
                for future in concurrent.futures.as_completed(futures):
                    if self.cancel_event.is_set():
                        # best-effort cancel remaining futures
                        for f in futures:
                            f.cancel()
                        self.log_signal.emit("⏹️ Cancelling remaining tasks…")
                        try:
                            executor.shutdown(cancel_futures=True)
                        except TypeError:
                            pass
                        break

                    result = future.result()

                    # ✅ Support both old and updated return values
                    if isinstance(result, tuple):
                        result_msg, had_error = result
                        if had_error:
                            error_occurred = True
                    else:
                        result_msg = result  # fallback
                        error_occurred = True

                    self.completed_tasks += 1
                    progress_percent = int((self.completed_tasks / self.total_tasks) * 100) if getattr(self, "total_tasks", 0) else 100
                    self.log_signal.emit(result_msg)
                    self.progress_signal.emit(progress_percent)

        if self.cancel_event.is_set():
            self.log_signal.emit("⏹️ Scan aborted by user.")
            self.finished_signal.emit("done_error")
            return
        
        # ✅ Emit final status based on error flag
        self.finished_signal.emit("done_error" if error_occurred else "done_success")


    # Refactored to handle both raw text and pre-saved paths
    def run_tool_and_save(self, tool, target, target_folder):
        """
        Runs a plugin (self.run_tool) and saves output to:
        Scan Results/<scan_folder>/All Reports/<target>/<tool>/<run_id>/raw_<tool>.log
        Creates formatted/ and exports/ for that run.
        Ensures empty machine/ under <scan_folder>.

        NOTE:
        - Dedupe is per (tool, target) so multiple targets never merge.
        - run_id is time-based (target is a folder above).
        """
        if self.cancel_event.is_set():
            return f"⏹️ Skipping {tool} for {target} (aborted).", True
        # --- small helpers (local; no external deps) ---
        def _norm(s: str) -> str:
            s = (s or "").strip().lower()
            return "".join(ch if (ch.isalnum() or ch in "-_.") else "_" for ch in s).strip("_")

        try:
            tool_key   = _norm(tool)
            target_key = _norm(target)

            # expose current (tool, target) to run_command() without changing its signature
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            setattr(self, "_active_run_ctx", {"tool": tool_key, "target": target_key, "run_id": ts})
            try:

                output = self.run_tool(tool, target)
            finally:
                # always clear context
                try:
                    delattr(self, "_active_run_ctx")
                except Exception:
                    pass

            # --- If plugin returned (msg, had_error) keep the contract ---
            if isinstance(output, tuple):
                msg, had_error = output
                if had_error:
                    return f"❌ {tool} failed for {target}: {msg}", True
                output = msg

            # --- If plugin already saved via run_command() and returned the path, use it ---
            if isinstance(output, str):
                p = Path(output)
                if p.is_file():
                    return f"✅ {tool} finished for {target}. Output saved to: {p}", False

            # --- Look for a very recent raw path recorded by run_command() for THIS (tool, target) ---
            recent_map = getattr(self, "_last_run_paths", {})
            rec = recent_map.get((tool_key, target_key))
            if rec:
                last_path = Path(rec.get("path", ""))
                last_ts = rec.get("ts", 0)
                if last_path.is_file() and (time.time() - last_ts) <= 15:
                    return f"✅ {tool} finished for {target}. Output saved to: {last_path}", False

            # --- Additional safeguard for blank output ---
            if output is None or (isinstance(output, str) and output.strip() == ""):
                return f"❌ {tool} produced no output for {target}.", True

            # Roots
            scan_root = Path(self.report_root_folder)
            all_reports_root = scan_root / "All Reports"
            all_reports_root.mkdir(parents=True, exist_ok=True)
            # ✅ machine under scan folder (not under All Reports)
            (scan_root / "machine").mkdir(parents=True, exist_ok=True)

            # Per-run dirs — target-first layout
            run_id = ts

            run_dir = all_reports_root / target_key / tool_key / run_id
            formatted_dir = run_dir / "formatted"
            exports_dir = run_dir / "exports"
            run_dir.mkdir(parents=True, exist_ok=True)
            formatted_dir.mkdir(parents=True, exist_ok=True)
            exports_dir.mkdir(parents=True, exist_ok=True)

            raw_log_path = run_dir / f"raw_{tool_key}.log"
            with open(raw_log_path, "w", encoding="utf-8") as f:
                f.write(output if isinstance(output, str) else str(output))

            # remember this write in case plugin returns non-path
            try:
                if not hasattr(self, "_last_run_paths"):
                    self._last_run_paths = {}
                self._last_run_paths[(tool_key, target_key)] = {
                    "path": str(raw_log_path),
                    "ts": time.time(),
                }
            except Exception:
                pass

            return f"✅ {tool} finished for {target}. Output saved to: {raw_log_path}", False

        except subprocess.CalledProcessError as e:
            return f"❌ {tool} failed for {target}: {e.output}", True
        except Exception as e:
            return f"❌ {tool} crashed for {target}: {str(e)}", True

    #Running ⚙️ Plugin-based tools only 
    def run_tool(self, tool, target):
            if tool in self.plugin_map:
                # Use per-run dir so plugin self-writes are isolated per target/tool/run
                def _norm(s: str) -> str:
                    s = (s or "").strip().lower()
                    return "".join(ch if (ch.isalnum() or ch in "-_.") else "_" for ch in s).strip("_")
                tool_key = _norm(tool)
                target_key = _norm(target)
                ctx = getattr(self, "_active_run_ctx", {}) or {}
                run_id = ctx.get("run_id") or datetime.now().strftime("%Y%m%d_%H%M%S")
                raw_dir = os.path.join(self.report_root_folder, "All Reports", target_key, tool_key, run_id)
                os.makedirs(raw_dir, exist_ok=True)
                os.makedirs(os.path.join(raw_dir, "formatted"), exist_ok=True)
                os.makedirs(os.path.join(raw_dir, "exports"), exist_ok=True)


                plugin_module = self.plugin_map[tool]                 # ✅ now full module
                plugin_func = getattr(plugin_module, "run")           # ✅ access .run
                default_args = getattr(plugin_module, "DEFAULT_ARGS", {})

                # Prefer explicit runtime profile if provided; else your original scan_mode
                active_mode = getattr(self, "profile_mode", None) or getattr(self, "scan_mode", "Normal")
                scan_mode = active_mode

                # Map lowercase to plugin DEFAULT_ARGS keys (Aggressive/Normal/Passive)
                if isinstance(scan_mode, str):
                    _low = scan_mode.strip().lower()
                    if _low != "custom":
                        _keymap = {"aggressive": "Aggressive", "normal": "Normal", "passive": "Passive"}
                        scan_mode = _keymap.get(_low, scan_mode)

                scan_args_template = default_args.get(scan_mode, "")

                # ---------- CUSTOM PROFILE HANDLING (non-invasive) ----------
                if isinstance(scan_mode, str) and scan_mode.lower() == "custom":
                    # Expect a flattened map like {"nmap": "-sn {{target}}"}; safe default = ""
                    custom_map = getattr(self, "custom_args_map", {}) or {}
                    raw_template = (custom_map.get(tool) or "").strip()

                    # Empty or explicit DISABLED => skip WITHOUT error
                    if not raw_template or raw_template.upper() == "DISABLED":
                        msg = f"⚠ Custom disables: {tool} (skipped for {target})."
                        # (message, had_error=False) so final status isn't marked as failure
                        return msg, False

                    # Support BOTH {{target}} (new template) and {target} (legacy)
                    replaced_args = (
                        raw_template.replace("{{target}}", target).replace("{target}", target)
                    )

                    # Optional: one-line telemetry to the UI, if log_signal exists
                    try:
                        self.log_signal.emit(f"🧩 Using Custom args for {tool}: {raw_template} -> {replaced_args}")
                    except Exception:
                        pass

                    return plugin_func(                                # ✅ call .run from module
                        target,
                        raw_dir,
                        self.report_root_folder,
                        self.run_command,
                        self.check_tool_installed,
                        self.extract_cves,
                        replaced_args,
                        self.log_signal.emit
                    )

                # ---------- NON-CUSTOM PROFILES (Aggressive / Normal / Passive): UNCHANGED ----------
                scan_args_template = default_args.get(scan_mode, "")

                if isinstance(scan_args_template, str) and scan_args_template.upper() == "DISABLED":
                    return f"[!] {tool} is disabled for {scan_mode} mode. Skipping {target}.", True

                # Support BOTH {{target}} (new template) and {target} (legacy)
                replaced_args = (
                    scan_args_template.replace("{{target}}", target).replace("{target}", target)
                )

                return plugin_func(                                # ✅ call .run from module
                    target,
                    raw_dir,
                    self.report_root_folder,
                    self.run_command,
                    self.check_tool_installed,
                    self.extract_cves,
                    replaced_args,
                    self.log_signal.emit
                )
            else:
                raise Exception(f"Tool '{tool}' is not supported.")


    # 🔧 Helper methods passed into plugins
    def run_command(self, cmd_list, outfile_name, output_callback=None):
        """
        Runs a command and writes output to a file (new layout).
        Writes to:
        Scan Results/<scan_folder>/All Reports/<target>/<tool>/<run_id>/raw_<tool>.log
        Ensures formatted/ and exports/ exist for that run.
        Also ensures an empty machine/ exists under <scan_folder>.
        """
        # Normalize names
        def _norm(s: str) -> str:
            s = (s or "").strip().lower()
            return "".join(ch if (ch.isalnum() or ch in "-_.") else "_" for ch in s).strip("_")

        # Roots
        scan_root = Path(self.report_root_folder)
        all_reports_root = scan_root / "All Reports"
        all_reports_root.mkdir(parents=True, exist_ok=True)
        # ✅ machine under scan folder (not under All Reports)
        (scan_root / "machine").mkdir(parents=True, exist_ok=True)

        # Tool key
        tool_name = Path(cmd_list[0]).name
        if tool_name.lower().endswith(".exe"):
            tool_name = tool_name[:-4]
        tool_key = _norm(tool_name)

        # Target key: prefer context from run_tool_and_save; else derive a safe fallback
        ctx = getattr(self, "_active_run_ctx", {}) or {}
        target_key = ctx.get("target")
        if not target_key:
            tail = (outfile_name or "").split("_", 1)[-1]
            target_key = _norm(tail) or "target"

        # run_id = timestamp only (target is above)
        ctx_run_id = (getattr(self, "_active_run_ctx", {}) or {}).get("run_id")
        run_id = ctx_run_id or datetime.now().strftime("%Y%m%d_%H%M%S")


        # Canonical run paths — target-first layout
        run_dir = all_reports_root / target_key / tool_key / run_id
        formatted_dir = run_dir / "formatted"
        exports_dir = run_dir / "exports"
        run_dir.mkdir(parents=True, exist_ok=True)
        formatted_dir.mkdir(parents=True, exist_ok=True)
        exports_dir.mkdir(parents=True, exist_ok=True)
        out_path = str(run_dir / f"raw_{tool_key}.log")

        # Execute
        command_str = " ".join(cmd_list)
        if output_callback:
            output_callback(f"🟢 Running: {command_str}")

        # ✅ Cancellable & non-blocking execution: stream output and honor self.cancel_event
        aborted = False
        try:
            # Create a new process group so we can terminate the whole tree on cancel.
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
                # Track live processes for abort
                with self._procs_lock:
                    self._procs.add(proc)


                last_log = time.time()
                if proc.stdout is not None:
                    for line in iter(proc.stdout.readline, ""):
                        f.write(line)

                        # trickle progress to UI (non-spammy)
                        if output_callback and (time.time() - last_log) > 0.25:
                            last_log = time.time()
                            output_callback(line.rstrip())

                        # cooperative cancel
                        if ( (getattr(self, "cancel_event", None) and self.cancel_event.is_set())
                             or (getattr(self, "_cancel", None) and self._cancel.is_set()) ):

                            aborted = True
                            # try to terminate the process tree
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
                            except Exception as e:
                                if output_callback:
                                    output_callback(f"❌ Error running: {command_str}")
                                    output_callback(str(e))
                            finally:
                                # untrack proc
                                try:
                                    with self._procs_lock:
                                        self._procs.discard(proc)
                                except Exception:
                                    pass

                            if output_callback:
                                output_callback("⏹️ Aborted by user.")
                            break

                # finalize
                ret = proc.wait()
                if not aborted:
                    if output_callback:
                        output_callback(f"✅ Finished: {command_str} (Exit code: {ret})")
                    if ret != 0 and output_callback:
                        output_callback("⚠️ Warning: Tool exited with code "
                                        f"{ret}. Check the output file for errors.")
        except Exception as e:
            if output_callback:
                output_callback(f"❌ Error running: {command_str}")
                output_callback(str(e))

        # Remember most recent raw path for THIS (tool, target)
        try:
            if not hasattr(self, "_last_run_paths"):
                self._last_run_paths = {}
            self._last_run_paths[(tool_key, target_key)] = {"path": out_path, "ts": time.time()}
        except Exception:
            pass

        return out_path

    def check_tool_installed(self, tool_name):
        return any(
            os.access(os.path.join(path, tool_name), os.X_OK)
            for path in os.environ["PATH"].split(os.pathsep)
        )

    def extract_cves(self, filepath, ip):
        # Optional placeholder for plugin CVE parsing
        pass
