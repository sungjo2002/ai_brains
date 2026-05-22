from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .app_metadata import get_default_data_root


def sample_seed_path() -> Path:
    return get_default_data_root() / "sample" / "disabled" / "initial_seed.json"


def load_disabled_seed_data() -> dict[str, Any]:
    path = sample_seed_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
