import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from midi2key import winutil  # noqa: E402
from midi2key.engine import Engine  # noqa: E402
from midi2key.mapping import MappingSet  # noqa: E402
from midi2key.midiin import MidiEvent  # noqa: E402


class FakeSender:
    def __init__(self):
        self.calls = []
        self.held = set()

    def key_down(self, name):
        if name in self.held:
            self.calls.append(("down-repeat", name))
            return False
        self.held.add(name)
        self.calls.append(("down", name))
        return True

    def key_up(self, name):
        if name not in self.held:
            self.calls.append(("up-none", name))
            return False
        self.held.discard(name)
        self.calls.append(("up", name))
        return True

    def press(self, name):
        self.key_down(name)
        self.key_up(name)

    def release_all(self):
        self.calls.append(("release_all",))
        self.held.clear()


def make_engine(mapping_set=None):
    ms = mapping_set if mapping_set is not None else MappingSet(mode="hold")
    engine = Engine(ms)
    sender = FakeSender()
    setattr(engine, "_sender", sender)
    return engine, sender


def note_on(note, velocity=100):
    return MidiEvent("note_on", 0, note, velocity)


def note_off(note):
    return MidiEvent("note_off", 0, note, 0)


def cc(number, value):
    return MidiEvent("control_change", 0, number, value)


class EngineTests(unittest.TestCase):
    def test_note_on_off(self):
        engine, sender = make_engine()
        engine.upsert(60, "a")
        engine._handle(note_on(60))
        engine._handle(note_off(60))
        self.assertEqual(sender.calls, [("down", "a"), ("up", "a")])

    def test_unmapped_note_is_ignored(self):
        engine, sender = make_engine()
        engine._handle(note_on(60))
        self.assertEqual(sender.calls, [])

    def test_duplicate_note_on_ignored(self):
        engine, sender = make_engine()
        engine.upsert(60, "a")
        engine._handle(note_on(60))
        engine._handle(note_on(60))
        self.assertEqual(sender.calls, [("down", "a")])

    def test_shared_key_reference_counted(self):
        engine, sender = make_engine()
        engine.upsert(60, "a")
        engine.upsert(61, "a")
        engine._handle(note_on(60))
        engine._handle(note_on(61))
        self.assertEqual(sender.calls, [("down", "a")])
        engine._handle(note_off(60))
        self.assertEqual(sender.calls, [("down", "a")])
        engine._handle(note_off(61))
        self.assertEqual(sender.calls, [("down", "a"), ("up", "a")])

    def test_velocity_threshold(self):
        ms = MappingSet(mode="hold", velocity_threshold=64)
        engine, sender = make_engine(ms)
        engine.upsert(60, "a")
        engine._handle(note_on(60, velocity=30))
        self.assertEqual(sender.calls, [])
        engine._handle(note_on(60, velocity=100))
        self.assertEqual(sender.calls, [("down", "a")])

    def test_disabled_mapping_ignored(self):
        engine, sender = make_engine()
        engine.upsert(60, "a", enabled=False)
        engine._handle(note_on(60))
        self.assertEqual(sender.calls, [])

    def test_all_notes_off(self):
        engine, sender = make_engine()
        engine.upsert(60, "a")
        engine._handle(note_on(60))
        engine._handle(cc(123, 0))
        self.assertEqual(sender.calls, [("down", "a"), ("release_all",)])
        self.assertEqual(engine.active_notes(), {})

    def test_panic(self):
        engine, sender = make_engine()
        engine.upsert(60, "a")
        engine._handle(note_on(60))
        engine.panic()
        self.assertEqual(sender.calls, [("down", "a"), ("release_all",)])
        self.assertEqual(engine.active_notes(), {})

    def test_events_reported(self):
        collected = []
        engine, _ = make_engine()
        engine.on_event = collected.append
        engine.upsert(60, "a")
        engine._handle(note_on(60))
        actions = [e.get("action") for e in collected if e.get("type") == "note"]
        self.assertIn("down", actions)

    def test_remove_during_playback_releases(self):
        engine, sender = make_engine()
        engine.upsert(60, "a")
        engine._handle(note_on(60))
        engine.remove(60)
        engine._handle(note_off(60))
        self.assertEqual(sender.calls, [("down", "a"), ("up", "a")])

    def test_release_uses_pressed_key_not_current_mapping(self):
        engine, sender = make_engine()
        engine.upsert(60, "a")
        engine._handle(note_on(60))
        engine.upsert(60, "b")
        engine._handle(note_off(60))
        self.assertEqual(sender.calls, [("down", "a"), ("up", "a")])

    def test_release_after_mapping_disabled(self):
        engine, sender = make_engine()
        engine.upsert(60, "a")
        engine._handle(note_on(60))
        engine.set_enabled(60, False)
        engine._handle(note_off(60))
        self.assertEqual(sender.calls, [("down", "a"), ("up", "a")])

    def test_release_works_even_without_any_mapping(self):
        engine, sender = make_engine()
        engine.upsert(60, "a")
        engine._handle(note_on(60))
        engine.mappings.mappings = []
        engine._handle(note_off(60))
        self.assertEqual(sender.calls, [("down", "a"), ("up", "a")])


