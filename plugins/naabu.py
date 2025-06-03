def run(ip, raw_dir, base_dir, run_command, check_tool_installed, extract_cves):
    if check_tool_installed("naabu"):
        run_command(f"naabu -host {ip} -silent", f"{ip}_naabu.txt")