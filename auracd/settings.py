from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any


DEFAULTS: dict[str, Any] = {
    "musicbrainz_contact": "",
    "auto_lyrics": True,
    "default_volume": 80,
}


class SettingsStore:
    """Armazena preferências fora da pasta do programa.

    Em uma instalação normal o arquivo fica em:
    ``%APPDATA%\\AuraCD\\settings.json``.
    Chaves antigas de versões anteriores são simplesmente ignoradas.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        if base_dir is None:
            appdata = os.getenv("APPDATA")
            base_dir = Path(appdata) / "AuraCD" if appdata else Path.home() / ".auracd"
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.base_dir / "settings.json"
        self._lock = threading.RLock()
        self._values = dict(DEFAULTS)
        self._load()

    def _load(self) -> None:
        with self._lock:
            if not self.path.exists():
                return
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return
            if isinstance(payload, dict):
                for key in DEFAULTS:
                    if key in payload:
                        self._values[key] = payload[key]

    def save(self) -> None:
        with self._lock:
            temp = self.path.with_suffix(".tmp")
            temp.write_text(json.dumps(self._values, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(self.path)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._values.get(key, default)

    def update(self, values: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            for key in DEFAULTS:
                if key not in values:
                    continue
                value = values[key]
                if key == "auto_lyrics":
                    self._values[key] = bool(value)
                elif key == "default_volume":
                    try:
                        self._values[key] = max(0, min(100, int(value)))
                    except (TypeError, ValueError):
                        pass
                else:
                    self._values[key] = str(value or "").strip()
            self.save()
            return dict(self._values)

    def public(self) -> dict[str, Any]:
        with self._lock:
            return {
                "musicbrainz_contact": str(self._values.get("musicbrainz_contact") or ""),
                "auto_lyrics": bool(self._values.get("auto_lyrics", True)),
                "default_volume": int(self._values.get("default_volume", 80)),
                "settings_path": str(self.path),
            }
