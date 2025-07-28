# 🧭 ReconCraft GUI

> **ReconCraft** is a powerful, modular, and visually interactive reconnaissance automation tool for security professionals and bug bounty hunters.

---

## 🚀 Features

- 🎯 **Multi-target scanning** — Input multiple domains or IPs.
- 🔌 **Plugin-based architecture** — Integrate tools like Nmap, Subfinder, Naabu, and more.
- 📁 **Auto-organized Reports** — Every scan saved in a well-structured directory.
- 📊 **Stylish Dashboard** — Real-time stats: scan status, tools used, latest reports, and more.
- 🧮 **CVSS v3.1 Calculator** — Score vulnerabilities with an interactive metric selector.
- 💡 **Dark mode UI** — Futuristic and user-friendly interface built with PyQt5.

---

## 📸 Screenshots

| Dashboard | CVSS Calculator |
|----------|----------------|
| ![Dashboard](assets/demo_dashboard.png) | ![CVSS](assets/demo_cvss.png) |

---

## 🛠️ Getting Started

### 1. Clone the Repo
```bash
git clone https://github.com/Sneakywarwolf/ReconCraft.git
cd ReconCraft
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Launch the App
```bash
python main.py
```

---

## 🔧 Settings & Customization

Configure plugin paths and tool settings via the **Settings** tab. More control coming soon!

---

## 📚 Tech Stack

- 🐍 Python 3.x
- 🎨 PyQt5 (for GUI)
- ⚙️ subprocess (for tool execution)
- 📊 cvsslib (for CVSS scoring)

---

## 📦 Folder Structure

```
ReconCraft/
├── assets/              # Icons, logos, demo screenshots
├── core/                # Main scan logic & threading
├── plugins/             # Tool-specific logic (e.g., nmap, subfinder)
├── reports/             # Saved output for each scan
├── gui/                 # UI logic, tabs, widgets
├── main.py              # Launcher
└── README.md
```

---

## ✨ Upcoming Enhancements

- 🧩 Add more plugins (e.g., Shodan, Wappalyzer)
- 📑 Full report viewer with search & export to PDF
- ⚙️ Advanced tool configuration per plugin in Settings

---

## 🤝 Contribute

Feel free to fork, suggest features, or submit pull requests. We welcome contributions!

---

## 🔐 Disclaimer

This tool is intended for **authorized security assessments only**. Use it responsibly.

---

## 🌐 Connect

- 💬 [LinkedIn](https://www.linkedin.com/in/nirmalchak)
- 🐙 [GitHub](https://github.com/sneakywarwolf)
- ✉️ sneakypentester@gmail.com

---

> Made with ❤️ for Recon lovers.