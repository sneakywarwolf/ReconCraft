# ReconCraft by Nirmal Chakraborty
# Copyright (c) 2025. All rights reserved.
# See LICENSE for details.

"""
ReconCraft MCP server.

Exposes ReconCraft's dynamically-discovered plugins as MCP tools so that any
MCP-capable client (Claude Code, Codex, Kimi Code, Cursor, etc.) can trigger
ReconCraft's recon/scan functionality over stdio.

Design / safety notes (aligned with least-privilege agent design):
  * Reuses the existing plugin contract via ``core.headless_runner`` — no GUI
    code, no plugin, and no existing behaviour is modified.
  * Commands are executed as argv lists by the plugins (no shell=True), exactly
    as in the GUI.
  * Optional tool allowlist via ``RECONCRAFT_MCP_ALLOWED_TOOLS``.
  * Per-command wall-clock timeout via ``RECONCRAFT_MCP_TIMEOUT`` (default 600s).
  * Result-file reads are confined to the server's output directory (no path
    traversal outside it).
  * The server only runs tools the operator has installed on PATH; it never
    auto-installs anything.

Run:
    python -m mcp_server.server            # stdio transport (default)
    RECONCRAFT_MCP_OUTPUT_DIR=/data python -m mcp_server.server

Environment variables:
    RECONCRAFT_MCP_OUTPUT_DIR   Base dir for scan output (default: ./mcp_runs)
    RECONCRAFT_MCP_ALLOWED_TOOLS  Comma-separated plugin allowlist (default: all)
    RECONCRAFT_MCP_TIMEOUT      Per-command timeout seconds (default: 600; 0 = none)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional

# Ensure the project root is importable when launched as a script.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Support both MCP SDK generations:
#   * v1.x exposes mcp.server.fastmcp.FastMCP
#   * v2.x renamed it to mcp.server.mcpserver.MCPServer (same .tool()/.run() API)
_MCPServer = None
try:  # v1
    from mcp.server.fastmcp import FastMCP as _MCPServer  # type: ignore
except ModuleNotFoundError:
    try:  # v2
        from mcp.server.mcpserver import MCPServer as _MCPServer  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency guidance
        raise SystemExit(
            "The 'mcp' package is required to run the ReconCraft MCP server.\n"
            "Install it with:\n"
            "    pip install -r requirements-mcp.txt\n"
            "or:\n"
            '    pip install "mcp[cli]>=1.2"\n'
            f"(import error: {exc})"
        )

from core.headless_runner import HeadlessRunner, VALID_PROFILES, new_scan_root
from core.target_validation import validate_target


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
def _env_output_dir() -> str:
    base = os.environ.get("RECONCRAFT_MCP_OUTPUT_DIR") or os.path.join(
        os.getcwd(), "mcp_runs"
    )
    os.makedirs(base, exist_ok=True)
    return base


def _env_allowed_tools() -> Optional[set]:
    raw = (os.environ.get("RECONCRAFT_MCP_ALLOWED_TOOLS") or "").strip()
    if not raw:
        return None
    return {t.strip() for t in raw.split(",") if t.strip()}


def _env_timeout() -> Optional[float]:
    raw = (os.environ.get("RECONCRAFT_MCP_TIMEOUT") or "").strip()
    if raw == "":
        return 600.0
    try:
        val = float(raw)
    except ValueError:
        return 600.0
    return None if val <= 0 else val


OUTPUT_DIR = _env_output_dir()
ALLOWED_TOOLS = _env_allowed_tools()
DEFAULT_TIMEOUT = _env_timeout()

# One long-lived runner; each run gets its own scan-root subfolder.
_runner = HeadlessRunner(report_root_folder=OUTPUT_DIR, default_timeout=DEFAULT_TIMEOUT)

mcp = _MCPServer(
    "ReconCraft",
    instructions=(
        "ReconCraft exposes reconnaissance and vulnerability-scanning tools "
        "(nmap, nuclei, httpx, ffuf, amass, sqlmap, and more) as MCP tools. "
        "Use `list_recon_tools` to see what is available and installed, "
        "`check_tool_status` to verify a specific tool, and `run_recon_tool` to "
        "execute a scan against an authorized target. Only scan systems you are "
        "explicitly authorized to test."
    ),
)


def _tool_allowed(tool: str) -> bool:
    if ALLOWED_TOOLS is None:
        return True
    return tool in ALLOWED_TOOLS


def _visible_tools() -> List[str]:
    tools = _runner.available_tools()
    if ALLOWED_TOOLS is None:
        return tools
    return [t for t in tools if t in ALLOWED_TOOLS]


# --------------------------------------------------------------------------- #
# MCP tools
# --------------------------------------------------------------------------- #
@mcp.tool()
def list_recon_tools() -> dict:
    """
    List all ReconCraft recon/scan tools available via this server.

    Returns each tool's required binary, install hint, supported scan profiles
    (Aggressive/Normal/Passive/Custom) with their argument templates, and
    whether the underlying binary is currently installed on PATH.
    """
    meta = [m for m in _runner.all_metadata() if _tool_allowed(m["name"])]
    return {
        "count": len(meta),
        "output_dir": OUTPUT_DIR,
        "default_timeout_seconds": DEFAULT_TIMEOUT,
        "profiles": list(VALID_PROFILES),
        "allowlist_active": ALLOWED_TOOLS is not None,
        "tools": meta,
    }


@mcp.tool()
def check_tool_status(tool: str) -> dict:
    """
    Check whether a specific ReconCraft tool's underlying binary is installed
    and usable on PATH, and return its metadata.

    Args:
        tool: Plugin name, e.g. "nmap", "nuclei", "httpx".
    """
    if not _tool_allowed(tool):
        return {"tool": tool, "error": "Tool not permitted by server allowlist."}
    try:
        return _runner.tool_metadata(tool)
    except KeyError:
        return {
            "tool": tool,
            "error": f"Unknown tool '{tool}'.",
            "available": _visible_tools(),
        }


@mcp.tool()
def run_recon_tool(
    tool: str,
    target: str,
    profile: str = "Normal",
    custom_args: Optional[str] = None,
    timeout_seconds: Optional[float] = None,
) -> dict:
    """
    Run a single ReconCraft tool against a target and return its output.

    Args:
        tool: Plugin name to run (see `list_recon_tools`), e.g. "nmap".
        target: IP address, hostname, URL, or CIDR to scan. Only scan targets
            you are authorized to test.
        profile: One of "Aggressive", "Normal", "Passive", or "Custom"
            (case-insensitive). Defaults to "Normal".
        custom_args: Required when profile is "Custom". Argument string; use
            "{{target}}" (or "{target}") as the target placeholder. If omitted
            for Custom, the plugin's own Custom template is used when defined.
        timeout_seconds: Optional per-command wall-clock timeout override. If
            omitted, the server default is used (0/none = unbounded).

    Returns a structured result: ok, skipped, message, command, output,
    output_path (on disk), exit_code, and streamed logs.
    """
    if not target or not str(target).strip():
        return {"ok": False, "error": "A non-empty target is required."}

    # Validate the target at the boundary, before any tool/install checks, so an
    # argument-injection attempt is always rejected regardless of tool state.
    _ok_target, _reason = validate_target(str(target))
    if not _ok_target:
        return {
            "ok": False,
            "status": "rejected",
            "tool": tool,
            "target": target,
            "error": f"Invalid target rejected: {_reason}",
        }

    if not _tool_allowed(tool):
        return {"ok": False, "error": "Tool not permitted by server allowlist."}

    if tool not in _runner.available_tools():
        return {
            "ok": False,
            "error": f"Unknown tool '{tool}'.",
            "available": _visible_tools(),
        }

    norm_profile = (profile or "Normal").strip().capitalize()
    if norm_profile not in VALID_PROFILES:
        return {
            "ok": False,
            "error": f"Invalid profile '{profile}'. Choose one of {list(VALID_PROFILES)}.",
        }

    # Verify the binary before spending a run folder on it.
    meta = _runner.tool_metadata(tool)
    if not meta.get("installed"):
        return {
            "ok": False,
            "skipped": True,
            "tool": tool,
            "target": target,
            "message": (
                f"'{meta.get('runtime_name', tool)}' is not installed on PATH. "
                f"Install hint: {meta.get('install_hint') or 'n/a'} "
                f"{meta.get('install_url') or ''}".strip()
            ),
        }

    # Isolate each MCP-initiated scan in its own GUI-compatible scan folder.
    scan_root = new_scan_root(OUTPUT_DIR, label=f"{tool}_{target}")
    runner = HeadlessRunner(report_root_folder=scan_root, default_timeout=DEFAULT_TIMEOUT)

    to = DEFAULT_TIMEOUT if timeout_seconds is None else (
        None if timeout_seconds <= 0 else float(timeout_seconds)
    )

    result = runner.run_tool(
        tool=tool,
        target=str(target).strip(),
        profile=norm_profile,
        custom_args=custom_args,
        timeout=to,
    )
    payload = result.to_dict()
    payload["scan_root"] = scan_root
    # Keep the payload lean: cap very large outputs, full copy remains on disk.
    if payload.get("output") and len(payload["output"]) > 100_000:
        payload["output_truncated"] = True
        payload["output"] = payload["output"][:100_000] + "\n...[truncated; see output_path]"
    return payload


@mcp.tool()
def read_result_file(path: str, max_bytes: int = 200_000) -> dict:
    """
    Read a previously produced result file.

    Reads are confined to the server's output directory; paths outside it are
    rejected.

    Args:
        path: Absolute or relative path to a result file (e.g. an `output_path`
            returned by `run_recon_tool`).
        max_bytes: Maximum number of bytes to return (default 200000).
    """
    base = Path(OUTPUT_DIR).resolve()
    try:
        resolved = Path(path).resolve()
    except Exception as exc:
        return {"error": f"Invalid path: {exc}"}

    if base not in resolved.parents and resolved != base:
        return {"error": "Access denied: path is outside the ReconCraft output directory."}
    if not resolved.is_file():
        return {"error": f"Not a file: {resolved}"}

    data = resolved.read_bytes()[: max(0, int(max_bytes))]
    return {
        "path": str(resolved),
        "size_returned": len(data),
        "content": data.decode("utf-8", errors="replace"),
    }


def main() -> None:
    """Entry point: run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
