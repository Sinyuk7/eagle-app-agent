"""Backward-compatible provider exports.

Implementations live in :mod:`moodtag_core.common`, :mod:`moodtag_core.remote`,
and :mod:`moodtag_core.ollama`; this module preserves the original import path.
"""

import subprocess  # noqa: F401  (legacy monkeypatch path)
import sys  # noqa: F401  (legacy monkeypatch path)
import time  # noqa: F401  (legacy monkeypatch path)

from .common import *  # noqa: F401,F403
from .ollama import (  # noqa: F401
    OLLAMA_PRESETS,
    OllamaVisionClient,
    moodtag_json_schema,
    validate_json_schema,
)
from .remote import VisionClient  # noqa: F401
