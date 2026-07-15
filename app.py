from __future__ import annotations

import argparse
import logging
import os
import random
import socket
import sys
import threading
import time
import traceback
import webbrowser
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_from_directory
from werkzeug.serving import BaseWSGIServer, make_server

from auracd.collection import CollectionStore
from auracd.demo_player import DemoCDPlayer
from auracd.metadata import MetadataService
from auracd.settings import SettingsStore


APP_VERSION = "2.6.0"
FROZEN = bool(getattr(sys, "frozen", False))
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
PROJECT_DIR = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
load_dotenv(PROJECT_DIR / ".env")

settings = SettingsStore()
collection_store = CollectionStore(settings.base_dir)
CACHE_DIR = settings.base_dir / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = settings.base_dir / "auracd.log"
_log_handlers: list[logging.Handler] = [logging.FileHandler(LOG_FILE, encoding="utf-8")]
if sys.stdout is not None:
    _log_handlers.append(logging.StreamHandler(sys.stdout))
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(threadName)s | %(message)s",
    handlers=_log_handlers,
    force=True,
)
logger = logging.getLogger("auracd")


def show_error_dialog(title: str, message: str) -> None:
    """Mostra um erro mesmo quando o programa foi iniciado fora do terminal."""
    logger.error("%s: %s", title, message)
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)
            return
        except Exception:
            pass


def unhandled_exception(exc_type: type[BaseException], exc: BaseException, tb: Any) -> None:
    details = "".join(traceback.format_exception(exc_type, exc, tb))
    logger.critical("Erro não tratado:\n%s", details)
    show_error_dialog(
        "AuraCD — erro ao iniciar",
        f"O AuraCD encontrou um erro e não pôde continuar.\n\n{exc}\n\nLog: {LOG_FILE}",
    )


sys.excepthook = unhandled_exception


_single_instance_handle: int | None = None


def acquire_single_instance() -> bool:
    """Impede duas cópias do aplicativo empacotado no mesmo usuário.

    O executável final é construído sem console. Quando o usuário clica duas
    vezes no atalho, mostramos apenas uma mensagem amigável em vez de iniciar
    dois servidores locais e dois controladores para o mesmo leitor de CD.
    """

    global _single_instance_handle
    if os.name != "nt" or not FROZEN:
        return True

    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        handle = kernel32.CreateMutexW(None, False, "Local\\AuraCD_Player_2_6")
        if not handle:
            return True

        ERROR_ALREADY_EXISTS = 183
        if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            show_error_dialog(
                "AuraCD já está aberto",
                "O AuraCD já está em execução. Verifique a janela aberta ou o ícone na barra de tarefas.",
            )
            return False

        _single_instance_handle = int(handle)
        return True
    except Exception:
        logger.exception("Não foi possível criar o bloqueio de instância única.")
        return True


def create_player() -> Any:
    demo = os.getenv("AURACD_DEMO", "0").lower() in {"1", "true", "yes"}
    if demo or os.name != "nt":
        return DemoCDPlayer()
    from auracd.cd_player import CDPlayer

    return CDPlayer()


player = create_player()
metadata_service = MetadataService(
    CACHE_DIR,
    youtube_api_key="",
    musicbrainz_contact=os.getenv("MUSICBRAINZ_CONTACT") or settings.get("musicbrainz_contact", ""),
)

app = Flask(
    __name__,
    template_folder=str(BUNDLE_DIR / "templates"),
    static_folder=str(BUNDLE_DIR / "static"),
)
app.config["JSON_AS_ASCII"] = False

state_lock = threading.RLock()
state: dict[str, Any] = {
    "version": APP_VERSION,
    "drives": [],
    "selected_drive": None,
    "disc": None,
    "metadata_loading": False,
    "error": None,
    "revision": 0,
}
current_toc: dict[str, Any] | None = None
force_scan = threading.Event()
shutdown_event = threading.Event()
server: BaseWSGIServer | None = None

