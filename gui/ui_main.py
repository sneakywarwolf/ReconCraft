# ReconCraft by Nirmal Chakraborty
# Copyright (c) 2025. All rights reserved.
# See LICENSE for details.

# === Qt bindings (PyQt5 preferred, fall back to PySide6) ======================
try:
    from PyQt5.QtWidgets import (
        QMainWindow, QWidget, QTabWidget, QVBoxLayout, QPushButton, QTextEdit,
        QLineEdit, QLabel, QCheckBox, QListWidget, QGroupBox, QHBoxLayout,
        QToolButton, QProgressBar, QGridLayout, QListWidgetItem, QTreeWidget,
        QTreeWidgetItem, QFileDialog, QTableWidget, QSplitter,QSizePolicy, QSpacerItem,
        QMenu, QAction, QMessageBox, QToolButton

    )
    from PyQt5.QtCore import Qt, pyqtSignal, QUrl, QSize, QObject, pyqtSignal, Qt, QEventLoop, QTimer
    from PyQt5.QtGui import QIcon, QDesktopServices
    QT_BINDING = "PyQt5"
except Exception:
    from PySide6.QtWidgets import (
        QMainWindow, QWidget, QTabWidget, QVBoxLayout, QPushButton, QTextEdit,
        QLineEdit, QLabel, QCheckBox, QListWidget, QGroupBox, QHBoxLayout,
        QToolButton, QProgressBar, QGridLayout, QListWidgetItem, QTreeWidget,
        QTreeWidgetItem, QFileDialog
    )
    from PySide6.QtCore import Qt, Signal as pyqtSignal, QUrl, QSize
    from PySide6.QtGui import QIcon, QDesktopServices
    QT_BINDING = "PySide6"

# === Standard library =========================================================
import os
import sys
import re
import csv
import json
import shutil
import platform
import subprocess
import webbrowser
import ipaddress, traceback
from urllib.parse import urlparse
from pathlib import Path
from datetime import datetime
from PyQt5.QtWidgets import QTreeWidgetItem
from PyQt5.QtCore import Qt

# === Optional third-party =====================================================
try:
    import pandas as pd  # noqa: F401
except ImportError:
    pd = None

# === Project imports ==========================================================
from core.scan_thread import ScanThread
from core.cvss_calc import CVSSCalcTab
from core.tools_utils import is_tool_installed
from core.plugin_loader import discover_plugins
from core.report_model import load_run_model
from core.report_exporter import (export_csv, export_html, export_pdf, export_json, export_copy_raw,
    export_raw_to_html,export_findings_csv,export_findings_json
)
from core.installer_utils import get_plugin_install_meta, has_cmd

from gui.flow_layout import FlowLayout
from gui.settings_profiles_tab import ScanProfileSettingsTab
from gui.common_widgets import try_install_tool, get_copyright_label, ElapsedTicker,SudoPromptDialog
from gui.tool_worker import ToolCheckWorker, ToolInstallWorker
from gui.ansi_text_viewer import AnsiTextViewer, strip_ansi

import importlib.util  # keep last; rarely used and isolated


# This is the main UI class for the ReconCraft application
class ReconCraftUI(QMainWindow):
    
    def __init__(self):
        super().__init__()

        self.setWindowTitle("ReconCraft GUI")
        self.setGeometry(500, 100, 1000, 800)   

        # load plugins here
        self.plugin_map = discover_plugins()
        self.plugins = self.plugin_map
            
        # Workers (avoid AttributeError before first use)
        self.installer_worker = None
        self.check_worker = None
        self.scan_thread = None
        self.plugin_metas = self._build_plugin_metas(self.plugin_map) # Build plugin metadata (alias/exec/docker etc.)
        self.install_ticker = None
        self.check_ticker = None
        self.scan_ticker = None
        
        # Sudo prompt bridge for Linux
        self.sudo_bridge = _SudoPromptBridge(self)

        # create small QLabel placeholders in your status bar or a footer widget
        self.check_ticker_label = QLabel("")     # styled as you wish
        self.install_ticker_label = QLabel("")
        self.scan_ticker_label = QLabel("")
        self.statusBar().addPermanentWidget(self.check_ticker_label)
        self.statusBar().addPermanentWidget(self.install_ticker_label)
        self.statusBar().addPermanentWidget(self.scan_ticker_label)

        # wrap them with tickers
        self.check_ticker   = ElapsedTicker(self.check_ticker_label)
        self.install_ticker = ElapsedTicker(self.install_ticker_label)
        self.scan_ticker    = ElapsedTicker(self.scan_ticker_label)

        # optionally hide all by default
        self.check_ticker.hide_label()
        self.install_ticker.hide_label()
        self.scan_ticker.hide_label()

        # Make local shims (for Docker aliases) available to PATH
        from pathlib import Path
        import os
        shims = Path.cwd() / ".rc_shims"
        if shims.exists():
            os.environ["PATH"] = str(shims) + os.pathsep + os.environ.get("PATH", "")

        # DEFAULT THEME DARK
        self.theme_mode = "dark"
        self.set_dark_theme()

        # Set the custom window icon
        self.setWindowIcon(QIcon("assets/reconcraft_icon.png"))

        self.tool_container_layout = QVBoxLayout()
        self.plugins = {}

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.init_dashboard_tab()           # call to initialize the dashboard tab
        self.init_scan_tab()                # call to initialize the scan tab
        self.init_settings_tab(self.plugin_map)   # call to initialize the settings tab   
        self.init_reports_tab()             # call to initialize the reports tab
        self.init_cvss_tab()                # call to initialize the CVSS Calculator tab

        self.refresh_plugins()  # Refreshing plugins on startup
  
    #For Sudo Prompt
    def prompt_sudo_password(self, pkg_name: str):
        """
        Thread-safe callable for ToolInstallWorker.sudo_prompt:
          returns (password_or_None, skip_this: bool, skip_all: bool)
        """
        loop = QEventLoop()
        result = {"v": (None, False, False)}

        def _answered(tup):
            result["v"] = tup
            loop.quit()

        self.sudo_bridge.answered.connect(_answered, Qt.QueuedConnection)
        self.sudo_bridge.ask.emit(pkg_name)   # marshals to GUI thread
        loop.exec_()
        try:
            self.sudo_bridge.answered.disconnect(_answered)
        except Exception:
            pass
        return result["v"]
    
    # Initialize the CVSS Calculator tab
    def init_cvss_tab(self):
        self.cvss_tab = CVSSCalcTab()
        self.tabs.addTab(self.cvss_tab, QIcon("assets/cvss_icon.png"), "")
        index = self.tabs.indexOf(self.cvss_tab)
        self.tabs.setTabToolTip(index, "CVSS Calculator")
        self.tabs.setTabText(index, "CVSS Calc.")

    #CLEAR OUTPUT FIELD
    def clear_output(self):
        self.output_console.clear()
        self.progress_bar.setValue(0)
        self.status_label.setText("Status: Idle")  

    #ABORT/Cancel SCAN
    def abort_scan(self):
            """
            Called when 'Abort Scan / Cancel Install' is pressed.
            Signals the worker to stop; does NOT block the GUI thread.
            """
            # prevent repeat clicks
            try:
                self.abort_button.setEnabled(False)
            except Exception:
                pass

            # tell ScanThread to stop
            st = getattr(self, "scan_thread", None)
            if st is not None:
                try:
                    # show immediate feedback but do not reset/clear yet
                    if hasattr(self, "output_console"):
                        self.output_console.append("⏹️ Aborting scan…")
                    if hasattr(self, "status_label"):
                        self.status_label.setText("Aborting…")
                except Exception:
                    pass
                try:
                    # cooperative cancel (handled inside scan thread / run_command)
                    if hasattr(st, "request_cancel"):
                        st.request_cancel()
                except Exception:
                    # optional: surface the error to console
                    try:
                        if hasattr(self, "output_console"):
                            self.output_console.append("⚠️ Failed to signal cancel to scan thread.")
                    except Exception:
                        pass

            # if you also use an installer worker, signal it similarly:
            it = getattr(self, "install_thread", None)
            if it is None:
                it = getattr(self, "installer_worker", None)
            if it is not None and hasattr(it, "request_cancel"):
                try:
                    if hasattr(self, "output_console"):
                        self.output_console.append("⏹️ Cancelling install…")
                    it.request_cancel()
                except Exception:
                    try:
                        if hasattr(self, "output_console"):
                            self.output_console.append("⚠️ Failed to signal cancel to installer.")
                    except Exception:
                        pass

            # NOTE: Do NOT hard-reset UI here; let handle_scan_finished(status)
            #       stop ticker, clear progress, and re-enable controls.
            #       This avoids freezes while the worker tears down.
            # self.progress_bar.setValue(0)
            # self.status_label.setText("Idle")

    
    #Timer to update the status label
    def _bind_status_to_ticker(self, ticker_attr: str):
        """
        Returns a slot that updates the given ticker's prefix from a worker's status signal.
        ticker_attr is the attribute name holding the ElapsedTicker instance
        (e.g., 'check_ticker', 'install_ticker', 'scan_ticker').
        """
        def _slot(text: str):
            ticker = getattr(self, ticker_attr, None)
            if ticker:
                # just change the prefix; elapsed timer keeps running on GUI thread
                ticker.set_prefix(text)
        return _slot

    # Switches the ticker context based on the current operation
    def _switch_context(self, ctx: str):
        """
        ctx: 'scan' | 'install' | 'check' | 'idle'
        Ensures only the relevant ticker is visible and clears stale messages.
        """
        # Clear transient statusbar message so 'Install complete' doesn't linger
        self.statusBar().clearMessage()

        # Hide all ticker widgets by default
        for attr in ("scan_ticker", "install_ticker", "check_ticker"):
            t = getattr(self, attr, None)
            if t:
                t.hide_label()  # add this helper to ElapsedTicker (below)

        # Show only the active one
        if ctx == "scan" and getattr(self, "scan_ticker", None):
            self.scan_ticker.show_label()
        elif ctx == "install" and getattr(self, "install_ticker", None):
            self.install_ticker.show_label()
        elif ctx == "check" and getattr(self, "check_ticker", None):
            self.check_ticker.show_label()

    # Build plugin metadata for easier access
    def _build_plugin_metas(self, plugin_map):
        metas = {}
        for name, mod in (plugin_map or {}).items():
            # Prefer new template’s get_install_info() if present
            gi = {}
            try:
                if hasattr(mod, "get_install_info"):
                    gi = mod.get_install_info() or {}
            except Exception:
                gi = {}

            # Fallbacks to support old/simple plugins
            required_tool = gi.get("required_tool") or getattr(mod, "REQUIRED_TOOL", "")
            install_hint  = (gi.get("install_hint") or getattr(mod, "INSTALL_HINT", "manual") or "manual").lower()
            install_url   = gi.get("install_url") or getattr(mod, "INSTALL_URL", "")
            exec_name     = gi.get("exec_name") or getattr(mod, "EXECUTABLE", "") or required_tool
            alias_name    = gi.get("alias_name") or getattr(mod, "TOOL_ALIAS", "") or exec_name or required_tool
            docker_run    = gi.get("docker_run") or getattr(mod, "DOCKER_RUN", "")

            metas[name] = {
                "required_tool": required_tool,
                "install_hint":  install_hint,
                "install_url":   install_url,
                "exec_name":     exec_name,
                "alias_name":    alias_name,
                "docker_run":    docker_run,
            }
        return metas

