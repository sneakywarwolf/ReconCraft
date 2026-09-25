# ReconCraft by Nirmal Chakraborty
# Copyright (c) 2025. All rights reserved.
# See LICENSE for details.

"""ReconCraft MCP integration package.

Exposes ReconCraft's plugin-based recon/scan tools over the Model Context
Protocol (MCP) so MCP-capable clients (Claude Code, Codex, Kimi, etc.) can
trigger them. Purely additive: it reuses the existing plugin contract via
``core.headless_runner`` and does not alter the GUI or any plugin.
"""

__all__ = ["server"]
