# ReconCraft by Nirmal Chakraborty
# Copyright (c) 2025. All rights reserved.
# See LICENSE for details.

"""
    Discover and import all plugins under the 'plugins' package.
    Returns a dict {name: module}.
    """
from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Dict, Optional


# Files we never load as plugins (case-insensitive stem match)
IGNORE_STEMS = {"__init__", "template"}  # keeps your template.py ignored


def _find_plugins_dir(start_file: Optional[Path] = None) -> tuple[Optional[Path], Optional[Path]]:
    """
    Try to locate the real <project_root>/plugins directory in a robust way.

    1) Prefer Python's import system (find_spec('plugins')) to get the package dir.
    2) Fallback: walk upward from this file (or a provided start_file) until 'plugins' is found.

    Returns:
        (plugin_dir, project_root) or (None, None) if not found.
    """
    # 1) Look up as an importable package
    spec = importlib.util.find_spec("plugins")
    if spec and spec.submodule_search_locations:
        plugin_dir = Path(list(spec.submodule_search_locations)[0]).resolve()
        project_root = plugin_dir.parent
        return plugin_dir, project_root

    # 2) Fallback: walk up directories to find a 'plugins' folder
    here = (start_file or Path(__file__)).resolve()
    for p in [here.parent, *here.parents]:
        candidate = p / "plugins"
        if candidate.is_dir():
            return candidate.resolve(), p.resolve()

    return None, None


def _should_ignore(path: Path) -> bool:
    """
    Decide whether a file should be ignored by the loader.
    """
    name = path.name
    stem = path.stem.lower()

    # Only .py files are considered
    if path.suffix != ".py":
        return True

    # Ignore __init__.py and template.py (case-insensitive)
    if stem in IGNORE_STEMS:
        return True

    # Skip dunder/hidden and common junk/disabled suffixes
    if name.startswith("__") or name.startswith("_"):
        return True
    if name.endswith((".bak", ".disabled", ".example", ".tmp", "~")):
        return True

    return False


def discover_plugins(run_validate: bool = True, verbose: bool = True) -> Dict[str, object]:
    """
    Discover and import all modules under the 'plugins' package.

    Args:
        run_validate: if True and a plugin exposes validate(), call it and skip on failure.
        verbose:      if True, print loader status and reasons for skipping.

    Returns:
        Dict[str, module] mapping plugin name -> imported module.
    """
    plugin_map: Dict[str, object] = {}

    plugin_dir, project_root = _find_plugins_dir()
    if plugin_dir is None or project_root is None:
        if verbose:
            print(f"[Plugin loader] Could not locate 'plugins' directory from {Path(__file__).resolve()}")
        return plugin_map

    # Ensure the project root is importable so 'import plugins.x' works consistently
    root_str = str(project_root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    if verbose:
        print(f"[Plugin loader] Using plugins dir: {plugin_dir}")

    # Iterate deterministically
    for file in sorted(plugin_dir.iterdir(), key=lambda p: p.name.lower()):
        if not file.is_file() or _should_ignore(file):
            continue

        plugin_name = file.stem
        module_name = f"plugins.{plugin_name}"

        try:
            module = importlib.import_module(module_name)
        except Exception as e:
            if verbose:
                print(f"[Plugin import] skip {plugin_name}: {e}")
            continue

        if run_validate and hasattr(module, "validate"):
            try:
                module.validate()
            except Exception as e:
                if verbose:
                    print(f"[Plugin validate] skip {plugin_name}: {e}")
                continue

        plugin_map[plugin_name] = module

    return plugin_map


def list_plugin_names(run_validate: bool = True) -> list[str]:
    """
    Convenience: return the list of discovered plugin names.
    """
    return sorted(discover_plugins(run_validate=run_validate, verbose=False).keys())
