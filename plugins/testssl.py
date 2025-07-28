"""
Testssl - Performs detailed SSL/TLS analysis.
"""
REQUIRED_TOOL = "testssl.py"


def run(ip_or_domain, raw_dir, base_dir, run_command, check_tool_installed, extract_cves):
    plugin_name = "testssl"

    # ✅ Step 1: Check if tool is installed
    if not check_tool_installed("testssl.sh"):
        print(f"[!] testssl.sh is not installed. Skipping {ip_or_domain}.")
        return

    # ✅ Step 2: Set output file path
    raw_file = f"{ip_or_domain}_{plugin_name}.txt"

    # ✅ Step 3: Run the command
    cmd = ["testssl.sh"] + [] + [ip_or_domain]
    output_path = run_command(cmd, raw_file)

    # ✅ Step 4: Optionally extract CVEs
    extract_cves(output_path, ip_or_domain)