#DASHBOARD TAB
    def init_dashboard_tab(self):
        
        # 🌐 Create the dashboard tab
        self.dashboard_tab = QWidget()
        layout = QVBoxLayout()

        # 🏠 Dashboard Header
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(0)  # 🔧 The gap between RECONCRAFT and logo

        # 🧭 Tool Title Header
        tool_title = QLabel("🔍 RECONCRAFT")
        tool_title.setAlignment(Qt.AlignCenter)
        tool_title.setStyleSheet("""
            font-size: 26px;
            color: #00d9ff;
            font-weight: bold;
            letter-spacing: 12px;
            margin-top: 16px;
            margin-bottom: 0px;                         
            margin: 0px;
            padding: 0px;
        """)
        tool_title.setFixedHeight(40)  # Control height tightly
        layout.addWidget(tool_title)

        # 🛰️ Tool Logo/Icon (centered)
        logo = QLabel()
        logo.setPixmap(QIcon("assets/reconcraft_icon.png").pixmap(570, 170))
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet("margin-top: 4px; margin-bottom: 10px;")  # reduced
        layout.addWidget(logo)


        # 👤 Creator credit with GitHub icon beside it
        creator_layout = QHBoxLayout()

        # Creator label
        creator_label = QLabel("👨‍💻 Created by <b style='color:#ff0055;'>SneakyWarwolf</b>")
        creator_label.setStyleSheet("font-size: 14px; color: #ffffff;")
        creator_label.setTextFormat(Qt.RichText)
        creator_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        creator_label.setOpenExternalLinks(False)

        # GitHub button
        github_btn = QPushButton()
        github_btn.setIcon(QIcon("assets/github_icon.png"))  # Make sure the icon is placed here
        github_btn.setIconSize(QSize(24, 24))
        github_btn.setCursor(Qt.PointingHandCursor)
        github_btn.setToolTip("Visit GitHub")
        github_btn.setStyleSheet("background: transparent; border: none; margin-left: 6px; margin-bottom: 10px; margin-top: 10px;")
        github_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/sneakywarwolf")))


        # Combine in horizontal layout
        creator_layout.addStretch()
        creator_layout.addWidget(creator_label)
        creator_layout.addWidget(github_btn)
        creator_layout.addStretch()

        layout.addLayout(creator_layout)

        # 📊 Stylized Stats Grid using QGroupBox
        stats_grid = QGridLayout()
        stats_grid.setSpacing(12)

        # 🧮 Initialize labels (these can be updated dynamically later)
        self.total_scans_label = QLabel("5")
        self.last_target_label = QLabel("example.com")
        self.last_tools_label = QLabel("Nmap, Subfinder")
        self.last_time_label = QLabel("2025-06-03 10:30 AM")
        self.last_status_label = QLabel("✅ Successful")
        self.last_report_label = QLabel("<a href='#'>demo_report_01.txt</a>")
        self.last_report_label.setOpenExternalLinks(False)

        # 📦 Define the metrics with labels
        metrics = {
            "🧮 Total Scans Run": self.total_scans_label,
            "🕵️‍♂️ Last Target": self.last_target_label,
            "🧰 Tools Used": self.last_tools_label,
            "🕒 Last Scan Time": self.last_time_label,
            "✅ Status": self.last_status_label,
            "📁 Last Report": self.last_report_label
        }

        # 🧱 Add each metric to the grid as a group card
        row, col = 0, 0
        for title, label in metrics.items():
            group = QGroupBox(title)
            group.setStyleSheet("""
                QGroupBox {
                    border: 2px solid #00d9ff;
                    border-radius: 8px;
                    margin-top: 6px;
                    padding: 6px;
                    font-weight: bold;
                    color: #00d9ff;
                }
                QLabel {
                    color: #ffffff;
                    font-size: 15px;
                }
            """)
            inner_layout = QVBoxLayout()
            label.setStyleSheet("margin-left: 4px;")
            inner_layout.addWidget(label)
            group.setLayout(inner_layout)
            stats_grid.addWidget(group, row, col)

            col += 1
            if col > 2:
                col = 0
                row += 1

        # ✅ Add grid to layout
        layout.addLayout(stats_grid)

        # 💡 Tip or quick help
        tip = QLabel("💡 <i>Tip: Review CVSS scores for your findings in the 'CVSS Calc.' tab!</i>")
        tip.setStyleSheet("font-size: 14px; color: #ffaa00; margin-top: 16px;")
        tip.setAlignment(Qt.AlignCenter)
        layout.addWidget(tip)

        # 📋 Finalize Dashboard layout
        self.dashboard_tab.setLayout(layout)

        # 🛠️ Add dashboard tab with icon and tooltip
        index = self.tabs.addTab(self.dashboard_tab, QIcon("assets/home_icon.png"), "")
        self.tabs.setTabToolTip(index, "🏠 Dashboard – Overview of your scans")
        self.tabs.setTabText(index, "Dashboard")  # ✅ Use the captured index

    
 #SCAN TAB
    def init_scan_tab(self):
      

        # This defines the actual scan tab.
        self.scan_tab = QWidget()  
        layout = QVBoxLayout()
        
        self.scan_tab.setLayout(layout)  # ✅ Correct: apply layout to the tab actually being used


        header = QLabel("🛠 ReconCraft - Craft Your Edge")
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #00d9ff;")
        layout.addWidget(header)
        layout.addWidget(get_copyright_label())

        layout.addWidget(QLabel("Target(s):"))

        # Create horizontal layout for target input and clear button
        target_layout = QHBoxLayout()

        self.target_input = QLineEdit()
        self.target_input.setPlaceholderText("Enter IP, Domain, or URL (comma-separated for multiple targets)")
        self.target_input.setStyleSheet("margin-bottom: 10px;")

        # Add a clear button next to the input    
        clear_btn = QToolButton()
        clear_btn.setIcon(QIcon("assets/clear_icon.jpg"))
        clear_btn.setToolTip("Clear target")
        clear_btn.clicked.connect(self.target_input.clear)

        clear_btn.setStyleSheet("""
            QPushButton {
                background: none;
                border: none;
                padding: 4px;
            }
            QPushButton:hover {
                background: #222;
                border: 1px solid #00d9ff;
            }
            QPushButton:pressed {
                background: #111;
            }
        """)
        target_layout.addWidget(self.target_input) #input field
        target_layout.addWidget(clear_btn)  # clear button

        # After creating self.target_input and clear_btn
        upload_btn = QPushButton()
        upload_btn.setIcon(QIcon("assets/upload_icon.jpg"))  # Use a suitable upload icon in your assets
        upload_btn.setToolTip("Upload targets from a .txt file")
        upload_btn.clicked.connect(self.upload_targets)

        # Add upload_btn to the target_layout (just like clear_btn)
        upload_btn.setStyleSheet("""
            QPushButton {
                background: none;
                border: none;
                padding: 4px;
            }
            QPushButton:hover {
                background: #222;
                border: 1px solid #00d9ff;
            }
            QPushButton:pressed {
                background: #111;
            }
        """)
        target_layout.addWidget(upload_btn)

        # Now add the target label and full horizontal layout to your main layout
        layout.addLayout(target_layout)

        # --- Tools group (persist on self; not checkable; force-enabled) ---
        self.tools_group = QGroupBox("Select Tools to Run")
        self.tools_group.setCheckable(False)     # IMPORTANT: if checkable+unchecked → children disabled
        self.tools_group.setEnabled(True)
        self.tools_group.setStyleSheet("""
            /* Scope only the tools container */
            QGroupBox {
                color: #FFA500;
                background-color: #222;
                font-weight: bold;
                border: 2px solid #00FFFF;
                border-radius: 5px;
                margin-top: 10px;
            }
            QGroupBox:title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px;
            }                                                           
            #pluginsContainer QCheckBox::indicator {
                width: 16px; height: 16px;           /* optional; keeps things crisp */
                background: transparent;
            }

            /* 🔴 Unchecked: red border, empty box */
            #pluginsContainer QCheckBox::indicator:unchecked {
                border: 1px solid #ff0000;
                image: none;
            }

            /* ☑ Checked: red tick (no border) */
            #pluginsContainer QCheckBox::indicator:checked {
                border: 1px solid transparent;
                background: transparent;
                image: url(assets/tick_red.svg);
                image-position: center;
                }
        """)


        # Clear any previous registry and host FlowLayout inside a QWidget
        self.tools = {}
        self.tools_container = QWidget(self.tools_group)
        self.tools_container.setObjectName("pluginsContainer")

        # Your custom FlowLayout attached to the host widget
        self.tool_container_layout = FlowLayout(self.tools_container)
        self.tools_container.setLayout(self.tool_container_layout)

        # Dynamically add checkboxes (this should populate self.tool_checkboxes and self.tool_availability)
        self.init_dynamic_tool_checkboxes(self.tool_container_layout)

        # Put the host into the group with a normal VBox (stable margins)
        _tools_group_layout = QVBoxLayout()
        _tools_group_layout.setContentsMargins(8, 8, 8, 8)
        _tools_group_layout.addWidget(self.tools_container)
        self.tools_group.setLayout(_tools_group_layout)

        # Add to main layout
        layout.addWidget(self.tools_group)

        # --- Plugin Actions Row (Refresh Plugins + Check Tools) ---
        plugin_action_layout = QHBoxLayout()
        plugin_action_layout.setSpacing(12)

        self.refresh_button = QPushButton("🔄 Refresh Plugins")
        self.refresh_button.setToolTip("Reload plugins and update tool list")
        self.refresh_button.clicked.connect(self.refresh_plugins)

        self.check_tools_btn = QPushButton("🧪 Check Tools")
        self.check_tools_btn.setToolTip("Check if all loaded tools are installed")
        #self.check_tools_btn.setIcon(QIcon("assets/check_tools_icon.png"))
        self.check_tools_btn.clicked.connect(self.check_tools_installed)

        # Uniform height, expanding width
        for b in (self.refresh_button, self.check_tools_btn):
            b.setMinimumHeight(40)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Equal stretches -> equal widths
        plugin_action_layout.addWidget(self.refresh_button, 1)
        plugin_action_layout.addWidget(self.check_tools_btn, 1)

        # Add the plugin action layout to the main layout
        layout.addLayout(plugin_action_layout)

        # --- Install Missing Tools Button ---
        install_tools_layout = QHBoxLayout()
        install_tools_layout.setSpacing(12)

        self.install_tools_btn = QPushButton("⬇ Install Missing Tools")
        self.install_tools_btn.setToolTip("Try to install all missing tools automatically")
        #self.install_tools_btn.setIcon(QIcon("assets/install_icon.png"))
        self.install_tools_btn.clicked.connect(self.install_missing_tools)
        self.install_tools_btn.setMinimumHeight(40)
        self.install_tools_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Center it nicely with side spacers that shrink/grow
        install_tools_layout.addItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))
        install_tools_layout.addWidget(self.install_tools_btn, 2)
        install_tools_layout.addItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))

        layout.addLayout(install_tools_layout)


        #ADDING START & ABORT BUTTON
       
        self.start_button = QPushButton("▶ Start Scan")
        self.start_button.clicked.connect(self.launch_scan)

        self.abort_button = QPushButton("⛔ Abort Scan/Cancel Install")
        self.abort_button.setEnabled(False)
        self.abort_button.clicked.connect(self.abort_scan)

        for b in (self.start_button, self.abort_button):
            b.setMinimumHeight(40)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)
        button_layout.addWidget(self.start_button, 1)  # start button
        button_layout.addWidget(self.abort_button, 1)   # abort button
        layout.addLayout(button_layout)


        self.check_result_label = QLabel("")
        self.check_result_label.setAlignment(Qt.AlignCenter)
        self.check_result_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #ff5555;")
        layout.addWidget(self.check_result_label)

        #Progress Bar, Status Label, and Output Console
        self.progress_bar = QProgressBar()
        self.progress_bar.setAlignment(Qt.AlignCenter)
        self.progress_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.progress_bar.setValue(0)
        
        # Force bold font!
        font = self.progress_bar.font()
        font.setBold(True)
        font.setPointSize(8)  # Or any size you prefer
        self.progress_bar.setFont(font)
        
        self.progress_bar.setVisible(True)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Status: Idle")
        layout.addWidget(self.status_label)

        self.output_console = QTextEdit()
        self.output_console.setReadOnly(True)
        # Render output as plain text to keep font size consistent even with emojis
        self.output_console.setAcceptRichText(False)
        self.output_console.setText("Scan output will be shown here.")
        self.output_console.setStyleSheet("""
            background-color: #111;
            color: #33ff33;
            font-family: Consolas, monospace;
            font-size: 13px;
        """)

        layout.addWidget(QLabel("Output:"))
        layout.addWidget(self.output_console)

    # ➕ Add Clear and Reset buttons
        button_row = QWidget()
        button_layout = QVBoxLayout()
        button_layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        self.clear_button = QPushButton("🧹 Clear Output")
        self.clear_button.clicked.connect(self.clear_output)

        self.reset_button = QPushButton("🔁 Reset Tools")
        self.reset_button.clicked.connect(self.reset_tools)

        # Optional styling
        self.clear_button.setStyleSheet("margin-bottom: 4px;")
        self.reset_button.setStyleSheet("margin-bottom: 4px;")

        button_layout.addWidget(self.clear_button)
        button_layout.addWidget(self.reset_button)

        button_row.setLayout(button_layout)
        layout.addWidget(button_row)

        scan_index=self.tabs.addTab(self.scan_tab, QIcon("assets/scan.png"), "")
        self.tabs.setTabToolTip(scan_index, "🔍 Scan – Start recon with selected tools")
        self.tabs.setTabText(scan_index, "Scan")

 #CHECK IF TOOLS ARE INSTALLED   
    def check_tools_installed(self):
        
        #Switch ticker context to check
        self._switch_context("check")
        self.scan_ticker.start("Checking tools…")

        self.progress_bar.setStyleSheet("QProgressBar::chunk { background: #00bfff; }")
        self.check_result_label.setText("")  # (optional) clears old label

        
        self.output_console.clear()
        self.progress_bar.setValue(0)
        self.statusBar().showMessage("Starting tool check...")
        
        
        self.check_worker = ToolCheckWorker(self.plugins, is_tool_installed)
        self.check_worker.progress.connect(self.progress_bar.setValue)
        self.check_worker.status.connect(self.statusBar().showMessage)
        
        #self.check_worker.status.connect(self._bind_status_to_ticker("check_ticker"))
        self.check_worker.output.connect(self.output_console.append)
        self.check_worker.finished.connect(self._on_check_tools_finished)
        # start
        self.check_worker.start()

    
    # Installing missing tools    
    def install_missing_tools(self):
        
        #Switch ticker context to install
        self._switch_context("install")
        self.install_ticker.start("Installing…")
        
        if not hasattr(self, "missing_tools") or not self.missing_tools:
            self.statusBar().showMessage("No missing tools found. Please run check tools first.")
            return

        # ✅ Clear console & reset progress
        self.output_console.clear()
        self.progress_bar.setValue(0)
        self.statusBar().showMessage("🔧 Starting installation of missing tools...")

        # 🔒 Safeguard: don't start another installer if one is already running
        w = getattr(self, "installer_worker", None)
        if w is not None and w.isRunning():
            # (optional) surface a message in your UI here if you already have a mechanism
            # e.g., self.statusBar().showMessage("Installer is already running", 3000)
            return

        # ✅ Create ToolInstallWorker (matches __init__(missing_plugins, plugins))
        self.installer_worker = ToolInstallWorker(self.missing_tools, self.plugins)
        # Provide the sudo popup callable (defined in ui_main.py as prompt_sudo_password)
        self.installer_worker.sudo_prompt = self.prompt_sudo_password
        
        # Wire signals to your existing slots/handlers
        self.installer_worker.output.connect(self.output_console.append)
        self.installer_worker.status.connect(self.statusBar().showMessage)
        self.installer_worker.progress.connect(self.progress_bar.setValue)

        # Keep the missing list in sync for the UI (optional but useful)
        self.installer_worker.missing.connect(lambda lst: setattr(self, "missing_tools", lst))

        # Clear worker reference when done so we can re-run later
        self.installer_worker.finished.connect(lambda _ok: setattr(self, "installer_worker", None))

        # Call your existing finish handler
        self.installer_worker.finished.connect(self._on_install_tools_finished)

        # Start once
        self.installer_worker.start()

        # ✅ Connect signals for real-time feedback
        self.installer_worker.output.connect(self.output_console.append)
        self.installer_worker.status.connect(self.statusBar().showMessage)
        self.installer_worker.progress.connect(self.progress_bar.setValue)
        
       # This method is called when the ToolInstallWorker finishes installing tools
        self.installer_worker.finished.connect(self._on_install_tools_finished) 
       # ✅ Start the worker thread
        self.installer_worker.start()


    def _on_install_tools_finished(self, ok: bool):
        t = getattr(self, "install_ticker", None)
        if t:
            t.stop("Install complete." if ok else "Install failed.")
            self._switch_context("idle")

        self.statusBar().showMessage("Install complete." if ok else "Some tools could not be installed. See logs.", 6000)
        self.output_console.append("✅ All missing tools (if any) have been handled.")

       
    # This method is called when the ToolCheckWorker finishes checking tools
    def _on_check_tools_finished(self, missing_tools):
        
        self.missing_tools = missing_tools
        if missing_tools:
            self.check_result_label.setText("Some tools missing.")
            self.check_result_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #ff5555;")  # red
            self.progress_bar.setStyleSheet("QProgressBar::chunk { background: #ff5555; }")  # red bar
            #stopping ticker
            self.check_ticker.stop("Check complete.")
            self._switch_context("idle")
            
        else:
            self.check_result_label.setText("All tools are installed.")
            self.check_result_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #55ff55;")  # green
            self.progress_bar.setStyleSheet("QProgressBar::chunk { background: #55ff55; }")  # green bar
            #stopping ticker
            self.check_ticker.stop("Check complete.")
            self._switch_context("idle")
        
    # -------------------- Target parsing & validation --------------------
    def _parse_and_validate_targets(self, raw: str):
            """
            Parse multi-target input and validate each token.
            Rules:
            - Split by comma and newlines.
            - Trim, remove internal whitespace (warn user).
            - Reject tokens containing special characters (outside [A-Za-z0-9._:/-]).
            - Accept: domain names, IPv4 addresses, IPv4/CIDR.
            - Also accept URLs (http/https) by extracting the hostname.
            Returns a **deduped, ordered** list of cleaned targets or [].
            """
            def _norm(s: str) -> str:
                return s.strip()

            def _strip_url(t: str) -> str:
                # If a URL is pasted, extract host part
                try:
                    if "://" in t:
                        u = urlparse(t)
                        host = u.netloc or u.path
                        # drop :port if present
                        if ":" in host and host.count(":") == 1:
                            host = host.split(":", 1)[0]
                        return host
                except Exception:
                    pass
                return t

            # Domain regex (simple & safe)
            domain_re = re.compile(
                r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,}$"
            )

            # Allowed character class for pre-validation (before domain/IP checks)
            # Allows dots, dashes, underscores, colon (for :port), slash (for CIDR/URL remnants).
            _allowed_pattern = r"[A-Za-z0-9._:/-]"
            _special_finder = re.compile(fr"[^{_allowed_pattern}]")

            tokens = []
            # split by comma and newlines
            for chunk in re.split(r"[,\n]+", raw or ""):
                t = _norm(chunk)
                if not t:
                    continue
                t0 = t
                t = _strip_url(t)

                # remove any internal whitespace and warn
                t_ws = re.sub(r"\s+", "", t)
                if t_ws != t:
                    if hasattr(self, "output_console"):
                        self.output_console.append(f"⚠️ Removed spaces from “{t}” → “{t_ws}”.")
                    t = t_ws

                # 🔒 Special characters check (early failure with explicit message)
                bad_chars = _special_finder.findall(t)
                if bad_chars:
                    bad_display = "".join(sorted(set(bad_chars)))
                    if hasattr(self, "output_console"):
                        self.output_console.append(
                            f"❌ Invalid target: special characters detected [{bad_display}] in “{t0}”."
                        )
                    continue

                # drop trailing dot on domains like "example.com."
                if t.endswith("."):
                    t = t[:-1]

                # allow host:port → strip port (tools usually accept host separately)
                if ":" in t and t.count(":") == 1:
                    host, port = t.split(":", 1)
                    if port.isdigit():
                        t = host

                # Validate: IPv4 (addr or CIDR) OR domain
                is_ok = False
                try:
                    ipaddress.IPv4Address(t)
                    is_ok = True
                except Exception:
                    try:
                        ipaddress.IPv4Network(t, strict=False)
                        is_ok = True
                    except Exception:
                        if domain_re.match(t):
                            is_ok = True

                if not is_ok:
                    if hasattr(self, "output_console"):
                        self.output_console.append(
                            f"❌ Invalid target format: “{t0}”. Remove special chars/spaces or fix typos."
                        )
                    continue

                tokens.append(t.lower())

            # de-duplicate while preserving order
            seen = set()
            cleaned = []
            for t in tokens:
                if t not in seen:
                    seen.add(t)
                    cleaned.append(t)
            return cleaned
      