# Estado de reprodução mantido no backend. O navegador continua sendo a
# interface, mas a troca automática de faixa não depende mais do timer do
# JavaScript. Isso evita falhas quando a aba fica em segundo plano ou quando o
# driver MCI retorna um estado transitório no final da música.
playback_lock = threading.RLock()
playback_state: dict[str, Any] = {
    "active": False,
    "paused": False,
    "track": 1,
    "repeat": "off",  # off | all | one
    "shuffle": False,
    "last_mode": "stopped",
    "last_position": 0.0,
    "last_duration": 0.0,
    "started_at": 0.0,
    "generation": 0,
}


def playback_snapshot() -> dict[str, Any]:
    with playback_lock:
        return deepcopy(playback_state)


def playback_mark_started(track: int) -> None:
    with playback_lock:
        playback_state.update(
            {
                "active": True,
                "paused": False,
                "track": int(track),
                "last_mode": "starting",
                "last_position": 0.0,
                "last_duration": 0.0,
                "started_at": time.monotonic(),
                "generation": int(playback_state.get("generation", 0)) + 1,
            }
        )


def playback_mark_paused() -> None:
    with playback_lock:
        playback_state["paused"] = True
        playback_state["last_mode"] = "paused"


def playback_mark_resumed() -> None:
    with playback_lock:
        playback_state["active"] = True
        playback_state["paused"] = False
        playback_state["last_mode"] = "starting"
        playback_state["started_at"] = time.monotonic()
        playback_state["generation"] = int(playback_state.get("generation", 0)) + 1


def playback_mark_stopped() -> None:
    with playback_lock:
        playback_state["active"] = False
        playback_state["paused"] = False
        playback_state["last_mode"] = "stopped"
        playback_state["last_position"] = 0.0
        playback_state["last_duration"] = 0.0
        playback_state["generation"] = int(playback_state.get("generation", 0)) + 1


def playback_next_track(current_track: int, track_count: int) -> int | None:
    with playback_lock:
        repeat = str(playback_state.get("repeat") or "off")
        shuffle = bool(playback_state.get("shuffle"))

    if track_count <= 0:
        return None
    if repeat == "one":
        return current_track
    if shuffle:
        if track_count == 1:
            return 1
        choices = [number for number in range(1, track_count + 1) if number != current_track]
        return random.choice(choices)
    if current_track < track_count:
        return current_track + 1
    if repeat == "all":
        return 1
    return None


