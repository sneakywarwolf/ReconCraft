#!/bin/bash

set -e

echo "[+] Installing dependencies for ReconCraft..."

TOOLS=(nmap naabu nuclei nikto enum4linux amass exploitdb)

for tool in "${TOOLS[@]}"; do
    if ! command -v "$tool" &> /dev/null; then
        echo "[*] Installing $tool..."
        case "$tool" in
            enum4linux)
                sudo apt-get install -y enum4linux
                ;;
            exploitdb)
                sudo apt-get install -y exploitdb
                ;;
            *)
                sudo apt-get install -y "$tool"
                ;;
        esac
    else
        echo "[✓] $tool already installed."
    fi
done

# Clone testssl.sh if not already present
if [ ! -f ./testssl.sh/testssl.sh ]; then
    echo "[*] Cloning testssl.sh..."
    git clone --depth 1 https://github.com/drwetter/testssl.sh.git
else
    echo "[✓] testssl.sh already present."
fi

echo "[✓] All tools installed or already present."

# Install Python dependencies from requirements.txt
if [ -f requirements.txt ]; then
    echo "[+] Installing Python requirements..."
    pip install -r requirements.txt
else
    echo "[!] requirements.txt not found. Skipping Python package installation."
fi
