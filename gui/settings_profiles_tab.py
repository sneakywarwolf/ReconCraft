# ReconCraft by Nirmal Chakraborty
# Copyright (c) 2025. All rights reserved.
# See LICENSE for details.

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QRadioButton, QButtonGroup, QPushButton,
    QScrollArea, QFormLayout, QLabel, QLineEdit, QPlainTextEdit, QSpinBox, QToolButton, QMessageBox,
    QDialog
)
from PyQt5.QtCore import Qt, pyqtSignal
import webbrowser, subprocess, os, json


class ScanProfileSettingsTab(QWidget):
    # Let the main UI listen for profile changes and custom profile updates
    profileChanged      = pyqtSignal(str)   # e.g., "Aggressive" | "Normal" | "Passive" | "Custom"
    customProfileSaved  = pyqtSignal(dict)  # flattened: {tool_key: "args"}
    customProfileLoaded = pyqtSignal(dict)  # flattened: {tool_key: "args"}

    def __init__(self, plugin_map, parent=None):
        super().__init__(parent)
        self.plugin_map = plugin_map   # {plugin_name: plugin_module}
        self.profiles = ['Aggressive', 'Normal', 'Passive', 'Custom']
        self.current_mode = "Normal"
        self.schemas = self.get_plugin_schemas()
        self.profile_configs = self.build_default_profiles()

        # Custom args store (persists across profile switches)
        # Shape: {plugin: {"args": "..."}}
        self.custom_args = {plugin: self.profile_configs["Normal"][plugin].copy() for plugin in self.schemas}

        # UI build
        self.init_ui()

        # On load, try to pre-load any saved custom profile silently
        self._load_custom_profile_silent()

    # ---------- Helpers: schema & defaults ----------

    def get_plugin_schemas(self):
        schemas = {}
        for name, module in self.plugin_map.items():
            schemas[name] = getattr(module, "CONFIG_SCHEMA", {
                "args": {
                    "type": "str",
                    "label": "Arguments",
                    "default": ""
                }
            })
        return schemas

    def build_default_profiles(self):
        profiles = {mode: {} for mode in self.profiles}
        for plugin, module in self.plugin_map.items():
            plugin_args = getattr(module, "DEFAULT_ARGS", {})
            for mode in self.profiles:
                # Use plugin's default, or blank if not set
                arg = plugin_args.get(mode, "")
                profiles[mode][plugin] = {"args": arg}
        return profiles

    # ---------- UI ----------

    def init_ui(self):
        self.layout = QVBoxLayout(self)
        self.setLayout(self.layout)

        # --- Max Concurrent Scans control ---
        concurrency_row = QHBoxLayout()
        concurrency_label = QLabel("⚡ Max Concurrent Scans:")
        self.concurrency_spin = QSpinBox()
        self.concurrency_spin.setRange(1, 8)
        self.concurrency_spin.setValue(2)  # Default value
        concurrency_row.addWidget(concurrency_label)
        concurrency_row.addWidget(self.concurrency_spin)
        concurrency_row.addStretch()
        self.layout.addLayout(concurrency_row)

        # --- Resource usage/warning label ---
        self.resource_warning = QLabel()
        self.resource_warning.setStyleSheet("color: #ffaa00; font-size: 13px; font-style: italic;")
        self.layout.addWidget(self.resource_warning)

        self.concurrency_spin.valueChanged.connect(self.update_resource_warning)
        self.update_resource_warning()  # Set initial text

        # Profile radios
        self.profile_group = QButtonGroup(self)
        self.profile_radios = {}
        profile_row = QHBoxLayout()
        for prof in self.profiles:
            rb = QRadioButton(prof)
            self.profile_group.addButton(rb)
            self.profile_radios[prof] = rb
            profile_row.addWidget(rb)
        self.profile_radios['Normal'].setChecked(True)
        self.layout.addLayout(profile_row)

        # --------- Scrollable Tools Config Area ---------
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.tools_area_layout = QFormLayout(self.scroll_content)
        self.scroll_content.setLayout(self.tools_area_layout)
        self.scroll.setWidget(self.scroll_content)
        self.layout.addWidget(self.scroll)

        self.tool_fields = {}  # {plugin: {field: widget}}

        # Save / Load Custom Profile buttons (shown only in Custom)
        buttons_row = QHBoxLayout()
        buttons_row.addStretch(1)

        self.save_btn = QPushButton("Save Custom Profile")
        self.save_btn.hide()
        self.save_btn.clicked.connect(self.save_custom_profile)
        buttons_row.addWidget(self.save_btn)

        self.load_btn = QPushButton("Load Custom Profile")
        self.load_btn.hide()
        self.load_btn.clicked.connect(self.load_custom_profile)
        buttons_row.addWidget(self.load_btn)

        buttons_row.addStretch(1)
        self.layout.addLayout(buttons_row)

        # Connect radios
        for prof in self.profiles:
            self.profile_radios[prof].toggled.connect(self.on_profile_change)

        self.on_profile_change()  # Initial fill

    def update_resource_warning(self):
        val = self.concurrency_spin.value()
        if val == 1:
            self.resource_warning.setText("🕓 Sequential scan: slow but minimal resource usage.")
        elif val <= 3:
            self.resource_warning.setText("😊 Balanced performance for most VMs (recommended).")
        elif val <= 4:
            self.resource_warning.setText("🏎️ Your VM should be turbocharged! 🏎️   Monitor usage!!🚦")
        else:
            self.resource_warning.setText(
                "⚠️ High concurrency may slow down or freeze your VM! Use only on powerful systems."
            )

    # ---------- Profile switching & field building ----------

    def on_profile_change(self):
        selected = None
        for prof, rb in self.profile_radios.items():
            if rb.isChecked():
                selected = prof
                break

        if getattr(self, "_last_mode_emitted", None) == selected:
            return
        self._last_mode_emitted = selected
        
        self.current_mode = selected

        # Only show Save/Load when Custom is active
        custom_active = (selected == "Custom")
        self.save_btn.setVisible(custom_active)
        self.load_btn.setVisible(custom_active)

        # Pick config to SHOW (do not overwrite self.custom_args when leaving Custom)
        if selected == "Custom":
            config = self.custom_args
        else:
            config = self.profile_configs[selected]

        # Clear and rebuild tool fields
        for i in reversed(range(self.tools_area_layout.count())):
            item = self.tools_area_layout.itemAt(i)
            if item and item.widget():
                item.widget().deleteLater()
        self.tool_fields = {}

        # Build all plugin fields with help button (emoji)
        for plugin, fields in self.schemas.items():
            self.tool_fields[plugin] = {}
            plugin_label = QLabel(f"<b>{plugin}</b>")
            # ORANGE color for tool/plugin name
            plugin_label.setStyleSheet("color: #ff9900; font-weight: bold; font-size: 15px;")
            self.tools_area_layout.addRow(plugin_label)

            for field, opts in fields.items():
                value = config.get(plugin, {}).get(field, opts.get("default", ""))

                # Choose field type
                if opts["type"] == "str":
                    w = QPlainTextEdit() if opts.get("multiline") else QLineEdit()
                    if isinstance(w, QPlainTextEdit):
                        w.setPlainText(str(value))
                        w.setFixedHeight(28)
                    else:
                        w.setText(str(value))
                    w.setStyleSheet("""
                        border: 2px solid #00d9ff;
                        border-radius: 3px;
                    """)
                    # Editable only in Custom
                    w.setReadOnly(not custom_active)
                    # Connect change to capture into self.custom_args
                    if isinstance(w, QLineEdit):
                        w.textChanged.connect(self.on_any_arg_changed)
                    else:
                        w.textChanged.connect(self.on_any_arg_changed)  # QPlainTextEdit has textChanged(str)
                elif opts["type"] == "int":
                    w = QSpinBox()
                    w.setMinimum(0)
                    w.setMaximum(10000)
                    w.setValue(int(value) if str(value).isdigit() else opts.get("default", 0))
                    w.setStyleSheet("""
                        border: 2px solid #00d9ff;
                        border-radius: 3px;
                    """)
                    w.setReadOnly(not custom_active)
                    w.valueChanged.connect(self.on_any_arg_changed)
                else:
                    w = QLineEdit(str(value))
                    w.setReadOnly(not custom_active)
                    w.setStyleSheet("""
                        border: 2px solid #00d9ff;
                        border-radius: 3px;
                    """)
                    w.textChanged.connect(self.on_any_arg_changed)

                arg_row = QHBoxLayout()
                arg_label = QLabel(opts.get("label", field))
                arg_row.addWidget(arg_label)
                arg_row.addWidget(w)

                # Help Button with Emoji
                help_btn = QToolButton()
                help_btn.setText("📝")
                help_btn.setToolTip("Open docs/help page")
                plugin_mod = self.plugin_map[plugin]
                doc_url = getattr(plugin_mod, "INSTALL_URL", "")
                if not doc_url:
                    doc_url = f"https://www.google.com/search?q={plugin}+usage"
                help_btn.clicked.connect(lambda _, url=doc_url: webbrowser.open(url))
                arg_row.addWidget(help_btn)

                row_widget = QWidget()
                row_widget.setLayout(arg_row)
                self.tools_area_layout.addRow(row_widget)
                self.tool_fields[plugin][field] = w

        # If Custom was selected, auto-load saved profile so fields reflect disk
        if custom_active:
            self._apply_custom_args_to_fields(self.custom_args)

        # Let parent know which profile is active
        self.profileChanged.emit(self.current_mode)

    # ---------- Tool help ----------

    def show_tool_help(self, tool_name):
        help_text = ""
        success = False
        # Step 1: Try man page
        try:
            help_text = subprocess.check_output(['man', tool_name], stderr=subprocess.STDOUT, universal_newlines=True, timeout=5)
            if len(help_text.strip()) > 10:
                success = True
        except Exception:
            pass
        # Step 2: Try -h
        if not success:
            try:
                help_text = subprocess.check_output([tool_name, '-h'], stderr=subprocess.STDOUT, universal_newlines=True, timeout=5)
                if len(help_text.strip()) > 10:
                    success = True
            except Exception:
                pass
        # Step 3: Try --help
        if not success:
            try:
                help_text = subprocess.check_output([tool_name, '--help'], stderr=subprocess.STDOUT, universal_newlines=True, timeout=5)
                if len(help_text.strip()) > 10:
                    success = True
            except Exception:
                pass

        if success:
            # Show in a scrollable dialog
            dlg = QDialog(self)
            dlg.setWindowTitle(f"Help: {tool_name}")
            dlg.resize(900, 650)
            layout = QVBoxLayout()
            label = QLabel(f"<b>Help for <code>{tool_name}</code>:</b>")
            layout.addWidget(label)
            edit = QPlainTextEdit()
            edit.setPlainText(help_text)
            edit.setReadOnly(True)
            layout.addWidget(edit)
            btn = QPushButton("Close")
            btn.clicked.connect(dlg.accept)
            layout.addWidget(btn)
            dlg.setLayout(layout)
            dlg.exec_()
        else:
            # Step 4: Open Google search for manual
            url = f"https://www.google.com/search?q={tool_name}+manual"
            webbrowser.open(url)

    # ---------- Custom args change tracking ----------

    def on_any_arg_changed(self, *_):
        # Switch to Custom mode if not already
        if self.current_mode != "Custom":
            self.profile_radios["Custom"].setChecked(True)
            self.current_mode = "Custom"
            self.profileChanged.emit(self.current_mode)

        # Update custom_args with current values from the visible fields
        for plugin, fields in self.tool_fields.items():
            for field, widget in fields.items():
                if isinstance(widget, QLineEdit):
                    value = widget.text()
                elif isinstance(widget, QPlainTextEdit):
                    value = widget.toPlainText()
                elif isinstance(widget, QSpinBox):
                    value = widget.value()
                else:
                    # Fallback
                    try:
                        value = widget.text()
                    except Exception:
                        value = ""
                self.custom_args.setdefault(plugin, {})[field] = value

    # ---------- Save / Load Custom profile ----------

    def _custom_profile_path(self) -> str:
        # Single JSON file next to your project; adjust if you prefer a config dir
        return os.path.join(os.getcwd(), "custom_scan_profile.json")

    def _flatten_args(self, data: dict) -> dict:
        """Return {tool: args_str} from a nested map {tool:{'args':...}}."""
        flat = {}
        for tool, inner in (data or {}).items():
            # only 'args' field participates in runtime commands
            flat[tool] = (inner.get("args") if isinstance(inner, dict) else "")
        return flat

    def _apply_custom_args_to_fields(self, data: dict):
        """Push current self.custom_args into visible widgets when Custom is active."""
        for plugin, fields in self.tool_fields.items():
            src = (data or {}).get(plugin, {})
            for field, widget in fields.items():
                val = src.get(field, "")
                if isinstance(widget, QLineEdit):
                    widget.setText(str(val))
                elif isinstance(widget, QPlainTextEdit):
                    widget.setPlainText(str(val))
                elif isinstance(widget, QSpinBox):
                    try:
                        widget.setValue(int(val))
                    except Exception:
                        pass

    def _collect_fields_into_custom(self):
        """Refresh self.custom_args from the visible widgets."""
        for plugin, fields in self.tool_fields.items():
            for field, widget in fields.items():
                if isinstance(widget, QLineEdit):
                    value = widget.text()
                elif isinstance(widget, QPlainTextEdit):
                    value = widget.toPlainText()
                elif isinstance(widget, QSpinBox):
                    value = widget.value()
                else:
                    try:
                        value = widget.text()
                    except Exception:
                        value = ""
                self.custom_args.setdefault(plugin, {})[field] = value

    def _load_custom_profile_silent(self):
        """Internal: load if exists, no message boxes."""
        try:
            with open(self._custom_profile_path(), "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                # Expect nested shape {tool:{'args':...}}
                self.custom_args.update(loaded)
        except Exception:
            pass

    def save_custom_profile(self):
        """Persist the current Custom arguments to disk and emit a flattened map."""
        # Ensure we capture current on-screen edits before saving
        self._collect_fields_into_custom()
        try:
            with open(self._custom_profile_path(), "w", encoding="utf-8") as f:
                json.dump(self.custom_args, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "Success", "Custom profile saved!")
            self.customProfileSaved.emit(self._flatten_args(self.custom_args))
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to save profile: {e}")

    def load_custom_profile(self):
        """Load saved Custom arguments from disk into memory and into the visible fields."""
        try:
            with open(self._custom_profile_path(), "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if not isinstance(loaded, dict):
                loaded = {}
        except FileNotFoundError:
            loaded = {}
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load profile: {e}")
            loaded = {}

        # Update store and fields (only shown if Custom is active)
        self.custom_args = loaded or {}
        if self.current_mode == "Custom":
            self._apply_custom_args_to_fields(self.custom_args)

        self.customProfileLoaded.emit(self._flatten_args(self.custom_args))