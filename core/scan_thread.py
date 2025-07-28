from PyQt5.QtCore import QThread, pyqtSignal
import subprocess
import os
import concurrent.futures
import importlib

class ScanThread(QThread):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    status_signal = pyqtSignal(str)

    def __init__(self, targets, tools, report_root_folder):
        super().__init__()
        self.targets = targets
        self.tools = tools
        self.report_root_folder = report_root_folder
        self.total_tasks = len(targets) * len(tools)
        self.completed_tasks = 0
        self.plugin_map = {}
        self.load_plugins()

    def load_plugins(self):
        plugin_folder = "plugins"
        for file in os.listdir(plugin_folder):
            if file.endswith(".py") and not file.startswith("__"):
                plugin_name = file[:-3]
                module = importlib.import_module(f"plugins.{plugin_name}")
                self.plugin_map[plugin_name] = module.run

    def get_all_tools(self):
        """
        Returns the list of dynamically loaded plugin tools only.
        """
        return list(self.plugin_map.keys())


    def run(self):
        
        error_occurred = False  # ✅ Track if any tool fails
        os.makedirs(self.report_root_folder, exist_ok=True)
        self.log_signal.emit(f"⚙ Launching tools on {len(self.targets)} target(s)...")

        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = []
            for target in self.targets:
                target_folder = os.path.join(self.report_root_folder, target.replace(".", "_"))
                os.makedirs(target_folder, exist_ok=True)

                for tool in self.tools:
                    futures.append(executor.submit(self.run_tool_and_save, tool, target, target_folder))

            for future in concurrent.futures.as_completed(futures):
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
                progress_percent = int((self.completed_tasks / self.total_tasks) * 100)
                self.log_signal.emit(result_msg)
                self.progress_signal.emit(progress_percent)

        # ✅ Emit final status based on error flag
        if error_occurred:
            self.finished_signal.emit("done_error")
        else:
            self.finished_signal.emit("done_success")

    def run_tool_and_save(self, tool, target, target_folder):
        try:
            output = self.run_tool(tool, target)
            file_path = os.path.join(target_folder, f"{tool}_{target}.txt")

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(output)

            return f"✅ {tool} finished for {target}. Output saved to: {file_path}", False  # No error
        except subprocess.CalledProcessError as e:
            return f"❌ {tool} failed for {target}: {e.output}", True
        except Exception as e:
            return f"❌ {tool} crashed for {target}: {str(e)}", True

    def run_tool(self, tool, target):
        # ⚙️ Plugin-based tools only (built-in tools removed)
        if tool in self.plugin_map:
            raw_dir = os.path.join(self.report_root_folder, "raw")
            os.makedirs(raw_dir, exist_ok=True)
            self.plugin_map[tool](
                ip=target,
                raw_dir=raw_dir,
                base_dir=self.report_root_folder,
                run_command=self.run_command,
                check_tool_installed=self.check_tool_installed,
                extract_cves=self.extract_cves,
            )
            return f"🔌 Plugin {tool} executed for {target}"
        else:
            raise Exception(f"Tool '{tool}' is not supported.")


    # 🔧 Helper methods passed into plugins
    def run_command(self, cmd_list, outfile_name):
        out_path = os.path.join(self.report_root_folder, "raw", outfile_name)
        with open(out_path, "w", encoding="utf-8") as f:
            subprocess.run(cmd_list, stdout=f, stderr=subprocess.STDOUT, check=True)
        return out_path

    def check_tool_installed(self, tool_name):
        return any(
            os.access(os.path.join(path, tool_name), os.X_OK)
            for path in os.environ["PATH"].split(os.pathsep)
        )

    def extract_cves(self, filepath, ip):
        # Optional placeholder for plugin CVE parsing
        pass
