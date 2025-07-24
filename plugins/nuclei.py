"""
nuclei - Fast vulnerability scanner using custom templates.
"""
def run(ip, raw_dir, base_dir, run_command, check_tool_installed, extract_cves):
    if not check_tool_installed("nuclei"):
        print(f"[!] nuclei not installed. Skipping {ip}.")
        return
    raw_file = f"{ip}_nuclei.txt"
    output_path = run_command(["nuclei", "-u", ip], raw_file)
    extract_cves(output_path, ip)
    print(f"[✓] Nuclei scan completed for {ip}. Results saved to {output_path}.")