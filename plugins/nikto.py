def run(ip, raw_dir, base_dir, run_command, check_tool_installed, extract_cves):
    if check_tool_installed("nikto"):
        output = run_command(f"nikto -host {ip}", f"{ip}_nikto.txt")
        extract_cves(output, ip)