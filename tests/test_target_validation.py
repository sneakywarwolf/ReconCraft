# ReconCraft by Nirmal Chakraborty
# Copyright (c) 2025. All rights reserved.
# See LICENSE for details.

"""Tests for core.target_validation (argument-injection guard)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.target_validation import (  # noqa: E402
    TargetValidationError,
    ensure_valid_target,
    safe_substitute,
    validate_target,
)


@pytest.mark.parametrize(
    "target",
    [
        "127.0.0.1",
        "10.0.0.0/24",
        "example.com",
        "sub.domain.example.co.uk",
        "http://example.com",
        "https://example.com:8443/path?q=1&x=2",
        "user@host.example",
        "[2001:db8::1]",
        "2001:db8::1",
    ],
)
def test_valid_targets_accepted(target):
    ok, reason = validate_target(target)
    assert ok, f"expected valid, got: {reason}"


@pytest.mark.parametrize(
    "target",
    [
        "127.0.0.1 -oN /etc/crontab",   # whitespace -> extra argv tokens
        "-sV",                           # leading dash -> parsed as a flag
        "--script=evil",                 # leading dash
        "1.1.1.1\t-p-",                  # tab whitespace
        "host\nname",                    # newline
        "host\x00name",                  # NUL byte
        "",                               # empty
        "   ",                            # blank
        "a b",                            # internal space
    ],
)
def test_injection_and_bad_targets_rejected(target):
    ok, _ = validate_target(target)
    assert not ok


def test_ensure_valid_target_raises():
    with pytest.raises(TargetValidationError):
        ensure_valid_target("1.2.3.4 -oN x")


def test_ensure_valid_target_strips():
    assert ensure_valid_target("  example.com  ") == "example.com"


def test_safe_substitute_replaces_both_placeholders():
    assert safe_substitute("-sV {{target}}", "1.2.3.4") == "-sV 1.2.3.4"
    assert safe_substitute("scan {target}", "1.2.3.4") == "scan 1.2.3.4"


def test_safe_substitute_blocks_injection():
    with pytest.raises(TargetValidationError):
        safe_substitute("-sV {{target}}", "1.2.3.4 -oN /tmp/x")


def test_length_bound():
    ok, _ = validate_target("a" * 5000)
    assert not ok
