import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from midi2key import vk  # noqa: E402
from midi2key.mapping import note_name, parse_note  # noqa: E402
from midi2key.presets import PRESETS, SKY_KEYS, sky  # noqa: E402

EXPECTED_SKY = [
    ("C4", "y"),
    ("D4", "u"),
    ("E4", "i"),
    ("F4", "o"),
    ("G4", "p"),
    ("A4", "h"),
    ("B4", "j"),
    ("C5", "k"),
    ("D5", "l"),
    ("E5", "semicolon"),
    ("F5", "n"),
    ("G5", "m"),
    ("A5", "comma"),
    ("B5", "period"),
    ("C6", "slash"),
]


class SkyPresetTests(unittest.TestCase):
    def test_c4_to_c6_white_keys(self):
        preset = sky()
        self.assertEqual(len(preset.mappings), 15)
        for name, key in EXPECTED_SKY:
            self.assertEqual(preset.get(parse_note(name)), key, name)

    def test_only_white_keys_mapped(self):
        preset = sky()
        mapped = {m.note for m in preset.mappings}
        for note in range(60, 85):
            if note % 12 in (1, 3, 6, 8, 10):
                self.assertNotIn(note, mapped, note_name(note))
        self.assertEqual(mapped, {parse_note(n) for n, _ in EXPECTED_SKY})

    def test_key_sequence(self):
        preset = sky()
        self.assertEqual([m.key for m in preset.sorted_mappings()], SKY_KEYS)

    def test_mode_and_device_defaults(self):
        preset = sky()
        self.assertEqual(preset.mode, "tap")
        self.assertIsNone(preset.device)

    def test_all_keys_are_valid(self):
        for m in sky().mappings:
            self.assertTrue(vk.is_valid_key(m.key), m.key)

    def test_start_note_shifts_octave(self):
        preset = sky(start_note=48)
        self.assertEqual(preset.get(48), "y")
        self.assertEqual(preset.get(48 + 24), "slash")

    def test_registry(self):
        self.assertIs(PRESETS["sky"], sky)


if __name__ == "__main__":
    unittest.main()
