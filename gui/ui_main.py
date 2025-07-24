
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QTabWidget, QVBoxLayout,
    QPushButton, QTextEdit, QLineEdit, QLabel, QCheckBox,
    QListWidget, QGroupBox, QHBoxLayout, QToolButton, QProgressBar, QAction  
)
from core.scan_thread import ScanThread
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from core.controller import scan_targets
import datetime, os
from PyQt5.QtGui import QIcon
from cvss_calc import CVSSCalcTab

class ReconCraftUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ReconCraft GUI")
        self.setGeometry(450, 100, 1000, 900)


        #DEFAULT THEME DARK
        self.theme_mode = "dark"
        self.set_dark_theme()

        # Set the custom window icon
        self.setWindowIcon(QIcon("assets/reconcraft_icon.png"))
                
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.init_dashboard_tab()
        self.init_scan_tab()
        self.init_reports_tab()
        self.init_settings_tab()
        self.init_cvss_tab()

    def init_cvss_tab(self):
        self.cvss_tab = CVSSCalcTab()
        self.tabs.addTab(self.cvss_tab, QIcon("assets/cvss_icon.png"), "")
        index = self.tabs.indexOf(self.cvss_tab)
        self.tabs.setTabToolTip(index, "CVSS Calculator")
        self.tabs.setTabText(index, "CVSS Calc.")

#CLEAR OUTPUT AND RESET TOOLS
    def clear_output(self):
        self.output_console.clear()
        self.progress_bar.setValue(0)
        self.status_label.setText("Status: Idle")


    def reset_tools(self):
        for checkbox in self.tools.values():
            checkbox.setChecked(False)
        self.status_label.setText("Status: Select tools to run")    


#DASHBOARD TAB
    def init_dashboard_tab(self):
        dashboard_tab = QWidget()
        layout = QVBoxLayout()

        # Logo/Icon (if you have a PNG)
        logo = QLabel()
        logo.setPixmap(QIcon("assets/reconcraft_icon.png").pixmap(70, 70))
        logo.setAlignment(Qt.AlignCenter)
        layout.addWidget(logo)

        # Welcome headline
        header = QLabel("🧭 ReconCraft Dashboard")
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("font-size: 22px; color: #00d9ff; font-weight: bold; margin-top: 10px; margin-bottom: 10px;")
        layout.addWidget(header)

        # Stats area (use a group box for a card effect)
        stats_group = QGroupBox()
        stats_group.setStyleSheet("""
            QGroupBox {
                border: 2px solid #00d9ff;
                border-radius: 12px;
                margin-top: 8px;
                background-color: #222;
            }
        """)
        stats_layout = QVBoxLayout()

        self.total_scans_label = QLabel("Total Scans Run: 5")
        self.last_target_label = QLabel("Last Scan Target: example.com")
        self.last_tools_label = QLabel("Tools Used: Nmap, Subfinder")
        self.last_time_label = QLabel("Last Scan Time: 2025-06-03 10:30 AM")
        self.last_status_label = QLabel("Scan Status: ✅ Successful")

        for lbl in [
            self.total_scans_label,
            self.last_target_label,
            self.last_tools_label,
            self.last_time_label,
            self.last_status_label,
        ]:
            lbl.setStyleSheet("font-size: 16px; color: #fff; margin: 8px 4px;")
            stats_layout.addWidget(lbl)

        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)

        # Show last report file link (if any)
        self.last_report_label = QLabel("Last Report: <a href='#'>demo_report_01.txt</a>")
        self.last_report_label.setStyleSheet("font-size: 15px; color: #00ffae; margin: 12px 0 6px 0;")
        self.last_report_label.setOpenExternalLinks(False)
        layout.addWidget(self.last_report_label)

        # Fun tip or quick link
        tip = QLabel("💡 <i>Tip: Review CVSS scores for your findings in the 'CVSS Calc.' tab!</i>")
        tip.setStyleSheet("font-size: 14px; color: #33c3f0; margin-top: 12px;")
        tip.setAlignment(Qt.AlignCenter)
        layout.addWidget(tip)

        dashboard_tab.setLayout(layout)

        index = self.tabs.insertTab(0, dashboard_tab, QIcon("assets/home_icon.png"), "HOME")
        self.tabs.setTabToolTip(index, "Summary of Scans")

        # Added a method to update self.last_report_label on scan/report completion
        self.tabs.setTabText(index, "Dashboard")

#SCAN TAB
    def init_scan_tab(self):
        scan_tab = QWidget()
        layout = QVBoxLayout()

        header = QLabel("🛠 ReconCraft - Reconnaissance Interface")
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #00d9ff;")
        layout.addWidget(header)

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

        target_layout.addWidget(self.target_input)
        target_layout.addWidget(clear_btn)

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

        tool_layout = QVBoxLayout()
        self.tools = {
            "Nmap": QCheckBox("Nmap"),
            "Whois": QCheckBox("Whois"),
            "Subfinder": QCheckBox("Subfinder")
        }
        for tool in self.tools.values():
            tool_layout.addWidget(tool)

        tool_group.setLayout(tool_layout)
        layout.addWidget(tool_group)

        for tool in self.tools.values():
            tool_layout.addWidget(tool)
        tool_group.setLayout(tool_layout)
        layout.addWidget(tool_group)

        self.start_button = QPushButton("Start Scan")
        self.start_button.clicked.connect(self.launch_scan)
        layout.addWidget(self.start_button)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
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


        scan_tab.setLayout(layout)
        index = self.tabs.addTab(scan_tab, "Scan")
        self.tabs.setTabToolTip(index, "Run reconnaissance tools")
        
