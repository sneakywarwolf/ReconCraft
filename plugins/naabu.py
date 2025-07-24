"""
naabu - Fast port scanner.
"""
def run(ip, raw_dir, base_dir, run_command, check_tool_installed, extract_cves):
    if not check_tool_installed("naabu"):
        print(f"[!] naabu not installed. Skipping {ip}.")
        return
    raw_file = f"{ip}_naabu.txt"
    output_path = run_command(["naabu", "-host", ip], raw_file)
    # naabu doesn't output CVEs; no extract_cves needed
    print(f"[✓] naabu scan completed for {ip}. Results saved to {output_path}.")