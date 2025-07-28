REQUIRED_TOOL = "sslscan"   # e.g., "nmap", "gobuster", etc.
INSTALL_HINT = "apt"         # "apt", "brew", "pip", "go", or "manual"
INSTALL_URL = ""             # For manual tools (if any)

def run(ip_or_domain, raw_dir, base_dir, run_command, check_tool_installed, extract_cves):
    plugin_name = REQUIRED_TOOL

    # ✅ Step 1: Check if tool is installed
    if not check_tool_installed(plugin_name):
        return (f"[!] {plugin_name} not installed. Skipping {ip_or_domain}.", True)

    # ✅ Step 2: Set output file path
    raw_file = f"{ip_or_domain}_{plugin_name}.txt"

    # ✅ Step 3: Run the command (customize as needed)
    cmd = ['sslscan', 'ip_or_domain']
    output_path = run_command(cmd, raw_file)

    # ✅ Step 4: Optionally extract CVEs
    # extract_cves(output_path, ip_or_domain)  ← Optional

    # ✅ Step 5: Read and return the output as a tuple (output, False)
    with open(output_path, "r", encoding="utf-8") as f:
        output = f.read()
    return (output, False)
