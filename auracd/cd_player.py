from __future__ import annotations

import atexit
import base64
import ctypes
import hashlib
import os
import queue
import string
import threading
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from .libdiscid_reader import read_disc as read_disc_with_libdiscid


class MCIError(RuntimeError):
    """Erro retornado pela API multimídia MCI do Windows."""


@dataclass(frozen=True)
class TrackTOC:
    number: int
    offset_frames: int
    length_frames: int

    @property
    def duration_seconds(self) -> float:
        return round(self.length_frames / 75.0, 3)


T = TypeVar("T")


class CDPlayer:
    """Controla CDs de áudio pelo MCI nativo do Windows.

    Todas as chamadas MCI são executadas em uma única thread dedicada. Isso é
    importante porque alguns drivers de leitor óptico perdem o alias do
    dispositivo quando comandos MCI são enviados alternadamente por threads
    diferentes (monitor do CD e rotas do Flask).
    """

    DRIVE_CDROM = 5

    def __init__(self, alias: str = "auracd") -> None:
        if os.name != "nt":
            raise RuntimeError("O controle de CD desta versão requer Windows 10 ou 11.")

        self.alias = alias
        self._winmm = ctypes.WinDLL("winmm")
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._lock = threading.RLock()

        self._opened_drive: str | None = None
        self._toc: dict[str, Any] | None = None
        self._current_track = 1
        self._last_volume = 80

        self._software_paused = False
        self._paused_track = 1
        self._paused_position = 0.0

        self._worker_ident: int | None = None
        self._shutdown = False
        self._commands: queue.Queue[Any] = queue.Queue()
        self._worker = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="AuraCD-MCI",
        )
        self._worker.start()
        atexit.register(self.shutdown)

    # ------------------------------------------------------------------
    # Thread dedicada ao MCI
    # ------------------------------------------------------------------
    def _worker_loop(self) -> None:
        self._worker_ident = threading.get_ident()
        while True:
            item = self._commands.get()
            if item is None:
                return

            callback, args, kwargs, completed, result_box = item
            try:
                result_box["value"] = callback(*args, **kwargs)
            except BaseException as exc:  # devolve o erro à thread solicitante
                result_box["error"] = exc
            finally:
                completed.set()

    def _on_worker(self) -> bool:
        return threading.get_ident() == self._worker_ident

    def _dispatch(self, callback: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        if self._on_worker():
            return callback(*args, **kwargs)
        if self._shutdown:
            raise MCIError("O controlador do CD já foi encerrado.")

        completed = threading.Event()
        result_box: dict[str, Any] = {}
        self._commands.put((callback, args, kwargs, completed, result_box))
        if not completed.wait(timeout=20):
            raise MCIError("O leitor de CD demorou demais para responder.")
        if "error" in result_box:
            raise result_box["error"]
        return result_box.get("value")

    def shutdown(self) -> None:
        if self._shutdown:
            return
        try:
            self.close()
        except Exception:
            pass
        self._shutdown = True
        self._commands.put(None)
        if self._worker.is_alive() and not self._on_worker():
            self._worker.join(timeout=2)

    # ------------------------------------------------------------------
    # MCI helpers
    # ------------------------------------------------------------------
    def _send(self, command: str, buffer_size: int = 512) -> str:
        buffer = ctypes.create_unicode_buffer(buffer_size)
        result = self._winmm.mciSendStringW(command, buffer, buffer_size, None)
        if result != 0:
            error_buffer = ctypes.create_unicode_buffer(512)
            self._winmm.mciGetErrorStringW(result, error_buffer, 512)
            message = error_buffer.value or f"Código MCI {result}"
            raise MCIError(f"{message} | comando: {command}")
        return buffer.value.strip()

    @staticmethod
    def _normalize_drive(drive: str) -> str:
        clean = drive.strip().upper().replace("\\", "").replace("/", "")
        if len(clean) == 1 and clean in string.ascii_uppercase:
            clean += ":"
        if len(clean) != 2 or clean[1] != ":" or clean[0] not in string.ascii_uppercase:
            raise ValueError("Unidade inválida. Use o formato D:.")
        return clean

    @staticmethod
    def _msf_to_frames(value: str) -> int:
        parts = [int(part) for part in value.split(":") if part != ""]
        if len(parts) < 3:
            raise MCIError(f"Tempo MSF inesperado: {value!r}")
        minutes, seconds, frames = parts[-3:]
        return ((minutes * 60) + seconds) * 75 + frames

    @staticmethod
    def _tmsf_to_parts(value: str) -> tuple[int, int, int, int]:
        parts = [int(part) for part in value.split(":") if part != ""]
        if len(parts) == 4:
            return parts[0], parts[1], parts[2], parts[3]
        if len(parts) == 3:
            return 1, parts[0], parts[1], parts[2]
        raise MCIError(f"Tempo TMSF inesperado: {value!r}")

    @staticmethod
    def _seconds_to_tmsf(track: int, seconds: float) -> str:
        seconds = max(0.0, float(seconds))
        whole = int(seconds)
        frames = int(round((seconds - whole) * 75))
        if frames >= 75:
            whole += 1
            frames = 0
        minutes, secs = divmod(whole, 60)
        return f"{track}:{minutes}:{secs}:{frames}"

    @staticmethod
    def _musicbrainz_disc_id(first_track: int, last_track: int, leadout: int, offsets: list[int]) -> str:
        payload = f"{first_track:02X}{last_track:02X}{leadout:08X}"
        for index in range(99):
            value = offsets[index] if index < len(offsets) else 0
            payload += f"{value:08X}"

        digest = hashlib.sha1(payload.encode("ascii")).digest()
        encoded = base64.b64encode(digest).decode("ascii")
        return encoded.replace("+", ".").replace("/", "_").replace("=", "-")

    def _open_alias(self, drive: str) -> None:
        try:
            self._send(f"open {drive} type cdaudio alias {self.alias} shareable")
        except MCIError:
            self._send(f"open {drive} type cdaudio alias {self.alias}")
        self._send(f"set {self.alias} time format tmsf")

    def _ensure_open(self) -> None:
        """Confirma que o alias MCI continua válido e o reabre se necessário."""
        if not self._opened_drive:
            raise MCIError("Nenhum leitor de CD foi aberto.")

        try:
            self._send(f"status {self.alias} mode")
            return
        except MCIError:
            pass

        drive = self._opened_drive
        toc = self._toc
        current_track = self._current_track
        paused = self._software_paused
        paused_track = self._paused_track
        paused_position = self._paused_position

        try:
            self._send(f"close {self.alias}")
        except Exception:
            pass

        self._open_alias(drive)
        self._opened_drive = drive
        self._toc = toc
        self._current_track = current_track
        self._software_paused = paused
        self._paused_track = paused_track
        self._paused_position = paused_position

    # ------------------------------------------------------------------
    # Unidade e mídia
    # ------------------------------------------------------------------
    def list_cd_drives(self) -> list[str]:
        drives: list[str] = []
        with self._lock:
            for letter in string.ascii_uppercase:
                root = f"{letter}:\\"
                if self._kernel32.GetDriveTypeW(root) == self.DRIVE_CDROM:
                    drives.append(f"{letter}:")
        return drives

    @property
    def opened_drive(self) -> str | None:
        with self._lock:
            return self._opened_drive

    def open_drive(self, drive: str) -> None:
        if not self._on_worker():
            return self._dispatch(self.open_drive, drive)

        normalized = self._normalize_drive(drive)
        with self._lock:
            if self._opened_drive == normalized:
                try:
                    self._ensure_open()
                    return
                except MCIError:
                    pass

            self.close()
            self._open_alias(normalized)
            self._opened_drive = normalized
            self._toc = None
            self._software_paused = False

    def close(self) -> None:
        if not self._on_worker():
            return self._dispatch(self.close)

        with self._lock:
            if self._opened_drive:
                try:
                    self._send(f"close {self.alias}")
                except Exception:
                    pass
            self._opened_drive = None
            self._toc = None
            self._software_paused = False

    def media_present(self, drive: str | None = None) -> bool:
        if not self._on_worker():
            return self._dispatch(self.media_present, drive)

        with self._lock:
            if drive:
                self.open_drive(drive)
            if not self._opened_drive:
                return False
            try:
                self._ensure_open()
                result = self._send(f"status {self.alias} media present").lower()
                return result in {"true", "1", "yes", "on"}
            except MCIError:
                return False

    def read_toc(self, drive: str) -> dict[str, Any] | None:
        if not self._on_worker():
            return self._dispatch(self.read_toc, drive)

        with self._lock:
            drive = self._normalize_drive(drive)

            # O libdiscid é a fonte preferencial para Disc ID, TOC, MCN e ISRC.
            # Se a DLL não estiver disponível, o AuraCD usa o leitor MCI abaixo.
            lib_toc = read_disc_with_libdiscid(drive)
            self.open_drive(drive)
            if not self.media_present():
                return None
            if lib_toc:
                self._toc = lib_toc
                self._current_track = 1
                self._software_paused = False
                return lib_toc

            self._send(f"set {self.alias} time format msf")
            try:
                track_count = int(self._send(f"status {self.alias} number of tracks"))
                if track_count <= 0:
                    return None

                tracks: list[TrackTOC] = []
                for number in range(1, track_count + 1):
                    start = self._send(f"status {self.alias} position track {number}")
                    length = self._send(f"status {self.alias} length track {number}")
                    tracks.append(
                        TrackTOC(
                            number=number,
                            offset_frames=self._msf_to_frames(start),
                            length_frames=self._msf_to_frames(length),
                        )
                    )

                if tracks and tracks[0].offset_frames < 150:
                    tracks = [
                        TrackTOC(
                            number=item.number,
                            offset_frames=item.offset_frames + 150,
                            length_frames=item.length_frames,
                        )
                        for item in tracks
                    ]

                offsets = [item.offset_frames for item in tracks]
                leadout = tracks[-1].offset_frames + tracks[-1].length_frames
                disc_id = self._musicbrainz_disc_id(1, track_count, leadout, offsets)
                toc_string = "+".join(
                    ["1", str(track_count), str(leadout), *[str(value) for value in offsets]]
                )

                result: dict[str, Any] = {
                    "drive": self._opened_drive,
                    "disc_id": disc_id,
                    "toc": toc_string,
                    "first_track": 1,
                    "last_track": track_count,
                    "leadout": leadout,
                    "track_count": track_count,
                    "reader": "mci",
                    "submission_url": f"https://musicbrainz.org/cdtoc/{disc_id}",
                    "tracks": [
                        {
                            "number": item.number,
                            "offset_frames": item.offset_frames,
                            "length_frames": item.length_frames,
                            "duration": item.duration_seconds,
                        }
                        for item in tracks
                    ],
                }
                self._toc = result
                self._current_track = 1
                self._software_paused = False
                return result
            finally:
                try:
                    self._send(f"set {self.alias} time format tmsf")
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Reprodução
    # ------------------------------------------------------------------
    def _require_toc(self) -> dict[str, Any]:
        if not self._toc:
            raise MCIError("Nenhum CD foi carregado.")
        return self._toc

    def play_track(self, track: int, offset_seconds: float = 0.0) -> None:
        if not self._on_worker():
            return self._dispatch(self.play_track, track, offset_seconds)

        with self._lock:
            toc = self._require_toc()
            self._ensure_open()
            self._send(f"set {self.alias} time format tmsf")

            track_count = int(toc["track_count"])
            if track < 1 or track > track_count:
                raise ValueError(f"Faixa deve estar entre 1 e {track_count}.")

            duration = float(toc["tracks"][track - 1]["duration"])
            offset_seconds = min(max(0.0, float(offset_seconds)), max(0.0, duration - 0.2))
            start = self._seconds_to_tmsf(track, offset_seconds)

            # Alguns drivers retornam erro ao receber STOP quando já estão parados.
            try:
                mode = self._send(f"status {self.alias} mode").lower()
            except MCIError:
                self._ensure_open()
                mode = "stopped"
            if mode in {"playing", "paused", "seeking", "recording"}:
                try:
                    self._send(f"stop {self.alias}")
                except MCIError:
                    # O PLAY com FROM reposiciona o dispositivo mesmo que o
                    # driver não aceite STOP neste estado.
                    pass

            if track < track_count:
                end = f"{track + 1}:0:0:0"
                self._send(f"play {self.alias} from {start} to {end}")
            else:
                self._send(f"play {self.alias} from {start}")

            self._current_track = track
            self._software_paused = False
            self._paused_track = track
            self._paused_position = offset_seconds

    def pause(self) -> None:
        if not self._on_worker():
            return self._dispatch(self.pause)

        with self._lock:
            self._require_toc()
            self._ensure_open()
            status = self.status()
            self._paused_track = int(status.get("track") or self._current_track)
            self._paused_position = float(status.get("position") or 0.0)
            try:
                self._send(f"pause {self.alias}")
            except MCIError:
                self._send(f"stop {self.alias}")
            self._software_paused = True

    def resume(self) -> None:
        if not self._on_worker():
            return self._dispatch(self.resume)

        with self._lock:
            self._require_toc()
            self._ensure_open()
            if self._software_paused:
                track = self._paused_track
                position = self._paused_position
                self.play_track(track, position)
                return
            try:
                self._send(f"resume {self.alias}")
            except MCIError:
                status = self.status()
                self.play_track(int(status["track"]), float(status["position"]))

    def stop(self) -> None:
        if not self._on_worker():
            return self._dispatch(self.stop)

        with self._lock:
            if not self._opened_drive:
                return
            try:
                self._ensure_open()
                mode = self._send(f"status {self.alias} mode").lower()
                if mode not in {"stopped", "not ready"}:
                    self._send(f"stop {self.alias}")
            except MCIError:
                # STOP é uma operação idempotente para a interface; se o
                # dispositivo já foi fechado/removido, não há nada a parar.
                pass
            self._software_paused = False

    def seek(self, seconds: float) -> None:
        if not self._on_worker():
            return self._dispatch(self.seek, seconds)

        with self._lock:
            self.play_track(self._current_track, seconds)

    def eject(self) -> None:
        if not self._on_worker():
            return self._dispatch(self.eject)

        with self._lock:
            if not self._opened_drive:
                return
            self._ensure_open()
            try:
                self._send(f"stop {self.alias}")
            except Exception:
                pass
            self._send(f"set {self.alias} door open")
            self._toc = None
            self._software_paused = False

    def close_tray(self) -> None:
        if not self._on_worker():
            return self._dispatch(self.close_tray)

        with self._lock:
            if self._opened_drive:
                self._ensure_open()
                self._send(f"set {self.alias} door closed")

    def set_volume(self, volume: int) -> bool:
        if not self._on_worker():
            return self._dispatch(self.set_volume, volume)

        volume = max(0, min(100, int(volume)))
        with self._lock:
            self._last_volume = volume
            if not self._opened_drive:
                return False
            try:
                self._ensure_open()
                self._send(f"setaudio {self.alias} volume to {volume * 10}")
                return True
            except MCIError:
                return False

    def status(self) -> dict[str, Any]:
        if not self._on_worker():
            return self._dispatch(self.status)

        with self._lock:
            if not self._opened_drive or not self._toc:
                return {
                    "mode": "stopped",
                    "track": self._current_track,
                    "position": 0.0,
                    "duration": 0.0,
                    "volume": self._last_volume,
                    "drive": self._opened_drive,
                }

            if self._software_paused:
                track = max(1, min(self._paused_track, int(self._toc["track_count"])))
                duration = float(self._toc["tracks"][track - 1]["duration"])
                return {
                    "mode": "paused",
                    "track": track,
                    "position": round(self._paused_position, 3),
                    "duration": round(duration, 3),
                    "volume": self._last_volume,
                    "drive": self._opened_drive,
                }

            try:
                self._ensure_open()
                mode = self._send(f"status {self.alias} mode").lower()
                current_track_raw = self._send(f"status {self.alias} current track")
                current_track = int(current_track_raw or self._current_track)
                position_raw = self._send(f"status {self.alias} position")
                _, minutes, seconds, frames = self._tmsf_to_parts(position_raw)
                position = minutes * 60 + seconds + frames / 75.0
                self._current_track = current_track
                duration = float(self._toc["tracks"][current_track - 1]["duration"])
                return {
                    "mode": mode,
                    "track": current_track,
                    "position": round(position, 3),
                    "duration": round(duration, 3),
                    "volume": self._last_volume,
                    "drive": self._opened_drive,
                }
            except (MCIError, ValueError, IndexError):
                return {
                    "mode": "stopped",
                    "track": self._current_track,
                    "position": 0.0,
                    "duration": 0.0,
                    "volume": self._last_volume,
                    "drive": self._opened_drive,
                }
