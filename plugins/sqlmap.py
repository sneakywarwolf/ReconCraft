REQUIRED_TOOL = "sqlmap"     # e.g., "nmap", "gobuster", etc.
INSTALL_HINT = "apt"         # "apt", "brew", "pip", "go", or "manual"
INSTALL_URL = ""             # For manual tools (if any)

# Arguments for different scan modes
DEFAULT_ARGS = {
    "Aggressive": "-u {target} --batch --random-agent --level=5 --risk=3 --threads=10",  # Aggressive scanning
    "Normal":     "-u {target} --batch --random-agent --level=3 --risk=2",               # Standard scanning
    "Passive":    "DISABLED",                                                # (set to DISABLED to skip this plugin in passive mode, else provide passive args)
}

def run(ip_or_domain, raw_dir, base_dir, run_command, check_tool_installed, extract_cves, args="", output_callback=None):
    plugin_name = REQUIRED_TOOL

    # ✅ Step 0: Skip if DISABLED (from profile/mode)
    if isinstance(args, str) and args.upper() == "DISABLED":
        return (f"[!] {plugin_name} is disabled for this profile. Skipping {ip_or_domain}.", True)

    # ✅ Step 1: Check if tool is installed
    if not check_tool_installed(plugin_name):
        return (f"[!] {plugin_name} not installed. Skipping {ip_or_domain}.", True)

    # ✅ Step 2: Set output file path
    raw_file = f"{ip_or_domain}_{plugin_name}.txt"

    # --- If your tool uses a script in tool_scripts/, use the following ---
    # import os
    # script_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tool_scripts'))
    # script_path = os.path.join(script_dir, "scriptname.sh")
    # cmd = ["bash", script_path, ip_or_domain]

    # Split args for subprocess, e.g. "-a -b 1" => ["-a", "-b", "1"]
    # ✅ Step 3: Prepare arguments, replacing {target} with actual target
    if args:
        replaced_args = args.replace("{target}", ip_or_domain)
        arg_list = replaced_args.split()
    else:
        arg_list = []

    cmd = [plugin_name] + arg_list  # Note: ip_or_domain will already be in args if desired
    output_path = run_command(cmd, raw_file, output_callback=output_callback)

    # ✅ Step 4: Optionally extract CVEs
    # extract_cves(output_path, ip_or_domain)  # ← Optional

    # ✅ Step 5: Read and return the output as a tuple (output, False)
    with open(output_path, "r", encoding="utf-8") as f:
        output = f.read()
    return (output, False)
