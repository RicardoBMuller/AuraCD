from __future__ import annotations

import hashlib
import html
import json
import re
import threading
import time
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import quote, quote_plus, unquote, urlparse

import requests


CACHE_SCHEMA = 4


class JsonCache:
    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, key: str) -> Path:
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
        return self.directory / f"{digest}.json"

    def get(self, key: str, max_age: int | None = None) -> Any | None:
        path = self._path(key)
        with self._lock:
            if not path.exists():
                return None
            if max_age is not None and time.time() - path.stat().st_mtime > max_age:
                return None
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None

    def set(self, key: str, value: Any) -> None:
        path = self._path(key)
        temp = path.with_suffix(".tmp")
        with self._lock:
            temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(path)

    def delete(self, key: str) -> None:
        with self._lock:
            try:
                self._path(key).unlink(missing_ok=True)
            except OSError:
                pass

    def clear(self) -> None:
        with self._lock:
            for path in self.directory.glob("*.json"):
                try:
                    path.unlink()
                except OSError:
                    pass


class RateLimiter:
    def __init__(self, interval_seconds: float) -> None:
        self.interval = interval_seconds
        self._last_call = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            elapsed = time.monotonic() - self._last_call
            if elapsed < self.interval:
                time.sleep(self.interval - elapsed)
            self._last_call = time.monotonic()