def monitor_playback() -> None:
    """Detecta o fim da faixa e inicia a próxima no próprio backend.

    Alguns drivers ópticos retornam ``stopped`` apenas por uma fração de
    segundo e outros zeram a posição no exato final. Por isso guardamos a
    última posição válida e usamos uma pequena janela de tolerância.
    """

    stats_last_tick = time.monotonic()
    stats_buffer = 0.0
    stats_disc: dict[str, Any] | None = None
    stats_track = 0

    while not shutdown_event.is_set():
        try:
            status = player.status()
            mode = str(status.get("mode") or "stopped").lower()
            observed_track = int(status.get("track") or 1)
            position = max(0.0, float(status.get("position") or 0.0))
            duration = max(0.0, float(status.get("duration") or 0.0))
            now = time.monotonic()

            # Soma o tempo realmente reproduzido ao acervo. A gravação ocorre
            # em blocos para não acessar o disco a cada consulta do driver.
            elapsed_for_stats = max(0.0, min(now - stats_last_tick, 1.5))
            stats_last_tick = now
            current_disc_for_stats = snapshot().get("disc") or {}
            if mode == "playing" and current_disc_for_stats.get("identified"):
                current_key = (current_disc_for_stats.get("disc_id"), observed_track)
                previous_key = ((stats_disc or {}).get("disc_id"), stats_track)
                if stats_buffer > 0 and stats_disc and current_key != previous_key:
                    collection_store.add_listening_time(stats_disc, stats_track, stats_buffer)
                    stats_buffer = 0.0
                stats_disc = current_disc_for_stats
                stats_track = observed_track
                stats_buffer += elapsed_for_stats
                if stats_buffer >= 8.0:
                    collection_store.add_listening_time(stats_disc, stats_track, stats_buffer)
                    stats_buffer = 0.0
            elif stats_buffer > 0 and stats_disc:
                collection_store.add_listening_time(stats_disc, stats_track, stats_buffer)
                stats_buffer = 0.0

            with playback_lock:
                active = bool(playback_state.get("active"))
                paused = bool(playback_state.get("paused"))
                expected_track = int(playback_state.get("track") or observed_track)
                last_mode = str(playback_state.get("last_mode") or "stopped")
                last_position = float(playback_state.get("last_position") or 0.0)
                last_duration = float(playback_state.get("last_duration") or 0.0)
                started_at = float(playback_state.get("started_at") or 0.0)
                generation = int(playback_state.get("generation") or 0)

                # Alguns leitores continuam para a próxima faixa sozinhos.
                # Nesse caso apenas sincronizamos o estado, sem disparar outro
                # comando PLAY sobre uma música que já está tocando.
                if active and mode == "playing" and observed_track != expected_track:
                    playback_state["track"] = observed_track
                    playback_state["last_position"] = position
                    playback_state["last_duration"] = duration
                    playback_state["last_mode"] = "playing"
                    playback_state["started_at"] = now
                    continue

                if mode == "playing":
                    playback_state["active"] = True
                    playback_state["paused"] = False
                    playback_state["track"] = observed_track
                    playback_state["last_mode"] = "playing"
                    playback_state["last_position"] = position
                    if duration > 0:
                        playback_state["last_duration"] = duration
                    continue

                if mode == "paused" or paused:
                    playback_state["paused"] = True
                    playback_state["last_mode"] = "paused"
                    if position > 0:
                        playback_state["last_position"] = position
                    if duration > 0:
                        playback_state["last_duration"] = duration
                    continue

                if not active:
                    playback_state["last_mode"] = mode
                    continue

                effective_duration = duration or last_duration
                effective_position = max(position, last_position)
                near_end = effective_duration > 0 and effective_position >= max(0.0, effective_duration - 1.8)
                played_long_enough = (now - started_at) >= 1.2
                transitioned_from_playing = last_mode == "playing" and mode in {"stopped", "stop", "not ready"}
                ended = played_long_enough and (near_end or transitioned_from_playing)

                if not ended:
                    # Ignora estados transitórios de STOP logo após um PLAY.
                    playback_state["last_mode"] = mode
                    continue

                disc = snapshot().get("disc") or {}
                track_count = int(disc.get("track_count") or len(disc.get("tracks") or []))
                finished_track = expected_track
                next_track = playback_next_track(finished_track, track_count)

                # Desarma antes de sair do lock. Se outro comando do usuário
                # ocorrer, a geração muda e esta troca automática é descartada.
                playback_state["active"] = False
                playback_state["last_mode"] = "advancing"

            if next_track is None:
                playback_mark_stopped()
                continue

            try:
                player.play_track(next_track, 0.0)
                current_disc = snapshot().get("disc") or {}
                if current_disc.get("identified"):
                    collection_store.record_play(current_disc, next_track)
            except Exception as exc:
                logger.warning("Não foi possível iniciar automaticamente a faixa %s: %s", next_track, exc)
                playback_mark_stopped()
                continue

            with playback_lock:
                # Só confirma a troca se nenhum comando manual ocorreu durante
                # o pequeno intervalo entre a detecção e o PLAY.
                if int(playback_state.get("generation") or 0) == generation:
                    playback_state.update(
                        {
                            "active": True,
                            "paused": False,
                            "track": next_track,
                            "last_mode": "starting",
                            "last_position": 0.0,
                            "last_duration": 0.0,
                            "started_at": time.monotonic(),
                            "generation": generation + 1,
                        }
                    )
        except Exception as exc:
            logger.debug("Monitor de reprodução: %s", exc)

        shutdown_event.wait(0.28)


def mutate_state(callback: Callable[[dict[str, Any]], Any]) -> None:
    with state_lock:
        changed = callback(state)
        if changed is not False:
            state["revision"] = int(state.get("revision", 0)) + 1


def snapshot() -> dict[str, Any]:
    with state_lock:
        return deepcopy(state)


