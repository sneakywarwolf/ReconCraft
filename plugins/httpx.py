"""
HTTPX - HTTP probing for web servers and IPs.
"""
REQUIRED_TOOL = "httpx"

def run(ip, raw_dir, base_dir, run_command, check_tool_installed, extract_cves):
    if not check_tool_installed("httpx"):
        print(f"[!] httpx not installed. Skipping {ip}.", True)
        return
    raw_file = f"{ip}_httpx.txt"
    output_path = run_command([
        "echo", ip, "|", "httpx", "-silent"
    ], raw_file)