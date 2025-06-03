# 🚀 ReconCraft - Advanced Reconnaissance Automation Tool

**ReconCraft** is a modular, plugin-driven CLI utility that enhances efficiency, accuracy, and speed during active reconnaissance. Designed for hybrid environments, it supports IPs, domains, and URLs as targets and is flexible enough for both red team professionals and beginner developers.

---

## 🧰 Features

- ✅ **Plugin-Based Architecture** – Easily extend with custom plugins
- ✅ **Cross-Platform Installer** – Python-based setup with support for Linux and Windows (via `winget`)
- ✅ **Multiple Scanners Integrated**
  - `nmap`, `naabu`, `nuclei`, `nikto`, `testssl.sh`, `enum4linux`, and more
- ✅ **CVE Extraction** from raw scan outputs using `searchsploit`
- ✅ **Auto-Report Generation**
  - Structured `report.json` output under timestamped directories
- ✅ **Dynamic Plugin Selection**
  - Choose specific plugins per scan via CLI
- ✅ **Self-Documenting Plugins**
  - Use `--list-plugins` to view and manage available modules
- ✅ **Plugin Boilerplate Generator**
  - Create new plugins with `--create-plugin <name>`

---

## 🖥️ Getting Started

### 🔧 Installation

```bash
git clone https://github.com/yourusername/reconcraft.git
cd reconcraft
python install.py
```

### 📂 File Structure

```
ReconCraft/
├── plugins/            # Modular scanning plugins
├── third_party/        # Optional local tool binaries (future)
├── scan_results_*/     # Time-stamped scan output folders
│   ├── raw_outputs/
│   ├── cve_results/
│   └── reports/
├── install.py          # Cross-platform installer
├── requirements.txt
└── reconcraft.py       # Main executable script
```

---

## ⚙️ Usage

### 🔎 Basic Scan (Runs All Plugins)

```bash
python reconcraft.py -f ip-list.txt
```

### 🎯 Scan with Selected Plugins

```bash
python reconcraft.py -f ip-list.txt -p nmap,nuclei,nikto
```

### 📜 List Available Plugins

```bash
python reconcraft.py --list-plugins
```

### ⚡ Create a New Plugin

```bash
python reconcraft.py --create-plugin myscanner
```

---

## 🌱 Roadmap

We are actively building more features to make ReconCraft a truly comprehensive recon suite:

- 🌐 **Optional Web UI/UX Dashboard**
- 📦 **Built-in third_party/ tools** for non-installable binaries
- 📊 **Markdown & HTML Report Generation**
- 💾 **JSON export per plugin**
- 🔒 **Plugin Signature Verification** (for marketplace integration)

---

## 🤝 Contributing

We aim to keep ReconCraft beginner-friendly! If you’re a new developer or a seasoned hacker, check out our well-structured plugins and start contributing.

---

## 📜 License

MIT License. Tool usage is your responsibility. We are not liable for any misuse.

---

## 👨‍💻 Developed by

**ReconCraft Team** – Helping teams recon smarter and faster.