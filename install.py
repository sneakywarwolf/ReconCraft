import os
import shutil
import subprocess
import sys
import platform

tools = {
    "nmap": {"linux": "nmap", "windows": "Nmap.Nmap"},
    "naabu": {"linux": "naabu", "windows": None},
    "nuclei": {"linux": "nuclei", "windows": None},
    "nikto": {"linux": "nikto", "windows": None},
    "amass": {"linux": "amass", "windows": None},
    "searchsploit": {"linux": "exploitdb", "windows": None}
}

missing_tools = []

def is_tool_installed(tool):
    return shutil.which(tool) is not None

def install_on_linux(package_name):
    try:
        subprocess.run(["sudo", "apt-get", "install", "-y", package_name], check=True)
        print(f"[✓] Installed {package_name} on Linux.")
    except subprocess.CalledProcessError:
        print(f"[!] Failed to install {package_name} on Linux. Please install it manually.")

def install_on_windows(package_name):
    if package_name:
        try:
            subprocess.run(["winget", "install", "-e", "--id", package_name], check=True)
            print(f"[✓] Installed {package_name} on Windows using winget.")
        except subprocess.CalledProcessError:
            print(f"[!] Failed to install {package_name} via winget. Please install it manually.")
    else:
        print(f"[!] No known Windows package mapping. Please install this tool manually.")

def check_and_install_tools():
    system_platform = platform.system().lower()
    print(f"[+] Detected OS: {system_platform.capitalize()}")
    for tool, pkg_map in tools.items():
        if is_tool_installed(tool):
            print(f"[✓] {tool} is already installed.")
        else:
            print(f"[!] {tool} is missing.")
            missing_tools.append(tool)
            package_name = pkg_map.get(system_platform)
            if system_platform == "linux" and package_name:
                install_on_linux(package_name)
            elif system_platform == "windows":
                install_on_windows(package_name)
            else:
                print(f"[!] Auto-install not supported for {tool} on {system_platform}. Please install it manually.")

def check_testssl():
    if os.path.isfile("./testssl.sh/testssl.sh"):
        print("[✓] testssl.sh is present.")
    else:
        print("[!] testssl.sh not found. Cloning...")
        try:
            subprocess.run(["git", "clone", "https://github.com/drwetter/testssl.sh.git"], check=True)
            print("[✓] testssl.sh cloned successfully.")
        except subprocess.CalledProcessError:
            print("[!] Failed to clone testssl.sh. Please install it manually.")

def install_python_requirements():
    if os.path.isfile("requirements.txt"):
        print("[+] Installing Python requirements...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)
    else:
        print("[!] requirements.txt not found. Skipping.")

def summary():
    if missing_tools:
        print("\n[!] The following tools were not installed automatically:")
        for tool in missing_tools:
            print(f"    - {tool}")
    else:
        print("\n[✓] All tools installed or already present.")

if __name__ == "__main__":
    print("=== ReconCraft Python Installer ===")
    check_and_install_tools()
    check_testssl()
    install_python_requirements()
    summary()