#UPLOAD TARGETS FROM FILE
    def upload_targets(self):
    
        allowed_pattern = re.compile(r'^[a-zA-Z0-9\-._:,]+$')

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Target List",
            "",
            "Target Files (*.txt *.csv *.xlsx);;Text Files (*.txt);;CSV Files (*.csv);;Excel Files (*.xlsx);;All Files (*)"
        )
        if file_path:
            _, ext = os.path.splitext(file_path)
            lines = []
            try:
                if ext.lower() == ".txt":
                    with open(file_path, 'r') as f:
                        lines = [line.strip() for line in f if line.strip()]
                elif ext.lower() == ".csv":
                    with open(file_path, 'r', newline='') as csvfile:
                        reader = csv.reader(csvfile)
                        for row in reader:
                            for item in row:
                                item = item.strip()
                                if item:
                                    lines.append(item)
                elif ext.lower() == ".xlsx":
                    if pd is None:
                        self.output_console.append("❌ 'pandas' library is required to read Excel files. Please install it.")
                        return
                    try:
                        df = pd.read_excel(file_path, header=None)
                    except Exception as ex:
                        self.output_console.append(f"❌ Error reading Excel file: {str(ex)}")
                        return
                    for value in df.values.flatten():
                        if pd.isna(value):
                            continue
                        value = str(value).strip()
                        if value:
                            lines.append(value)
                else:
                    self.output_console.append("❌ Unsupported file type.")
                    return

                if not lines:
                    self.output_console.append("❌ The uploaded file is empty.")
                    return

                valid_lines = []
                invalid_lines = []
                for line in lines:
                    if allowed_pattern.match(line):
                        valid_lines.append(line)
                    else:
                        invalid_lines.append(line)

                if not valid_lines:
                    self.output_console.append("❌ No valid targets found (special characters detected).")
                    return

                self.target_input.setText(", ".join(valid_lines))
                self.output_console.append(f"✅ Imported {len(valid_lines)} valid targets from file.")

                if invalid_lines:
                    self.output_console.append(f"⚠️ Ignored {len(invalid_lines)} invalid lines due to special characters:")
                    for invalid in invalid_lines:
                        self.output_console.append(f"   - {invalid}")

            except Exception as e:
                self.output_console.append(f"❌ Failed to import targets: {str(e)}")


    # DYNAMICALLY POPULATE TOOL/PLUGIN CHECKBOXES
    def init_dynamic_tool_checkboxes(self, tool_container_layout):
        """
        Dynamically populate tool checkboxes into a layout based on available tools.
        Tools are ALWAYS clickable. Missing tools are visually marked and noted via tooltip.
        Availability is stored in self.tool_availability for later checks.
        """
        # 0) Clear existing items from the layout (if user re-enters tab or reloads)
        while tool_container_layout.count():
            item = tool_container_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        # 1) Discover plugins once (single source of truth)
        plugin_map = discover_plugins(run_validate=False)
        self.plugin_map = plugin_map
        self.plugins = plugin_map  # keep in sync
        self.tool_checkboxes = {}
        self.tool_availability = {}

        # 2) Build rows (NO UI ops here)
        rows = []
        for key, mod in plugin_map.items():
            META = getattr(mod, "META", None)
            name = (getattr(META, "NAME", None) or getattr(mod, "NAME", None) or key)

            hint = (getattr(META, "INSTALL_HINT", "") or getattr(mod, "INSTALL_HINT", "") or "")
            url  = (getattr(META, "INSTALL_URL", "")  or getattr(mod, "INSTALL_URL", "")  or "")

            meta = get_plugin_install_meta(mod)
            exe_name = meta.get("runtime_name") or ""

            win_hint = getattr(META, "WINDOWS_EXE_HINT", None) or getattr(mod, "WINDOWS_EXE_HINT", None)
            if os.name == "nt" and win_hint:
                exe_name = win_hint

            available = bool(exe_name and has_cmd(exe_name))
            rows.append((name, key, available, hint, url, exe_name or ""))

        # 3) Create checkboxes (UI ops ONLY here)
        for name, key, available, hint, url, exe in sorted(rows, key=lambda r: r[0].lower()):
            cb = QCheckBox(name)
            cb.setObjectName(f"tool_{key}")
            cb.setChecked(False)
            cb.setFocusPolicy(Qt.StrongFocus)
            cb.setEnabled(True)  # always clickable

            if not available:
                cb.setToolTip(f"'{exe}' not found on PATH")

            tool_container_layout.addWidget(cb)
            self.tool_checkboxes[key] = cb
            self.tool_availability[key] = available