def basic_disc_from_toc(toc: dict[str, Any]) -> dict[str, Any]:
    return {
        "disc_id": toc["disc_id"],
        "drive": toc["drive"],
        "track_count": toc["track_count"],
        "reader": toc.get("reader", "mci"),
        "identified": False,
        "needs_manual_search": False,
        "album": "Lendo o CD…",
        "artist": "Buscando informações…",
        "cover_url": "/static/img/disc-placeholder.svg",
        "year": "",
        "country": "",
        "metadata_ready": False,
        "tracks": [
            {
                "number": item["number"],
                "title": f"Faixa {item['number']:02d}",
                "artist": "",
                "duration": item["duration"],
                "recording_id": None,
            }
            for item in toc["tracks"]
        ],
        "artist_details": {
            "name": "",
            "biography": "Buscando biografia e discografia…",
            "discography": [],
            "tags": [],
        },
    }


def apply_disc_metadata(metadata: dict[str, Any], toc: dict[str, Any]) -> None:
    metadata.update(
        {
            "drive": toc["drive"],
            "track_count": toc["track_count"],
            "reader": toc.get("reader", "mci"),
            "metadata_ready": True,
        }
    )
    if metadata.get("identified"):
        try:
            collection_store.upsert_disc(metadata)
        except Exception as exc:
            logger.warning("Não foi possível atualizar o acervo pessoal: %s", exc)

    def apply(current: dict[str, Any]) -> None:
        disc = current.get("disc")
        if disc and disc.get("disc_id") == toc["disc_id"]:
            current["disc"] = metadata
            current["metadata_loading"] = False
            current["error"] = None

    mutate_state(apply)


def load_metadata_async(toc: dict[str, Any], *, force: bool = False) -> None:
    try:
        metadata = metadata_service.identify_disc(toc, force=force)
        apply_disc_metadata(metadata, toc)
    except Exception as exc:
        def fail(current: dict[str, Any]) -> None:
            disc = current.get("disc")
            if disc and disc.get("disc_id") == toc["disc_id"]:
                current["metadata_loading"] = False
                current["error"] = f"Falha ao buscar informações: {exc}"
                disc["needs_manual_search"] = True
                disc["metadata_ready"] = True

        mutate_state(fail)


def clear_disc(error: str | None = None) -> None:
    global current_toc
    current_toc = None

    def apply(current: dict[str, Any]) -> None:
        current["disc"] = None
        current["metadata_loading"] = False
        current["error"] = error

    mutate_state(apply)


def monitor_disc() -> None:
    global current_toc
    while not shutdown_event.is_set():
        try:
            drives = player.list_cd_drives()
            with state_lock:
                selected = state.get("selected_drive")
                existing_disc = deepcopy(state.get("disc"))

            if selected not in drives:
                selected = drives[0] if drives else None

            def update_drives(current: dict[str, Any]) -> bool:
                changed = current.get("drives") != drives or current.get("selected_drive") != selected
                if not changed:
                    return False
                current["drives"] = drives
                current["selected_drive"] = selected
                if current.get("disc") and current["disc"].get("drive") != selected:
                    current["disc"] = None
                    current["metadata_loading"] = False
                return True

            mutate_state(update_drives)

            if not selected:
                try:
                    player.close()
                except Exception:
                    pass
                if existing_disc:
                    clear_disc("Nenhum leitor de CD/DVD foi encontrado.")
                shutdown_event.wait(2.0)
                continue

            should_scan = force_scan.is_set() or not existing_disc
            force_scan.clear()
            if existing_disc and existing_disc.get("drive") == selected and not should_scan:
                if not player.media_present(selected):
                    clear_disc(None)
                    player.close()
                shutdown_event.wait(2.0)
                continue

            toc = player.read_toc(selected)
            if not toc:
                if existing_disc:
                    clear_disc(None)
                shutdown_event.wait(2.0)
                continue

            current_toc = toc
            if not existing_disc or existing_disc.get("disc_id") != toc["disc_id"] or should_scan:
                basic = basic_disc_from_toc(toc)

                def set_basic(current: dict[str, Any]) -> None:
                    current["disc"] = basic
                    current["metadata_loading"] = True
                    current["error"] = None

                mutate_state(set_basic)
                threading.Thread(
                    target=load_metadata_async,
                    args=(toc,),
                    daemon=True,
                    name="AuraCD-Metadata",
                ).start()
        except Exception as exc:
            clear_disc(str(exc))
            try:
                player.close()
            except Exception:
                pass
        shutdown_event.wait(2.0)


