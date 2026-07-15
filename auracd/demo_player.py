from __future__ import annotations

import time
from typing import Any


class DemoCDPlayer:
    """Leitor simulado para desenvolvimento fora do Windows."""

    def __init__(self) -> None:
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
        self.track = track
        self.position = offset_seconds
        self.started = time.monotonic()
        self.mode = "playing"

    def pause(self) -> None:
        status = self.status()
        self.position = status["position"]
        self.mode = "paused"

    def resume(self) -> None:
        self.started = time.monotonic()
        self.mode = "playing"

    def stop(self) -> None:
        self.mode = "stopped"
        self.position = 0.0

    def seek(self, seconds: float) -> None:
        self.position = seconds
        self.started = time.monotonic()

    def set_volume(self, volume: int) -> bool:
        self.volume = max(0, min(100, int(volume)))
        return True

    def eject(self) -> None:
        self.stop()

    def close(self) -> None:
        self.stop()

    def shutdown(self) -> None:
        self.stop()

    def status(self) -> dict[str, Any]:
        position = self.position
        if self.mode == "playing":
            position += time.monotonic() - self.started
        duration = self.toc["tracks"][self.track - 1]["duration"]
        if position >= duration:
            self.mode = "stopped"
            position = duration
        return {
            "mode": self.mode,
            "track": self.track,
            "position": round(position, 3),
            "duration": duration,
            "volume": self.volume,
            "drive": self.drive,
        }
