from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QGridLayout, QTextEdit, QListWidget, QListWidgetItem, QApplication
)
from PyQt5.QtCore import Qt, QTimer, QSize
from PyQt5.QtGui import QIcon
from datetime import datetime
from cvss import CVSS3

class CVSSCalcTab(QWidget):
    def __init__(self):
        super().__init__()
        main_layout = QVBoxLayout()

        # Heading section
        heading_layout = QHBoxLayout()
        heading_icon = QLabel()
        heading_icon.setPixmap(QIcon("assets/cvss_icon.jpg").pixmap(130, 100))
        heading_icon.setStyleSheet("margin-right: 8px;")

        heading_text = QLabel("<b>CVSS v3.1 Calculator</b>")
        heading_text.setStyleSheet("font-size: 18px; text-align: center;")

        heading_layout.addStretch()
        heading_layout.addWidget(heading_icon)
        heading_layout.addWidget(heading_text)
        heading_layout.addStretch()

        main_layout.addLayout(heading_layout)
        grid_layout = QGridLayout()
        self.vector = {
            'AV': None, 'AC': None, 'PR': None, 'UI': None,
            'S': None, 'C': None, 'I': None, 'A': None
        }
        self.previous_scores = []

        self.metric_definitions = {
            'AV': [('Network', 'N'), ('Adjacent', 'A'), ('Local', 'L'), ('Physical', 'P')],
            'AC': [('Low', 'L'), ('High', 'H')],
            'PR': [('None', 'N'), ('Low', 'L'), ('High', 'H')],
            'UI': [('None', 'N'), ('Required', 'R')],
            'S': [('Unchanged', 'U'), ('Changed', 'C')],
            'C': [('None', 'N'), ('Low', 'L'), ('High', 'H')],
            'I': [('None', 'N'), ('Low', 'L'), ('High', 'H')],
            'A': [('None', 'N'), ('Low', 'L'), ('High', 'H')],
        }

        
        self.metric_labels = {
            'AV': ('Attack Vector', ''),
            'AC': ('Attack Complexity', ''),
            'PR': ('Privileges Required', ''),
            'UI': ('User Interaction', ''),
            'S': ('Scope', ''),
            'C': ('Confidentiality', ''),
            'I': ('Integrity', ''),
            'A': ('Availability', '')
        }

        self.metric_buttons = {}

        metrics = ['AV', 'AC', 'PR', 'UI', 'S', 'C', 'I', 'A']
        for i, metric in enumerate(metrics):
            group = self.create_metric_group(metric)
            row = i // 2
            col = i % 2
            grid_layout.addWidget(group, row, col)

        main_layout.addLayout(grid_layout)

        # Result display with copy icon button, severity label, and tooltip label
        result_layout = QVBoxLayout()

        # Score and vector in same line with copy button
        score_row = QHBoxLayout()
        self.result_label = QLabel("<b>Score:</b> -  <b>Vector:</b> CVSS:3.1/-")
        score_row.addWidget(self.result_label)

        self.copy_button = QPushButton()
        self.copy_button.setIcon(QIcon("assets/copy_icon.png"))
        self.copy_button.setIconSize(QSize(24, 24))
        self.copy_button.setFixedSize(36, 36)
        self.copy_button.setStyleSheet("border: none; padding: 0px;")
        self.copy_button.setToolTip("Copy Score + Vector")
        self.copy_button.clicked.connect(self.copy_vector)
        score_row.addWidget(self.copy_button)

        result_layout.addLayout(score_row)

        self.severity_label = QLabel("<b>Severity:</b> -")
        self.severity_label.setStyleSheet("color: white; padding: 2px 6px; border-radius: 4px;")
        result_layout.addWidget(self.severity_label, alignment=Qt.AlignLeft)

        self.copied_label = QLabel("Copied ✅")
        self.copied_label.setStyleSheet("color: green")
        self.copied_label.hide()
        result_layout.addWidget(self.copied_label, alignment=Qt.AlignRight)

        main_layout.addLayout(result_layout)

        
        self.setLayout(main_layout)

    def create_metric_group(self, metric):
        label, tooltip = self.metric_labels[metric]
        group = QGroupBox(label)
        group.setToolTip(tooltip)
        layout = QHBoxLayout()
        buttons = []

        tooltip_texts = {
            'AV': {
                'N': 'Worst: [Add description for Network]',
                'A': 'Worse: [Add description for Adjacent]',
                'L': 'Bad: [Add description for Local]',
                'P': 'Bad: [Add description for Physical]'
            },
            'AC': {
                'L': 'Worst: [Add description for Low]',
                'H': 'Bad: [Add description for High]'
            },
            'PR': {
                'N': 'Worst: [Add description for None]',
                'L': 'Worse: [Add description for Low]',
                'H': 'Bad: [Add description for High]'
            },
            'UI': {
                'N': 'Worst: [Add description for None]',
                'R': 'Bad: [Add description for Required]'
            },
            'S': {
                'U': 'Bad: [Add description for Unchanged]',
                'C': 'Worst: [Add description for Changed]'
            },
            'C': {
                'N': 'Good: [Add description for None]',
                'L': 'Bad: [Add description for Low]',
                'H': 'Worst: [Add description for High]'
            },
            'I': {
                'N': 'Good: [Add description for None]',
                'L': 'Bad: [Add description for Low]',
                'H': 'Worst: [Add description for High]'
            },
            'A': {
                'N': 'Good: [Add description for None]',
                'L': 'Bad: [Add description for Low]',
                'H': 'Worst: [Add description for High]'
            }
        }

        for name, code in self.metric_definitions[metric]:
            # styling of icons for vectors
            icon_path = f"assets/icons/{metric}_{code}.png" if metric and code else None
            btn = QPushButton(name)
            btn.setToolTip(f"<div style='background-color: #fff8dc; padding: 4px; border-radius: 6px;'>" + tooltip_texts.get(metric, {}).get(code, '') + "</div>")
            if icon_path:
                btn.setIcon(QIcon(icon_path))
            btn.setIconSize(QSize(32, 32))
            btn.setText(name)
            btn.setCheckable(True)
            # Color-coding based on severity and meaning
            if metric == 'AV':
                color_map = {'N': '#ff9999', 'A': '#ffcc66', 'L': '#ffff99', 'P': '#ccffcc'}
            elif metric == 'AC':
                color_map = {'L': '#ff9999', 'H': '#ccffcc'}
            elif metric == 'PR':
                color_map = {'N': '#ff9999', 'L': '#ffcc66', 'H': '#ccffcc'}
            elif metric == 'UI':
                color_map = {'N': '#ff9999', 'R': '#ccffcc'}
            elif metric == 'S':
                color_map = {'U': '#ccffcc', 'C': '#ff9999'}
            elif metric in ['C', 'I', 'A']:
                color_map = {'H': '#ff9999', 'L': '#ffcc66', 'N': '#ccffcc'}
            else:
                color_map = {}

            bg = color_map.get(code, '#e0e0e0')
            btn.setStyleSheet(f"QPushButton:hover {{ background-color: #f0f0f0; }} QPushButton:checked {{ background-color: {bg}; color: black; }}")
            btn.clicked.connect(lambda checked, m=metric, c=code: self.update_metric(m, c))
            layout.addWidget(btn)
            buttons.append(btn)

        self.metric_buttons[metric] = buttons
        group.setLayout(layout)
        return group

    def update_metric(self, metric, code):
        self.vector[metric] = code
        for btn in self.metric_buttons[metric]:
            selected = btn.text()[0] == code or (btn.text() == 'None' and code == 'N')
            btn.setChecked(selected)
        self.update_score()

    def update_score(self):
        if None in self.vector.values():
            self.result_label.setText("Score: -\nVector: Incomplete")
            return

        vector_str = "CVSS:3.1/" + "/".join([f"{k}:{v}" for k, v in self.vector.items()])
        try:
            cvss = CVSS3(vector_str)
            score = cvss.scores()[0]  # Base Score
            self.current_score = score
            self.current_vector = vector_str
            self.result_label.setText(f"<b>Score:</b> {score}<br><b>Vector:</b> {vector_str}")
            if score >= 9.0:
                severity = ('Critical', '#800000')
            elif score >= 7.0:
                severity = ('High', '#ff0000')
            elif score >= 4.0:
                severity = ('Medium', '#ffcc00')
            else:
                severity = ('Low', '#33cc33')

            self.severity_label.setText(f"<b>Severity:</b> {severity[0]}")
            self.severity_label.setStyleSheet(f"background-color: {severity[1]}; color: white; padding: 2px 6px; border-radius: 4px;")
        except Exception as e:
            self.result_label.setText(f"Invalid vector: {e}")

    def copy_vector(self):
        clipboard = QApplication.clipboard()
        if hasattr(self, 'current_vector') and hasattr(self, 'current_score'):
            clipboard.setText(f"{self.current_score} | {self.current_vector}")
            self.copied_label.show()
            QTimer.singleShot(1500, self.copied_label.hide)

    def save_score(self):
        if hasattr(self, 'current_vector'):
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            item = QListWidgetItem(f"{self.current_vector} | {now}")
            self.score_list.addItem(item)

    def reset_all(self):
        for key in self.vector:
            self.vector[key] = None
            for btn in self.metric_buttons[key]:
                btn.setChecked(False)
        self.result_label.setText("Score: -\nVector: CVSS:3.1/-")
        self.current_vector = ""
        self.current_score = ""