monitor_thread = threading.Thread(target=monitor_disc, daemon=True, name="AuraCD-DiscMonitor")
monitor_thread.start()
playback_thread = threading.Thread(target=monitor_playback, daemon=True, name="AuraCD-PlaybackMonitor")
playback_thread.start()


# ----------------------------------------------------------------------
# Interface e configuração
# ----------------------------------------------------------------------
@app.get("/")
def index():
    return render_template("index.html", version=APP_VERSION)


@app.get("/api/health")
def api_health():
    return jsonify({"ok": True, "windows": os.name == "nt", "version": APP_VERSION})


@app.get("/api/settings")
def api_settings_get():
    public = settings.public()
    public["providers"] = {
        "metadata": "MusicBrainz + GnuDB",
        "covers": "Cover Art Archive",
        "biography": "Wikipedia",
        "lyrics": "LRCLIB",
        "collection": "Acervo local AuraCD",
    }
    return jsonify(public)


@app.post("/api/settings")
def api_settings_save():
    body = request.get_json(silent=True) or {}
    values = settings.update(body)
    metadata_service.update_credentials(
        "",
        values.get("musicbrainz_contact", "") or os.getenv("MUSICBRAINZ_CONTACT", ""),
    )
    # Uma alteração de contato pode liberar MusicBrainz/GnuDB. Reprocessa o
    # disco automaticamente para que o usuário não precise ejetá-lo.
    force_scan.set()
    return jsonify({"ok": True, **settings.public(), "rescan_requested": True})


@app.post("/api/cache/clear")
def api_clear_cache():
    metadata_service.cache.clear()
    force_scan.set()
    return jsonify({"ok": True, "message": "Cache apagado. O CD será pesquisado novamente."})


# ----------------------------------------------------------------------
# Acervo pessoal e estatísticas
# ----------------------------------------------------------------------
@app.get("/api/collection")
def api_collection():
    return jsonify(collection_store.snapshot())


@app.get("/api/collection/covers/<path:filename>")
def api_collection_cover(filename: str):
    return send_from_directory(collection_store.covers_dir, filename, conditional=True)


@app.post("/api/collection/clear")
def api_collection_clear():
    collection_store.clear()
    return jsonify({"ok": True, "message": "Acervo pessoal e estatísticas apagados. O CD atual voltará à galeria na próxima reprodução ou leitura."})


# ----------------------------------------------------------------------
# CD e identificação manual
# ----------------------------------------------------------------------
@app.get("/api/disc")
def api_disc():
    return jsonify(snapshot())


@app.post("/api/scan")
def api_scan():
    force_scan.set()
    return jsonify({"ok": True, "message": "Nova leitura solicitada."})


@app.post("/api/disc/retry")
def api_disc_retry():
    if not current_toc:
        return jsonify({"ok": False, "error": "Nenhum CD carregado."}), 409

    def loading(current: dict[str, Any]) -> None:
        current["metadata_loading"] = True
        current["error"] = None

    mutate_state(loading)
    threading.Thread(
        target=load_metadata_async,
        kwargs={"toc": deepcopy(current_toc), "force": True},
        daemon=True,
    ).start()
    return jsonify({"ok": True})


@app.post("/api/disc/search")
def api_disc_search():
    if not current_toc:
        return jsonify({"ok": False, "error": "Nenhum CD carregado."}), 409
    body = request.get_json(silent=True) or {}
    query = str(body.get("query") or "").strip()
    try:
        releases = metadata_service.search_releases(query, int(current_toc["track_count"]))
        return jsonify({"ok": True, "results": releases})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Falha na pesquisa: {exc}"}), 502


