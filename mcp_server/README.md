# ReconCraft MCP Integration

Expose ReconCraft's plugin-based recon/scan tools over the **Model Context
Protocol (MCP)** so MCP-capable clients — **Claude Code**, **OpenAI Codex**,
**Kimi Code**, Cursor, Cline, Windsurf, and others — can trigger ReconCraft's
tools directly.

This integration is **additive and non-invasive**: it reuses the exact plugin
execution contract used by the PyQt GUI (via `core/headless_runner.py`) and
does **not** modify the GUI, `core/scan_thread.py`, or any plugin. Anything you
run through MCP produces output in the same on-disk layout as a GUI scan
(`<output>/Scan Results/<ts>_<label>/All Reports/<target>/<tool>/<run_id>/`).

## How it works

```
MCP client (Claude Code / Codex / Kimi)
        │  stdio (JSON-RPC / MCP)
        ▼
mcp_server/server.py  (FastMCP)
        │  reuses plugin contract
        ▼
core/headless_runner.py  ── discover_plugins() ──►  plugins/*.py  (unchanged)
        │
        ▼
subprocess (argv, no shell) ──►  nmap / nuclei / httpx / ffuf / ...
```

The GUI's `ScanThread` and this server are two independent providers of the same
plugin callbacks (`run_command`, `check_tool_installed`, `extract_cves`). The
plugins do not know or care which one is calling them.

## Install

```bash
pip install -r requirements-mcp.txt      # installs: mcp[cli]
```

(The base `requirements.txt` is unchanged; MCP deps are optional.)

## Run the server

```bash
# from the ReconCraft project root
python -m mcp_server.server
```

The server speaks MCP over **stdio**; MCP clients launch it for you using the
config below, so you normally don't run it by hand except to smoke-test.

## MCP tools exposed

| Tool | Purpose |
|------|---------|
| `list_recon_tools` | List all discovered plugins, supported profiles, arg templates, and install status. |
| `check_tool_status` | Report whether one tool's binary is installed on PATH + its metadata. |
| `run_recon_tool` | Run one tool against a target with a profile (`Aggressive`/`Normal`/`Passive`/`Custom`); returns output + on-disk path. |
| `read_result_file` | Read a produced result file (confined to the output directory). |

### `run_recon_tool` arguments

- `tool` — plugin name (e.g. `nmap`, `nuclei`, `httpx`).
- `target` — IP / host / URL / CIDR. **Only scan authorized targets.**
- `profile` — `Aggressive` | `Normal` | `Passive` | `Custom` (default `Normal`).
- `custom_args` — used when `profile=Custom`; use `{{target}}` (or `{target}`)
  as the target placeholder.
- `timeout_seconds` — optional per-command override.

## Client configuration

Example configs are in [`examples/`](examples/). Replace
`/ABSOLUTE/PATH/TO/ReconCraft` with your clone path.

- **Claude Code / Claude Desktop** → [`examples/claude_code.json`](examples/claude_code.json)
  (merge the `reconcraft` entry into your `mcpServers`). With the Claude Code
  CLI you can also run:
  ```bash
  claude mcp add reconcraft -- python -m mcp_server.server
  ```
  (run from the project root, or pass an absolute `cwd`).
- **OpenAI Codex CLI** → [`examples/codex.toml`](examples/codex.toml)
  (merge into `~/.codex/config.toml`).
- **Kimi Code / Cursor / Cline / Windsurf / generic** →
  [`examples/kimi_cursor_generic.json`](examples/kimi_cursor_generic.json).

> Exact config file locations vary by client and version; the transport
> (stdio), command (`python -m mcp_server.server`), and env vars are the same
> everywhere. Check your client's current MCP docs for where its config lives.

## Configuration (environment variables)

| Variable | Default | Meaning |
|----------|---------|---------|
| `RECONCRAFT_MCP_OUTPUT_DIR` | `./mcp_runs` | Base directory for scan output. |
| `RECONCRAFT_MCP_ALLOWED_TOOLS` | *(all)* | Comma-separated allowlist, e.g. `nmap,httpx,nuclei`. |
| `RECONCRAFT_MCP_TIMEOUT` | `600` | Per-command wall-clock timeout in seconds (`0` = unbounded). |

## Safety / least privilege

- Commands run as **argv lists** (no `shell=True`), exactly as in the GUI.
- The server **never installs** tools; it only runs binaries already on PATH.
- Use `RECONCRAFT_MCP_ALLOWED_TOOLS` to restrict the exposed tool surface.
- `read_result_file` refuses paths outside `RECONCRAFT_MCP_OUTPUT_DIR`.
- Keep a **human-approval gate** enabled in your MCP client for `run_recon_tool`
  — it launches real scanners against real targets. Only test systems you are
  authorized to assess.

## Headless CLI (bonus)

The same engine is available without MCP:

```bash
python reconcraft_cli.py list
python reconcraft_cli.py status nmap
python reconcraft_cli.py run nmap 127.0.0.1 --profile Normal
python reconcraft_cli.py run nmap example.com --profile Custom \
    --custom-args "-sV -p1-1000 {{target}}"
```
