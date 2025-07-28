"""
DirBuster - Directory brute-force using Java GUI or CLI mode.
"""
REQUIRED_TOOL = "dirbuster"


def run(ip, raw_dir, base_dir, run_command, check_tool_installed, extract_cves):
    if not check_tool_installed("dirbuster"):
        print(f"[!] dirbuster not installed. Skipping {ip}.", True)
        return
    raw_file = f"{ip}_dirbuster.txt"
    output_path = run_command([
        "java", "-jar", "/path/to/DirBuster-*.jar",
        "-u", f"http://{ip}",
        "-l", "/usr/share/wordlists/dirbuster/directory-list-2.3-medium.txt"
    ], raw_file)