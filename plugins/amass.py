"""
Amass - Performs advanced passive and active subdomain enumeration.
"""
REQUIRED_TOOL = "amass"
INSTALL_HINT = "apt"         # or "brew", "pip", "go", or "manual"
INSTALL_URL = ""  # For manual tools

def run(ip_or_domain, raw_dir, base_dir, run_command, check_tool_installed, extract_cves):
    plugin_name = "amass"

    # ✅ Step 1: Check if tool is installed
    if not check_tool_installed("amass"):
        return(f"[!] amass is not installed. Skipping {ip_or_domain}." , True)
        
    # ✅ Step 2: Set output file path
    raw_file = f"{ip_or_domain}_{plugin_name}.txt"

    # ✅ Step 3: Run the command
    cmd = ["amass"] + ['enum', '-passive', '-d'] + [ip_or_domain]
    output_path = run_command(cmd, raw_file)

    # ✅ Step 4: Optionally extract CVEs
    # extract_cves(output_path, ip_or_domain)  ← Not used for Amass