@app.post("/api/disc/select-release")
def api_disc_select_release():
    if not current_toc:
        return jsonify({"ok": False, "error": "Nenhum CD carregado."}), 409
    body = request.get_json(silent=True) or {}
    release_id = str(body.get("release_id") or "").strip()
    if not release_id:
        return jsonify({"ok": False, "error": "Edição inválida."}), 400
    try:
        result = metadata_service.select_release(release_id, deepcopy(current_toc))
        apply_disc_metadata(result, current_toc)
        return jsonify({"ok": True, "disc": result})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Não foi possível carregar o álbum: {exc}"}), 502


@app.post("/api/disc/custom")
def api_disc_custom():
    if not current_toc:
        return jsonify({"ok": False, "error": "Nenhum CD carregado."}), 409
    body = request.get_json(silent=True) or {}
    artist = str(body.get("artist") or "")
    album = str(body.get("album") or "")
    titles = body.get("titles") or []
    if not isinstance(titles, list):
        titles = []
    try:
        result = metadata_service.save_custom_metadata(
            deepcopy(current_toc),
            artist=artist,
            album=album,
            titles=[str(value) for value in titles],
        )
        apply_disc_metadata(result, current_toc)
        return jsonify({"ok": True, "disc": result})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.post("/api/drive")
def api_drive():
    body = request.get_json(silent=True) or {}
    drive = str(body.get("drive") or "").upper()
    drives = player.list_cd_drives()
    if drive not in drives:
        return jsonify({"ok": False, "error": "Leitor inválido."}), 400

    def apply(current: dict[str, Any]) -> None:
        current["selected_drive"] = drive
        current["disc"] = None
        current["metadata_loading"] = False
        current["error"] = None

    mutate_state(apply)
    player.close()
    force_scan.set()
    return jsonify({"ok": True, "drive": drive})


def current_disc_or_error() -> tuple[dict[str, Any] | None, Any | None]:
    disc = snapshot().get("disc")
    if not disc:
        return None, (jsonify({"ok": False, "error": "Insira um CD de áudio primeiro."}), 409)
    return disc, None


# ----------------------------------------------------------------------
# Player
# ----------------------------------------------------------------------
@app.get("/api/player/status")
def api_player_status():
    status = player.status()
    status["disc_id"] = (snapshot().get("disc") or {}).get("disc_id")
    playback = playback_snapshot()
    status["shuffle"] = bool(playback.get("shuffle"))
    status["repeat"] = str(playback.get("repeat") or "off")
    status["auto_advance"] = True
    return jsonify(status)


