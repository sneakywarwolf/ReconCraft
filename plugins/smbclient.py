# ===================== ReconCraft Plugin (Simple + Alias + Docker-Run) =====================

# Required
REQUIRED_TOOL = 'smbclient'    # e.g., "nmap", "gobuster", "rustscan", "nuclei"
INSTALL_HINT  = 'apt'         # one: "apt" | "brew" | "choco" | "pip" | "go" | "git" | "manual" | "docker"

# Optional
INSTALL_URL   = ''            # Docs/repo page (shown to user for manual/git)
EXECUTABLE    = ''            # How ReconCraft should call it; default = REQUIRED_TOOL
TOOL_ALIAS    = ''            # Name of shim/alias to create (used esp. for Docker); default = EXECUTABLE or REQUIRED_TOOL

# Optional (ONLY if INSTALL_HINT == "docker")

# Example (RustScan): "docker run -it --rm --name rustscan rustscan/rustscan:alpine"
DOCKER_RUN    = ''            # Leave empty unless you want Docker-backed install

# 🟦 Default arguments for scan profiles (use {target} where the target should go)
DEFAULT_ARGS = {
    "Aggressive": "-L {{target}} -U '%' -N -d 3",
    "Normal":     "-L {{target}} -U '%' -N",
    "Passive":    "-L {{target}} -N",
    "Custom": "{{target}}"
}

def build_command_args(final_args_str: str) -> list:
    """Convert the already-substituted args string into argv list (no shell=True)."""
    return [a for a in (final_args_str or "").split() if a]

def get_install_info() -> dict:
    """
    Minimal metadata the installer/GUI needs.
    - If INSTALL_HINT == 'docker' and DOCKER_RUN is set, ReconCraft will:
        1) ensure `docker` exists,
        2) create a shim named `alias_name` that executes: DOCKER_RUN + " " + "$@"
       (so the same plugin works like a normal binary)
    """
    return {
        "required_tool": REQUIRED_TOOL,
        "install_hint":  INSTALL_HINT,
        "install_url":   INSTALL_URL,
        "exec_name":     (EXECUTABLE or REQUIRED_TOOL),
        "alias_name":    (TOOL_ALIAS or EXECUTABLE or REQUIRED_TOOL),
        "docker_run":    DOCKER_RUN,
    }

def validate():
    if not REQUIRED_TOOL:
        raise ValueError("REQUIRED_TOOL is required")
    if INSTALL_HINT not in {"apt","brew","choco","pip","go","git","manual","docker"}:
        raise ValueError("INSTALL_HINT must be one of apt|brew|choco|pip|go|git|manual|docker")
    if INSTALL_HINT == "docker" and not DOCKER_RUN:
        raise ValueError("DOCKER_RUN is required when INSTALL_HINT='docker'")

def run(ip_or_domain, raw_dir, base_dir, run_command, check_tool_installed, extract_cves, args="", output_callback=None):
    """
    - `args` is expected to be preprocessed by the GUI ({target} already replaced).
    - Uses TOOL_ALIAS/EXECUTABLE if provided; falls back to REQUIRED_TOOL.
    - Returns (message, is_error) where is_error=True means skip/fail.
    """
    runtime_name = (TOOL_ALIAS or EXECUTABLE or REQUIRED_TOOL).strip()
    plugin_name  = REQUIRED_TOOL

    if isinstance(args, str) and args.upper().strip() == "DISABLED":
        return (f"[!] {plugin_name} is disabled for this profile. Skipping {ip_or_domain}.", True)

    if not check_tool_installed(runtime_name):
        return (f"[!] {runtime_name} not available on PATH. Skipping {ip_or_domain}.", True)

    raw_file = f"{ip_or_domain}_{plugin_name}.txt"
    argv = [runtime_name] + build_command_args(args)

    if output_callback:
        output_callback(f"DEBUG CMD: {' '.join(argv)}")
        output_callback(f"ARGS RECEIVED: {args}")

    output_path = run_command(argv, raw_file, output_callback=output_callback)

    with open(output_path, "r", encoding="utf-8") as f:
        output = f.read()
    return (output, False)
