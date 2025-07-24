"""
testssl - SSL/TLS scanner for discovering cryptographic weaknesses.
"""
def run(ip, raw_dir, base_dir, run_command, check_tool_installed, extract_cves):
    if not check_tool_installed("testssl.sh"):
        print(f"[!] testssl.sh not installed. Skipping {ip}.")
        return
    raw_file = f"{ip}_testssl.txt"
    output_path = run_command(["testssl.sh", ip], raw_file)
    extract_cves(output_path, ip)
    print(f"[✓] testssl scan completed for {ip}. Results saved to {output_path}.")