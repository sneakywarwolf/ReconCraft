from PyQt5.QtWidgets import QLabel
from PyQt5.QtCore import Qt
import platform, shutil, subprocess, sys, webbrowser, importlib, os, shlex, threading, queue

def get_copyright_label():
    label = QLabel('<a href="https://www.linkedin.com/in/nirmalchak/" style="color: #ffaa00; text-decoration: none;"><b>© Nirmal Chakraborty</b></a>')
    label.setOpenExternalLinks(True)
    label.setAlignment(Qt.AlignHCenter)
    label.setStyleSheet("""
        color: #ffaa00;
        font-size: 12px;
        font-weight: bold;
        margin-bottom: 2px;
        margin-top: 0px;
        margin: 0px;
        padding: 0px;
        font-family: Segoe UI, Arial, sans-serif;
    """)
    return label

# Utility function to run command attempting installations and stream output
def try_install_tool(command_or_tool, output_func, install_hint=None, install_url=None, max_attempts=2):
    """
    Attempts to install a tool using known methods.
    command_or_tool: A full shell command (str) or just the tool name.
    output_func: Function to emit output to UI or console.
    install_hint: Optional explicit hint like 'go', 'apt', etc. from plugin.
    install_url: Optional URL to use (especially for 'go' or 'git' installs).
    """
    system = platform.system().lower()
    is_shell_command = isinstance(command_or_tool, str) and " " in command_or_tool
    tool_bin = command_or_tool.strip().split()[0]

    # 🔹 Handle explicit full shell commands (streamed)
    if is_shell_command:
        output_func(f"⚙️ Executing: {command_or_tool}")
        try:
            rc = run_streamed(command_or_tool, output_func, shell=True)
            if rc == 0:
                output_func(f"✅ Successfully installed via: {command_or_tool}")
                return "installed"
            else:
                output_func(f"❌ Install failed (exit {rc}).")
                return "failed"
        except Exception as e:
            output_func(f"❌ Exception occurred: {e}")
            return "exception"

    # 🔹 Prepare fallback install methods (with sudo handling)
    methods = []

    is_linux = (system == "linux")
    is_darwin = (system == "darwin")
    is_windows = (system == "windows")

    # sudo/root detection (Linux only)
    is_root = False
    try:
        is_root = hasattr(os, "geteuid") and os.geteuid() == 0
    except Exception:
        is_root = False
    has_sudo = shutil.which("sudo") is not None

    # apt (Linux)
    if install_hint == "apt" or (is_linux and shutil.which("apt")):
        if is_root:
            cmd = ["apt", "install", "-y", tool_bin]
        elif has_sudo:
            cmd = ["sudo", "apt", "install", "-y", tool_bin]
        else:
            # No sudo + not root -> warn and still try non-sudo apt (likely to fail),
            # but at least we explain it.
            cmd = ["apt", "install", "-y", tool_bin]
            output_func(
                f"⚠️ Not running as root and 'sudo' not available. "
                f"APT install may fail.\n💡 Try: sudo apt install -y {tool_bin}"
            )
        methods.append(("apt", cmd))

    # brew (macOS)
    if install_hint == "brew" or (is_darwin and shutil.which("brew")):
        methods.append(("brew", ["brew", "install", tool_bin]))

    # choco (Windows)
    if install_hint == "choco" or (is_windows and shutil.which("choco")):
        methods.append(("choco", ["choco", "install", tool_bin, "-y"]))

    # go (use INSTALL_URL if provided; otherwise fallback with warning)
    if install_hint == "go" or shutil.which("go"):
        if install_url:
            go_path = install_url
        else:
            go_path = f"github.com/projectdiscovery/{tool_bin}/cmd/{tool_bin}@latest"
            output_func(f"⚠️ No INSTALL_URL for Go tool '{tool_bin}', assuming ProjectDiscovery path: {go_path}")
        methods.append(("go", ["go", "install", go_path]))

    # pip (cross-platform); add late so system package managers get first shot if hinted
    if install_hint == "pip" or install_hint is None:
        methods.append(("pip", [sys.executable, "-m", "pip", "install", tool_bin]))

    # git clone + build path (only if hinted and URL exists)
    if install_hint == "git" and install_url:
        # NOTE: This is shell chaining; streaming handles it.
        methods.append(("git", f"git clone {install_url} && cd {tool_bin} && sudo make install"))

    # 🔹 Try all methods, streamed
    for method_name, cmd in methods:
        for attempt in range(1, max_attempts + 1):
            if isinstance(cmd, list):
                pretty = " ".join(cmd)
            else:
                pretty = cmd  # string shell form (git chain)
            output_func(f"🔁 Attempt {attempt} via {method_name}: {pretty}")

            # Sudo prompt warning
            if (isinstance(cmd, list) and "sudo" in cmd) or (isinstance(cmd, str) and "sudo " in cmd):
                output_func(
                    "🔑 Sudo password might be required!\n"
                    f"💡 Command: {pretty}\n"
                    "👉 Check your terminal for a password prompt.\n"
                    "⚠️ ReconCraft may appear frozen until input is received.\n"
                )

            try:
                rc = run_streamed(cmd, output_func, shell=isinstance(cmd, str))
                if rc == 0:
                    output_func(f"✅ {tool_bin} installed successfully via {method_name}.")
                    return "installed"
                else:
                    output_func(f"❌ {method_name} failed (exit {rc}).")
            except Exception as e:
                output_func(f"❌ {method_name} exception: {e}")

    # 🔹 If all fail
    output_func(f"⚠️ All install methods failed for '{tool_bin}'.")
    output_func("🔍 Opening browser for manual instructions…")
    try:
        webbrowser.open(f"https://www.google.com/search?q=install+{tool_bin}+tool")
    except Exception:
        output_func("🌐 Could not open browser — please search manually.")
    return "manual"


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


def load_plugins():
    plugin_map = {}
    plugin_folder = "plugins"
    for file in os.listdir(plugin_folder):
        if file.endswith(".py") and not file.startswith("__"):
            plugin_name = file[:-3]
            module = importlib.import_module(f"plugins.{plugin_name}")
            plugin_map[plugin_name] = module
    return plugin_map