# Get selected tools from checkboxes 
    def get_selected_tools(self):
        """
        Returns a list of tool names (as in self.tool_checkboxes)
        that are currently selected by the user.
        """
        return [name for name, checkbox in self.tool_checkboxes.items() if checkbox.isChecked()]


#RESET TOOLS
    def reset_tools(self):
        # Uncheck all tool checkboxes
        for checkbox in self.tool_checkboxes.values():
            checkbox.setChecked(False)

        # Clear the target input field
        self.target_input.clear()
  
#REFRESH PLUGINS

    def refresh_plugins(self):
        
        # Remove all existing checkboxes from layout
        for i in reversed(range(self.tool_container_layout.count())):
            widget = self.tool_container_layout.itemAt(i).widget()
            if widget:
                self.tool_container_layout.removeWidget(widget)
                widget.setParent(None)

        # --- LOAD PLUGINS DYNAMICALLY ---
        plugins_dir = os.path.join(os.getcwd(), "plugins")
        self.plugins = {}  # <--- ADD THIS: plugin name => plugin module

        for filename in os.listdir(plugins_dir):
            if filename.endswith(".py") and not filename.startswith("__"):
                plugin_name = filename[:-3]  # remove .py
                plugin_path = os.path.join(plugins_dir, filename)
                spec = importlib.util.spec_from_file_location(plugin_name, plugin_path)
                plugin_module = importlib.util.module_from_spec(spec)
                try:
                    spec.loader.exec_module(plugin_module)
                    self.plugins[plugin_name] = plugin_module
                except Exception as e:
                    self.output_console.append(f"❌ Failed to load {plugin_name}: {e}")

        # Reload tool checkboxes
        self.init_dynamic_tool_checkboxes(self.tool_container_layout)
        self.output_console.append("🔁 Plugins refreshed successfully.\n")

    # Central lock/unlock for scan UI (start/abort, targets, tool checkboxes, etc.)
    def _set_scan_ui_running(self, running: bool):
            """
            Lock/unlock scan controls so a finished/aborted run doesn't leave the UI stuck.
            This helper is defensive about widget names and only touches those that exist.
            """
            # Start button (support a few common names without assuming)
            start_btn = None
            for name in ("start_button", "start_scan_button", "start_scan_btn"):
                if hasattr(self, name):
                    start_btn = getattr(self, name)
                    break
            if start_btn:
                start_btn.setEnabled(not running)

            # Abort button
            if hasattr(self, "abort_button") and self.abort_button:
                self.abort_button.setEnabled(running)

            # Targets input
            if hasattr(self, "target_input") and self.target_input:
                self.target_input.setEnabled(not running)

            # Tool checkboxes (avoid users changing mid-run)
            if hasattr(self, "tool_checkboxes") and isinstance(self.tool_checkboxes, dict):
                for cb in self.tool_checkboxes.values():
                    try:
                        cb.setEnabled(not running)
                    except Exception:
                        pass

            # Optional cosmetics (only if present)
            if hasattr(self, "status_label") and self.status_label:
                self.status_label.setText("Scanning…" if running else "Idle")

    # HANDLE SCAN FINISHED
    def handle_scan_finished(self, status: str):
            
            """Stop ticker, reset context when scan finishes."""
            note = "Scan complete." if status == "done_success" else "Scan failed."
            try:
                if hasattr(self, "scan_ticker") and self.scan_ticker:
                    self.scan_ticker.stop(note)
            except Exception:
                pass

            # Switch to idle context (your existing behavior)
            self._switch_context("idle")

            # Ensure Abort is disabled
            if hasattr(self, "abort_button"):
                try:
                    self.abort_button.setEnabled(False)
                except Exception:
                    pass

            # Progress bar color (your existing behavior)
            if status == "done_success":
                # Green
                self.progress_bar.setStyleSheet("QProgressBar::chunk {background-color: #28a745;}")
            else:
                # Red
                self.progress_bar.setStyleSheet("QProgressBar::chunk {background-color: #dc3545;}")

            # Also set a final progress value for clarity
            try:
                if hasattr(self, "progress_bar") and self.progress_bar:
                    self.progress_bar.setValue(100 if status == "done_success" else 0)
            except Exception:
                pass
            
            # Update status line (your existing behavior)
            self.update_status_label(status)

            # Unlock scan UI so a new run can be started
            try:
                # Re-enable Start button (support common attribute names defensively)
                for name in ("start_button", "start_scan_button", "start_scan_btn"):
                    if hasattr(self, name) and getattr(self, name):
                        getattr(self, name).setEnabled(True)

                # Re-enable target input
                if hasattr(self, "target_input") and self.target_input:
                    self.target_input.setEnabled(True)

                # Re-enable tool checkboxes
                if hasattr(self, "tool_checkboxes") and isinstance(self.tool_checkboxes, dict):
                    for cb in self.tool_checkboxes.values():
                        try:
                            cb.setEnabled(True)
                        except Exception:
                            pass
            except Exception:
                pass

            # Refresh the Reports tree so new results appear immediately
            try:
                if hasattr(self, "load_report_tree"):
                    self.load_report_tree()
            except Exception:
                pass

            # Drop/cleanup the worker reference so a fresh one can be created next time
            st = getattr(self, "scan_thread", None)
            if st is not None:
                try:
                    if hasattr(st, "deleteLater"):
                        st.deleteLater()
                except Exception:
                    pass
                try:
                    del self.scan_thread
                except Exception:
                    pass

            # Final console note (your existing behavior)
            self.output_console.append("📌 Scan finished.")


# FOR STARTING & LAUNCHING SCAN
    def launch_scan(self):
            
        """
        Validate inputs, warn on missing tools, then start the scan
        with installed tools only. Ticker/UI locking occur only after
        all validations succeed.
        """

            # -- Targets --
        targets_input = self.target_input.text().strip() if hasattr(self, "target_input") else ""
        if not targets_input:
            self.output_console.append("❌ Please enter at least one target.")
            return
        targets = self._parse_and_validate_targets(targets_input)
        if not targets:
            self.output_console.append("❌ Invalid target format. Remove Spaces or special characters.")
            return

        # -- Selected tools --
        selected_plugins = self.get_selected_tools() if hasattr(self, "get_selected_tools") else [
            k for k, cb in getattr(self, "tool_checkboxes", {}).items() if cb.isChecked()
        ]
        if not selected_plugins:
            self.output_console.append("❌ Please select at least one tool.")
            return

        # -- Recompute availability for selected tools (single source of truth) --
        missing, available = [], []
        plugin_map = getattr(self, "plugin_map", {}) or getattr(self, "plugins", {})
        for k in selected_plugins:
            mod = plugin_map.get(k)
            meta = get_plugin_install_meta(mod) if mod else {}
            runtime = (meta.get("runtime_name") or "").strip()
            if not runtime:
                missing.append(k)
                continue
            if has_cmd(runtime):
                available.append(k)
            else:
                missing.append(k)

        if missing:
            self.output_console.append(f"⚠ Some selected tools are not installed: {', '.join(missing)}")
            if not available:
                self.output_console.append("❌ No installed tools selected. Use 'Install Missing Tools' or select available tools.")
                return
            else:
                self.output_console.append(f"➡ Proceeding with available tools only: {', '.join(available)}")

        selected_tools = available if available else selected_plugins

        # -- Prepare scan dir --
        # NOTE: pass full targets list so multi-target runs are named "multi_<timestamp>"
        scan_folder = self.prepare_scan_folder(targets) if hasattr(self, "prepare_scan_folder") else None

        if not scan_folder:
            self.output_console.append("❌ Failed to prepare scan directory.")
            return

        # ✅ Now it’s safe to enable Abort and start ticker
        self.abort_button.setEnabled(True)
        if hasattr(self, "scan_ticker") and self.scan_ticker:
            try:
                self._switch_context("scan")
                self.scan_ticker.start(prefix="Scan running")
            except Exception:
                pass

        # Toggle buttons if present
        try:
            if hasattr(self, "start_button") and self.start_button:
                self.start_button.setEnabled(False)
            if hasattr(self, "abort_button") and self.abort_button:
                self.abort_button.setEnabled(True)
        except Exception:
            pass

        # Optional: update status/progress
        if hasattr(self, "status_label") and self.status_label:
            self.status_label.setText("Status: Running")
        if hasattr(self, "progress_bar") and self.progress_bar:
            try:
                # ensure scan color scheme (blue) overrides any previous 'check tools' color
                self.update_status_label("indeterminate")
                self.progress_bar.setValue(0)
            except Exception:
                pass


        # ✅ Log starting message
        self.output_console.append(f"🚀 Starting scan on {len(targets)} target(s)...")
        self.output_console.append(f"📂 Scan folder created: {scan_folder}")


        # 🔁 Reset status and progress bar for new scan
        self.status_label.setText("Status: ⏳ Scan in progress...")
        self.progress_bar.setValue(0)

        #Switch ticker context to scan
        #self._switch_context("scan")
        #self.scan_ticker.start("Scan running…")
        
        # All validations passed — now lock the UI for a run
        self._set_scan_ui_running(True) 

        # ✅ Get selected scan mode from settings tab
        selected_mode = self.scan_profiles_widget.current_mode

        # ✅ Flatten custom args map for ScanThread
        custom_args_map = getattr(self, "_custom_args_cache", {}) or {}

        # ✅ Passing it to ScanThread, STARTING SCAN
        self.scan_thread = ScanThread(
            targets,
            selected_plugins,
            scan_folder,
            selected_mode,                          # keep passing your UI mode as-is
            profile_mode=(selected_mode or "Normal"),  #explicit runtime profile
            custom_args_map=custom_args_map,            #flattened {tool_key: "args"}
        )

        # connect FIRST
        self.scan_thread.log_signal.connect(self.output_console.append)
        self.scan_thread.progress_signal.connect(self.progress_bar.setValue)
        self.scan_thread.status_signal.connect(self.update_status_label)
        self.scan_thread.finished_signal.connect(self.handle_scan_finished)
        self.scan_thread.finished_signal.connect(
            lambda status: (
                self.update_status_label(status),
                self.progress_bar.setValue(100) if status == "done_success" else None
            )
        )
        
        #Starting the scan thread
        self.scan_thread.start()
        self.output_console.append("🔄 Scan in progress...")
        
        # Update dashboard with initial scan status
        self.scan_thread.finished_signal.connect(
            lambda status: (
                self.update_status_label(status),
                self.update_dashboard(', '.join(targets), selected_plugins)
            )
        )

