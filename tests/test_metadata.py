from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from auracd.cd_player import CDPlayer
from auracd.metadata import MetadataService


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(self.responses.pop(0))


class MetadataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.service = MetadataService(
            Path(self.temp.name),
            musicbrainz_contact="tester@example.com",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_musicbrainz_disc_id_official_example(self) -> None:
        offsets = [150, 22767, 41887, 58317, 72102, 91375, 104652, 115380, 132165, 143932, 159870, 174597]
        disc_id = CDPlayer._musicbrainz_disc_id(1, 12, 267257, offsets)
        self.assertEqual(disc_id, "I5l9cCSFccLKFEKS.7wqSZAorPU-")

    def test_freedb_id_known_example(self) -> None:
        toc = {
            "tracks": [{"offset_frames": 150}],
            "leadout": (3612 * 75),
        }
        disc_id, total_seconds = self.service._freedb_disc_id(toc)
        self.assertEqual(disc_id, "020e1a01")
        self.assertEqual(total_seconds, 3610)

    def test_parse_xmcd(self) -> None:
        parsed = self.service._parse_xmcd(
            "DTITLE=Artista / Album\nDYEAR=1999\nDGENRE=Rock\nTTITLE0=Primeira\nTTITLE1=Segunda\n"
        )
        self.assertEqual(parsed["artist"], "Artista")
        self.assertEqual(parsed["album"], "Album")
        self.assertEqual(parsed["tracks"], ["Primeira", "Segunda"])

    def test_gnudb_lookup(self) -> None:
        self.service.session = FakeSession(
            [
                "200 rock 12345678 Banda / Disco\n",
                "210 OK\nDTITLE=Banda / Disco\nDYEAR=2001\nDGENRE=Rock\nTTITLE0=Musica A\nTTITLE1=Musica B\n.\n",
            ]
        )
        self.service.get_artist_details = lambda _id, name: {"name": name, "biography": "", "discography": [], "tags": []}
        toc = {
            "disc_id": "test",
            "submission_url": None,
            "track_count": 2,
            "leadout": 20000,
            "tracks": [
                {"number": 1, "offset_frames": 150, "length_frames": 9000, "duration": 120.0},
                {"number": 2, "offset_frames": 9150, "length_frames": 10850, "duration": 144.67},
            ],
        }
        result = self.service.lookup_gnudb(toc)
        self.assertIsNotNone(result)
        self.assertEqual(result["artist"], "Banda")
        self.assertEqual(result["album"], "Disco")
        self.assertEqual(result["tracks"][0]["title"], "Musica A")
        self.assertEqual(result["tracks"][1]["title"], "Musica B")



if __name__ == "__main__":
    unittest.main()
