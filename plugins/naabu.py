"""
Naabu - Fast port scanner focused on TCP ports.
"""
REQUIRED_TOOL = "naabu"


def run(ip, raw_dir, base_dir, run_command, check_tool_installed, extract_cves):
    if not check_tool_installed("naabu"):
        print(f"[!] naabu not installed. Skipping {ip}.", True)
        return
    raw_file = f"{ip}_naabu.txt"
    output_path = run_command([
        "naabu", "-host", ip, "-top-ports", "100"
    ], raw_file)