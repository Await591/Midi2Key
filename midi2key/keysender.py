"""Simulate keyboard input on Windows via user32!SendInput.

No third-party dependencies; works for normal applications, DAWs and editors.
Tracks currently held keys so they can all be released at once (panic/exit).
"""

import ctypes
from ctypes import wintypes

from . import vk as vkmod
from .mapping import (
    SEND_MODE_BOTH,
    SEND_MODE_SCANCODE,
    SEND_MODE_VK,
    VALID_SEND_MODES,
)

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

MAPVK_VK_TO_VSC_EX = 4

MODE_BOTH = SEND_MODE_BOTH
MODE_VK = SEND_MODE_VK
MODE_SCANCODE = SEND_MODE_SCANCODE
SEND_MODES = VALID_SEND_MODES


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("u", _INPUTUNION),
    ]


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
_user32.SendInput.restype = wintypes.UINT
_user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
_user32.MapVirtualKeyW.restype = wintypes.UINT


def scan_code_for_vk(vk):
    """Return (scan_code_low_byte, is_extended) for a virtual-key code."""
    code = int(_user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC_EX))
    if code == 0:
        code = int(_user32.MapVirtualKeyW(vk, 0))
    extended = (code & 0xE000) == 0xE000 or vkmod.is_extended(vk)
    return code & 0xFF, extended


class KeySender:
    """Sends key down / key up events and remembers what is held.

    ``send_mode`` picks how each event is encoded, which matters for games:
    ``vk`` uses only the virtual-key code, ``scancode`` sends hardware scan
    codes (KEYEVENTF_SCANCODE), ``both`` fills in both fields.
    """

    def __init__(self, send_mode=MODE_BOTH):
        self._held = set()
        self.send_mode = send_mode if send_mode in SEND_MODES else MODE_BOTH

    @property
    def held_keys(self):
        return set(self._held)

    def _send(self, vk, keyup):
        scan, extended = scan_code_for_vk(vk)
        flags = 0
        if extended:
            flags |= KEYEVENTF_EXTENDEDKEY
        if keyup:
            flags |= KEYEVENTF_KEYUP

        if self.send_mode == MODE_VK:
            w_vk, w_scan = vk, 0
        elif self.send_mode == MODE_SCANCODE:
            w_vk, w_scan = 0, scan
            flags |= KEYEVENTF_SCANCODE
        else:  # MODE_BOTH
            w_vk, w_scan = vk, scan

        inp = INPUT(type=INPUT_KEYBOARD)
        inp.ki = KEYBDINPUT(
            wVk=w_vk, wScan=w_scan, dwFlags=flags, time=0, dwExtraInfo=None
        )

        sent = _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        if sent != 1:
            err = ctypes.get_last_error()
            raise OSError("SendInput failed (error %d)" % err)

    def key_down(self, name):
        """Press and hold the key named *name*. Returns True if newly pressed."""
        vk = vkmod.vk_code(name)
        if vk in self._held:
            return False
        self._send(vk, keyup=False)
        self._held.add(vk)
        return True

    def key_up(self, name):
        """Release the key named *name*. Returns True if it was held."""
        vk = vkmod.vk_code(name)
        if vk not in self._held:
            return False
        self._send(vk, keyup=True)
        self._held.discard(vk)
        return True

    def press(self, name):
        """Tap a key (down then up)."""
        self.key_down(name)
        self.key_up(name)

    def release_all(self):
        """Release every key currently held by this sender."""
        for vk in list(self._held):
            name = vkmod.name_for_vk(vk)
            if name is None:
                continue
            try:
                self._send(vk, keyup=True)
            except OSError:
                pass
            self._held.discard(vk)
