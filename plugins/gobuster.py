"""
Gobuster - Directory brute-forcing using wordlists.
"""
REQUIRED_TOOL = "gobuster"


def run(ip, raw_dir, base_dir, run_command, check_tool_installed, extract_cves):
    if not check_tool_installed("gobuster"):
        print(f"[!] gobuster not installed. Skipping {ip}.", True)
        return
    raw_file = f"{ip}_gobuster.txt"
    output_path = run_command([
        "gobuster", "dir",
        "-u", f"http://{ip}",
        "-w", "/usr/share/wordlists/dirb/common.txt",
        "-t", "10"
    ], raw_file)