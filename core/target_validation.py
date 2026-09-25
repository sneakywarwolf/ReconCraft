# ReconCraft by Nirmal Chakraborty
# Copyright (c) 2025. All rights reserved.
# See LICENSE for details.

"""
Target validation and safe argument substitution.

Plugins substitute a ``{{target}}`` placeholder into an argument string that is
then split on whitespace into an argv list (no ``shell=True``). Because the
target flows into argv, a target value that contains whitespace or begins with
``-`` can inject *additional tool arguments* (argument injection). This is not
shell injection — no shell is involved — but an attacker-influenced or
AI-supplied target such as ``127.0.0.1 -oN /etc/crontab`` would still add
unintended flags to the scanner.

This module centralises the guard so the headless/CLI/MCP entry points (which
may be driven autonomously) validate targets before substitution. It is
deliberately conservative about *injection* (hard-blocked) while remaining
permissive about *format* (hosts, IPs, CIDRs, URLs all pass), so legitimate
recon targets are not rejected.

It is standalone (no PyQt, no project imports) and does not alter GUI behaviour;
existing callers are unaffected unless they choose to use it.
"""

from __future__ import annotations

import re
from typing import Tuple

# Characters that must never appear in a target because they would break it
# into multiple argv tokens or smuggle in flags / null bytes.
_WHITESPACE_RE = re.compile(r"\s")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")

# Permissive "looks like a plausible target" character set: hostnames, IPv4/6,
# CIDR, and URLs (scheme, path, query, userinfo, brackets for IPv6).
_ALLOWED_TARGET_RE = re.compile(r"^[A-Za-z0-9._:/%?=&@~+#!$,;()\[\]-]+$")

MAX_TARGET_LEN = 2048


def validate_target(target: str) -> Tuple[bool, str]:
    """
    Return ``(ok, reason)`` for a scan target.

    ``ok=False`` means the target is rejected; ``reason`` explains why. The
    checks, in order:

      1. non-empty string
      2. length bound
      3. no NUL / control characters
      4. no internal whitespace (would split into multiple argv tokens)
      5. does not start with ``-`` (would be parsed as a tool flag)
      6. matches a permissive target character set

    Hostnames, IPv4/IPv6, CIDR ranges, and http(s) URLs all pass.
    """
    if not isinstance(target, str):
        return False, "target must be a string"

    t = target.strip()
    if not t:
        return False, "target is empty"
    if len(t) > MAX_TARGET_LEN:
        return False, f"target exceeds {MAX_TARGET_LEN} characters"
    if _CONTROL_RE.search(t):
        return False, "target contains control or NUL characters"
    if _WHITESPACE_RE.search(t):
        return False, (
            "target contains whitespace, which would inject additional command "
            "arguments"
        )
    if t.startswith("-"):
        return False, (
            "target starts with '-', which would be interpreted as a tool flag"
        )
    if not _ALLOWED_TARGET_RE.match(t):
        return False, "target contains characters not allowed in a scan target"
    return True, ""


class TargetValidationError(ValueError):
    """Raised when a target fails validation."""


def ensure_valid_target(target: str) -> str:
    """Return the stripped target if valid, else raise ``TargetValidationError``."""
    ok, reason = validate_target(target)
    if not ok:
        raise TargetValidationError(reason)
    return target.strip()


def safe_substitute(template: str, target: str) -> str:
    """
    Substitute ``{{target}}`` / ``{target}`` in ``template`` with a validated
    target.

    Raises ``TargetValidationError`` if the target is unsafe, so callers cannot
    accidentally build an argv with an injected flag.
    """
    valid = ensure_valid_target(target)
    return (template or "").replace("{{target}}", valid).replace("{target}", valid)