# UPDATE STATUS LABEL
    def update_status_label(self, status):
            if status == "indeterminate":
                self.status_label.setText("Status: Initializing...")
                self.progress_bar.setStyleSheet("""
                    QProgressBar {
                        border: 1px solid #444;
                        border-radius: 5px;
                        text-align: center;
                        background-color: #111;
                        color: #ffffff;
                        font-weight: bold;
                        font-size: 14px;
                    }
                    QProgressBar::chunk {
                        background-color: #00d9ff;  /* Blue for scan start */
                    }
                """)
                self._force_center_progress_text()

            elif status == "done_success":
                self.status_label.setText("Status: ✅ Scan completed successfully.")
                self.progress_bar.setStyleSheet("""
                    QProgressBar {
                        border: 1px solid #444;
                        border-radius: 5px;
                        text-align: center;
                        background-color: #111;
                        color: #ffffff;
                        font-weight: bold;
                        font-size: 14px;
                    }
                    QProgressBar::chunk {
                        background-color: #00c853;
                    }
                """)
                self._force_center_progress_text()

            elif status == "done_error":
                self.status_label.setText("Status: ❌ Scan completed with some errors.")
                self.progress_bar.setStyleSheet("""
                    QProgressBar {
                        border: 1px solid #444;
                        border-radius: 5px;
                        text-align: center;
                        background-color: #111;
                        color: #ffffff;
                        font-weight: bold;
                        font-size: 14px;
                    }
                    QProgressBar::chunk {
                        background-color: #d32f2f;  /* Red for error */
                    }
                """)
                self._force_center_progress_text()

            elif "Completed" in status:
                self.status_label.setText(status)
                self._force_center_progress_text()


    # Force the progress text to be centered
    def _force_center_progress_text(self):
        
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.progress_bar.setLayoutDirection(Qt.LeftToRight)
        self.progress_bar.setInvertedAppearance(False)
        # Nudge a repaint without changing the value
        self.progress_bar.setValue(self.progress_bar.value())


#DASHBOARD UPDATE
    def update_dashboard(self, target, plugins):
        self.total_scans_label.setText("Total Scans Run: updated dynamically")
        self.last_target_label.setText(f"Last Scan Target: {target}")
        self.last_tools_label.setText(f"Tools Used: {', '.join(plugins)}")
        now = datetime.now().strftime("%Y-%m-%d %I:%M %p")
        self.last_time_label.setText(f"Last Scan Time: {now}")
        self.last_status_label.setText("Scan Status: ✅ Successful")

# Display last report link
    def linking_display_report(self, item):
        file_path = item.data(Qt.UserRole)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                self.report_viewer.setPlainText(content)
        except Exception as e:
            self.report_viewer.setPlainText(f"⚠️ Failed to load report:\n{str(e)}")

# Method to populate QTreeWidget (only "All Reports")
    def load_report_tree(self):
            
            root_dir = Path("Scan Results")

            # ✅ Fallback: create if missing
            if not root_dir.exists():
                root_dir.mkdir(parents=True, exist_ok=True)

            self.report_tree.clear()
            self.report_tree.setHeaderLabel("Scan Reports")
            self.report_tree.headerItem().setTextAlignment(0, Qt.AlignHCenter)

            def is_hidden(p: Path) -> bool:
                name = p.name
                return name.startswith(".") or name.startswith("_") or name.endswith("~")

            # Level 1: scan roots => "<scan_id>_<label>/"
            for scan_dir in sorted([d for d in root_dir.iterdir() if d.is_dir() and not is_hidden(d)]):
                all_reports = scan_dir / "All Reports"

                # If "All Reports" exists but is empty, fall back to the scan root.
                # If it doesn't exist, also fall back to the scan root.
                has_visible_in_all = (
                    all_reports.exists()
                    and any(d.is_dir() and not is_hidden(d) for d in all_reports.iterdir())
                )
                base_for_targets = all_reports if has_visible_in_all else scan_dir

                scan_item = QTreeWidgetItem([scan_dir.name])
                scan_item.setData(0, Qt.UserRole, {
                    "kind": "scan_root",
                    "scan_path": str(scan_dir),
                    "all_reports_path": str(all_reports),
                })
                self.report_tree.addTopLevelItem(scan_item)

                # Level 2: targets => "<target_name>/"
                # Exclude known non-target folders that sometimes sit at the scan root
                RESERVED = {"raw", "formatted", "exports", "tmp", "temp", "_temp", ".cache", ".tmp", "All Reports"}
                target_dirs = [
                    d for d in base_for_targets.iterdir()
                    if d.is_dir() and not is_hidden(d) and d.name not in RESERVED
                ]
                for tgt_dir in sorted(target_dirs, key=lambda p: p.name.lower()):
                    tgt_item = QTreeWidgetItem([tgt_dir.name])
                    tgt_item.setData(0, Qt.UserRole, {
                        "kind": "target",
                        "scan_path": str(scan_dir),
                        "target": tgt_dir.name,
                        "target_path": str(tgt_dir),
                    })
                    scan_item.addChild(tgt_item)

                    # Level 3: tools => "<tool-name>/"
                    tool_dirs = [d for d in tgt_dir.iterdir() if d.is_dir() and not is_hidden(d) and d.name not in RESERVED]
                    for tool_dir in sorted(tool_dirs, key=lambda p: p.name.lower()):
                        tool_item = QTreeWidgetItem([tool_dir.name])
                        tool_item.setData(0, Qt.UserRole, {
                            "kind": "tool",
                            "scan_path": str(scan_dir),
                            "target": tgt_dir.name,
                            "tool": tool_dir.name,
                            "tool_path": str(tool_dir),
                        })
                        tgt_item.addChild(tool_item)

                        # MACHINE-FACING (commented for later)
                        # machine_run_dir = (scan_dir / "machine" / tool_dir.name / run_dir.name)
                        # run_json = machine_run_dir / "run.json"
                        # findings_jsonl = machine_run_dir / "findings.jsonl"

                        # Level 4: runs => "<run_id>/"
                        run_dirs = [d for d in tool_dir.iterdir() if d.is_dir() and not is_hidden(d)]
                        # If a tool writes files directly (no per-run folder), treat the tool folder itself as one run
                        if not run_dirs:
                            run_dirs = [tool_dir]
                        for run_dir in sorted(run_dirs, key=lambda p: p.name.lower()):
                            raw_log = run_dir / f"raw_{tool_dir.name}.log"
                            if not raw_log.exists():
                                raw_log = run_dir / f"raw_{tool_dir.name.lower()}.log"
                            exports_dir = run_dir / "exports"
                            formatted_dir = run_dir / "formatted"

                            run_item = QTreeWidgetItem([run_dir.name])
                            run_item.setData(0, Qt.UserRole, {
                                "kind": "run",
                                "scan_path": str(scan_dir),
                                "target": tgt_dir.name,
                                "tool": tool_dir.name,
                                "run_id": run_dir.name,
                                "human": {
                                    "run_path": str(run_dir),
                                    "raw_log": str(raw_log) if raw_log.exists() else None,
                                    "exports_dir": str(exports_dir) if exports_dir.exists() else None,
                                    "formatted_dir": str(formatted_dir) if formatted_dir.exists() else None,
                                },
                            # "machine": {
                            #     "run_path": str(machine_run_dir) if machine_run_dir.exists() else None,
                            #     "run_json": str(run_json) if run_json.exists() else None,
                            #     "findings_jsonl": str(findings_jsonl) if findings_jsonl.exists() else None,
                            # },
                        })
                        tool_item.addChild(run_item)

            self.report_tree.expandToDepth(0)  # expand only first level by default


#clicking tree item to display report
    def _on_report_tree_clicked(self, item, _col):
        data = item.data(0, Qt.UserRole) or {}
        kind = (data.get("kind") or "").lower()
        if kind in ("scan", "scan_root", "target", "tool") or not kind:  # ✅ added scan_root + target
            item.setExpanded(not item.isExpanded())
            return
        self.display_report_from_tree(item, _col)