class TapModeTests(unittest.TestCase):
    def make_tap_engine(self, tap_ms=30):
        return make_engine(MappingSet(mode="tap", tap_ms=tap_ms))

    def test_press_is_a_tap_and_release_is_ignored(self):
        engine, sender = self.make_tap_engine(tap_ms=0)
        engine.upsert(60, "a")
        engine._handle(note_on(60))
        self.assertEqual(sender.calls, [("down", "a")])
        self.assertEqual(sender.held, {"a"})
        engine._flush_releases()
        self.assertEqual(sender.calls, [("down", "a"), ("up", "a")])
        self.assertEqual(sender.held, set())
        engine._handle(note_off(60))
        self.assertEqual(sender.calls, [("down", "a"), ("up", "a")])

    def test_key_stays_down_until_tap_ms_elapsed(self):
        engine, sender = self.make_tap_engine(tap_ms=500)
        engine.upsert(60, "a")
        engine._handle(note_on(60))
        engine._flush_releases()
        self.assertEqual(sender.calls, [("down", "a")])
        engine._flush_releases(now=1e18)
        self.assertEqual(sender.calls, [("down", "a"), ("up", "a")])

    def test_repeat_note_on_keeps_key_held(self):
        engine, sender = self.make_tap_engine(tap_ms=30)
        engine.upsert(60, "a")
        engine._handle(note_on(60))
        engine._handle(note_on(60))
        self.assertEqual(sender.calls, [("down", "a"), ("down-repeat", "a")])
        engine._flush_releases(now=1e18)
        self.assertEqual(
            sender.calls, [("down", "a"), ("down-repeat", "a"), ("up", "a")]
        )

    def test_no_hold_state_is_kept(self):
        engine, _ = self.make_tap_engine()
        engine.upsert(60, "a")
        engine._handle(note_on(60))
        self.assertEqual(engine.active_notes(), {})

    def test_velocity_threshold(self):
        ms = MappingSet(mode="tap", velocity_threshold=64)
        engine, sender = make_engine(ms)
        engine.upsert(60, "a")
        engine._handle(note_on(60, velocity=10))
        self.assertEqual(sender.calls, [])
        engine._handle(note_on(60, velocity=90))
        self.assertEqual(sender.calls, [("down", "a")])

    def test_note_off_emits_nothing(self):
        collected = []
        engine, _ = self.make_tap_engine()
        engine.on_event = collected.append
        engine.upsert(60, "a")
        engine._handle(note_on(60))
        collected.clear()
        engine._handle(note_off(60))
        self.assertEqual(collected, [])

    def test_tap_event_reported(self):
        collected = []
        engine, _ = self.make_tap_engine()
        engine.on_event = collected.append
        engine.upsert(60, "a")
        engine._handle(note_on(60))
        actions = [e.get("action") for e in collected if e.get("type") == "note"]
        self.assertEqual(actions, ["tap"])

    def test_chords_do_not_block_each_other(self):
        engine, sender = self.make_tap_engine(tap_ms=50)
        engine.upsert(60, "a")
        engine.upsert(64, "s")
        engine.upsert(67, "d")
        for note in (60, 64, 67):
            engine._handle(note_on(note))
        self.assertEqual(sender.held, {"a", "s", "d"})
        engine._flush_releases(now=1e18)
        self.assertEqual(sender.held, set())

    def test_panic_clears_pending_releases(self):
        engine, sender = self.make_tap_engine(tap_ms=500)
        engine.upsert(60, "a")
        engine._handle(note_on(60))
        engine.panic()
        self.assertEqual(sender.held, set())
        self.assertEqual(engine._tap_deadlines, {})

    def test_set_mode_releases_held_keys(self):
        engine, sender = make_engine()
        engine.upsert(60, "a")
        engine._handle(note_on(60))
        self.assertTrue(engine.set_mode("tap"))
        self.assertEqual(engine.mode, "tap")
        self.assertEqual(sender.calls, [("down", "a"), ("release_all",)])

    def test_set_mode_rejects_unknown(self):
        engine, _ = make_engine()
        self.assertFalse(engine.set_mode("nope"))
        self.assertEqual(engine.mode, "hold")

    def test_set_send_mode(self):
        engine, _ = make_engine()
        self.assertEqual(engine.send_mode, "both")
        self.assertTrue(engine.set_send_mode("scancode"))
        self.assertEqual(engine.send_mode, "scancode")
        self.assertEqual(engine._sender.send_mode, "scancode")
        self.assertTrue(engine.set_send_mode("vk"))
        self.assertEqual(engine._sender.send_mode, "vk")

    def test_set_send_mode_rejects_unknown(self):
        engine, _ = make_engine()
        self.assertFalse(engine.set_send_mode("nope"))
        self.assertEqual(engine.send_mode, "both")

    def test_replace_mappings_applies_send_mode(self):
        engine, _ = make_engine()
        engine.replace_mappings(MappingSet(mode="hold", send_mode="scancode"))
        self.assertEqual(engine._sender.send_mode, "scancode")

    def test_switch_to_tap_then_note_off_is_noop(self):
        engine, sender = make_engine()
        engine.upsert(60, "a")
        engine._handle(note_on(60))
        engine.set_mode("tap")
        engine._handle(note_off(60))
        self.assertEqual(sender.calls, [("down", "a"), ("release_all",)])


