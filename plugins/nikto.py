REQUIRED_TOOL = "nikto"
INSTALL_HINT = "apt"
INSTALL_URL = ""

DEFAULT_ARGS = {
    "Aggressive": "-h {target} -Tuning 123bde -C all",
    "Normal":     "-h {target}",
    "Passive":    "DISABLED",
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

    # ✅ Step 3: Use preprocessed args (should already have {target} replaced)
    arg_list = args.split() if args else []

    # 📌 Construct the final command as a list
    cmd = [plugin_name] + arg_list

    # 🔍 Debug output (prints to console and optionally to status/output callback)
    print("DEBUG CMD:", cmd)
    if output_callback:
        output_callback(f"DEBUG CMD: {' '.join(cmd)}")
    print("ARGS RECEIVED:", args)
    if output_callback:
        output_callback(f"ARGS RECEIVED: {args}")

    # ✅ Step 4: Run the command
    output_path = run_command(cmd, raw_file, output_callback=output_callback)

    # ✅ Step 5: (Optional) Extract CVEs from output (if implemented)
    # extract_cves(output_path, ip_or_domain)

    # ✅ Step 6: Return final output
    with open(output_path, "r", encoding="utf-8") as f:
        output = f.read()
    return (output, False)