# Handler for displaying tree item   
    def display_report_from_tree(self, item, column):
            from pathlib import Path
            import json

            # We stored a dict in Qt.UserRole when building the tree
            data = item.data(0, Qt.UserRole)  # Qt.UserRole sits on column 0   <-- FIX: use Qt.UserRole
            if not isinstance(data, dict):
                return

            kind = data.get("kind")

            # Helper: safe file read
            def _read_text(p: Path) -> str:
                try:
                    return p.read_text(encoding="utf-8", errors="replace")
                except Exception as e:
                    return f"[!] Error reading {p}:\n{e}"

            # Expectation: self.rawViewer (ANSI-aware) and self.report_viewer (plain/JSON)
            has_raw_viewer = hasattr(self, "rawViewer") and self.rawViewer is not None
            has_plain_view = hasattr(self, "report_viewer") and self.report_viewer is not None

            if kind == "run":
                # >>> NEW: unified loader using All Reports
                # Metadata was stored under "all_reports" (preferred); fall back to "human" if older items exist.
                all_reports = data.get("all_reports") or {}
                run_folder = all_reports.get("run_path") or all_reports.get("run_dir")

                # Backward-compat (older tree code used "human")
                if not run_folder:
                    human = data.get("human") or {}
                    run_folder = human.get("run_path") or human.get("run_dir")

                # --- Try full renderer; on ANY error, gracefully fall back to Raw ---
                if run_folder:
                    try:
                        # Centralized render: fills Raw (ANSI) + Formatted + sets _currentRunModel
                        self.display_report(run_folder)
                        return
                    except Exception as e:  # <--- catch NameError from report_model (SCHEMA_VERSION), etc.
                        if has_plain_view:
                            self.report_viewer.setPlainText(f"[i] Formatted loader not ready: {e}\nShowing raw log instead…")

                # --- If no run_folder metadata (very old nodes) OR display_report failed, load raw file directly ---
                raw_log_path = (data.get("all_reports") or {}).get("raw_log")
                if not raw_log_path:
                    raw_log_path = (data.get("human") or {}).get("raw_log")
                # final fallback: derive raw path from run_folder + tool name
                if not raw_log_path and run_folder:
                    tool_name = (data.get("tool") or "").lower()
                    p = Path(run_folder)
                    cand1 = p / f"raw_{tool_name}.log"
                    cand2 = p / f"raw_{(data.get('tool') or '')}.log"
                    raw_log_path = str(cand1 if cand1.exists() else cand2)

                if raw_log_path and Path(raw_log_path).exists():
                    raw_text = _read_text(Path(raw_log_path))
                    if has_raw_viewer:
                        try:
                            self.rawViewer.set_ansi_text(raw_text)
                        except Exception:
                            if has_plain_view:
                                self.report_viewer.setPlainText(raw_text)
                    elif has_plain_view:
                        self.report_viewer.setPlainText(raw_text)
                else:
                    if has_plain_view:
                        self.report_viewer.setPlainText("[i] No raw log found for this run.")

                # 2) FORMATTED (MCP/machine artifacts — keep commented for later stage)
                # machine = data.get("machine") or {}
                # run_json_path = machine.get("run_json")
                # findings_path = machine.get("findings_jsonl")
                # try:
                #     run_meta = {}
                #     if run_json_path and Path(run_json_path).exists():
                #         run_meta = json.loads(Path(run_json_path).read_text(encoding="utf-8", errors="replace"))
                #     findings = []
                #     if findings_path and Path(findings_path).exists():
                #         with Path(findings_path).open("r", encoding="utf-8", errors="replace") as fh:
                #             for line in fh:
                #                 line = line.strip()
                #                 if line:
                #                     try:
                #                         findings.append(json.loads(line))
                #                     except Exception:
                #                         pass
                #     # Example hooks (uncomment when ready):
                #     # self._render_header_cards(run_meta, self._count_by_sev(findings))
                #     # self._render_findings_table(findings)
                # except Exception as e:
                #     if has_plain_view:
                #         self.report_viewer.append(f"\n[i] Formatted view not available yet: {e}")

            elif kind == "tool":
                # Optional: show a brief summary for tool level
                if has_plain_view:
                    self.report_viewer.setPlainText(f"[i] Select a run under tool: {data.get('tool')}")

            elif kind == "scan_root":
                if has_plain_view:
                    # Prefer the All Reports path if present
                    ar = data.get("all_reports_path") or data.get("scan_path")
                    self.report_viewer.setPlainText(f"[i] Select a tool, then a run inside: {ar}")

            else:
                # Legacy: if a bare file node slipped through, try to show it sensibly
                file_path = data.get("path")
                if file_path and Path(file_path).is_file():
                    p = Path(file_path)
                    text = _read_text(p)
                    if p.suffix.lower() in {".json", ".jsonl"}:
                        # pretty print JSON (best-effort)
                        try:
                            if p.suffix.lower() == ".jsonl":
                                # show first N lines prettified for convenience
                                lines = []
                                with p.open("r", encoding="utf-8", errors="replace") as fh:
                                    for i, line in enumerate(fh):
                                        if i >= 200:  # don't blow up UI
                                            break
                                        line = line.strip()
                                        if line:
                                            lines.append(json.dumps(json.loads(line), ensure_ascii=False, indent=2))
                                text = "[JSON Lines preview — first 200 lines]\n\n" + "\n\n".join(lines)
                            else:
                                text = json.dumps(json.loads(text), ensure_ascii=False, indent=2)
                        except Exception:
                            pass
                    if has_plain_view:
                        self.report_viewer.setPlainText(text)



#LOAD REPORT FILES for Refresh funtionality
    def load_report_files(self):
        """
        Loads readable reports from the intended tree:
        Scan Results/<scan>/All Reports/<tool>/<run_id>/{raw_<tool>.log, formatted/*, exports/*}
        and populates self.report_list (QListWidget).
        """
        scan_results_dir = os.path.join(os.getcwd(), "Scan Results")
        self.report_list.clear()

        # Create/enable state
        if not os.path.isdir(scan_results_dir):
            self.report_list.addItem("⚠️ 'Scan Results' folder not found.")
            self.report_list.setEnabled(False)
            return
        else:
            self.report_list.setEnabled(True)

        items = []  # (mtime, display_name, full_path)

        # Walk only the intended structure
        for scan_name in sorted(os.listdir(scan_results_dir)):
            scan_path = os.path.join(scan_results_dir, scan_name)
            if not os.path.isdir(scan_path):
                continue

            all_reports = os.path.join(scan_path, "All Reports")
            if not os.path.isdir(all_reports):
                # skip scans that don't have the required 'All Reports'
                continue

            # tools
            for tool_name in sorted(os.listdir(all_reports)):
                tool_path = os.path.join(all_reports, tool_name)
                if not os.path.isdir(tool_path):
                    continue
                if tool_name.lower() == "machine":
                    # safety: in case someone dropped a folder here by mistake
                    continue

                # runs
                for run_id in sorted(os.listdir(tool_path)):
                    run_path = os.path.join(tool_path, run_id)
                    if not os.path.isdir(run_path):
                        continue

                    # 1) raw_<tool>.log
                    for f in os.listdir(run_path):
                        fl = f.lower()
                        if fl.startswith("raw_") and (fl.endswith(".log") or fl.endswith(".txt")):
                            fp = os.path.join(run_path, f)
                            items.append((os.path.getmtime(fp),
                                        os.path.relpath(fp, scan_results_dir),
                                        fp))

                    # 2) formatted/*
                    formatted_path = os.path.join(run_path, "formatted")
                    if os.path.isdir(formatted_path):
                        for root, _, files in os.walk(formatted_path):
                            for f in files:
                                fl = f.lower()
                                if fl.endswith((".txt", ".log", ".html")):
                                    fp = os.path.join(root, f)
                                    items.append((os.path.getmtime(fp),
                                                os.path.relpath(fp, scan_results_dir),
                                                fp))

                    # 3) exports/*
                    exports_path = os.path.join(run_path, "exports")
                    if os.path.isdir(exports_path):
                        for root, _, files in os.walk(exports_path):
                            for f in files:
                                fl = f.lower()
                                if fl.endswith((".csv", ".json", ".pdf", ".html", ".txt", ".log")):
                                    fp = os.path.join(root, f)
                                    items.append((os.path.getmtime(fp),
                                                os.path.relpath(fp, scan_results_dir),
                                                fp))

        if not items:
            self.report_list.addItem("ℹ️ No reports found in 'Scan Results/<scan>/All Reports/'.")
            self.report_list.setEnabled(False)
            return

        # Newest-first
        items.sort(key=lambda x: x[0], reverse=True)

        for _, display_name, full_path in items:
            item = QListWidgetItem(display_name)
            item.setToolTip(full_path)
            item.setData(Qt.UserRole, full_path)
            self.report_list.addItem(item)



#THIS IS FOR REPORT TAB
    def init_reports_tab(self):
        """
        Build the Reports tab:
        - Title row (with refresh)
        - Splitter: left tree, right (search + Raw/Formatted tabs)
        """
        # --- Tab container you will attach to self.tabs ---
        self.report_tab = QWidget(self)
        layout = QVBoxLayout(self.report_tab)

        # --- Title bar with refresh ---
        title = QLabel("📁 Reports")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 18px; color: #00d9ff; font-weight: bold; margin-bottom: 6px;")

        # Single, canonical refresh button for the tree loader
        self.refresh_button = QPushButton()
        self.refresh_button.setIcon(QIcon("assets/refresh_icon.png"))  # use one icon path consistently
        self.refresh_button.setToolTip("Refresh Reports")
        self.refresh_button.setFixedSize(32, 32)
        self.refresh_button.setStyleSheet("border: none;")
        self.refresh_button.clicked.connect(self.load_report_tree)

        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.addStretch(1)                     # left stretch
        title_layout.addWidget(title, 0, Qt.AlignCenter)
        title_layout.addStretch(1)                     # right stretch (keeps title centered)
        title_layout.addWidget(self.refresh_button, 0, Qt.AlignRight)  # <-- adds refresh button

        layout.addLayout(title_layout)

        # --- Splitter for left tree and right panel ---
        self.reportsSplitter = QSplitter(Qt.Horizontal, self.report_tab)

        # LEFT: report tree
        self.report_tree = QTreeWidget(self.reportsSplitter)
        self.report_tree.setColumnCount(1)
        self.report_tree.setHeaderHidden(False)
        self.report_tree.header().setStretchLastSection(True)
        self.report_tree.setRootIsDecorated(True)
        self.report_tree.setItemsExpandable(True)
        self.report_tree.setExpandsOnDoubleClick(True)
        self.report_tree.setAnimated(True)
        self.report_tree.setUniformRowHeights(True)

        try:
            self.report_tree.itemClicked.disconnect(self.display_report_from_tree)
        except (TypeError, RuntimeError):
            pass

        self.report_tree.itemClicked.connect(self._on_report_tree_clicked)
        self.report_tree.setStyleSheet("""
            QTreeWidget {
                background-color: #121212;
                color: #00d9ff;
                border: 1px solid #303030;
                font-family: Consolas, monospace;
            }
            QHeaderView::section {
                background-color: #1a1a1a;
                color: #00d9ff;
                padding: 4px;
                font-weight: bold;
                border: 1px solid #303030;
            }
            QTreeWidget::item:selected {
                background-color: #1e1e1e;
                color: #00ffcc;
            }
            QTreeView::branch {                /* ✅ arrow color */
                color: #00d9ff;
            }
        """)

        # RIGHT: search bar + tabs (Raw/Formatted)
        right_container = QWidget(self.reportsSplitter)
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # ── Top bar: search + prev/next + Export ──
        top_bar = QHBoxLayout()
        self.reportSearchEdit = QLineEdit(right_container)
        self.reportSearchEdit.setPlaceholderText("Search (e.g., TLS1.0, VULNERABLE, OPEN)…")
        self._btnPrev = QPushButton("Prev", right_container)
        self._btnNext = QPushButton("Next", right_container)
        
        # Export button with dropdown menu
        self._btnExport = QToolButton(right_container)
        self._btnExport.setText("Export…")
        self._btnExport.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self._btnExport.setPopupMode(QToolButton.InstantPopup)  # click opens menu immediately


        top_bar.addWidget(QLabel("Find:", right_container))
        top_bar.addWidget(self.reportSearchEdit, 1)
        top_bar.addWidget(self._btnPrev)
        top_bar.addWidget(self._btnNext)
        top_bar.addStretch(1)
        top_bar.addWidget(self._btnExport)

        # Hook search + export
        self.reportSearchEdit.textChanged.connect(self.on_report_search)
        self._btnNext.clicked.connect(lambda: self._search_step(forward=True))
        self._btnPrev.clicked.connect(lambda: self._search_step(forward=False))
        self._connect_report_exports(self._btnExport)

        # ── Tabs: Raw (ANSI) + Formatted ──
        self.reportTabWidget = QTabWidget(right_container)

        # Raw tab
        raw_page = QWidget(self.reportTabWidget)
        raw_layout = QVBoxLayout(raw_page)
        self.rawViewer = AnsiTextViewer(raw_page)
        raw_layout.addWidget(self.rawViewer)
        self.reportTabWidget.addTab(raw_page, "Raw")

        # Formatted tab
        formatted_page = QWidget(self.reportTabWidget)
        f_layout = QVBoxLayout(formatted_page)

        header_row = QHBoxLayout()
        self._hdr_target = QLabel("Target: -", formatted_page)
        self._hdr_runid  = QLabel("Run ID: -", formatted_page)
        self._hdr_time   = QLabel("Started: -  Ended: -  Duration: -", formatted_page)
        self._hdr_status = QLabel("Status: - (exit -)", formatted_page)
        self._hdr_counts = QLabel("Critical:0  High:0  Medium:0  Low:0  Info:0", formatted_page)
        for w in (self._hdr_target, self._hdr_runid, self._hdr_time, self._hdr_status, self._hdr_counts):
            w.setTextInteractionFlags(Qt.TextSelectableByMouse)
            header_row.addWidget(w)
        header_row.addStretch(1)

        self.formattedTable = QTableWidget(formatted_page)
        self.formattedTable.setColumnCount(8)
        self.formattedTable.setHorizontalHeaderLabels([
            "Severity", "Title", "Asset", "Location", "Port", "Service", "Category", "Evidence"
        ])
        self.formattedTable.setSortingEnabled(True)

        f_layout.addLayout(header_row)
        f_layout.addWidget(self.formattedTable)
        self.reportTabWidget.addTab(formatted_page, "Formatted")

        # Assemble right side
        right_layout.addLayout(top_bar)
        right_layout.addWidget(self.reportTabWidget)

        # Add both panes to the splitter
        self.reportsSplitter.addWidget(self.report_tree)
        self.reportsSplitter.addWidget(right_container)
        
        self.report_tree.setMinimumWidth(290)
        #QTimer.singleShot(0, lambda: self.reportsSplitter.setSizes([540, 600]))
        self.reportsSplitter.setStretchFactor(0, 3)  # Left:Right ratio
        self.reportsSplitter.setStretchFactor(1, 2) # Right side: search+tabs ratio

        # Put splitter on the tab layout
        layout.addWidget(self.reportsSplitter)

        # Build tree contents
        self.load_report_tree()

        # Attach tab to main tabs
        report_index = self.tabs.addTab(self.report_tab, QIcon("assets/report.png"), "Reports")
        self.tabs.setTabToolTip(report_index, "📊 Reports – View generated scan reports")

        # Internal: model holder for exports
        self._currentRunModel = None

        # Copyright (keep if you want it on the tab)
        layout.addWidget(get_copyright_label())

