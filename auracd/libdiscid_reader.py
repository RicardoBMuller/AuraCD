from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

_DLL_HANDLES: list[Any] = []


def _candidate_vendor_dirs() -> list[Path]:
    here = Path(__file__).resolve().parent.parent
    bundle = Path(getattr(sys, "_MEIPASS", here))
    return [
        here / "vendor" / "libdiscid",
        bundle / "vendor" / "libdiscid",
        Path(sys.executable).resolve().parent / "vendor" / "libdiscid",
    ]


def prepare_dll_search_path() -> None:
    if os.name != "nt":
        return
    for directory in _candidate_vendor_dirs():
        if not directory.exists():
            continue
        try:
            handle = os.add_dll_directory(str(directory))
            _DLL_HANDLES.append(handle)
        except (AttributeError, OSError):
            os.environ["PATH"] = f"{directory}{os.pathsep}{os.environ.get('PATH', '')}"


def read_disc(drive: str) -> dict[str, Any] | None:
    """Lê o CD com libdiscid quando a DLL oficial estiver disponível.

    A aplicação continua funcionando com o leitor MCI caso libdiscid não esteja
    instalado. O retorno usa o mesmo formato esperado pelo restante do AuraCD.
    """

    prepare_dll_search_path()
    try:
        import discid  # type: ignore
    except (ImportError, OSError):
        return None

    try:
        try:
            disc = discid.read(drive, features=["mcn", "isrc"])
        except (NotImplementedError, ValueError):
            disc = discid.read(drive)
    except Exception:
        return None

    offsets: list[int] = []
    tracks: list[dict[str, Any]] = []
    for track in disc.tracks:
        offset = int(track.offset)
        sectors = int(track.sectors)
        offsets.append(offset)
        tracks.append(
            {
                "number": int(track.number),
                "offset_frames": offset,
                "length_frames": sectors,
                "duration": round(sectors / 75.0, 3),
                "isrc": getattr(track, "isrc", None),
            }
        )

    first = int(disc.first_track_num)
    last = int(disc.last_track_num)
    leadout = int(disc.sectors)
    toc = str(getattr(disc, "toc_string", "") or "").strip()
    if not toc:
        toc = "+".join([str(first), str(last), str(leadout), *map(str, offsets)])
    return {
        "drive": drive,
        "disc_id": str(disc.id),
        "toc": toc,
        "first_track": first,
        "last_track": last,
        "leadout": leadout,
        "track_count": len(tracks),
        "tracks": tracks,
        "mcn": getattr(disc, "mcn", None),
        "reader": "libdiscid",
        "submission_url": getattr(disc, "submission_url", None),
    }
