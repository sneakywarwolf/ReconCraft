def run(ip, raw_dir, base_dir, run_command, check_tool_installed, extract_cves):
    if check_tool_installed("nmap"):
        output = run_command(f"nmap -sC -sV -oN - {ip}", f"{ip}_nmap.txt")
        extract_cves(output, ip)