class MetadataService:
    MUSICBRAINZ = "https://musicbrainz.org/ws/2"
    LRCLIB = "https://lrclib.net/api"
    YOUTUBE = "https://www.googleapis.com/youtube/v3"

    def __init__(
        self,
        cache_dir: Path,
        *,
        youtube_api_key: str = "",
        musicbrainz_contact: str = "",
    ) -> None:
        self.cache = JsonCache(cache_dir)
        self.session = requests.Session()
        self.mb_rate_limiter = RateLimiter(1.05)
        self._memory_lock = threading.RLock()
        self._lyrics_memory: dict[str, dict[str, Any]] = {}
        self._video_memory: dict[str, dict[str, Any]] = {}
        self.youtube_api_key = ""
        self.musicbrainz_contact = ""
        self.update_credentials(youtube_api_key, musicbrainz_contact)

    def update_credentials(self, youtube_api_key: str, musicbrainz_contact: str) -> None:
        new_youtube_key = str(youtube_api_key or "").strip()
        if new_youtube_key != self.youtube_api_key:
            with self._memory_lock:
                self._video_memory.clear()
        self.youtube_api_key = new_youtube_key
        self.musicbrainz_contact = str(musicbrainz_contact or "").strip()

    @property
    def youtube_configured(self) -> bool:
        return bool(self.youtube_api_key)

    def _headers(self, *, lrclib: bool = False) -> dict[str, str]:
        contact = self.musicbrainz_contact or "local-desktop-user"
        headers = {
            "User-Agent": f"AuraCD/2.4 ({contact})",
            "Accept": "application/json",
        }
        if lrclib:
            headers["Lrclib-Client"] = "AuraCD/2.4"
        return headers

    def _get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int = 18,
        musicbrainz: bool = False,
        allow_404: bool = False,
    ) -> Any | None:
        if musicbrainz:
            self.mb_rate_limiter.wait()
        response = self.session.get(
            url,
            params=params,
            headers=headers or self._headers(),
            timeout=timeout,
        )
        if allow_404 and response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _clean(value: str) -> str:
        value = unicodedata.normalize("NFKD", str(value or ""))
        value = "".join(char for char in value if not unicodedata.combining(char))
        value = re.sub(r"[^a-zA-Z0-9]+", " ", value.lower())
        return " ".join(value.split())

    @classmethod
    def _similarity(cls, left: str, right: str) -> float:
        return SequenceMatcher(None, cls._clean(left), cls._clean(right)).ratio()

    @staticmethod
    def _artist_credit(credit: list[dict[str, Any]] | None) -> tuple[str, str | None]:
        if not credit:
            return "Artista desconhecido", None
        names: list[str] = []
        primary_id: str | None = None
        for index, item in enumerate(credit):
            artist = item.get("artist") or {}
            name = item.get("name") or artist.get("name")
            if name:
                names.append(str(name) + str(item.get("joinphrase") or ""))
            if index == 0:
                primary_id = artist.get("id")
        return "".join(names).strip() or "Artista desconhecido", primary_id

    @staticmethod
    def _track_credit(track: dict[str, Any], fallback: str) -> str:
        credit = track.get("artist-credit") or (track.get("recording") or {}).get("artist-credit")
        if not credit:
            return fallback
        names: list[str] = []
        for item in credit:
            artist = item.get("artist") or {}
            names.append(str(item.get("name") or artist.get("name") or ""))
            names.append(str(item.get("joinphrase") or ""))
        return "".join(names).strip() or fallback

    @staticmethod
    def fallback_disc(toc: dict[str, Any], reason: str = "not_found") -> dict[str, Any]:
        return {
            "cache_schema": CACHE_SCHEMA,
            "identified": False,
            "identification_reason": reason,
            "needs_manual_search": True,
            "disc_id": toc["disc_id"],
            "album": "CD de áudio",
            "artist": "Artista desconhecido",
            "artist_id": None,
            "release_id": None,
            "release_group_id": None,
            "date": "",
            "year": "",
            "country": "",
            "cover_url": "/static/img/disc-placeholder.svg",
            "source": "toc",
            "submission_url": toc.get("submission_url"),
            "tracks": [
                {
                    "number": item["number"],
                    "title": f"Faixa {item['number']:02d}",
                    "artist": "Artista desconhecido",
                    "duration": item["duration"],
                    "recording_id": None,
                    "isrc": item.get("isrc"),
                }
                for item in toc["tracks"]
            ],
            "artist_details": {
                "name": "Artista desconhecido",
                "biography": "Pesquise o álbum para carregar biografia e discografia.",
                "discography": [],
                "tags": [],
                "source_url": None,
            },
        }

    # ------------------------------------------------------------------
    # Identificação do CD
    # ------------------------------------------------------------------
    def identify_disc(self, toc: dict[str, Any], *, force: bool = False) -> dict[str, Any]:
        disc_id = str(toc["disc_id"])
        cache_key = f"v{CACHE_SCHEMA}:disc:{disc_id}"
        choice_key = f"v{CACHE_SCHEMA}:choice:{disc_id}"

        if not force:
            cached = self.cache.get(cache_key, max_age=60 * 60 * 24 * 60)
            if cached and cached.get("identified"):
                return cached

        manual_choice = self.cache.get(choice_key)
        if manual_choice and manual_choice.get("release_id"):
            try:
                result = self.release_to_disc(str(manual_choice["release_id"]), toc, source="manual")
                self.cache.set(cache_key, result)
                return result
            except requests.RequestException:
                pass

        params = {
            "fmt": "json",
            "toc": toc["toc"],
            "cdstubs": "no",
            "media-format": "all",
            "inc": "artist-credits+recordings+release-groups+discids",
        }
        errors: list[str] = []
        payload: dict[str, Any] | None = None

        # Primeira tentativa: Disc ID calculado. Segunda: lookup puramente pela TOC.
        for lookup_id in (disc_id, "-"):
            try:
                candidate = self._get_json(
                    f"{self.MUSICBRAINZ}/discid/{quote(lookup_id, safe='._-')}",
                    params=params,
                    headers=self._headers(),
                    musicbrainz=True,
                    allow_404=True,
                )
                if candidate and (candidate.get("releases") or candidate.get("cdstub")):
                    payload = candidate
                    break
            except requests.RequestException as exc:
                errors.append(str(exc))

        releases = (payload or {}).get("releases") or []
        if releases:
            release, _medium = self._choose_release(releases, toc)
            release_id = release.get("id")
            if release_id:
                try:
                    result = self.release_to_disc(str(release_id), toc, source="musicbrainz")
                    self.cache.set(cache_key, result)
                    return result
                except requests.RequestException as exc:
                    errors.append(str(exc))

        # Segunda fonte: GnuDB (sucessora pública do FreeDB/CDDB). Ela costuma
        # reconhecer prensagens que ainda não possuem Disc ID no MusicBrainz.
        try:
            gnudb = self.lookup_gnudb(toc)
            if gnudb:
                # Com artista e álbum em mãos, tentamos enriquecer o resultado
                # usando uma edição equivalente no MusicBrainz (capa, IDs, etc.).
                query = f'artist:"{gnudb["artist"]}" AND release:"{gnudb["album"]}"'
                candidates = self.search_releases(query, int(toc["track_count"]))
                if candidates:
                    best = candidates[0]
                    if best.get("matches_track_count"):
                        try:
                            enriched = self.release_to_disc(str(best["release_id"]), toc, source="gnudb+musicbrainz")
                            self.cache.set(cache_key, enriched)
                            return enriched
                        except requests.RequestException as exc:
                            errors.append(str(exc))
                self.cache.set(cache_key, gnudb)
                return gnudb
        except requests.RequestException as exc:
            errors.append(str(exc))

        result = self.fallback_disc(toc, "network_error" if errors and not payload else "not_found")
        result["diagnostic"] = errors[-1] if errors else "Nenhuma edição compatível foi localizada pela TOC no MusicBrainz ou GnuDB."
        # Falhas não ficam presas por semanas. A próxima leitura tentará novamente.
        self.cache.set(f"v{CACHE_SCHEMA}:miss:{disc_id}", {"time": time.time(), "reason": result["identification_reason"]})
        return result

    # ------------------------------------------------------------------
    # GnuDB / protocolo CDDB (fallback de identificação)
    # ------------------------------------------------------------------
    @staticmethod
    def _cddb_digit_sum(value: int) -> int:
        return sum(int(char) for char in str(max(0, int(value))))

    @classmethod
    def _freedb_disc_id(cls, toc: dict[str, Any]) -> tuple[str, int]:
        offsets = [int(track.get("offset_frames") or 0) for track in toc.get("tracks") or []]
        if not offsets:
            raise ValueError("A TOC do CD não possui offsets de faixas.")
        first_seconds = offsets[0] // 75
        leadout_seconds = int(toc.get("leadout") or 0) // 75
        total_seconds = max(0, leadout_seconds - first_seconds)
        checksum = sum(cls._cddb_digit_sum(offset // 75) for offset in offsets) % 255
        disc_id = (checksum << 24) | (total_seconds << 8) | len(offsets)
        return f"{disc_id:08x}", total_seconds

    def _gnudb_request(self, command: str) -> str:
        contact = (self.musicbrainz_contact or "").strip()
        if "@" not in contact:
            return ""
        local, domain = contact.split("@", 1)
        local = re.sub(r"[^A-Za-z0-9._-]", "", local) or "auracd"
        domain = re.sub(r"[^A-Za-z0-9.-]", "", domain) or "example.com"
        hello = f"{local} {domain} AuraCD 2.6"
        response = self.session.get(
            "https://gnudb.gnudb.org/~cddb/cddb.cgi",
            params={"cmd": command, "hello": hello, "proto": 6},
            headers=self._headers(),
            timeout=18,
        )
        response.raise_for_status()
        return response.text.replace("\r\n", "\n")

    @staticmethod
    def _parse_xmcd(text: str) -> dict[str, Any]:
        values: dict[str, str] = {}
        for raw in text.splitlines():
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            key, value = raw.split("=", 1)
            values[key] = values.get(key, "") + value.replace("\\n", "\n").replace("\\t", "\t").replace("\\\\", "\\")
        title = values.get("DTITLE", "").strip()
        if " / " in title:
            artist, album = title.split(" / ", 1)
        elif "/" in title:
            artist, album = title.split("/", 1)
        else:
            artist = album = title
        tracks: list[str] = []
        index = 0
        while f"TTITLE{index}" in values:
            tracks.append(values[f"TTITLE{index}"].strip())
            index += 1
        return {
            "artist": artist.strip() or "Artista desconhecido",
            "album": album.strip() or "CD de áudio",
            "year": values.get("DYEAR", "").strip(),
            "genre": values.get("DGENRE", "").strip(),
            "tracks": tracks,
        }

    def lookup_gnudb(self, toc: dict[str, Any]) -> dict[str, Any] | None:
        if "@" not in (self.musicbrainz_contact or ""):
            return None
        offsets = [int(track.get("offset_frames") or 0) for track in toc.get("tracks") or []]
        disc_id, total_seconds = self._freedb_disc_id(toc)
        command = "cddb query " + " ".join(
            [disc_id, str(len(offsets)), *[str(value) for value in offsets], str(total_seconds)]
        )
        response = self._gnudb_request(command)
        lines = [line.strip() for line in response.splitlines() if line.strip() and line.strip() != "."]
        if not lines:
            return None
        code = lines[0].split(" ", 1)[0]
        matches: list[tuple[str, str]] = []
        if code == "200":
            parts = lines[0].split(" ", 3)
            if len(parts) >= 3:
                matches.append((parts[1], parts[2]))
        elif code in {"210", "211"}:
            for line in lines[1:]:
                parts = line.split(" ", 2)
                if len(parts) >= 2:
                    matches.append((parts[0], parts[1]))
        else:
            return None
        if not matches:
            return None

        category, matched_id = matches[0]
        detail = self._gnudb_request(f"cddb read {category} {matched_id}")
        detail_lines = detail.splitlines()
        if not detail_lines or not detail_lines[0].startswith(("210", "215")):
            return None
        parsed = self._parse_xmcd("\n".join(detail_lines[1:]))
        result = self.fallback_disc(toc, "gnudb")
        result.update(
            {
                "identified": True,
                "needs_manual_search": False,
                "album": parsed["album"],
                "artist": parsed["artist"],
                "date": parsed["year"],
                "year": parsed["year"][:4],
                "source": "gnudb",
                "genre": parsed["genre"],
            }
        )
        for index, track in enumerate(result["tracks"]):
            if index < len(parsed["tracks"]) and parsed["tracks"][index]:
                raw_title = parsed["tracks"][index]
                # Compilações costumam usar "Artista / Música" por faixa.
                if parsed["artist"].lower() in {"various", "various artists", "vários", "varios"} and " / " in raw_title:
                    track_artist, track_title = raw_title.split(" / ", 1)
                    track["artist"] = track_artist.strip() or parsed["artist"]
                    track["title"] = track_title.strip() or raw_title
                else:
                    track["artist"] = parsed["artist"]
                    track["title"] = raw_title
        result["artist_details"] = self.get_artist_details(None, parsed["artist"])
        return result

    def _choose_release(
        self, releases: list[dict[str, Any]], toc: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        best_release = releases[0]
        best_medium: dict[str, Any] | None = None
        best_score = -1
        for release in releases:
            media = release.get("media") or []
            for medium in media or [None]:
                score = 0
                if medium:
                    count = int(medium.get("track-count") or len(medium.get("tracks") or []))
                    if count == int(toc["track_count"]):
                        score += 50
                    discs = medium.get("discs") or []
                    if any(item.get("id") == toc["disc_id"] for item in discs):
                        score += 150
                    if str(medium.get("format") or "").lower() == "cd":
                        score += 8
                if release.get("status") == "Official":
                    score += 6
                if release.get("country") == "BR":
                    score += 3
                if score > best_score:
                    best_score = score
                    best_release = release
                    best_medium = medium
        return best_release, best_medium

    def search_releases(self, query: str, track_count: int = 0) -> list[dict[str, Any]]:
        query = str(query or "").strip()
        if len(query) < 2:
            return []
        payload = self._get_json(
            f"{self.MUSICBRAINZ}/release",
            params={"fmt": "json", "query": query, "limit": 20},
            headers=self._headers(),
            musicbrainz=True,
        )
        results: list[dict[str, Any]] = []
        for release in (payload or {}).get("releases") or []:
            artist, _artist_id = self._artist_credit(release.get("artist-credit"))
            media = release.get("media") or []
            counts = [int(item.get("track-count") or 0) for item in media]
            exact_count = track_count > 0 and track_count in counts
            score = int(release.get("score") or 0) + (20 if exact_count else 0)
            release_id = release.get("id")
            if not release_id:
                continue
            results.append(
                {
                    "release_id": release_id,
                    "album": release.get("title") or "Sem título",
                    "artist": artist,
                    "date": release.get("date") or "",
                    "country": release.get("country") or "",
                    "status": release.get("status") or "",
                    "track_counts": counts,
                    "matches_track_count": exact_count,
                    "score": score,
                    "cover_url": f"https://coverartarchive.org/release/{release_id}/front-250",
                }
            )
        return sorted(results, key=lambda item: (not item["matches_track_count"], -item["score"]))[:12]

    def select_release(self, release_id: str, toc: dict[str, Any]) -> dict[str, Any]:
        result = self.release_to_disc(release_id, toc, source="manual")
        self.cache.set(f"v{CACHE_SCHEMA}:choice:{toc['disc_id']}", {"release_id": release_id})
        self.cache.set(f"v{CACHE_SCHEMA}:disc:{toc['disc_id']}", result)
        return result

    def release_to_disc(self, release_id: str, toc: dict[str, Any], *, source: str) -> dict[str, Any]:
        payload = self._get_json(
            f"{self.MUSICBRAINZ}/release/{quote(release_id)}",
            params={
                "fmt": "json",
                "inc": "artist-credits+recordings+release-groups+discids",
            },
            headers=self._headers(),
            musicbrainz=True,
        )
        if not payload:
            raise requests.RequestException("Edição não encontrada no MusicBrainz.")

        album_artist, artist_id = self._artist_credit(payload.get("artist-credit"))
        media = payload.get("media") or []
        medium = self._best_medium_for_toc(media, toc)
        release_tracks = (medium or {}).get("tracks") or []

        tracks: list[dict[str, Any]] = []
        for index, physical in enumerate(toc["tracks"]):
            mb_track = release_tracks[index] if index < len(release_tracks) else {}
            recording = mb_track.get("recording") or {}
            tracks.append(
                {
                    "number": index + 1,
                    "title": mb_track.get("title") or recording.get("title") or f"Faixa {index + 1:02d}",
                    "artist": self._track_credit(mb_track, album_artist),
                    "duration": physical["duration"],
                    "recording_id": recording.get("id"),
                    "isrc": physical.get("isrc"),
                }
            )

        date = str(payload.get("date") or "")
        release_group = payload.get("release-group") or {}
        result = {
            "cache_schema": CACHE_SCHEMA,
            "identified": True,
            "needs_manual_search": False,
            "disc_id": toc["disc_id"],
            "album": payload.get("title") or "CD de áudio",
            "artist": album_artist,
            "artist_id": artist_id,
            "release_id": release_id,
            "release_group_id": release_group.get("id"),
            "date": date,
            "year": date[:4] if len(date) >= 4 else "",
            "country": payload.get("country") or "",
            "cover_url": f"https://coverartarchive.org/release/{release_id}/front-500",
            "source": source,
            "submission_url": toc.get("submission_url"),
            "tracks": tracks,
            "artist_details": self.get_artist_details(artist_id, album_artist),
        }
        return result

    @staticmethod
    def _best_medium_for_toc(media: list[dict[str, Any]], toc: dict[str, Any]) -> dict[str, Any] | None:
        if not media:
            return None
        target = int(toc["track_count"])
        exact = [item for item in media if int(item.get("track-count") or len(item.get("tracks") or [])) == target]
        if exact:
            cd = next((item for item in exact if str(item.get("format") or "").lower() == "cd"), None)
            return cd or exact[0]
        return min(media, key=lambda item: abs(int(item.get("track-count") or 0) - target))

    def save_custom_metadata(
        self,
        toc: dict[str, Any],
        *,
        artist: str,
        album: str,
        titles: list[str],
    ) -> dict[str, Any]:
        artist = artist.strip() or "Artista desconhecido"
        album = album.strip() or "CD de áudio"
        result = self.fallback_disc(toc, "manual_text")
        result.update(
            {
                "identified": True,
                "needs_manual_search": False,
                "artist": artist,
                "album": album,
                "source": "manual_text",
            }
        )
        for index, track in enumerate(result["tracks"]):
            track["artist"] = artist
            if index < len(titles) and str(titles[index]).strip():
                track["title"] = str(titles[index]).strip()
        result["artist_details"] = self.get_artist_details(None, artist)
        self.cache.set(f"v{CACHE_SCHEMA}:disc:{toc['disc_id']}", result)
        return result

    # ------------------------------------------------------------------
    # Artista, biografia e discografia
    # ------------------------------------------------------------------
    def get_artist_details(self, artist_id: str | None, artist_name: str) -> dict[str, Any]:
        cache_key = f"v{CACHE_SCHEMA}:artist:{artist_id or self._clean(artist_name)}"
        cached = self.cache.get(cache_key, max_age=60 * 60 * 24 * 30)
        if cached:
            return cached

        result: dict[str, Any] = {
            "name": artist_name,
            "type": "",
            "country": "",
            "begin": "",
            "end": "",
            "biography": "Biografia não encontrada.",
            "image": None,
            "source_url": None,
            "tags": [],
            "discography": [],
        }
        wikipedia_url: str | None = None

        if artist_id:
            try:
                artist_payload = self._get_json(
                    f"{self.MUSICBRAINZ}/artist/{artist_id}",
                    params={"fmt": "json", "inc": "url-rels+tags"},
                    headers=self._headers(),
                    musicbrainz=True,
                ) or {}
                life = artist_payload.get("life-span") or {}
                result.update(
                    {
                        "type": artist_payload.get("type") or "",
                        "country": artist_payload.get("country") or "",
                        "begin": life.get("begin") or "",
                        "end": life.get("end") or "",
                        "tags": [
                            item.get("name")
                            for item in sorted(
                                artist_payload.get("tags") or [],
                                key=lambda item: item.get("count", 0),
                                reverse=True,
                            )[:8]
                            if item.get("name")
                        ],
                    }
                )
                for relation in artist_payload.get("relations") or []:
                    resource = (relation.get("url") or {}).get("resource")
                    if relation.get("type") == "wikipedia" and resource:
                        wikipedia_url = resource
                        break
            except requests.RequestException:
                pass

            try:
                groups: list[dict[str, Any]] = []
                offset = 0
                while offset < 200:
                    page = self._get_json(
                        f"{self.MUSICBRAINZ}/release-group",
                        params={
                            "fmt": "json",
                            "artist": artist_id,
                            "type": "album|ep|single",
                            "limit": 100,
                            "offset": offset,
                        },
                        headers=self._headers(),
                        musicbrainz=True,
                    ) or {}
                    items = page.get("release-groups") or []
                    groups.extend(items)
                    offset += len(items)
                    if not items or len(groups) >= int(page.get("release-group-count") or len(groups)):
                        break
                seen: set[tuple[str, str]] = set()
                discography: list[dict[str, str]] = []
                for item in groups:
                    title = str(item.get("title") or "").strip()
                    kind = str(item.get("primary-type") or "Outro")
                    key = (title.lower(), kind.lower())
                    if not title or key in seen:
                        continue
                    seen.add(key)
                    discography.append(
                        {
                            "title": title,
                            "type": kind,
                            "date": str(item.get("first-release-date") or ""),
                            "id": str(item.get("id") or ""),
                        }
                    )
                result["discography"] = sorted(
                    discography,
                    key=lambda item: (item.get("date") or "9999", item.get("title") or ""),
                )
            except requests.RequestException:
                pass

        wiki = self._wikipedia_summary_from_url(wikipedia_url) if wikipedia_url else None
        if not wiki:
            wiki = self._search_wikipedia(artist_name)
        if wiki:
            result["biography"] = wiki.get("extract") or result["biography"]
            result["image"] = wiki.get("image")
            result["source_url"] = wiki.get("url")

        self.cache.set(cache_key, result)
        return result

    def _wikipedia_summary_from_url(self, url: str | None) -> dict[str, Any] | None:
        if not url:
            return None
        parsed = urlparse(url)
        if "wikipedia.org" not in parsed.netloc:
            return None
        language = parsed.netloc.split(".")[0]
        title = unquote(parsed.path.split("/wiki/")[-1]).replace("_", " ")
        return self._wikipedia_page(language, title)

    def _wikipedia_page(self, language: str, title: str) -> dict[str, Any] | None:
        try:
            payload = self._get_json(
                f"https://{language}.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "prop": "extracts|pageimages|info",
                    "exintro": 1,
                    "explaintext": 1,
                    "piprop": "thumbnail",
                    "pithumbsize": 700,
                    "inprop": "url",
                    "redirects": 1,
                    "format": "json",
                    "formatversion": 2,
                    "titles": title,
                },
                headers=self._headers(),
            ) or {}
            pages = (payload.get("query") or {}).get("pages") or []
            if not pages or pages[0].get("missing"):
                return None
            page = pages[0]
            return {
                "extract": page.get("extract") or "",
                "image": (page.get("thumbnail") or {}).get("source"),
                "url": page.get("fullurl"),
            }
        except requests.RequestException:
            return None

    def _search_wikipedia(self, artist_name: str) -> dict[str, Any] | None:
        if not artist_name or artist_name == "Artista desconhecido":
            return None
        for language in ("pt", "en"):
            try:
                payload = self._get_json(
                    f"https://{language}.wikipedia.org/w/api.php",
                    params={
                        "action": "query",
                        "list": "search",
                        "srsearch": artist_name,
                        "srlimit": 1,
                        "format": "json",
                        "formatversion": 2,
                    },
                    headers=self._headers(),
                ) or {}
                results = (payload.get("query") or {}).get("search") or []
                if results:
                    page = self._wikipedia_page(language, results[0]["title"])
                    if page:
                        return page
            except requests.RequestException:
                continue
        return None

    # ------------------------------------------------------------------
    # Letras
    # ------------------------------------------------------------------
    def get_lyrics(self, *, artist: str, title: str, album: str, duration: float) -> dict[str, Any]:
        if not artist or not title or title.lower().startswith("faixa "):
            return {
                "found": False,
                "provider": "LRCLIB",
                "message": "Identifique o álbum ou informe artista e música antes de buscar a letra.",
            }

        key = f"v{CACHE_SCHEMA}:lyrics:{self._clean(artist)}:{self._clean(title)}:{round(duration)}"
        with self._memory_lock:
            if key in self._lyrics_memory:
                return self._lyrics_memory[key]
        cached = self.cache.get(key, max_age=60 * 60 * 24 * 90)
        if cached and cached.get("found"):
            return cached

        payload: dict[str, Any] | None = None
        try:
            exact = self._get_json(
                f"{self.LRCLIB}/get",
                params={
                    "artist_name": artist,
                    "track_name": title,
                    "album_name": album,
                    "duration": round(duration),
                },
                headers=self._headers(lrclib=True),
                allow_404=True,
            )
            if isinstance(exact, dict):
                payload = exact
        except requests.RequestException:
            pass

        if not payload:
            try:
                candidates = self._get_json(
                    f"{self.LRCLIB}/search",
                    params={"track_name": title, "artist_name": artist},
                    headers=self._headers(lrclib=True),
                ) or []
                best_score = -1.0
                for item in candidates if isinstance(candidates, list) else []:
                    score = self._similarity(title, item.get("trackName") or "") * 0.65
                    score += self._similarity(artist, item.get("artistName") or "") * 0.30
                    item_duration = float(item.get("duration") or 0)
                    if duration and item_duration:
                        score += max(0.0, 0.05 - abs(duration - item_duration) / 600)
                    if score > best_score:
                        payload = item
                        best_score = score
                if best_score < 0.55:
                    payload = None
            except requests.RequestException:
                pass

        if not payload:
            result = {
                "found": False,
                "plain": "",
                "synced": "",
                "instrumental": False,
                "provider": "LRCLIB",
                "message": "A letra não foi encontrada na base pública.",
            }
        else:
            result = {
                "found": bool(payload.get("plainLyrics") or payload.get("syncedLyrics") or payload.get("instrumental")),
                "plain": payload.get("plainLyrics") or "",
                "synced": payload.get("syncedLyrics") or "",
                "instrumental": bool(payload.get("instrumental")),
                "provider": "LRCLIB",
                "track_name": payload.get("trackName") or title,
                "artist_name": payload.get("artistName") or artist,
                "message": "",
            }

        if result.get("found"):
            self.cache.set(key, result)
            with self._memory_lock:
                self._lyrics_memory[key] = result
        return result

    # ------------------------------------------------------------------
    # YouTube
    # ------------------------------------------------------------------
    def test_youtube(self) -> dict[str, Any]:
        """Valida a chave gastando somente 1 unidade de cota.

        search.list custa muito mais cota. Para o teste usamos videos.list com
        um vídeo público utilizado também nos exemplos oficiais do YouTube.
        """
        if not self.youtube_api_key:
            return {"ok": False, "message": "Nenhuma chave foi informada."}
        try:
            payload = self._get_json(
                f"{self.YOUTUBE}/videos",
                params={
                    "part": "id",
                    "id": "M7lc1UVf-VE",
                    "key": self.youtube_api_key,
                },
                headers=self._headers(),
            ) or {}
            items = payload.get("items") or []
            return {
                "ok": True,
                "message": "Chave válida e YouTube Data API v3 acessível." if items
                else "A API respondeu, mas não retornou o vídeo de validação.",
            }
        except requests.HTTPError as exc:
            return {"ok": False, "message": self._youtube_error(exc)}
        except requests.RequestException as exc:
            return {"ok": False, "message": f"Falha de rede ao consultar o YouTube: {exc}"}

    @staticmethod
    def _youtube_error(exc: requests.HTTPError) -> str:
        response = exc.response
        if response is None:
            return str(exc)
        reason = ""
        message = str(exc)
        try:
            payload = response.json()
            error = payload.get("error") or {}
            message = error.get("message") or message
            errors = error.get("errors") or []
            if errors:
                reason = str(errors[0].get("reason") or "")
            if not reason:
                for detail in error.get("details") or []:
                    reason = str(detail.get("reason") or detail.get("metadata", {}).get("reason") or "")
                    if reason:
                        break
        except Exception:
            pass
        normalized = reason.lower()
        hints = {
            "keyinvalid": "A chave informada é inválida.",
            "api_key_invalid": "A chave informada é inválida.",
            "accessnotconfigured": "Ative a YouTube Data API v3 no mesmo projeto da chave.",
            "service_disabled": "Ative a YouTube Data API v3 no mesmo projeto da chave.",
            "quotaexceeded": "A cota diária da API do YouTube foi excedida.",
            "dailylimitexceeded": "A cota diária da API do YouTube foi excedida.",
            "ratelimitexceeded": "O limite temporário de consultas do YouTube foi atingido.",
            "iprefererblocked": "A restrição da chave bloqueou o AuraCD. Para o backend local, use Nenhuma restrição de aplicativo ou uma restrição de IP compatível.",
            "forbidden": "A chave não possui permissão para usar a YouTube Data API v3.",
        }
        return hints.get(normalized, message)

    @classmethod
    def _youtube_candidate_score(
        cls,
        *,
        artist: str,
        title: str,
        candidate_title: str,
        channel: str,
        position: int,
    ) -> float:
        wanted_artist = cls._clean(artist)
        wanted_title = cls._clean(title)
        candidate = cls._clean(candidate_title)
        channel_clean = cls._clean(channel)
        score = cls._similarity(f"{wanted_artist} {wanted_title}", candidate) * 60
        title_words = [word for word in wanted_title.split() if len(word) > 2]
        artist_words = [word for word in wanted_artist.split() if len(word) > 2]
        score += sum(5 for word in title_words if word in candidate)
        score += sum(4 for word in artist_words if word in candidate or word in channel_clean)
        if any(marker in candidate for marker in ("official audio", "official video", "topic", "provided to youtube")):
            score += 12
        if any(marker in candidate for marker in ("reaction", "review", "tutorial", "cover by", "drum cover", "guitar cover")):
            score -= 18
        score -= position * 0.35
        return score

    def get_video(self, *, artist: str, title: str, force: bool = False) -> dict[str, Any]:
        query = " ".join(part.strip() for part in (artist, title) if str(part or "").strip())
        search_url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
        if not artist or not title or title.lower().startswith("faixa "):
            return {
                "found": False,
                "configured": self.youtube_configured,
                "search_url": search_url,
                "query": query,
                "message": "Identifique a música antes de procurar o vídeo.",
            }
        if not self.youtube_api_key:
            return {
                "found": False,
                "configured": False,
                "search_url": search_url,
                "query": query,
                "message": "Abra Configurações e informe uma chave da YouTube Data API v3.",
            }

        key = f"v{CACHE_SCHEMA}:video:{self._clean(artist)}:{self._clean(title)}"
        if not force:
            with self._memory_lock:
                if key in self._video_memory:
                    return self._video_memory[key]
            cached = self.cache.get(key, max_age=60 * 60 * 24 * 30)
            if cached and cached.get("found"):
                return cached

        try:
            search_payload = self._get_json(
                f"{self.YOUTUBE}/search",
                params={
                    "part": "snippet",
                    "q": query,
                    "type": "video",
                    "order": "relevance",
                    "maxResults": 10,
                    "videoEmbeddable": "true",
                    "videoSyndicated": "true",
                    "safeSearch": "moderate",
                    "key": self.youtube_api_key,
                },
                headers=self._headers(),
            ) or {}
            search_items = search_payload.get("items") or []
            video_ids = [
                str((entry.get("id") or {}).get("videoId"))
                for entry in search_items
                if (entry.get("id") or {}).get("videoId")
            ]
            if not video_ids:
                result = {
                    "found": False,
                    "configured": True,
                    "search_url": search_url,
                    "query": query,
                    "message": "A API não encontrou vídeos para esta faixa. Use o link de pesquisa direta.",
                }
            else:
                details_payload = self._get_json(
                    f"{self.YOUTUBE}/videos",
                    params={
                        "part": "snippet,status",
                        "id": ",".join(video_ids),
                        "key": self.youtube_api_key,
                    },
                    headers=self._headers(),
                ) or {}
                details_by_id = {str(item.get("id")): item for item in details_payload.get("items") or []}
                candidates: list[tuple[float, dict[str, Any]]] = []
                for position, search_item in enumerate(search_items):
                    video_id = str((search_item.get("id") or {}).get("videoId") or "")
                    details = details_by_id.get(video_id) or {}
                    status = details.get("status") or {}
                    if status.get("embeddable") is False or status.get("privacyStatus") not in (None, "public"):
                        continue
                    snippet = details.get("snippet") or search_item.get("snippet") or {}
                    candidate_title = html.unescape(str(snippet.get("title") or title))
                    channel = html.unescape(str(snippet.get("channelTitle") or "YouTube"))
                    score = self._youtube_candidate_score(
                        artist=artist,
                        title=title,
                        candidate_title=candidate_title,
                        channel=channel,
                        position=position,
                    )
                    candidates.append((score, {
                        "video_id": video_id,
                        "title": candidate_title,
                        "channel": channel,
                        "thumbnail": ((snippet.get("thumbnails") or {}).get("high") or (snippet.get("thumbnails") or {}).get("medium") or {}).get("url"),
                    }))

                if not candidates:
                    result = {
                        "found": False,
                        "configured": True,
                        "search_url": search_url,
                        "query": query,
                        "message": "Foram encontrados resultados, mas nenhum estava liberado para reprodução incorporada.",
                    }
                else:
                    _, chosen = max(candidates, key=lambda item: item[0])
                    video_id = chosen["video_id"]
                    result = {
                        "found": True,
                        "configured": True,
                        **chosen,
                        "query": query,
                        "embed_url": f"https://www.youtube.com/embed/{video_id}?rel=0&playsinline=1&autoplay=0",
                        "watch_url": f"https://www.youtube.com/watch?v={video_id}",
                        "search_url": search_url,
                    }
        except requests.HTTPError as exc:
            result = {
                "found": False,
                "configured": True,
                "search_url": search_url,
                "query": query,
                "message": self._youtube_error(exc),
            }
        except requests.RequestException as exc:
            result = {
                "found": False,
                "configured": True,
                "search_url": search_url,
                "query": query,
                "message": f"Falha de rede ao consultar o YouTube: {exc}",
            }

        if result.get("found"):
            self.cache.set(key, result)
            with self._memory_lock:
                self._video_memory[key] = result
        return result