@app.post("/api/player/play")
def api_player_play():
    _disc, error = current_disc_or_error()
    if error:
        return error
    body = request.get_json(silent=True) or {}
    try:
        track = int(body.get("track") or 1)
        offset = float(body.get("offset") or 0)
        player.play_track(track, offset)
        playback_mark_started(track)
        disc = snapshot().get("disc") or {}
        if disc.get("identified"):
            collection_store.record_play(disc, track)
        return jsonify({"ok": True, "track": track, "auto_advance": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.post("/api/player/pause")
def api_player_pause():
    try:
        player.pause()
        playback_mark_paused()
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.post("/api/player/resume")
def api_player_resume():
    try:
        player.resume()
        playback_mark_resumed()
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.post("/api/player/stop")
def api_player_stop():
    player.stop()
    playback_mark_stopped()
    return jsonify({"ok": True})


@app.post("/api/player/options")
def api_player_options():
    body = request.get_json(silent=True) or {}
    repeat = str(body.get("repeat") or "off").lower()
    if repeat not in {"off", "all", "one"}:
        return jsonify({"ok": False, "error": "Modo de repetição inválido."}), 400
    with playback_lock:
        playback_state["repeat"] = repeat
        playback_state["shuffle"] = bool(body.get("shuffle", False))
    return jsonify({"ok": True, "repeat": repeat, "shuffle": bool(body.get("shuffle", False))})


@app.post("/api/player/seek")
def api_player_seek():
    body = request.get_json(silent=True) or {}
    try:
        seconds = float(body.get("seconds") or 0)
        player.seek(seconds)
        current = int(player.status().get("track") or playback_snapshot().get("track") or 1)
        playback_mark_started(current)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.post("/api/player/volume")
def api_player_volume():
    body = request.get_json(silent=True) or {}
    try:
        volume = int(body.get("volume") or 0)
        supported = player.set_volume(volume)
        normalized = max(0, min(100, volume))
        settings.update({"default_volume": normalized})
        return jsonify({"ok": True, "volume": normalized, "driver_supported": supported})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.post("/api/player/eject")
def api_player_eject():
    try:
        player.eject()
        playback_mark_stopped()
        clear_disc(None)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def find_track(number: int) -> tuple[dict[str, Any], dict[str, Any]] | None:
    disc = snapshot().get("disc")
    if not disc:
        return None
    tracks = disc.get("tracks") or []
    if number < 1 or number > len(tracks):
        return None
    return disc, tracks[number - 1]


@app.get("/api/track/<int:number>/lyrics")
def api_track_lyrics(number: int):
    found = find_track(number)
    if not found:
        return jsonify({"ok": False, "error": "Faixa não encontrada."}), 404
    disc, track = found
    result = metadata_service.get_lyrics(
        artist=track.get("artist") or disc.get("artist") or "",
        title=track.get("title") or "",
        album=disc.get("album") or "",
        duration=float(track.get("duration") or 0),
    )
    return jsonify({"ok": True, **result})


# ----------------------------------------------------------------------
# Inicialização desktop / navegador
# ----------------------------------------------------------------------
def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_http(port: int) -> threading.Thread:
    global server
    server = make_server("127.0.0.1", port, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="AuraCD-HTTP")
    thread.start()
    return thread


def cleanup() -> None:
    shutdown_event.set()
    if server:
        try:
            server.shutdown()
        except Exception:
            pass
    try:
        player.shutdown()
    except AttributeError:
        try:
            player.close()
        except Exception:
            pass
    except Exception:
        pass


def run_browser(url: str) -> None:
    logger.info("Abrindo AuraCD no navegador: %s", url)
    opened = webbrowser.open(url, new=1)
    if not opened:
        print(f"Abra manualmente: {url}", flush=True)
    print("AuraCD está em execução. Feche esta janela para encerrar o player.", flush=True)
    while not shutdown_event.wait(1):
        pass


def run_native(url: str) -> None:
    """Tenta abrir uma janela desktop e recua para o navegador se necessário."""
    try:
        import webview

        window = webview.create_window(
            "AuraCD",
            url,
            width=1260,
            height=850,
            min_size=(980, 680),
            background_color="#282019",
            text_select=True,
        )
        window.events.closed += cleanup
        webview.start(debug=False)
    except Exception as exc:
        logger.exception("A janela desktop não pôde ser aberta; usando o navegador.")
        print(f"Janela desktop indisponível ({exc}). Abrindo no navegador...", flush=True)
        run_browser(url)


def main() -> None:
    if not acquire_single_instance():
        return

    parser = argparse.ArgumentParser(description="AuraCD — player retrô de CDs")
    parser.add_argument("--native", action="store_true", help="tenta abrir em uma janela desktop")
    parser.add_argument("--browser", action="store_true", help="abre no navegador (modo padrão)")
    parser.add_argument("--server-only", action="store_true", help="executa apenas o servidor local")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()

    port = args.port or free_port()
    logger.info("Iniciando AuraCD %s em %s", APP_VERSION, PROJECT_DIR)
    logger.info("Log: %s", LOG_FILE)
    start_http(port)
    url = f"http://127.0.0.1:{port}"
    time.sleep(0.35)

    try:
        if args.server_only:
            print(f"AuraCD disponível em {url}", flush=True)
            while not shutdown_event.wait(1):
                pass
        elif args.native or (FROZEN and not args.browser):
            run_native(url)
        else:
            run_browser(url)
    except KeyboardInterrupt:
        logger.info("Encerramento solicitado pelo usuário.")
    except Exception as exc:
        logger.exception("Falha durante a execução do AuraCD.")
        show_error_dialog(
            "AuraCD — falha de execução",
            f"Não foi possível manter o AuraCD aberto.\n\n{exc}\n\nLog: {LOG_FILE}",
        )
        raise
    finally:
        cleanup()


if __name__ == "__main__":
    main()
