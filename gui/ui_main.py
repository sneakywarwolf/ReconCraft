# ReconCraft by Nirmal Chakraborty
# Copyright (c) 2025. All rights reserved.
# See LICENSE for details.



from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QTabWidget, QVBoxLayout,
    QPushButton, QTextEdit, QLineEdit, QLabel, QCheckBox,
    QListWidget, QGroupBox, QHBoxLayout, QToolButton, QProgressBar,
    QGridLayout, QListWidgetItem, QTreeWidget, QTreeWidgetItem, QFileDialog
)
from core.scan_thread import ScanThread
from PyQt5.QtCore import Qt, pyqtSignal, QUrl, QSize
import datetime, os, sys
from datetime import datetime
from PyQt5.QtGui import QIcon, QDesktopServices
from core.cvss_calc import CVSSCalcTab
import re, shutil, subprocess, platform, webbrowser, csv
try:
    import pandas as pd
except ImportError:
    pd = None
from pathlib import Path
from gui.flow_layout import FlowLayout
import importlib.util
from core.tools_utils import is_tool_installed
from gui.settings_profiles_tab import ScanProfileSettingsTab
from gui.common_widgets import try_install_tool, load_plugins, get_copyright_label
from gui.tool_worker import ToolCheckWorker, ToolInstallWorker

# This is the main UI class for the ReconCraft application
class ReconCraftUI(QMainWindow):
    
    def __init__(self):
        super().__init__()

        self.setWindowTitle("ReconCraft GUI")
        self.setGeometry(450, 100, 1000, 900)   

        self.plugin_map = load_plugins()  # load plugins here

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
        #self.init_settings_tab()            
        self.init_settings_tab(self.plugin_map)   # call to initialize the settings tab   
        self.init_reports_tab()             # call to initialize the reports tab
        self.init_cvss_tab()                # call to initialize the CVSS Calculator tab

        self.refresh_plugins()  # Refreshing plugins on startup
  

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

#ABORT SCAN
    def abort_scan(self):
        # Cancel install if running
        if hasattr(self, 'installer_worker') and self.installer_worker.isRunning():
            try:
                self.installer_worker.cancel()
                self.output_console.append("⏹️ Installation cancel requested.")
            except Exception:
                pass

        # Existing scan abort logic
        if hasattr(self, 'scan_thread') and self.scan_thread.isRunning():
            self.scan_thread.terminate()  # you already had this
            self.output_console.append("⚠️ Scan aborted by user.")

        # Reset UI state
        self.abort_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_label.setText("Idle")


