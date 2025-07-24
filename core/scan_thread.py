from PyQt5.QtCore import QThread, pyqtSignal
import subprocess
import os
import concurrent.futures

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

    def run(self):
        os.makedirs(self.report_root_folder, exist_ok=True)
        self.log_signal.emit(f"⚙ Launching tools on {len(self.targets)} target(s)...")

        error_occurred = False  # ✅ Track if any tool fails

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
        if tool == "nmap":
            return subprocess.check_output(["nmap", "-Pn", target], text=True, stderr=subprocess.STDOUT)

        elif tool == "whois":
            return subprocess.check_output(["whois", target], text=True, stderr=subprocess.STDOUT)

        elif tool == "subfinder":
            return subprocess.check_output(["subfinder", "-d", target, "-silent"], text=True, stderr=subprocess.STDOUT)

        else:
            raise Exception(f"Tool '{tool}' is not supported.")