#RESET TOOLS
    def reset_tools(self):
        # Uncheck all tool checkboxes
        for checkbox in self.tools.values():
            checkbox.setChecked(False)

        # Clear the target input field
        self.target_input.clear()
  

# FOR STARTING & LAUNCHING SCAN
    def launch_scan(self):
        targets_input = self.target_input.text().strip()
        if not targets_input:
            self.output_console.append("❌ Please enter at least one target.")
            return

        # ✅ Parse multiple targets (comma-separated)
        targets = [t.strip() for t in targets_input.split(",") if t.strip()]
        if not targets:
            self.output_console.append("❌ Invalid target format.")
            return

        selected_plugins = [
            name.lower() for name, checkbox in self.tools.items()
            if checkbox.isChecked()
        ]

        if not selected_plugins:
            self.output_console.append("❌ Please select at least one tool.")
            return
        
         # ✅ Define base folder first
        base_folder = "Scan Results"
        os.makedirs(base_folder, exist_ok=True)

        # ✅ Create parent scan results folder
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        scan_folder = os.path.join(base_folder, f"scan_results_{timestamp}")
        os.makedirs(scan_folder, exist_ok=True)

        # ✅ Step 3: Create reports subfolder
        reports_folder = os.path.join(scan_folder, "reports")
        os.makedirs(reports_folder, exist_ok=True)

        # ✅ Step 4: Set report path for the thread
        self.report_path = scan_folder  # 👈 pass scan_folder, not just timestamp

        # ✅ Step 5: Start thread
        self.scan_thread = ScanThread(targets, selected_plugins, self.report_path)

        # ✅ Log starting message
        self.output_console.append(f"🚀 Starting scan on {len(targets)} target(s)...")
        self.output_console.append(f"📂 Scan folder created: {scan_folder}")

        # ✅ Start scan thread with multiple targets
        self.scan_thread = ScanThread(targets, selected_plugins, scan_folder)
        self.scan_thread.log_signal.connect(self.output_console.append)
        self.scan_thread.progress_signal.connect(self.progress_bar.setValue)
        self.scan_thread.status_signal.connect(self.update_status_label)
        self.scan_thread.finished_signal.connect(lambda: self.update_dashboard(', '.join(targets), selected_plugins))
        self.scan_thread.start()
        self.output_console.append("🔄 Scan in progress...")

#UPDATE STATUS LABEL
    def update_status_label(self, status):
        if status == "indeterminate":
            self.status_label.setText("Status: Initializing...")
        elif status == "done_success":
            self.status_label.setText("Status: ✅ Scan completed successfully.")
            self.progress_bar.setStyleSheet("QProgressBar::chunk { background-color: #00c853; }")
        elif status == "done_error":
            self.status_label.setText("Status: ❌ Scan completed with some errors.")
            self.progress_bar.setStyleSheet("QProgressBar::chunk { background-color: #ff1744; }")
        elif "Completed" in status:
            self.status_label.setText(status)


#DASHBOARD UPDATE
    def update_dashboard(self, target, plugins):
        self.total_scans_label.setText("Total Scans Run: updated dynamically")
        self.last_target_label.setText(f"Last Scan Target: {target}")
        self.last_tools_label.setText(f"Tools Used: {', '.join(plugins)}")
        now = datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p")
        self.last_time_label.setText(f"Last Scan Time: {now}")
        self.last_status_label.setText("Scan Status: ✅ Successful")



#THIS IS FOR REPORT TAB
    def init_reports_tab(self):
        reports_tab = QWidget()
        layout = QVBoxLayout()

        header = QLabel("📁 Reports")
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("font-size: 16px; color: #00d9ff; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(header)

        self.report_list = QListWidget()
        self.report_list.addItem("demo_report_01.txt")
        self.report_list.addItem("demo_report_02.txt")
        layout.addWidget(QLabel("Available Reports:"))
        layout.addWidget(self.report_list)

        reports_tab.setLayout(layout)
        index = self.tabs.addTab(reports_tab, "Reports")
        self.tabs.setTabToolTip(index, "View generated scan reports")

   
#PREPARE SCAN FOLDER
    def prepare_scan_folder(self):
        base_folder = "Scan Results"
        timestamp = datetime.now().strftime("scan_%Y-%m-%d_%H-%M-%S")
        scan_folder_path = os.path.join(base_folder, timestamp)

        os.makedirs(scan_folder_path, exist_ok=True)
        return scan_folder_path


#SETTINGS TAB
    def init_settings_tab(self):
        settings_tab = QWidget()
        layout = QVBoxLayout()

        header = QLabel("⚙ Settings")
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("font-size: 16px; color: #00d9ff; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(header)

        layout.addWidget(QLabel("Settings coming soon..."))

        self.theme_button = QPushButton("🌙 Switch to Light Theme")
        self.theme_button.clicked.connect(self.toggle_theme)
        layout.addWidget(self.theme_button)

        settings_tab.setLayout(layout)
        index = self.tabs.addTab(settings_tab, "Settings")
        self.tabs.setTabToolTip(index, "Adjust preferences and theme")

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


#DARK THEME
    def set_dark_theme(self):
        self.setStyleSheet("""
        QMainWindow {
            background-color: #1e1e1e;
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
