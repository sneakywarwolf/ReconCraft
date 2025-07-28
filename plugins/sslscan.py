"""
Sslscan - Scans SSL services and ciphers supported by the server.
"""
REQUIRED_TOOL = "sslscan"


def run(ip_or_domain, raw_dir, base_dir, run_command, check_tool_installed, extract_cves):
    plugin_name = "sslscan"

    # ✅ Step 1: Check if tool is installed
    if not check_tool_installed("sslscan"):
        print(f"[!] sslscan is not installed. Skipping {ip_or_domain}.", True)
        return

    # ✅ Step 2: Set output file path
    raw_file = f"{ip_or_domain}_{plugin_name}.txt"

    # ✅ Step 3: Run the command
    cmd = ["sslscan"] + [] + [ip_or_domain]
    output_path = run_command(cmd, raw_file)

    # ✅ Step 4: Optionally extract CVEs
    extract_cves(output_path, ip_or_domain)
