# ReconCraft by Nirmal Chakraborty
# Copyright (c) 2025. All rights reserved.
# See LICENSE for details.

"""
Guards the Passive-profile policy: the Passive tier must not send scan/attack
traffic to the target. Only OSINT / DNS footprinting tools may be enabled;
every tool that actively probes the target must be DISABLED under Passive.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.plugin_loader import discover_plugins  # noqa: E402

# Tools allowed to run under Passive because they query OSINT sources or DNS
# rather than probing the target's own services.
PASSIVE_ALLOWED = {"amass", "subfinder", "dnsrecon", "dig"}

# Tools that actively contact the target and therefore must be DISABLED under
# Passive.
MUST_BE_DISABLED = {
    "cmsmap", "dirbuster", "dirsearch", "ffuf", "gobuster", "httpx", "hydra",
    "masscan", "naabu", "nikto", "nmap", "nuclei", "rustscan", "smbclient",
    "snmpwalk", "sqlmap", "sslscan", "testssl", "wafw00f", "whatwaf",
    "whatweb", "wpscan",
}


def _passive_value(mod):
    return (getattr(mod, "DEFAULT_ARGS", {}) or {}).get("Passive", "")


def test_active_tools_disabled_in_passive():
    plugins = discover_plugins(verbose=False)
    offenders = []
    for name in MUST_BE_DISABLED:
        mod = plugins.get(name)
        if mod is None:
            continue
        val = _passive_value(mod)
        if not (isinstance(val, str) and val.strip().upper() == "DISABLED"):
            offenders.append((name, val))
    assert not offenders, f"Active tools not DISABLED under Passive: {offenders}"


def test_allowed_passive_tools_are_not_disabled():
    plugins = discover_plugins(verbose=False)
    for name in PASSIVE_ALLOWED:
        mod = plugins.get(name)
        if mod is None:
            continue
        val = _passive_value(mod)
        assert isinstance(val, str) and val.strip().upper() != "DISABLED", (
            f"{name} should remain enabled under Passive, got: {val!r}"
        )
