from PyQt5.QtWidgets import QLabel, QStatusBar,QSizePolicy, QSpacerItem
from PyQt5.QtCore import Qt, QTimer
from PyQt5 import QtCore
import time
import platform, shutil, subprocess, sys, webbrowser, importlib, os, shlex, threading, queue
from core.installer_utils import safe_install_tool, compat_try_install_tool, get_plugin_install_meta, has_cmd
from pathlib import Path
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QCheckBox


# Function to create a styled copyright label
from PyQt5.QtWidgets import QLabel, QSizePolicy, QSpacerItem
from PyQt5.QtCore import Qt

def get_copyright_label(parent_layout=None, *, place_bottom=False):
    """
    Create the styled copyright label.

    - If parent_layout and place_bottom=True are provided,
      the function will pin the label to the bottom-center of that layout.
    - If not provided, it just returns the label (current behavior).
    """
    label = QLabel(
        '<a href="https://www.linkedin.com/in/nirmalchak/" '
        'style="color: #ffaa00; text-decoration: none;"><b>© SneakyWarwolf</b></a>'
    )
    label.setOpenExternalLinks(True)
    label.setAlignment(Qt.AlignHCenter)
    # I recommend this way: fixed vertical size so it never creates a tall band
    label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    label.setStyleSheet("""
        color: #ffaa00;
        font-size: 12px;
        font-weight: bold;
        margin: 0px;
        padding: 0px;
        font-family: Segoe UI, Arial, sans-serif;
    """)

    # Optional bottom placement (only if caller supplies the layout)
    if place_bottom and parent_layout is not None:
        parent_layout.addItem(QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding))
        parent_layout.addWidget(label, 0, Qt.AlignHCenter | Qt.AlignBottom)

    return label

# Utility function to run command attempting installations and stream output
def try_install_tool(command_or_tool, output_func, install_hint=None, install_url=None, max_attempts=2):
    """
    Unified installer:
      - If `command_or_tool` is a plugin module (has REQUIRED_TOOL), use the new template-aware
        safe installer (supports Docker shims via TOOL_ALIAS/DOCKER_RUN).
      - Otherwise, preserve legacy behavior for plain tool names or full shell commands
        (attempt list, retries, sudo warnings, browser fallback).
    Returns one of: "installed" | "failed" | "exception" | "manual"
    """
    # ---------------------------
    # Path 1: New plugin module
    # ---------------------------
    if hasattr(command_or_tool, "REQUIRED_TOOL"):
        plugin = command_or_tool
        ok, msg = safe_install_tool(plugin, output_func)

        meta = get_plugin_install_meta(plugin)
        runtime_name = meta.get("runtime_name") or meta.get("alias_name") or meta.get("required_tool")

        if ok and has_cmd(runtime_name):
            output_func(f"✅ Installed: {runtime_name}")
            return "installed"
        else:
            output_func(f"❌ Failed: {msg}")
            return "failed"

    # ---------------------------
    # Path 2: Legacy/compat mode
    #   - command_or_tool can be a plain tool name or a full shell string
    #   - mirrors your previous try_install_tool behavior exactly
    # ---------------------------
    # Use your existing run_streamed if it exists in this module
    try:
        _runner = run_streamed  # defined elsewhere in common_widget.py
    except NameError:
        _runner = None

    return compat_try_install_tool(
        command_or_tool,
        output_func,
        install_hint=install_hint,
        install_url=install_url,
        max_attempts=max_attempts,
        run_streamed=_runner,  # preserves your streaming/UX
    )