# Added handler to load a selected run folder:
    def display_report(self, run_folder: str):
        """
        Given the human-facing run folder: Scan Results/<scan>/All Reports/<tool>/<run_id>,
        load raw_<tool>.log into the ANSI viewer and try to load machine artifacts
        (Scan Results/<scan>/machine/<tool>/<run_id>/run.json + findings.jsonl) if present.
        """
        from pathlib import Path

        run_path = Path(run_folder)
        if not run_path.exists() or not run_path.is_dir():
            return

        # 1) RAW — find raw_<tool>.log
        tool = run_path.parent.name
        run_id = run_path.name
        raw_file = run_path / f"raw_{tool}.log"
        if raw_file.exists():
            txt = raw_file.read_text(encoding="utf-8", errors="replace")
            self.rawViewer.set_ansi_text(txt)
        else:
            self.rawViewer.set_ansi_text("[i] No raw log found for this run.")

        # 2) FORMATTED — machine artifacts (commented layout stays for later)
        scan_dir = run_path.parents[2]  # .../<scan>/All Reports/<tool>/<run>
        run_json_path = scan_dir / "machine" / tool / run_id / "run.json"
        findings_path = scan_dir / "machine" / tool / run_id / "findings.jsonl"

        model = load_run_model(
            str(run_json_path) if run_json_path.exists() else "",
            str(findings_path) if findings_path.exists() else None
        )

        # Fallback minimal metadata if machine files not present yet
        if not model.get("run"):
            model["run"] = {
                "tool": tool,
                "run_id": run_id,
                "targets": ["-"],
                "started_at": "-",
                "ended_at": "-",
                "status": "unknown",
                "exit_code": None,
            }

        self._render_header_cards(model.get("run", {}), model.get("counts", {}))
        self._render_findings_table(model.get("findings", []))
        self._currentRunModel = model


#Search for a specific report
    def on_report_search(self):
        term = self.reportSearchEdit.text()
        if self.reportTabWidget.currentIndex() == 0: # Raw tab
            self.rawViewer.find_all(term, case_sensitive=False)
        else:
            self._filter_findings_table(term)

# Search next/prev in report
    def _search_step(self, forward: bool = True):
        term = self.reportSearchEdit.text().strip()
        if not term:
            return
        # Tab 0: Raw; Tab 1: Formatted
        if self.reportTabWidget.currentIndex() == 0:
            if forward:
                self.rawViewer.find_next(term, case_sensitive=False)
            else:
                self.rawViewer.find_prev(term, case_sensitive=False)
        else:
        # For formatted, we just filter the table rows; no next/prev
            self._filter_findings_table(term)

# Filter findings table by search term
    def _render_header_cards(self, run_meta: dict, counts: dict):
        target = (run_meta.get("targets") or ["-"])[0]
        self._hdr_target.setText(f"Target: {target}")
        self._hdr_runid.setText(f"Run ID: {run_meta.get('run_id', '-')}")
        started = run_meta.get("started_at", "-")
        ended = run_meta.get("ended_at", "-")
        duration = run_meta.get("duration_ms")
        dur_txt = f"{duration} ms" if duration is not None else "-"
        self._hdr_time.setText(f"Started: {started}    Ended: {ended}    Duration: {dur_txt}")
        status = run_meta.get("status", "-")
        exit_code = run_meta.get("exit_code", "-")
        self._hdr_status.setText(f"Status: {status} (exit {exit_code})")

        c = {k: counts.get(k, 0) for k in ("critical", "high", "medium", "low", "info")}
        self._hdr_counts.setText(
            f"Critical:{c['critical']}  High:{c['high']}  Medium:{c['medium']}  Low:{c['low']}  Info:{c['info']}"
        )

# Filter findings table by search term
    def _filter_findings_table(self, term: str):
        term_l = term.lower()
        rows = self.formattedTable.rowCount()
        cols = self.formattedTable.columnCount()
        for r in range(rows):
            visible = False
            if not term_l:
                visible = True
            else:
                for c in range(cols):
                    it = self.formattedTable.item(r, c)
                    if it and term_l in (it.text() or "").lower():
                        visible = True
                        break
            self.formattedTable.setRowHidden(r, not visible)

# Render findings table
    def _render_findings_table(self, findings: list):
        
        self.formattedTable.setRowCount(0)
        if not findings:
            return

        self.formattedTable.setRowCount(len(findings))
        for r, fi in enumerate(findings):
            vals = [
                fi.get("severity"), fi.get("title"), fi.get("asset"), fi.get("location"),
                str(fi.get("port") if fi.get("port") is not None else ""),
                fi.get("service"), fi.get("category"), fi.get("evidence"),
            ]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v if v is not None else "")
                if c == 0:  # let severity sort by string
                    it.setData(Qt.UserRole, (v or "").lower())
                self.formattedTable.setItem(r, c, it)
        self.formattedTable.resizeColumnsToContents()

    # ---------- Export dropdown glue (Reports tab) ----------

    def _get_current_run_context(self):
        """
        Returns the currently selected run-node context or None:
        {
            'run_dir': Path, 'exports_dir': Path, 'raw_log': Path,
            'tool': str, 'target': str, 'run_id': str
        }
        Uses the metadata we store on the tree nodes (Qt.UserRole).
        """
        from pathlib import Path

        item = self.report_tree.currentItem() if hasattr(self, "report_tree") else None
        data = (item.data(0, Qt.UserRole) if item else None) or {}

        if data.get("kind") == "run":
            human = data.get("human") or {}
            run_dir = Path(human.get("run_path", ""))
            tool    = (data.get("tool") or "").strip()
            target  = (data.get("target") or "").strip()
            run_id  = (data.get("run_id") or "").strip()

            if not run_dir or not run_dir.exists():
                QMessageBox.information(self, "Export", "Run folder not found.")
                return None

            raw_log = run_dir / f"raw_{tool}.log"
            if not raw_log.exists():
                raw_log = run_dir / f"raw_{tool.lower()}.log"

            exports_dir = run_dir / "exports"
            exports_dir.mkdir(parents=True, exist_ok=True)

            self._currentRunPaths = {
                "run_dir": run_dir,
                "exports_dir": exports_dir,
                "raw_log": raw_log,
                "tool": tool,
                "target": target,
                "run_id": run_id,
            }
            return self._currentRunPaths

        # Fallback to last-used context (after you previously opened a run)
        return getattr(self, "_currentRunPaths", None)


    def _connect_report_exports(self, btn):
        """
        Attach a dropdown to the Export… button.
        Saves into: All Reports/<target>/<tool>/<run_id>/exports/
        """
        menu = QMenu(btn)

        act_html = QAction("Export Raw → HTML", self)
        act_log  = QAction("Copy Raw → .log", self)
        act_csv  = QAction("Export Findings → CSV", self)
        act_json = QAction("Export Findings → JSON", self)

        act_html.triggered.connect(self._export_raw_to_html)
        act_log.triggered.connect(self._export_copy_raw)
        act_csv.triggered.connect(self._export_findings_csv)
        act_json.triggered.connect(self._export_findings_json)

        menu.addAction(act_html)
        menu.addAction(act_log)
        menu.addSeparator()
        menu.addAction(act_csv)
        menu.addAction(act_json)

        btn.setMenu(menu)


    def _export_copy_raw(self):
        """Copy raw_<tool>.log into exports/<tool>_<run_id>.log."""
        ctx = self._get_current_run_context()
        if not ctx:
            QMessageBox.information(self, "Export", "Please select a report first ❗")
            return
        try:
            out = export_copy_raw(
                raw_path=ctx["raw_log"],
                run_dir=ctx["run_dir"],
                tool=ctx["tool"],
                run_id=ctx["run_id"],
            )
            QMessageBox.information(self, "Export", f"Saved:\n{out}")
        except Exception as e:
            QMessageBox.critical(self, "Export", f"Failed: {e}")


    def _export_raw_to_html(self):
        """Wrap the raw text in a minimal HTML page and save to exports/<tool>_<run_id>.html."""
        ctx = self._get_current_run_context()
        if not ctx:
            QMessageBox.information(self, "Export", "Please select a report first ❗")
            return

        # Prefer what's already loaded in the Raw viewer; else read the file
        raw_text = ""
        try:
            if hasattr(self, "rawViewer") and getattr(self.rawViewer, "_raw_text", None):
                raw_text = self.rawViewer._raw_text
        except Exception:
            pass
        if not raw_text:
            try:
                raw_text = ctx["raw_log"].read_text(encoding="utf-8", errors="replace")
            except Exception:
                raw_text = ""

        if not raw_text:
            QMessageBox.warning(self, "Export", "No raw content available to export.")
            return

        try:
            out = export_raw_to_html(
                raw_text=raw_text,
                run_dir=ctx["run_dir"],
                tool=ctx["tool"],
                target=ctx["target"],
                run_id=ctx["run_id"],
            )
            QMessageBox.information(self, "Export", f"Saved:\n{out}")
        except Exception as e:
            QMessageBox.critical(self, "Export", f"Failed: {e}")


    def _export_findings_json(self):
        """Export current structured findings to exports/findings_<run_id>.json."""
        ctx = self._get_current_run_context()
        if not ctx:
            QMessageBox.information(self, "Export", "Please select a report first ❗")
            return
        model = getattr(self, "_currentRunModel", None) or {}
        findings = model.get("findings") or []
        try:
            out = export_findings_json(findings=findings, run_dir=ctx["run_dir"], run_id=ctx["run_id"])
            QMessageBox.information(self, "Export", f"Saved:\n{out}")
        except Exception as e:
            QMessageBox.critical(self, "Export", f"Failed: {e}")


    def _export_findings_csv(self):
        """Export current structured findings to exports/findings_<run_id>.csv."""
        ctx = self._get_current_run_context()
        if not ctx:
            QMessageBox.information(self, "Export", "Please select a report first ❗")
            return
        model = getattr(self, "_currentRunModel", None) or {}
        findings = model.get("findings") or []
        if not findings:
            QMessageBox.information(self, "Export", "No findings available for CSV export.")
            return
        try:
            out = export_findings_csv(findings=findings, run_dir=ctx["run_dir"], run_id=ctx["run_id"])
            QMessageBox.information(self, "Export", f"Saved:\n{out}")
        except Exception as e:
            QMessageBox.critical(self, "Export", f"Failed: {e}")