# HANDLE SCAN FINISHED
    def handle_scan_finished(self, status):
        if status == "done_success":
            # Green
            self.progress_bar.setStyleSheet("QProgressBar::chunk {background-color: #28a745;}")
        else:
            # Red
            self.progress_bar.setStyleSheet("QProgressBar::chunk {background-color: #dc3545;}")
        
        self.update_status_label(status)
        self.output_console.append("📌 Scan finished.")


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


        header = QLabel("🛠 ReconCraft - Reconnaissance Interface")
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


        tool_group = QGroupBox("Select Tools to Run")
        tool_group.setStyleSheet("""
            QGroupBox {
                color: #FFA500;               /* Title text color */
                background-color: #222;       /* Background color */
                font-weight: bold;           /* This makes the title text bold */
                border: 2px solid #00FFFF;    /* Border color */
                border-radius: 5px;
                margin-top: 10px;
            }
            QGroupBox:title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px;
            }
        """)

        # 🔄 Clear any existing tools to avoid duplication
        self.tools = {}

        # Create a FlowLayout for the tools
        self.tool_container_layout = FlowLayout()

        # Dynamically load and render checkboxes
        self.init_dynamic_tool_checkboxes(self.tool_container_layout)

        # Set layout to tool_group and add it to the main layout
        tool_group.setLayout(self.tool_container_layout)
        layout.addWidget(tool_group)

        # --- Plugin Actions Row (Refresh Plugins + Check Tools) ---
        plugin_action_layout = QHBoxLayout()

        self.refresh_button = QPushButton("🔄 Refresh Plugins")
        self.refresh_button.setToolTip("Reload plugins and update tool list")
        self.refresh_button.clicked.connect(self.refresh_plugins)
        plugin_action_layout.addWidget(self.refresh_button)

        self.check_tools_btn = QPushButton("Check Tools")
        self.check_tools_btn.setToolTip("Check if all loaded tools are installed")
        self.check_tools_btn.clicked.connect(self.check_tools_installed)
        self.check_tools_btn.setIcon(QIcon("assets/check_tools_icon.png"))
        plugin_action_layout.addWidget(self.check_tools_btn)

        plugin_action_layout.addStretch()  # Optional: pushes buttons to the left

        # Add the row to the main Scan tab layout, just above Start/Abort buttons
        layout.addLayout(plugin_action_layout)


        #SIZE for Refresh, Check Tools buttons
        self.refresh_button.setFixedHeight(40)
        self.refresh_button.setFixedWidth(500)

        self.check_tools_btn.setFixedHeight(40)
        self.check_tools_btn.setFixedWidth(500)

        # Install Missing Tools Button
        install_tools_layout = QHBoxLayout()
        self.install_tools_btn = QPushButton("Install Missing Tools")
        self.install_tools_btn.setToolTip("Try to install all missing tools automatically")
        self.install_tools_btn.setIcon(QIcon("assets/install_icon.png"))   # <-- Add your icon here
        self.install_tools_btn.clicked.connect(self.install_missing_tools)
        install_tools_layout.addWidget(self.install_tools_btn)
        layout.addLayout(install_tools_layout)

        #ADDING START & ABORT BUTTON
        # Start Scan Button
        self.start_button = QPushButton("▶ Start Scan")
        self.start_button.clicked.connect(self.launch_scan)

        # Abort Scan Button
        self.abort_button = QPushButton("⛔ Abort Scan/Cancel Install")
        self.abort_button.setEnabled(False)
        self.abort_button.clicked.connect(self.abort_scan)

        # Set START and ABORT button sizes
        self.start_button.setFixedHeight(40)
        self.start_button.setFixedWidth(500)
        self.abort_button.setFixedHeight(40)
        self.abort_button.setFixedWidth(500)

        # Create horizontal layout for both buttons
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.start_button)   # <-- add Start Scan
        button_layout.addWidget(self.abort_button)   # <-- add Abort Scan

        # Add this button layout to the main layout
        layout.addLayout(button_layout)


        self.check_result_label = QLabel("")
        self.check_result_label.setAlignment(Qt.AlignCenter)
        self.check_result_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #ff5555;")
        layout.addWidget(self.check_result_label)

        #Progress Bar, Status Label, and Output Console
        self.progress_bar = QProgressBar()
        self.progress_bar.setAlignment(Qt.AlignCenter)
        self.progress_bar.setValue(0)
        
        # Force bold font!
        font = self.progress_bar.font()
        font.setBold(True)
        font.setPointSize(9)  # Or any size you prefer
        self.progress_bar.setFont(font)
        
        self.progress_bar.setVisible(True)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Status: Idle")
        layout.addWidget(self.status_label)

        self.output_console = QTextEdit()
        self.output_console.setReadOnly(True)
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
        button_layout.setContentsMargins(0, 0, 0, 0)

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
        
        self.progress_bar.setStyleSheet("QProgressBar::chunk { background: #00bfff; }")
        self.check_result_label.setText("")  # (optional) clears old label

        
        self.output_console.clear()
        self.progress_bar.setValue(0)
        self.statusBar().showMessage("Starting tool check...")

        self.check_worker = ToolCheckWorker(self.plugins, is_tool_installed)
        self.check_worker.progress.connect(self.progress_bar.setValue)
        self.check_worker.status.connect(self.statusBar().showMessage)
        self.check_worker.output.connect(self.output_console.append)
        self.check_worker.finished.connect(self._on_check_tools_finished)
        self.check_worker.start()

    
    # Installing missing tools    
    def install_missing_tools(self):
        if not hasattr(self, "missing_tools") or not self.missing_tools:
            self.statusBar().showMessage("No missing tools found. Please run check tools first.")
            return

        # ✅ Clear console & reset progress
        self.output_console.clear()
        self.progress_bar.setValue(0)
        self.statusBar().showMessage("🔧 Starting installation of missing tools...")

        # ✅ Create ToolInstallWorker with updated plugin logic
        self.installer_worker = ToolInstallWorker(
            self.missing_tools,
            self.plugins,
            try_install_tool  # This should be your core installation function
        )

        # ✅ Connect signals for real-time feedback
        self.installer_worker.output.connect(self.output_console.append)
        self.installer_worker.status.connect(self.statusBar().showMessage)
        self.installer_worker.progress.connect(self.progress_bar.setValue)
        self.installer_worker.finished.connect(self._on_install_tools_finished)

        # ✅ Start the worker thread
        self.installer_worker.start()

    # This method is called when the ToolInstallWorker finishes installing tools
    # It updates the status bar and clears the missing tools list
    def _on_install_tools_finished(self, *args):
        self.statusBar().showMessage("✅ Tool installation completed.")
        self.output_console.append("✅ All missing tools (if any) have been handled.")   

       
    # This method is called when the ToolCheckWorker finishes checking tools
    def _on_check_tools_finished(self, missing_tools):
        self.missing_tools = missing_tools
        if missing_tools:
            self.check_result_label.setText("Some tools missing.")
            self.check_result_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #ff5555;")  # red
            self.progress_bar.setStyleSheet("QProgressBar::chunk { background: #ff5555; }")  # red bar
            
        else:
            self.check_result_label.setText("All tools are installed.")
            self.check_result_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #55ff55;")  # green
            self.progress_bar.setStyleSheet("QProgressBar::chunk { background: #55ff55; }")  # green bar
            
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
        This should be called after ScanThread has initialized plugins.
        """
        dummy_thread = ScanThread([], [], "")  # Only used for tool discovery
        all_tools = dummy_thread.get_all_tools()

        self.tool_checkboxes = {}  # Store for retrieval

        for tool in all_tools:
            checkbox = QCheckBox(tool)
            checkbox.setStyleSheet("color: #fff; font-size: 14px; margin: 4px;")
            tool_container_layout.addWidget(checkbox)
            self.tool_checkboxes[tool] = checkbox

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


# FOR STARTING & LAUNCHING SCAN
    def launch_scan(self):
        self.abort_button.setEnabled(True)
        targets_input = self.target_input.text().strip()
        if not targets_input:
            self.output_console.append("❌ Please enter at least one target.")
            return

        # ✅ Parse multiple targets (comma-separated)
        targets = [t.strip() for t in targets_input.split(",") if t.strip()]
        if not targets:
            self.output_console.append("❌ Invalid target format.")
            return

        ## Get selected tools
        selected_plugins = self.get_selected_tools()

        if not selected_plugins:
            self.output_console.append("❌ Please select at least one tool.")
            return
        
        # Prepare scan folder using target[0]
        scan_folder = self.prepare_scan_folder(targets[0])
        if not scan_folder:
            self.output_console.append("❌ Failed to prepare scan directory.")
            return

        # ✅ Log starting message
        self.output_console.append(f"🚀 Starting scan on {len(targets)} target(s)...")
        self.output_console.append(f"📂 Scan folder created: {scan_folder}")

        # 🔁 Reset status and progress bar for new scan
        self.status_label.setText("Status: ⏳ Scan in progress...")
        self.progress_bar.setValue(0)
        
        # ✅ Get selected scan mode from settings tab
        selected_mode = self.scan_profiles_widget.current_mode


        # ✅ Passing it to ScanThread, STARTING SCAN
        self.scan_thread = ScanThread(targets, selected_plugins, scan_folder, selected_mode)

        self.scan_thread.log_signal.connect(self.output_console.append)
        self.scan_thread.progress_signal.connect(self.progress_bar.setValue)
        self.scan_thread.status_signal.connect(self.update_status_label)
        self.scan_thread.finished_signal.connect(lambda: self.update_dashboard(', '.join(targets), selected_plugins))
        self.scan_thread.start()
        self.output_console.append("🔄 Scan in progress...")
        
        #This ensures the scan status (done_success or done_error) is passed to the handle_scan_finished()
        self.scan_thread.finished_signal.connect(self.handle_scan_finished)


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
            elif "Completed" in status:
                self.status_label.setText(status)


#DASHBOARD UPDATE
    def update_dashboard(self, target, plugins):
        self.total_scans_label.setText("Total Scans Run: updated dynamically")
        self.last_target_label.setText(f"Last Scan Target: {target}")
        self.last_tools_label.setText(f"Tools Used: {', '.join(plugins)}")
        now = datetime.now().strftime("%Y-%m-%d %I:%M %p")
        self.last_time_label.setText(f"Last Scan Time: {now}")
        self.last_status_label.setText("Scan Status: ✅ Successful")

# Display last report link
    def display_report(self, item):
        file_path = item.data(Qt.UserRole)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                self.report_viewer.setPlainText(content)
        except Exception as e:
            self.report_viewer.setPlainText(f"⚠️ Failed to load report:\n{str(e)}")

# Method to populate QTreeWidget
    def load_report_tree(self):
        from pathlib import Path

        self.report_tree.clear()
        base_dir = Path("Scan Results")
        if not base_dir.exists():
            return

        def add_items_recursively(parent, path):
            for item in path.iterdir():
                child = QTreeWidgetItem([item.name])
                child.setData(0, Qt.UserRole, str(item))
                parent.addChild(child)
                if item.is_dir():
                    add_items_recursively(child, item)

        for folder in base_dir.iterdir():
            if folder.is_dir():
                root = QTreeWidgetItem([folder.name])
                root.setData(0, Qt.UserRole, str(folder))
                self.report_tree.addTopLevelItem(root)
                add_items_recursively(root, folder)


# Handler for clicking file
    def display_report_from_tree(self, item, column):
        file_path = item.data(0, Qt.UserRole)
        if Path(file_path).is_file():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    self.report_viewer.setPlainText(content)
            except Exception as e:
                self.report_viewer.setPlainText(f"Error loading file:\n{e}")

#LOAD REPORT FILES
    def load_report_files(self):
        """
        Loads all readable reports from 'Scan Results/' and populates the QListWidget.
        """
        scan_results_dir = os.path.join(os.getcwd(), "Scan Results")

        if not os.path.exists(scan_results_dir):
            self.report_list.addItem("⚠️ 'Scan Results' folder not found.")
            self.report_list.setEnabled(False)
            return

        # Add the refresh button to the report tab layout
        self.refresh_button = QPushButton()
        self.refresh_button.setIcon(QIcon("assets/refresh.png"))
        self.refresh_button.setFixedSize(32, 32)
        self.refresh_button.clicked.connect(self.load_report_files)

        
        self.report_list.clear()

        for root, dirs, files in os.walk(scan_results_dir):
            for file in files:
                if file.endswith((".txt", ".log", ".html")):
                    full_path = os.path.join(root, file)
                    display_name = os.path.relpath(full_path, scan_results_dir)
                    
                    item = QListWidgetItem(display_name)
                    item.setToolTip(full_path)
                    item.setData(Qt.UserRole, full_path)
                    self.report_list.addItem(item)

        if self.report_list.count() == 0:
            self.report_list.addItem("ℹ️ No reports found in 'Scan Results'.")
            self.report_list.setEnabled(False)
        else:
            self.report_list.setEnabled(True)


#THIS IS FOR REPORT TAB
    def init_reports_tab(self):
        
        # This defines the actual report tab.
        
        self.report_tab = QWidget()
        layout = QVBoxLayout(self.report_tab)
        layout.addWidget(get_copyright_label())

        # Title bar with refresh
        title = QLabel("📁 Reports")
        title.setAlignment(Qt.AlignLeft)
        title.setStyleSheet("font-size: 18px; color: #00d9ff; font-weight: bold; margin-bottom: 6px;")

        refresh_btn = QPushButton()
        refresh_btn.setIcon(QIcon("assets/refresh_icon.png"))
        refresh_btn.setToolTip("Refresh Report List")
        refresh_btn.setFixedSize(32, 32)
        refresh_btn.setStyleSheet("border: none;")

        refresh_btn.clicked.connect(self.load_report_tree)

        title_layout = QHBoxLayout()
        title_layout.addWidget(title)
        title_layout.addStretch()
        title_layout.addWidget(refresh_btn)
        layout.addLayout(title_layout)

        layout.addSpacing(5)

        # Horizontal layout for browser + viewer
        content_layout = QHBoxLayout()

        self.report_tree = QTreeWidget()
        self.report_tree.setHeaderLabel("Scan Reports")
        self.report_tree.setMinimumWidth(300)
        self.report_tree.itemClicked.connect(self.display_report_from_tree)
        content_layout.addWidget(self.report_tree)
        
        # Set custom stylesheet for the report tree
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
    """)


        self.report_viewer = QTextEdit()
        self.report_viewer.setReadOnly(True)
        self.report_viewer.setStyleSheet("font-family: Consolas, monospace; font-size: 14px; background-color: #111; color: #00ff88;")
        content_layout.addWidget(self.report_viewer)

        layout.addLayout(content_layout)

        # Important: load the tree, not list
        self.load_report_tree()

        self.report_tab.setLayout(layout)
        report_index = self.tabs.addTab(self.report_tab, QIcon("assets/report.png"), "Reports")
        self.tabs.setTabToolTip(report_index, "📊 Reports – View generated scan reports")



   
#PREPARE SCAN RESULT FOLDER
    def prepare_scan_folder(self, target):
        base_folder = "Scan Results"
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        # Sanitize target for filesystem safety
        safe_target = re.sub(r'[^\w.-]', '_', target)

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
        layout.addWidget(get_copyright_label())

        # Pass plugin_map to ScanProfileSettingsTab
        self.scan_profiles_widget = ScanProfileSettingsTab(plugin_map)
        layout.addWidget(self.scan_profiles_widget)

        self.theme_button = QPushButton("🌙 Switch to Light Theme")
        self.theme_button.clicked.connect(self.toggle_theme)
        layout.addWidget(self.theme_button)

        self.settings_tab.setLayout(layout)
        settings_index = self.tabs.addTab(self.settings_tab, QIcon("assets/settings.jpg"), "Settings")
        self.tabs.setTabToolTip(settings_index, "⚙️ Settings – Customize ReconCraft preferences")

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