from __future__ import annotations

from pathlib import Path

import yaml

from .models import Config


def load_config(path: str | Path) -> Config:
    config_path = Path(path)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return Config.model_validate(data)
