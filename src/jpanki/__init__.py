"""Compatibility package for :mod:`jp_core`.

New projects should depend on ``jp-core`` and import ``jp_core`` directly.
This package preserves the published ``jpanki`` import paths while existing
consumers migrate.
"""
from __future__ import annotations

import sys

import jp_core
from jp_core import *  # noqa: F403

_MODULES = ("furigana", "ids", "model", "release", "romaji", "theme", "tts", "validate")

for _name in _MODULES:
    _module = __import__(f"jp_core.{_name}", fromlist=[_name])
    globals()[_name] = _module
    sys.modules[f"{__name__}.{_name}"] = _module

__all__ = [*jp_core.__all__, *_MODULES]
__version__ = jp_core.__version__
