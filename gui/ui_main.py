
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QTabWidget, QVBoxLayout,
    QPushButton, QTextEdit, QLineEdit, QLabel, QCheckBox,
    QListWidget, QGroupBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from cvss_calc import CVSSCalcTab

class ReconCraftUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ReconCraft GUI")
        self.setGeometry(100, 100, 800, 600)

        # Set the custom window icon
        self.setWindowIcon(QIcon("assets/reconcraft_icon.png"))

        self.dark_mode = True
        self.set_dark_theme()

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

    def init_dashboard_tab(self):
        dashboard_tab = QWidget()
        layout = QVBoxLayout()

        header = QLabel("🧭 Dashboard")
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("font-size: 18px; color: #00d9ff; font-weight: bold;")
        layout.addWidget(header)

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
            lbl.setStyleSheet("font-size: 14px; color: #ffffff; margin: 6px 0;")
            layout.addWidget(lbl)

            # Add tab with icon only
        index = self.tabs.insertTab(0, dashboard_tab, QIcon("assets/home_icon.png"), "HOME")

            # Add tooltip for hover
        self.tabs.setTabToolTip(index, "Summary of Scans")

    def init_scan_tab(self):
        scan_tab = QWidget()
        layout = QVBoxLayout()

        header = QLabel("🛠 ReconCraft - Reconnaissance Interface")
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #00d9ff;")
        layout.addWidget(header)

        self.target_input = QLineEdit()
        self.target_input.setPlaceholderText("Enter IP, Domain, or URL")
        self.target_input.setStyleSheet("margin-bottom: 10px;")
        layout.addWidget(QLabel("Target:"))
        layout.addWidget(self.target_input)

        tool_group = QGroupBox("Select Tools to Run")
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

        self.start_button = QPushButton("▶ Start Scan (Demo Only)")
        layout.addWidget(self.start_button)

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
        
        scan_tab.setLayout(layout)
        index = self.tabs.addTab(scan_tab, "Scan")
        self.tabs.setTabToolTip(index, "Run reconnaissance tools")


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


    def toggle_theme(self):
        if self.dark_mode:
            self.set_light_theme()
            self.theme_button.setText("🌙 Switch to Dark Theme")
            self.dark_mode = False
        else:
            self.set_dark_theme()
            self.theme_button.setText("☀ Switch to Light Theme")
            self.dark_mode = True

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
