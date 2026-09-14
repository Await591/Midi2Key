import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from midi2key.mapping import (  # noqa: E402
    Mapping,
    MappingSet,
    default_config,
    note_name,
    parse_note,
)


class NoteNameTests(unittest.TestCase):
    def test_note_name(self):
        self.assertEqual(note_name(0), "C-1")
        self.assertEqual(note_name(60), "C4")
        self.assertEqual(note_name(61), "C#4")
        self.assertEqual(note_name(69), "A4")
        self.assertEqual(note_name(127), "G9")

    def test_parse_note_names(self):
        self.assertEqual(parse_note("C4"), 60)
        self.assertEqual(parse_note("c4"), 60)
        self.assertEqual(parse_note("C#4"), 61)
        self.assertEqual(parse_note("Db4"), 61)
        self.assertEqual(parse_note("A4"), 69)
        self.assertEqual(parse_note("C-1"), 0)

    def test_parse_note_numbers(self):
        self.assertEqual(parse_note("60"), 60)
        self.assertEqual(parse_note(0), 0)

    def test_roundtrip(self):
        for note in range(128):
            self.assertEqual(parse_note(note_name(note)), note)

    def test_invalid(self):
        for bad in ("", "H4", "C", "Cx4", "C99", "200"):
            with self.assertRaises(ValueError):
                parse_note(bad)


class MappingSetTests(unittest.TestCase):
    def test_upsert_and_get(self):
        ms = MappingSet()
        ms.upsert(60, "a")
        self.assertEqual(ms.get(60), "a")
        ms.upsert(60, "b")
        self.assertEqual(ms.get(60), "b")
        self.assertEqual(len(ms.mappings), 1)

    def test_disabled_mapping_not_returned(self):
        ms = MappingSet()
        ms.upsert(60, "a", enabled=False)
        self.assertIsNone(ms.get(60))
        self.assertIsNotNone(ms.find(60))

    def test_remove(self):
        ms = MappingSet()
        ms.upsert(60, "a")
        self.assertTrue(ms.remove(60))
        self.assertFalse(ms.remove(60))
        self.assertIsNone(ms.get(60))

    def test_sorted(self):
        ms = MappingSet()
        ms.upsert(70, "b")
        ms.upsert(50, "a")
        self.assertEqual([m.note for m in ms.sorted_mappings()], [50, 70])

    def test_save_load_roundtrip(self):
        ms = MappingSet(
            device="Test Device", velocity_threshold=10, mode="hold", tap_ms=45
        )
        ms.upsert(60, "a")
        ms.upsert(61, "b", enabled=False)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.json")
            ms.save(path)
            loaded = MappingSet.load(path)
        self.assertEqual(loaded.device, "Test Device")
        self.assertEqual(loaded.velocity_threshold, 10)
        self.assertEqual(loaded.mode, "hold")
        self.assertEqual(loaded.tap_ms, 45)
        self.assertEqual(loaded.get(60), "a")
        self.assertIsNone(loaded.get(61))

    def test_default_tap_ms(self):
        self.assertEqual(MappingSet().tap_ms, 50)
        self.assertEqual(default_config().tap_ms, 50)
        self.assertEqual(MappingSet.from_dict({"mappings": []}).tap_ms, 50)

    def test_default_send_mode(self):
        self.assertEqual(MappingSet().send_mode, "both")
        self.assertEqual(MappingSet.from_dict({"mappings": []}).send_mode, "both")

    def test_invalid_send_mode_falls_back(self):
        ms = MappingSet.from_dict({"send_mode": "weird", "mappings": []})
        self.assertEqual(ms.send_mode, "both")

    def test_send_mode_roundtrip(self):
        ms = MappingSet(send_mode="scancode")
        self.assertEqual(MappingSet.from_dict(ms.to_dict()).send_mode, "scancode")

    def test_default_mode_is_tap(self):
        self.assertEqual(MappingSet().mode, "tap")
        self.assertEqual(default_config().mode, "tap")

    def test_invalid_mode_falls_back_to_tap(self):
        ms = MappingSet.from_dict({"mode": "weird", "mappings": []})
        self.assertEqual(ms.mode, "tap")
        self.assertEqual(MappingSet.from_dict({"mappings": []}).mode, "tap")

    def test_load_missing_uses_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            loaded = MappingSet.load(os.path.join(tmp, "nope.json"))
        self.assertEqual(len(loaded.mappings), len(default_config().mappings))

    def test_load_corrupt_uses_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("{ not json")
            loaded = MappingSet.load(path)
        self.assertTrue(loaded.mappings)

    def test_from_dict_skips_bad_rows(self):
        data = {
            "mappings": [
                {"note": 60, "key": "a"},
                {"note": "x", "key": "b"},
                {"key": "c"},
            ]
        }
        ms = MappingSet.from_dict(data)
        self.assertEqual(len(ms.mappings), 1)
        self.assertEqual(ms.get(60), "a")

    def test_mapping_roundtrip(self):
        m = Mapping(note=64, key="c", enabled=False)
        self.assertEqual(Mapping.from_dict(m.to_dict()), m)


if __name__ == "__main__":
    unittest.main()
