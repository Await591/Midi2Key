import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from midi2key import vk  # noqa: E402
from midi2key.gui import keysym_to_name  # noqa: E402
from midi2key.keysender import (  # noqa: E402
    MODE_BOTH,
    MODE_SCANCODE,
    MODE_VK,
    KeySender,
    scan_code_for_vk,
)


class VirtualKeyTests(unittest.TestCase):
    def test_letters_and_digits(self):
        self.assertEqual(vk.vk_code("a"), 0x41)
        self.assertEqual(vk.vk_code("A"), 0x41)
        self.assertEqual(vk.vk_code("0"), 0x30)
        self.assertEqual(vk.vk_code("f12"), 0x7B)

    def test_special_keys(self):
        self.assertEqual(vk.vk_code("space"), 0x20)
        self.assertEqual(vk.vk_code("enter"), 0x0D)
        self.assertEqual(vk.vk_code("left"), 0x25)

    def test_extended_flags(self):
        self.assertTrue(vk.is_extended(vk.vk_code("left")))
        self.assertTrue(vk.is_extended(vk.vk_code("insert")))
        self.assertFalse(vk.is_extended(vk.vk_code("a")))

    def test_roundtrip_names(self):
        for name in vk.key_names():
            self.assertEqual(vk.name_for_vk(vk.vk_code(name)), name)

    def test_invalid(self):
        self.assertFalse(vk.is_valid_key("nope"))
        with self.assertRaises(ValueError):
            vk.vk_code("nope")

    def test_sorted_labels_unique(self):
        names = vk.sorted_key_names()
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(all("[" in vk.key_label(n) for n in names))


class KeysymTests(unittest.TestCase):
    def test_letters_digits_fkeys(self):
        self.assertEqual(keysym_to_name("a"), "a")
        self.assertEqual(keysym_to_name("Z"), "z")
        self.assertEqual(keysym_to_name("5"), "5")
        self.assertEqual(keysym_to_name("F7"), "f7")

    def test_specials(self):
        self.assertEqual(keysym_to_name("Control_L"), "lctrl")
        self.assertEqual(keysym_to_name("Return"), "enter")
        self.assertEqual(keysym_to_name("Prior"), "pageup")
        self.assertEqual(keysym_to_name("KP_3"), "num3")
        self.assertEqual(keysym_to_name("grave"), "backtick")

    def test_unknown(self):
        self.assertIsNone(keysym_to_name("SomeUnknownKeysym"))
        self.assertIsNone(keysym_to_name(""))

    def test_all_mapped_names_are_valid(self):
        for name in vk.key_names():
            self.assertTrue(vk.is_valid_key(name))


class ScanCodeTests(unittest.TestCase):
    def test_letter_and_enter(self):
        self.assertEqual(scan_code_for_vk(vk.vk_code("a")), (0x1E, False))
        self.assertEqual(scan_code_for_vk(vk.vk_code("enter")), (0x1C, False))

    def test_extended_keys(self):
        scan, extended = scan_code_for_vk(vk.vk_code("left"))
        self.assertTrue(extended)
        self.assertEqual(scan, 0x4B)
        _, extended_insert = scan_code_for_vk(vk.vk_code("insert"))
        self.assertTrue(extended_insert)

    def test_send_mode_defaults(self):
        sender = KeySender()
        self.assertEqual(sender.send_mode, MODE_BOTH)

    def test_send_mode_validated(self):
        sender = KeySender("nonsense")
        self.assertIn(sender.send_mode, (MODE_BOTH, MODE_VK, MODE_SCANCODE))


if __name__ == "__main__":
    unittest.main()
