"""
nikto - Web server vulnerability scanner.
"""
def run(ip, raw_dir, base_dir, run_command, check_tool_installed, extract_cves):
    if not check_tool_installed("nikto"):
        print(f"[!] nikto not installed. Skipping {ip}.")
        return
    raw_file = f"{ip}_nikto.txt"
    output_path = run_command(["nikto", "-h", ip], raw_file)
    extract_cves(output_path, ip)
    print(f"[✓] Nikto scan completed for {ip}. Results saved to {output_path}.")