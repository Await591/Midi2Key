import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from midi2key import winutil  # noqa: E402


class IntegrityLabelTests(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(winutil.integrity_label(None), "未知")
        self.assertEqual(winutil.integrity_label(0x1000), "受限")
        self.assertEqual(winutil.integrity_label(0x2000), "普通")
        self.assertEqual(winutil.integrity_label(0x3000), "管理员")
        self.assertEqual(winutil.integrity_label(0x4000), "系统")


class CurrentProcessTests(unittest.TestCase):
    def test_current_integrity_readable(self):
        rid = winutil.current_integrity()
        if rid is None:
            self.fail("current integrity unreadable")
            return
        self.assertGreaterEqual(rid, 0x1000)
        self.assertLessEqual(rid, 0x4000)

    def test_is_elevated_matches_integrity(self):
        rid = winutil.current_integrity()
        if rid is None:
            self.fail("current integrity unreadable")
            return
        self.assertEqual(winutil.is_elevated(), rid >= winutil.INTEGRITY_HIGH)

    def test_foreground_pid_returns_int_or_none(self):
        pid = winutil.foreground_process_id()
        self.assertTrue(pid is None or pid > 0)

    def test_integrity_of_process(self):
        rid = winutil.integrity_of_process(os.getpid())
        self.assertEqual(rid, winutil.current_integrity())

    def test_integrity_of_missing_process(self):
        self.assertIsNone(winutil.integrity_of_process(0x7FFFFFFF))


class RelaunchTests(unittest.TestCase):
    def _capture(self, **patches):
        captured = {}

        def fake(hwnd, verb, exe, params, cwd, show):
            captured.update(verb=verb, exe=exe, params=params)
            return 42

        stack = mock.patch.object(winutil._shell32, "ShellExecuteW", fake)
        stack.start()
        self.addCleanup(stack.stop)
        for name, value in patches.items():
            patcher = mock.patch.object(winutil.sys, name, value, create=True)
            patcher.start()
            self.addCleanup(patcher.stop)
        return captured

    def test_frozen_does_not_repeat_executable(self):
        captured = self._capture(
            frozen=True,
            executable=r"C:\apps\Midi2Key.exe",
            argv=[r"C:\apps\Midi2Key.exe", "--config", "x y.json"],
        )
        self.assertTrue(winutil.relaunch_as_admin())
        self.assertEqual(captured["verb"], "runas")
        self.assertEqual(captured["exe"], r"C:\apps\Midi2Key.exe")
        self.assertEqual(captured["params"], '"--config" "x y.json"')

    def test_script_build_passes_script_path(self):
        captured = self._capture(
            frozen=False,
            executable=r"C:\Python\pythonw.exe",
            argv=[r"E:\proj\main.pyw", "--config", "x.json"],
        )
        self.assertTrue(winutil.relaunch_as_admin())
        self.assertEqual(captured["exe"], r"C:\Python\pythonw.exe")
        self.assertEqual(captured["params"], r'"E:\proj\main.pyw" "--config" "x.json"')


if __name__ == "__main__":
    unittest.main()