#PREPARE SCAN RESULT FOLDER
    def prepare_scan_folder(self, target):
        base_folder = "Scan Results"
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        # If 'target' is a list/tuple with multiple items → name folder as multi_<timestamp>
        # Else (single string or 1-item list) → <sanitized_target>_<timestamp>
        if isinstance(target, (list, tuple)) and len(target) > 1:
            folder_name = f"multi_{timestamp}"
        else:
            # Accept either a plain string or a single-item list/tuple
            t = target[0] if isinstance(target, (list, tuple)) else target

            # Sanitize target for filesystem safety
            safe_target = re.sub(r'[^\w.-]', '_', t)

            # Combine sanitized name + timestamp
            folder_name = f"{safe_target}_{timestamp}"

        scan_folder_path = os.path.join(base_folder, folder_name)

        os.makedirs(scan_folder_path, exist_ok=True)
        return scan_folder_path

#SETTINGS TAB
    def init_settings_tab(self, plugin_map):
            self.settings_tab = QWidget()
            layout = QVBoxLayout()

            header = QLabel("⚙ Settings")
            header.setAlignment(Qt.AlignCenter)
            header.setStyleSheet("font-size: 16px; color: #00d9ff; font-weight: bold; margin-bottom: 10px;")
            layout.addWidget(header)

            # Pass plugin_map to ScanProfileSettingsTab
            self.scan_profiles_widget = ScanProfileSettingsTab(plugin_map)
            layout.addWidget(self.scan_profiles_widget)

            # --- NEW: keep ui_main in sync with the Settings tab profile & custom args ---
            # Seed local state from the settings widget
            try:
                self.current_profile = (self.scan_profiles_widget.current_mode or "Normal").lower()
            except Exception:
                self.current_profile = "normal"

            # Seed flattened custom args cache from settings tab's nested store
            try:
                nested = getattr(self.scan_profiles_widget, "custom_args", {}) or {}
                self._custom_args_cache = {k: (v.get("args") if isinstance(v, dict) else "") for k, v in nested.items()}
            except Exception:
                self._custom_args_cache = {}

            # Listen for updates (safe connect: always disconnect first)
            self.scan_profiles_widget.profileChanged.connect(self._on_profile_changed_from_settings)
            self.scan_profiles_widget.customProfileSaved.connect(self._on_custom_profile_update)
            self.scan_profiles_widget.customProfileLoaded.connect(self._on_custom_profile_update)

            #Copyright
            layout.addWidget(get_copyright_label())

            self.theme_button = QPushButton("🌙 Switch to Light Theme")
            self.theme_button.clicked.connect(self.toggle_theme)
            layout.addWidget(self.theme_button)

            self.settings_tab.setLayout(layout)
            settings_index = self.tabs.addTab(self.settings_tab, QIcon("assets/settings.jpg"), "Settings")
            self.tabs.setTabToolTip(settings_index, "⚙️ Settings – Customize ReconCraft preferences")

# --- Profile bridge: receive active profile name from Settings tab ---
    def _on_profile_changed_from_settings(self, name: str):
            # Mirror the active profile (affects only command assembly)
            self.current_profile = (name or "normal").lower()
            # Optional one-line telemetry for clarity
            try:
                if hasattr(self, "output_console"):
                    self.output_console.append(f"🧩 Active profile: {name}")
            except Exception:
                pass

# --- Custom args bridge: receive flattened {tool_key: "args"} from Settings tab ---
    def _on_custom_profile_update(self, flat_map: dict):
            # Cache the current flattened custom args for runtime use
            try:
                self._custom_args_cache = dict(flat_map or {})
            except Exception:
                self._custom_args_cache = {}

# --- Resolve Custom args for a single tool/target (used only when profile == 'custom') ---
    def _resolve_custom_args_for_tool(self, tool_key: str, target: str):
            """
            Returns (args_str, skip_bool, note_for_log).
            Rules:
            - Empty or 'DISABLED' (case-insensitive) => skip this tool.
            - Expands {{target}} placeholder.
            """
            data = getattr(self, "_custom_args_cache", {}) or {}
            raw = (data.get(tool_key) or "").strip()
            if not raw or raw.upper() == "DISABLED":
                return ("", True, f"⚠ Custom disables: {tool_key} (skipped)")
            # Minimal templating
            args = raw.replace("{{target}}", target)
            return (args, False, f"Using Custom args for {tool_key}: {raw} -> {args}")

   

#TOGGLE THEME

    def toggle_theme(self):
        if self.theme_mode == "dark":
            self.set_light_theme()
            self.theme_button.setText("💻 Switch to Hackuuuurr Theme")
            self.theme_mode = "light"
        elif self.theme_mode == "light":
            self.set_hacker_theme()
            self.theme_button.setText("🌙 Switch to Dark Theme")
            self.theme_mode = "hacker"
        else:
            self.set_dark_theme()
            self.theme_button.setText("☀ Switch to Light Theme")
            self.theme_mode = "dark"


    def apply_current_theme_to_widget(self, widget):
        """Call this after adding new widgets/tabs to force them to match the selected theme."""
        if self.theme_mode == "dark":
            self.set_dark_theme(widget)
        elif self.theme_mode == "light":
            self.set_light_theme(widget)
        else:
            self.set_hacker_theme(widget)


#DARK THEME
    def set_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
            }
            QWidget {
                background-color: #1e1e1e;
                color: #ffffff;
            }
            QTabWidget::pane {
                border: 1px solid #444;
                background: #2d2d2d;
            }
            QTabBar::tab {
                background: #1e1e1e;
                color: #ffffff;
                padding: 8px;
                min-width: 110px;
                max-width: 110px;
                border: 1px solid #444;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 1px;
            }
            QTabBar::tab:selected {
                background: #3a3f44;
                font-weight: bold;
            }
            QTabBar::tab:hover {
                background: #50575e;
            }
            QLabel, QCheckBox, QPushButton, QListWidget, QLineEdit, QTextEdit {
                color: #ffffff;
                font-size: 14px;
            }
            QScrollArea {
                background-color: #232629;
                color: #fff;
                border: 1px solid #333;
                border-radius: 6px;
            }
            QPushButton {
                background-color: #3a3f44;
                border: 1px solid #555;
                padding: 6px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #50575e;
            }
            QLineEdit, QTextEdit, QListWidget {
                background-color: #252526;
                border: 1px solid #333;
                border-radius: 3px;
                padding: 4px;
            }
        """)


#HACKER THEME
    def set_hacker_theme(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #000000;
            }
            QWidget {
                background-color: #000000;
                color: #00ff00;
                font-family: Consolas, Courier New, monospace;
            }
            QTabWidget::pane {
                border: 1px solid #0f0;
                background: #010101;
            }
            QTabBar::tab {
                background: #000000;
                color: #00ff00;
                padding: 8px;
                min-width: 110px;
                max-width: 110px;
                border: 1px solid #0f0;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 1px;
            }
            QTabBar::tab:selected {
                background: #003300;
                font-weight: bold;
            }
            QTabBar::tab:hover {
                background: #004d00;
            }
            QLabel, QCheckBox, QPushButton, QListWidget, QLineEdit, QTextEdit {
                color: #00ff00;
                font-size: 14px;
                font-family: Consolas, Courier New, monospace;
            }
            QScrollArea {
                background-color: #040404;
                color: #00ff00;
                border: 1px solid #0f0;
                border-radius: 6px;
            }
            QPushButton {
                background-color: #001100;
                border: 1px solid #0f0;
                padding: 6px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #004d00;
            }
            QLineEdit, QTextEdit, QListWidget {
                background-color: #000000;
                border: 1px solid #0f0;
                border-radius: 3px;
                padding: 4px;
            }
        """)

#LIGHT THEME

    def set_light_theme(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f0f0;
            }
            QWidget {
                background-color: #f0f0f0;
                color: #000000;
            }
            QTabWidget::pane {
                border: 1px solid #aaa;
                background: #ffffff;
            }
            QTabBar::tab {
                background: #ffffff;
                color: #000000;
                padding: 8px;
                min-width: 110px;
                max-width: 110px;
                border: 1px solid #ccc;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background: #e0e0e0;
                font-weight: bold;
            }
            QTabBar::tab:hover {
                background: #d0d0d0;
            }
            QLabel, QCheckBox, QPushButton, QListWidget, QLineEdit, QTextEdit {
                color: #000000;
                font-size: 14px;
            }
            QScrollArea {
                background-color: #e0e0e0;  # or match your main bg
                border: none;
                color: inherit;
            }          
            QPushButton {
                background-color: #e0e0e0;
                border: 1px solid #999;
                padding: 6px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #d0d0d0;
            }
            QLineEdit, QTextEdit, QListWidget {
                background-color: #ffffff;
                border: 1px solid #ccc;
                border-radius: 3px;
                padding: 4px;
            }
        """)
class _SudoPromptBridge(QObject):
    ask = pyqtSignal(str)        # package name
    answered = pyqtSignal(object)  # (password_or_None, skip_this: bool, skip_all: bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Ensure UI work happens on the GUI thread
        self.ask.connect(self._on_ask, Qt.QueuedConnection)

    def _on_ask(self, pkg_name: str):
        dlg = SudoPromptDialog(pkg_name, parent=self.parent())
        dlg.setModal(True)
        dlg.exec_()  # Continue/Skip/etc set dlg.result_tuple
        self.answered.emit(dlg.result_tuple)