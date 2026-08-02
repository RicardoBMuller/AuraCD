from __future__ import annotations

import hashlib
import json
import threading
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests


SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


class CollectionStore:
    """Acervo pessoal persistente do AuraCD.

    O arquivo principal é salvo em ``%APPDATA%\\AuraCD\\collection.json``.
    Capas obtidas durante a identificação são copiadas para uma pasta local,
    para que a galeria continue visualmente útil mesmo sem internet.
    """

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.base_dir / "collection.json"
        self.covers_dir = self.base_dir / "collection_covers"
        self.covers_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._cover_jobs: set[str] = set()
        self._data: dict[str, Any] = {"schema": SCHEMA_VERSION, "albums": {}}
        self._load()

    def _load(self) -> None:
        with self._lock:
            if not self.path.exists():
                return
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return
            if isinstance(payload, dict) and isinstance(payload.get("albums"), dict):
                self._data = payload
                self._data["schema"] = SCHEMA_VERSION

    def _save(self) -> None:
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path)

    @staticmethod
    def _album_id(disc: dict[str, Any]) -> str:
        release_id = clean_text(disc.get("release_id"))
        if release_id:
            return f"release:{release_id}"
        disc_id = clean_text(disc.get("disc_id"), "unknown")
        return f"disc:{disc_id}"

    @staticmethod
    def _genres(disc: dict[str, Any]) -> list[str]:
        candidates: list[str] = []
        genre = clean_text(disc.get("genre"))
        if genre and genre.casefold() not in {"unknown", "desconhecido", "misc"}:
            candidates.append(genre)
        details = disc.get("artist_details") or {}
        for item in details.get("tags") or []:
            value = clean_text(item)
            if value:
                candidates.append(value)
        seen: set[str] = set()
        result: list[str] = []
        for value in candidates:
            key = value.casefold()
            if key in seen:
                continue
            seen.add(key)
            result.append(value)
            if len(result) >= 8:
                break
        return result

    def _download_cover(self, album_id: str, source_url: str) -> str | None:
        if not source_url.startswith(("http://", "https://")):
            return None
        parsed = urlparse(source_url)
        extension = Path(parsed.path).suffix.lower()
        if extension not in {".jpg", ".jpeg", ".png", ".webp"}:
            extension = ".jpg"
        filename = f"{hashlib.sha256(album_id.encode('utf-8')).hexdigest()[:24]}{extension}"
        destination = self.covers_dir / filename
        if destination.exists() and destination.stat().st_size > 1000:
            return filename
        try:
            response = requests.get(
                source_url,
                timeout=10,
                headers={"User-Agent": "AuraCD/2.6 personal collection"},
                allow_redirects=True,
            )
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "")
            if "image" not in content_type.lower() or len(response.content) > 12 * 1024 * 1024:
                return None
            destination.write_bytes(response.content)
            return filename
        except (requests.RequestException, OSError):
            return None

    def _schedule_cover(self, album_id: str, source_url: str) -> None:
        with self._lock:
            if album_id in self._cover_jobs:
                return
            self._cover_jobs.add(album_id)

        def worker() -> None:
            try:
                filename = self._download_cover(album_id, source_url)
                if not filename:
                    return
                with self._lock:
                    album = self._data.get("albums", {}).get(album_id)
                    if album:
                        album["cover_file"] = filename
                        self._save()
            finally:
                with self._lock:
                    self._cover_jobs.discard(album_id)

        threading.Thread(target=worker, daemon=True, name="AuraCD-CoverCache").start()

    def upsert_disc(self, disc: dict[str, Any]) -> str | None:
        if not disc or not disc.get("identified"):
            return None
        now = utc_now()
        album_id = self._album_id(disc)
        with self._lock:
            albums = self._data.setdefault("albums", {})
            current = albums.get(album_id) if isinstance(albums.get(album_id), dict) else {}
            previous_tracks = {
                int(item.get("number") or 0): item
                for item in current.get("tracks", [])
                if isinstance(item, dict)
            }
            tracks: list[dict[str, Any]] = []
            for index, source_track in enumerate(disc.get("tracks") or [], 1):
                number = int(source_track.get("number") or index)
                old = previous_tracks.get(number, {})
                tracks.append(
                    {
                        "number": number,
                        "title": clean_text(source_track.get("title"), f"Faixa {number:02d}"),
                        "artist": clean_text(source_track.get("artist"), clean_text(disc.get("artist"), "Artista desconhecido")),
                        "duration": float(source_track.get("duration") or 0),
                        "play_count": int(old.get("play_count") or 0),
                        "listened_seconds": float(old.get("listened_seconds") or 0),
                        "last_played": old.get("last_played"),
                    }
                )

            disc_ids = {clean_text(value) for value in current.get("disc_ids", []) if clean_text(value)}
            if clean_text(disc.get("disc_id")):
                disc_ids.add(clean_text(disc.get("disc_id")))

            cover_source = clean_text(disc.get("cover_url"))
            cover_file = clean_text(current.get("cover_file")) or None

            albums[album_id] = {
                "id": album_id,
                "disc_ids": sorted(disc_ids),
                "release_id": disc.get("release_id"),
                "release_group_id": disc.get("release_group_id"),
                "artist_id": disc.get("artist_id"),
                "artist": clean_text(disc.get("artist"), "Artista desconhecido"),
                "album": clean_text(disc.get("album"), "CD de áudio"),
                "year": clean_text(disc.get("year")),
                "country": clean_text(disc.get("country")),
                "source": clean_text(disc.get("source")),
                "cover_source": cover_source,
                "cover_file": cover_file,
                "genres": self._genres(disc),
                "track_count": len(tracks),
                "tracks": tracks,
                "play_count": int(current.get("play_count") or 0),
                "listened_seconds": float(current.get("listened_seconds") or 0),
                "added_at": current.get("added_at") or now,
                "last_seen": now,
                "last_played": current.get("last_played"),
            }
            self._save()
        if not cover_file and cover_source:
            self._schedule_cover(album_id, cover_source)
        return album_id

    def record_play(self, disc: dict[str, Any], track_number: int) -> None:
        album_id = self.upsert_disc(disc)
        if not album_id:
            return
        now = utc_now()
        with self._lock:
            album = self._data["albums"].get(album_id)
            if not album:
                return
            album["play_count"] = int(album.get("play_count") or 0) + 1
            album["last_played"] = now
            for track in album.get("tracks") or []:
                if int(track.get("number") or 0) == int(track_number):
                    track["play_count"] = int(track.get("play_count") or 0) + 1
                    track["last_played"] = now
                    break
            self._save()

    def add_listening_time(self, disc: dict[str, Any], track_number: int, seconds: float) -> None:
        if seconds <= 0 or not disc.get("identified"):
            return
        album_id = self._album_id(disc)
        with self._lock:
            album = self._data.get("albums", {}).get(album_id)
            if not album:
                return
            value = min(float(seconds), 60.0)
            album["listened_seconds"] = float(album.get("listened_seconds") or 0) + value
            for track in album.get("tracks") or []:
                if int(track.get("number") or 0) == int(track_number):
                    track["listened_seconds"] = float(track.get("listened_seconds") or 0) + value
                    break
            self._save()

    def clear(self) -> None:
        with self._lock:
            self._data = {"schema": SCHEMA_VERSION, "albums": {}}
            self._save()
            for file in self.covers_dir.glob("*"):
                try:
                    if file.is_file():
                        file.unlink()
                except OSError:
                    pass

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            albums = [dict(value) for value in self._data.get("albums", {}).values() if isinstance(value, dict)]

        for album in albums:
            cover_file = clean_text(album.get("cover_file"))
            album["cover_url"] = f"/api/collection/covers/{cover_file}" if cover_file else (
                clean_text(album.get("cover_source")) or "/static/img/disc-placeholder.svg"
            )

        albums.sort(key=lambda item: item.get("last_played") or item.get("last_seen") or item.get("added_at") or "", reverse=True)

        artist_stats: dict[str, dict[str, Any]] = {}
        genre_stats: dict[str, dict[str, Any]] = {}
        total_plays = 0
        total_seconds = 0.0
        total_tracks = 0
        for album in albums:
            plays = int(album.get("play_count") or 0)
            seconds = float(album.get("listened_seconds") or 0)
            total_plays += plays
            total_seconds += seconds
            total_tracks += int(album.get("track_count") or 0)

            artist = clean_text(album.get("artist"), "Artista desconhecido")
            artist_key = artist.casefold()
            artist_item = artist_stats.setdefault(artist_key, {"artist": artist, "albums": 0, "plays": 0, "listened_seconds": 0.0})
            artist_item["albums"] += 1
            artist_item["plays"] += plays
            artist_item["listened_seconds"] += seconds

            genres = album.get("genres") or ["Sem estilo definido"]
            for genre in genres:
                genre_name = clean_text(genre, "Sem estilo definido")
                genre_key = genre_name.casefold()
                genre_item = genre_stats.setdefault(genre_key, {"genre": genre_name, "albums": 0, "plays": 0, "listened_seconds": 0.0})
                genre_item["albums"] += 1
                genre_item["plays"] += plays
                genre_item["listened_seconds"] += seconds

        top_artists = sorted(
            artist_stats.values(),
            key=lambda item: (item["plays"], item["listened_seconds"], item["albums"]),
            reverse=True,
        )[:8]
        genres = sorted(
            genre_stats.values(),
            key=lambda item: (item["plays"] + item["albums"], item["listened_seconds"]),
            reverse=True,
        )[:12]
        top_albums = sorted(
            albums,
            key=lambda item: (int(item.get("play_count") or 0), float(item.get("listened_seconds") or 0)),
            reverse=True,
        )[:8]

        return {
            "ok": True,
            "summary": {
                "albums": len(albums),
                "artists": len(artist_stats),
                "tracks": total_tracks,
                "plays": total_plays,
                "listened_seconds": round(total_seconds, 2),
                "favorite_genre": genres[0]["genre"] if genres else "—",
            },
            "albums": albums,
            "top_albums": top_albums,
            "top_artists": top_artists,
            "genres": genres,
            "collection_path": str(self.path),
        }
