# ReconCraft by Nirmal Chakraborty
# Copyright (c) 2025. All rights reserved.
# See LICENSE for details.

"""
Tests for core.headless_runner.

These avoid real recon binaries by shimming an executable named after a
plugin's required tool onto PATH. They exercise discovery, profile/argument
resolution, the full plugin execution path, run.json emission, the argument
-injection guard, timeout, and cancel.
"""

import json
import os
import stat
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.headless_runner import HeadlessRunner, new_scan_root  # noqa: E402


def _make_shim(dir_path: str, name: str, body: str) -> None:
    p = Path(dir_path) / name
    p.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture()
def scan_root():
    base = tempfile.mkdtemp()
    return new_scan_root(base, "test")


def test_discovery_and_metadata(scan_root):
    r = HeadlessRunner(report_root_folder=scan_root)
    tools = r.available_tools()
    assert "nmap" in tools
    meta = r.tool_metadata("nmap")
    assert meta["required_tool"] == "nmap"
    assert "Normal" in meta["profiles"]


def test_argument_resolution(scan_root):
    r = HeadlessRunner(report_root_folder=scan_root)
    mod = r.plugin_map["nmap"]
    args, skip = r._resolve_args(mod, "nmap", "127.0.0.1", "Normal", None)
    assert skip is None and "127.0.0.1" in args
    args, _ = r._resolve_args(mod, "nmap", "10.0.0.1", "Custom", "-sV {{target}}")
    assert args == "-sV 10.0.0.1"


def test_invalid_target_rejected(scan_root):
    r = HeadlessRunner(report_root_folder=scan_root)
    res = r.run_tool("nmap", "127.0.0.1 -oN /tmp/x", "Normal")
    assert res.ok is False
    assert res.status == "rejected"


def test_unknown_tool(scan_root):
    r = HeadlessRunner(report_root_folder=scan_root)
    res = r.run_tool("definitely_not_a_tool", "127.0.0.1")
    assert res.ok is False and res.status == "unsupported"


def test_full_run_and_manifest(scan_root, monkeypatch):
    shim_dir = tempfile.mkdtemp()
    _make_shim(shim_dir, "nmap", 'echo "80/tcp open http"')
    monkeypatch.setenv("PATH", shim_dir + os.pathsep + os.environ["PATH"])

    r = HeadlessRunner(report_root_folder=scan_root)
    res = r.run_tool("nmap", "127.0.0.1", "Normal")

    assert res.ok is True and res.status == "ok" and res.exit_code == 0
    assert "80/tcp open" in res.output
    assert res.output_path and Path(res.output_path).is_file()

    # run.json manifest written and consumable
    assert res.run_json_path and Path(res.run_json_path).is_file()
    data = json.loads(Path(res.run_json_path).read_text())
    assert data["tool"] == "nmap"
    assert data["status"] == "ok"
    assert data["targets"] == ["127.0.0.1"]
    assert data["command"][0] == "nmap"


def test_timeout(scan_root, monkeypatch):
    shim_dir = tempfile.mkdtemp()
    _make_shim(shim_dir, "nmap", "echo begin; sleep 30")
    monkeypatch.setenv("PATH", shim_dir + os.pathsep + os.environ["PATH"])

    r = HeadlessRunner(report_root_folder=scan_root, default_timeout=2)
    t0 = time.time()
    res = r.run_tool("nmap", "127.0.0.1", "Normal")
    assert time.time() - t0 < 10
    assert res.ok is False and res.status == "timeout"


def test_cancel(scan_root, monkeypatch):
    shim_dir = tempfile.mkdtemp()
    _make_shim(shim_dir, "nmap", "echo begin; sleep 30")
    monkeypatch.setenv("PATH", shim_dir + os.pathsep + os.environ["PATH"])

    r = HeadlessRunner(report_root_folder=scan_root)
    threading.Timer(1.0, r.cancel).start()
    t0 = time.time()
    res = r.run_tool("nmap", "127.0.0.1", "Normal")
    assert time.time() - t0 < 10
    assert res.ok is False and res.status == "aborted"


def test_not_installed_is_error_not_crash(scan_root, monkeypatch):
    # Ensure the shimmed tool is NOT on PATH.
    monkeypatch.setenv("PATH", tempfile.mkdtemp())
    r = HeadlessRunner(report_root_folder=scan_root)
    res = r.run_tool("nmap", "127.0.0.1", "Normal")
    assert res.ok is False  # plugin reports "not available on PATH"
