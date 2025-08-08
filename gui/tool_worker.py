# ReconCraft by Nirmal Chakraborty
# Copyright (c) 2025. All rights reserved.
# See LICENSE for details.

from PyQt5.QtCore import QThread, pyqtSignal
import shutil, webbrowser


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
            tool_bin = getattr(plugin_module, "REQUIRED_TOOL", plugin_name)
            script_path = getattr(plugin_module, "SCRIPT_PATH", None)

            if not self.is_tool_installed(tool_bin, script_path):
                self.output.emit(f"❌ {plugin_name} (requires `{tool_bin}`) is NOT installed.")
                missing_tools.append(plugin_name)
            else:
                self.output.emit(f"✅ {plugin_name} (requires `{tool_bin}`) is installed.")

            self.status.emit(f"Checking {plugin_name}...")
            self.progress.emit(int(100 * (i + 1) / total))

        if missing_tools:
            self.output.emit("\n⚠️ Missing: " + ", ".join(missing_tools))
        else:
            self.output.emit("\n🎉 All dynamically loaded tools are installed!")

        self.status.emit("Check Tools Complete.")
        self.finished.emit(missing_tools)

# ToolInstallWorker handles the installation of missing tools.
# Enhanced ToolInstallWorker class with structured install strategies

class ToolInstallWorker(QThread):
    progress = pyqtSignal(int)        # For progress bar
    status = pyqtSignal(str)          # For status bar
    output = pyqtSignal(str)          # For output console
    finished = pyqtSignal(list)       # Emit missing tools at end

    def __init__(self, missing_tools, plugins, try_install_tool_func, log_path=None):
        super().__init__()
        self.missing_tools = missing_tools
        self.plugins = plugins
        self.try_install_tool_func = try_install_tool_func
        self._cancel = False

        self.install_strategies = {
            "apt": self.install_with_apt,
            "brew": self.install_with_brew,
            "pip": self.install_with_pip,
            "go": self.install_with_go,
            "git": self.install_with_git,
            "manual": self.install_manual,
        }

    def cancel(self):
        self._cancel = True

    def run(self):
        total = len(self.missing_tools)
        if total == 0:
            self.output.emit("🎉 All tools are already installed!")
            self.status.emit("✅ All tools are installed.")
            self.finished.emit([])
            return

        for i, plugin_name in enumerate(self.missing_tools):

            if self._cancel:
                self.status.emit("Installation cancelled.")
                self.output.emit("⏹️ User cancelled installation.")
                break

            try:
                plugin = self.plugins[plugin_name]
                tool_bin = getattr(plugin, "REQUIRED_TOOL", plugin_name)
                install_hint = getattr(plugin, "INSTALL_HINT", "manual").lower()
                install_url = getattr(plugin, "INSTALL_URL", "")

                self.status.emit(f"⚙ Installing {plugin_name}...")
                self.output.emit(f"🔽 Installing {plugin_name} ({tool_bin}) using method: {install_hint}")

                # choose the strategy and delegate ONCE (do NOT call try_install_tool_func directly here)
                install_method = self.install_strategies.get(install_hint, self.install_manual)
                result_msg = install_method(tool_bin, install_url)

                self.output.emit(f"📦 {plugin_name} ➜ {result_msg}")
                progress_percent = int((i + 1) / total * 100)
                self.progress.emit(progress_percent)

            except Exception as e:
                self.output.emit(f"❌ Error installing {plugin_name}: {str(e)}")
                self.status.emit(f"⚠️ Installation failed for {plugin_name}")

        self.output.emit("✅ All installations attempted.")
        self.status.emit("Tool installation complete.")
        self.finished.emit([])

    # ---------- STRATEGY FUNCTIONS ----------

    def install_with_apt(self, tool, url):
        # delegate to the smart installer (handles sudo/root detection itself)
        return self.try_install_tool_func(
            tool, self.output.emit, install_hint="apt", install_url=url
        )

    def install_with_brew(self, tool, url):
        return self.try_install_tool_func(
            tool, self.output.emit, install_hint="brew", install_url=url
        )

    def install_with_pip(self, tool, url):
        return self.try_install_tool_func(
            tool, self.output.emit, install_hint="pip", install_url=url
        )

    def install_with_go(self, tool, url):
        # delegate; try_install_tool will normalize https:// and add @latest if missing
        return self.try_install_tool_func(
            tool, self.output.emit, install_hint="go", install_url=url
        )

    def install_with_git(self, tool, url):
        # delegate; try_install_tool will chain git clone/build if URL is provided
        return self.try_install_tool_func(
            tool, self.output.emit, install_hint="git", install_url=url
        )

    def install_manual(self, tool, url):
        self.output.emit(f"⚠️ Manual installation required for: {tool}")
        if url:
            self.output.emit(f"📎 Visit: {url}")
        else:
            self.output.emit(f"🔍 Please search: {tool} install instructions.")
        return "Manual installation required."