# --- Live streaming command runner (stdout/stderr line-by-line) ---
def run_streamed(cmd, output_func, *, shell=False, timeout=None):
    """
    Run a command and stream stdout/stderr to output_func line-by-line.
    cmd: list[str] (preferred) or str (when shell=True)
    """
    if not shell and isinstance(cmd, str):
        cmd = shlex.split(cmd)

    p = subprocess.Popen(
        cmd if not shell else (cmd if isinstance(cmd, str) else " ".join(cmd)),
        shell=shell,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    def pump():
        for line in p.stdout:
            output_func(line.rstrip("\n"))
        p.stdout.close()

    t = threading.Thread(target=pump, daemon=True)
    t.start()
    rc = p.wait(timeout=timeout)
    t.join(timeout=1)
    return rc

# --- Sudo Prompt Dialog (Linux) ---
class SudoPromptDialog(QDialog):
    """
    Modal sudo prompt. Returns a tuple via .result_tuple:
      (password_or_None, skip_this: bool, skip_all: bool)
    """
    def __init__(self, package_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Administrator rights required")
        self.result_tuple = (None, False, False)

        v = QVBoxLayout(self)
        v.addWidget(QLabel(f"Installing '{package_name}' needs sudo.\n"
                           "Enter your password to continue, or choose a skip option."))

        self.le = QLineEdit(self)
        self.le.setEchoMode(QLineEdit.Password)
        self.le.setPlaceholderText("sudo password")
        v.addWidget(self.le)

        self.remember_cb = QCheckBox("Remember for this session", self)
        self.remember_cb.setChecked(True)  # worker may choose to cache it in-memory
        v.addWidget(self.remember_cb)

        btn_row1 = QHBoxLayout()
        btn_continue = QPushButton("Continue")
        btn_skip_this = QPushButton("Skip this tool")
        btn_row1.addWidget(btn_continue)
        btn_row1.addWidget(btn_skip_this)
        v.addLayout(btn_row1)

        btn_row2 = QHBoxLayout()
        btn_skip_all = QPushButton("Skip ALL privileged installs")
        btn_cancel = QPushButton("Cancel")
        btn_row2.addWidget(btn_skip_all)
        btn_row2.addWidget(btn_cancel)
        v.addLayout(btn_row2)

        btn_continue.clicked.connect(self._on_continue)
        btn_skip_this.clicked.connect(self._on_skip_this)
        btn_skip_all.clicked.connect(self._on_skip_all)
        btn_cancel.clicked.connect(self._on_skip_this)  # treat cancel as skip this

        self.resize(420, 180)

    def _on_continue(self):
        pwd = self.le.text().strip()
        self.result_tuple = (pwd if pwd else None, False, False)
        self.accept()

    def _on_skip_this(self):
        self.result_tuple = (None, True, False)
        self.reject()

    def _on_skip_all(self):
        self.result_tuple = (None, False, True)
        self.reject()

# This class provides a simple elapsed-time ticker for the status bar
class ElapsedTicker:
    def __init__(self, target, interval_ms: int = 250):
        """
        target may be:
          - QStatusBar: ticker creates its own QLabel and adds it as a permanent widget, or
          - QLabel:     ticker uses the provided label directly.
        """
        self._prefix = ""
        self._start = None
        self._timer = QtCore.QTimer()
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._on_tick)

        if isinstance(target, QStatusBar):
            self.status_bar = target
            self.label = QLabel("")
            self.status_bar.addPermanentWidget(self.label)
        elif isinstance(target, QLabel):
            self.status_bar = None
            self.label = target
        else:
            raise TypeError("ElapsedTicker target must be QStatusBar or QLabel")

        self.hide_label()  # start hidden

    def show_label(self):
        self.label.setVisible(True)

    def hide_label(self):
        self.label.setVisible(False)

    def set_prefix(self, text: str):
        self._prefix = text
        # optional immediate refresh on GUI thread
        QtCore.QTimer.singleShot(0, self._on_tick)

    def start(self, prefix="Working…"):
        self._prefix = prefix
        self._start = time.monotonic()
        self.show_label()
        self._timer.start()
        self._on_tick()

    def stop(self, final_note: str = None):
        self._timer.stop()
        self._start = None          # <- without this, text may keep updating
        if final_note:
            self.label.setText(final_note)
            self.show_label()
        else:
            self.hide_label()

    def _on_tick(self):
        if self._start is None:
            return
        elapsed = int(time.monotonic() - self._start)
        m, s = divmod(elapsed, 60)
        self.label.setText(f"{self._prefix}  [{m:02d}:{s:02d}]")