class UipiTests(unittest.TestCase):
    def test_warns_once_when_target_is_higher_integrity(self):
        collected = []
        engine, _ = make_engine()
        engine.on_event = collected.append
        engine.upsert(60, "a")
        with mock.patch.object(winutil, "current_integrity", return_value=0x2000), \
                mock.patch.object(winutil, "foreground_integrity", return_value=0x3000):
            engine._handle(note_on(60))
            engine._uipi_checked_at = 0.0
            engine._handle(note_on(60))
        warns = [e for e in collected if e.get("type") == "warn"]
        self.assertEqual(len(warns), 1)
        self.assertIn("管理员", warns[0]["message"])

    def test_no_warning_when_same_integrity(self):
        collected = []
        engine, _ = make_engine()
        engine.on_event = collected.append
        engine.upsert(60, "a")
        with mock.patch.object(winutil, "current_integrity", return_value=0x2000), \
                mock.patch.object(winutil, "foreground_integrity", return_value=0x2000):
            engine._handle(note_on(60))
        self.assertEqual([e for e in collected if e.get("type") == "warn"], [])

    def test_no_warning_when_integrity_unknown(self):
        collected = []
        engine, _ = make_engine()
        engine.on_event = collected.append
        engine.upsert(60, "a")
        with mock.patch.object(winutil, "current_integrity", return_value=None), \
                mock.patch.object(winutil, "foreground_integrity", return_value=0x3000):
            engine._handle(note_on(60))
        self.assertEqual([e for e in collected if e.get("type") == "warn"], [])

    def test_privilege_check_is_throttled(self):
        engine, _ = make_engine()
        engine.upsert(60, "a")
        with mock.patch.object(winutil, "current_integrity", return_value=0x2000) as mine, \
                mock.patch.object(winutil, "foreground_integrity", return_value=0x2000):
            for _ in range(5):
                engine._handle(note_on(60))
        self.assertLessEqual(mine.call_count, 2)


if __name__ == "__main__":
    unittest.main()
