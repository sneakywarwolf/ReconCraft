"""
nmap - Port and service discovery using Nmap.
"""
def run(ip, raw_dir, base_dir, run_command, check_tool_installed, extract_cves):
    if not check_tool_installed("nmap"):
        print(f"[!] nmap not installed. Skipping {ip}.")
        return
    raw_file = f"{ip}_nmap.txt"
    output_path = run_command(["nmap", "-sV", ip], raw_file)
    extract_cves(output_path, ip)
    print(f"[✓] Nmap scan completed for {ip}. Results saved to {output_path}.")