#!/usr/bin/env python3
# ReconCraft by Nirmal Chakraborty
# Copyright (c) 2025. All rights reserved.
# See LICENSE for details.

"""
ReconCraft headless CLI.

A GUI-free way to list and run ReconCraft plugins from a terminal or script.
It reuses the exact plugin execution contract (via core.headless_runner) that
the PyQt GUI uses, so results land in the same on-disk layout and behave
identically — without importing PyQt5.

Examples:
    python reconcraft_cli.py list
    python reconcraft_cli.py status nmap
    python reconcraft_cli.py run nmap 127.0.0.1 --profile Normal
    python reconcraft_cli.py run nmap scanme.nmap.org --profile Custom \\
        --custom-args "-sV -p1-1000 {{target}}" --output-dir ./cli_runs
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.headless_runner import HeadlessRunner, VALID_PROFILES, new_scan_root


def _cmd_list(args) -> int:
    runner = HeadlessRunner(report_root_folder=args.output_dir)
    meta = runner.all_metadata()
    if args.json:
        print(json.dumps(meta, indent=2))
        return 0
    print(f"{'TOOL':<14}{'INSTALLED':<11}{'HINT':<10}PROFILES")
    print("-" * 60)
    for m in meta:
        profiles = ",".join(k for k in m["profiles"].keys())
        print(
            f"{m['name']:<14}"
            f"{('yes' if m['installed'] else 'no'):<11}"
            f"{(m['install_hint'] or '-'):<10}"
            f"{profiles}"
        )
    return 0


def _cmd_status(args) -> int:
    runner = HeadlessRunner(report_root_folder=args.output_dir)
    try:
        meta = runner.tool_metadata(args.tool)
    except KeyError:
        print(f"Unknown tool: {args.tool}", file=sys.stderr)
        print("Available:", ", ".join(runner.available_tools()), file=sys.stderr)
        return 2
    print(json.dumps(meta, indent=2))
    return 0


def _cmd_run(args) -> int:
    base = args.output_dir
    scan_root = new_scan_root(base, label=f"{args.tool}_{args.target}")
    runner = HeadlessRunner(
        report_root_folder=scan_root,
        default_timeout=(None if args.timeout in (None, 0) else float(args.timeout)),
    )

    profile = args.profile.strip().capitalize()
    if profile not in VALID_PROFILES:
        print(
            f"Invalid profile '{args.profile}'. Choose one of {list(VALID_PROFILES)}.",
            file=sys.stderr,
        )
        return 2

    def _cb(line: str) -> None:
        if not args.quiet:
            print(line, file=sys.stderr)

    result = runner.run_tool(
        tool=args.tool,
        target=args.target,
        profile=profile,
        custom_args=args.custom_args,
        output_callback=_cb,
    )

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(result.message)
        if result.output_path:
            print(f"Saved to: {result.output_path}")
        if result.output and not result.skipped:
            print("-" * 60)
            print(result.output)
    return 0 if result.ok else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="reconcraft_cli",
        description="Headless CLI for ReconCraft plugins (GUI-free).",
    )
    p.add_argument(
        "--output-dir",
        default="cli_runs",
        help="Base directory for scan output (default: ./cli_runs).",
    )
    sub = p.add_subparsers(dest="command", required=True)

    pl = sub.add_parser("list", help="List available tools and install status.")
    pl.add_argument("--json", action="store_true", help="Emit JSON.")
    pl.set_defaults(func=_cmd_list)

    ps = sub.add_parser("status", help="Show one tool's metadata / install status.")
    ps.add_argument("tool")
    ps.set_defaults(func=_cmd_status)

    pr = sub.add_parser("run", help="Run a tool against a target.")
    pr.add_argument("tool")
    pr.add_argument("target")
    pr.add_argument("--profile", default="Normal", help="Aggressive|Normal|Passive|Custom")
    pr.add_argument("--custom-args", default=None, help="Args for Custom profile.")
    pr.add_argument("--timeout", type=float, default=None, help="Per-command timeout (s).")
    pr.add_argument("--json", action="store_true", help="Emit JSON result.")
    pr.add_argument("--quiet", action="store_true", help="Suppress streamed logs.")
    pr.set_defaults(func=_cmd_run)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
