from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from auracd.collection import CollectionStore


class CollectionStoreTests(unittest.TestCase):
    def sample_disc(self):
        return {
            "identified": True,
            "disc_id": "TEST_DISC",
            "release_id": "release-123",
            "album": "Álbum de Teste",
            "artist": "Banda de Teste",
            "year": "1994",
            "country": "BR",
            "cover_url": "/static/img/disc-placeholder.svg",
            "source": "test",
            "genre": "Rock",
            "artist_details": {"tags": ["progressive rock", "rock"]},
            "tracks": [
                {"number": 1, "title": "Faixa Um", "artist": "Banda de Teste", "duration": 180},
                {"number": 2, "title": "Faixa Dois", "artist": "Banda de Teste", "duration": 240},
            ],
        }

    def test_upsert_and_statistics(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CollectionStore(Path(directory))
            disc = self.sample_disc()
            store.upsert_disc(disc)
            store.record_play(disc, 1)
            store.add_listening_time(disc, 1, 30)
            result = store.snapshot()
            self.assertEqual(result["summary"]["albums"], 1)
            self.assertEqual(result["summary"]["artists"], 1)
            self.assertEqual(result["summary"]["plays"], 1)
            self.assertEqual(result["summary"]["listened_seconds"], 30)
            self.assertEqual(result["summary"]["favorite_genre"], "Rock")
            self.assertEqual(result["albums"][0]["tracks"][0]["play_count"], 1)

    def test_persists_between_instances(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            first = CollectionStore(path)
            first.upsert_disc(self.sample_disc())
            second = CollectionStore(path)
            self.assertEqual(second.snapshot()["summary"]["albums"], 1)

    def test_clear(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CollectionStore(Path(directory))
            store.upsert_disc(self.sample_disc())
            store.clear()
            self.assertEqual(store.snapshot()["summary"]["albums"], 0)


if __name__ == "__main__":
    unittest.main()
