def run(ip, raw_dir, base_dir, run_command, check_tool_installed, extract_cves):
    if check_tool_installed("nuclei"):
        run_command(f"nuclei -u {ip} -silent", f"{ip}_nuclei.txt")