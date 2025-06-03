def run(ip, raw_dir, base_dir, run_command, check_tool_installed, extract_cves):
    if check_tool_installed("amass"):
        run_command(f"amass enum -passive -d {ip}", f"{ip}_amass.txt")