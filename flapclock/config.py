"""JSON settings stored under the user's config directory."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


def config_path() -> Path:
    root = os.environ.get("XDG_CONFIG_HOME")
    base = Path(root) if root else Path.home() / ".config"
    return base / "flapclock" / "config.json"


@dataclass
class Settings:
    hour24: bool = True
    scale: float = 1.0
    x: int | None = None
    y: int | None = None
    idle_minutes: int = 5
    keep_above: bool = True

    @classmethod
    def load(cls) -> "Settings":
        path = config_path()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        if not isinstance(raw, dict):
            return cls()
        settings = cls()
        if isinstance(raw.get("hour24"), bool):
            settings.hour24 = raw["hour24"]
        if isinstance(raw.get("scale"), (int, float)):
            settings.scale = min(2.6, max(0.45, float(raw["scale"])))
        if isinstance(raw.get("x"), int):
            settings.x = raw["x"]
        if isinstance(raw.get("y"), int):
            settings.y = raw["y"]
        if isinstance(raw.get("idle_minutes"), int):
            settings.idle_minutes = min(240, max(0, raw["idle_minutes"]))
        if isinstance(raw.get("keep_above"), bool):
            settings.keep_above = raw["keep_above"]
        return settings

    def save(self) -> None:
        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")
