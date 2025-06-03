import os
def run(ip, raw_dir, base_dir, run_command, check_tool_installed, extract_cves):
    testssl_path = "./testssl.sh/testssl.sh"
    if os.path.isfile(testssl_path):
        run_command(f"{testssl_path} {ip}", f"{ip}_testssl.txt")