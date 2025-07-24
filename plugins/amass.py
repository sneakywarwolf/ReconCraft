"""
amass - Subdomain enumeration tool.
"""
def run(ip, raw_dir, base_dir, run_command, check_tool_installed, extract_cves):
    if not check_tool_installed("amass"):
        print(f"[!] amass not installed. Skipping {ip}.")
        return
    raw_file = f"{ip}_amass.txt"
    output_path = run_command(["amass", "enum", "-d", ip], raw_file)
    # Amass does not output CVEs, so no extract_cves here
    print(f"[✓] amass scan completed for {ip}. Results saved to {output_path}.")