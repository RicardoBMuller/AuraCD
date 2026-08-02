from __future__ import annotations

import threading
import time
from typing import Any


class DemoCDPlayer:
    """Leitor simulado para desenvolvimento fora do Windows."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.drive = "D:"
        self.track = 1
        self.position = 0.0
        self.mode = "stopped"
        self.volume = 80
        self.started = 0.0
        durations = [212, 248, 193, 271, 227, 205, 259, 221, 246, 198]
        offset = 150
        tracks = []
        for number, duration in enumerate(durations, 1):
            frames = duration * 75
            tracks.append({
                "number": number,
                "offset_frames": offset,
                "length_frames": frames,
                "duration": float(duration),
            })
            offset += frames
        self.toc = {
            "drive": self.drive,
            "disc_id": "DEMO_AuraCD_000000000000000-",
            "toc": "+".join(["1", str(len(tracks)), str(offset), *[str(t["offset_frames"]) for t in tracks]]),
            "first_track": 1,
            "last_track": len(tracks),
            "leadout": offset,
            "track_count": len(tracks),
            "tracks": tracks,
            "reader": "demo",
            "submission_url": None,
        }

    def list_cd_drives(self) -> list[str]:
        return [self.drive]

    def open_drive(self, drive: str) -> None:
        self.drive = drive

    def media_present(self, drive: str | None = None) -> bool:
        return True

    def read_toc(self, drive: str) -> dict[str, Any]:
        return dict(self.toc)

    def play_track(self, track: int, offset_seconds: float = 0.0) -> None:
        with self._lock:
            self.track = track
            self.position = offset_seconds
            self.started = time.monotonic()
            self.mode = "playing"

    def pause(self) -> None:
        with self._lock:
            status = self._status_locked()
            self.position = status["position"]
            self.mode = "paused"

    def resume(self) -> None:
        with self._lock:
            self.started = time.monotonic()
            self.mode = "playing"

    def stop(self) -> None:
        with self._lock:
            self.mode = "stopped"
            self.position = 0.0

    def seek(self, seconds: float) -> None:
        with self._lock:
            self.position = seconds
            self.started = time.monotonic()

    def set_volume(self, volume: int) -> bool:
        with self._lock:
            self.volume = max(0, min(100, int(volume)))
            return True

    def eject(self) -> None:
        self.stop()

    def close(self) -> None:
        self.stop()

    def shutdown(self) -> None:
        self.stop()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return self._status_locked()

    def _status_locked(self) -> dict[str, Any]:
        # Só deve ser chamado com self._lock já adquirido.
        duration = self.toc["tracks"][self.track - 1]["duration"]
        if self.mode == "playing":
            position = self.position + (time.monotonic() - self.started)
            if position >= duration:
                # Guarda a posição final em self.position (e não apenas na
                # variável local) para que chamadas seguintes, mesmo já com
                # mode == "stopped", continuem reportando a posição real de
                # término em vez de "congelar" num valor antigo/zerado.
                position = duration
                self.position = duration
                self.mode = "stopped"
        else:
            position = self.position
        return {
            "mode": self.mode,
            "track": self.track,
            "position": round(position, 3),
            "duration": duration,
            "volume": self.volume,
            "drive": self.drive,
        }
