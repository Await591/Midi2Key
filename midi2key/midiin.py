"""Read MIDI input on Windows via winmm!midiIn* (ctypes, no dependencies).

A dedicated thread opens the device and pumps a minimal message loop so the
winmm callback thread can deliver events.  The callback itself only parses the
raw 3-byte message and pushes it onto a thread-safe queue; all real work is
done by the consumer.
"""

import ctypes
import queue
import threading
from ctypes import wintypes
from collections import namedtuple

MAXPNAMELEN = 32

CALLBACK_FUNCTION = 0x00030000

MIM_OPEN = 0x3C1
MIM_CLOSE = 0x3C2
MIM_DATA = 0x3C3
MIM_LONGDATA = 0x3C4
MIM_ERROR = 0x3C5
MIM_LONGERROR = 0x3C6
MIM_MOREDATA = 0x3CC

WM_QUIT = 0x0012

MMSYSERR_NOERROR = 0


class MIDIINCAPSW(ctypes.Structure):
    _fields_ = [
        ("wMid", wintypes.WORD),
        ("wPid", wintypes.WORD),
        ("vDriverVersion", wintypes.UINT),
        ("szPname", wintypes.WCHAR * MAXPNAMELEN),
        ("wTechnology", wintypes.WORD),
        ("wVoices", wintypes.WORD),
        ("wNotes", wintypes.WORD),
        ("wChannelMask", wintypes.WORD),
        ("dwSupport", wintypes.DWORD),
    ]


DWORD_PTR = ctypes.c_size_t
HMIDIIN = ctypes.c_void_p
MidiInProc = ctypes.WINFUNCTYPE(
    None, HMIDIIN, wintypes.UINT, DWORD_PTR, DWORD_PTR, DWORD_PTR
)

_winmm = ctypes.WinDLL("winmm", use_last_error=True)
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_winmm.midiInGetNumDevs.restype = wintypes.UINT
_winmm.midiInGetNumDevs.argtypes = ()
_winmm.midiInGetDevCapsW.argtypes = (
    ctypes.c_size_t,
    ctypes.POINTER(MIDIINCAPSW),
    wintypes.UINT,
)
_winmm.midiInGetDevCapsW.restype = wintypes.UINT
_winmm.midiInOpen.argtypes = (
    ctypes.POINTER(HMIDIIN),
    wintypes.UINT,
    DWORD_PTR,
    DWORD_PTR,
    wintypes.DWORD,
)
_winmm.midiInOpen.restype = wintypes.UINT
_winmm.midiInStart.argtypes = (HMIDIIN,)
_winmm.midiInStart.restype = wintypes.UINT
_winmm.midiInStop.argtypes = (HMIDIIN,)
_winmm.midiInStop.restype = wintypes.UINT
_winmm.midiInReset.argtypes = (HMIDIIN,)
_winmm.midiInReset.restype = wintypes.UINT
_winmm.midiInClose.argtypes = (HMIDIIN,)
_winmm.midiInClose.restype = wintypes.UINT

_kernel32.GetCurrentThreadId.restype = wintypes.DWORD
_kernel32.GetCurrentThreadId.argtypes = ()
_user32.PostThreadMessageW.argtypes = (
    wintypes.DWORD,
    wintypes.UINT,
    ctypes.c_size_t,
    ctypes.c_size_t,
)
_user32.PostThreadMessageW.restype = wintypes.BOOL

MSG = wintypes.MSG

MidiEvent = namedtuple("MidiEvent", "kind channel data1 data2")


def _parse(status, data1, data2):
    """Turn a raw status/data triple into a MidiEvent (or None)."""
    if status < 0x80:
        return None
    msg_type = status & 0xF0
    channel = status & 0x0F
    if msg_type == 0x90 and data2 > 0:
        return MidiEvent("note_on", channel, data1, data2)
    if msg_type == 0x80 or (msg_type == 0x90 and data2 == 0):
        return MidiEvent("note_off", channel, data1, data2)
    if msg_type == 0xB0:
        return MidiEvent("control_change", channel, data1, data2)
    if msg_type == 0xC0:
        return MidiEvent("program_change", channel, data1, data2)
    if msg_type == 0xE0:
        return MidiEvent("pitchwheel", channel, data1, data2)
    if msg_type == 0xA0:
        return MidiEvent("aftertouch", channel, data1, data2)
    if msg_type == 0xD0:
        return MidiEvent("channel_aftertouch", channel, data1, data2)
    return MidiEvent("unknown", channel, data1, data2)


def device_count():
    """Return the number of MIDI input devices visible to Windows."""
    return int(_winmm.midiInGetNumDevs())


def list_devices():
    """Return a list of (index, name) for all MIDI input devices."""
    result = []
    for i in range(device_count()):
        caps = MIDIINCAPSW()
        rc = _winmm.midiInGetDevCapsW(i, ctypes.byref(caps), ctypes.sizeof(caps))
        if rc == MMSYSERR_NOERROR:
            result.append((i, caps.szPname))
        else:
            result.append((i, "<unknown device %d>" % i))
    return result


class MidiInputError(RuntimeError):
    pass


_winmm.midiInGetErrorTextW.argtypes = (
    wintypes.UINT,
    ctypes.c_wchar_p,
    wintypes.UINT,
)
_winmm.midiInGetErrorTextW.restype = wintypes.UINT


def _error_text(code):
    buf = ctypes.create_unicode_buffer(256)
    if _winmm.midiInGetErrorTextW(code, buf, len(buf)) == MMSYSERR_NOERROR:
        return buf.value
    return "winmm error %d" % code


class MidiInput:
    """Opens a MIDI input device and delivers parsed events to a queue."""

    def __init__(self, device_id, event_queue=None, on_error=None):
        self.device_id = int(device_id)
        self.queue = event_queue if event_queue is not None else queue.Queue()
        self.on_error = on_error
        self.device_name = None

        self._handle = HMIDIIN(None)
        self._thread = None
        self._thread_id = None
        self._ready = threading.Event()
        self._open_error = None
        self._running = False
        self._callback = MidiInProc(self._on_midi)

    # -- public API ---------------------------------------------------------

    def start(self, timeout=5.0):
        """Open the device and begin reading.  Raises MidiInputError."""
        if self._running:
            return
        self._ready.clear()
        self._open_error = None
        self._thread = threading.Thread(
            target=self._run, name="midi2key-midi", daemon=True
        )
        self._thread.start()
        if not self._ready.wait(timeout):
            raise MidiInputError("timed out opening MIDI device")
        if self._open_error:
            raise MidiInputError(self._open_error)
        self._running = True

    def stop(self, timeout=3.0):
        """Stop reading and close the device."""
        if not self._running:
            return
        self._running = False
        tid = self._thread_id
        if tid:
            _user32.PostThreadMessageW(tid, WM_QUIT, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout)
        self._thread = None
        self._thread_id = None

    @property
    def is_running(self):
        return self._running

    # -- internals ----------------------------------------------------------

    def _run(self):
        msg = MSG()
        # Force creation of this thread's message queue.
        _user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)
        self._thread_id = int(_kernel32.GetCurrentThreadId())

        caps = MIDIINCAPSW()
        rc = _winmm.midiInGetDevCapsW(
            self.device_id, ctypes.byref(caps), ctypes.sizeof(caps)
        )
        self.device_name = caps.szPname if rc == MMSYSERR_NOERROR else None

        handle = HMIDIIN(None)
        cb_ptr = ctypes.cast(self._callback, ctypes.c_void_p).value
        rc = _winmm.midiInOpen(
            ctypes.byref(handle),
            self.device_id,
            cb_ptr,
            0,
            CALLBACK_FUNCTION,
        )
        if rc != MMSYSERR_NOERROR:
            self._open_error = "cannot open MIDI device %d: %s" % (
                self.device_id,
                _error_text(rc),
            )
            self._ready.set()
            return

        self._handle = handle
        rc = _winmm.midiInStart(handle)
        if rc != MMSYSERR_NOERROR:
            self._open_error = "cannot start MIDI device %d: %s" % (
                self.device_id,
                _error_text(rc),
            )
            _winmm.midiInClose(handle)
            self._handle = HMIDIIN(None)
            self._ready.set()
            return

        self._ready.set()

        try:
            while True:
                ret = _user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret in (0, -1):
                    break
                _user32.TranslateMessage(ctypes.byref(msg))
                _user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            if self._handle:
                _winmm.midiInStop(self._handle)
                _winmm.midiInReset(self._handle)
                _winmm.midiInClose(self._handle)
                self._handle = HMIDIIN(None)

    def _on_midi(self, handle, msg, instance, param1, param2):
        """winmm callback: keep it tiny, never raise."""
        try:
            if msg not in (MIM_DATA, MIM_MOREDATA):
                return
            value = int(param1)
            status = value & 0xFF
            data1 = (value >> 8) & 0xFF
            data2 = (value >> 16) & 0xFF
            event = _parse(status, data1, data2)
            if event is not None:
                self.queue.put(event)
        except Exception as exc:  # pragma: no cover - defensive
            if self.on_error is not None:
                try:
                    self.on_error(exc)
                except Exception:
                    pass


_user32.GetMessageW.argtypes = (
    ctypes.POINTER(MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
)
_user32.GetMessageW.restype = wintypes.BOOL
_user32.TranslateMessage.argtypes = (ctypes.POINTER(MSG),)
_user32.TranslateMessage.restype = wintypes.BOOL
_user32.DispatchMessageW.argtypes = (ctypes.POINTER(MSG),)
_user32.DispatchMessageW.restype = ctypes.c_ssize_t
_user32.PeekMessageW.argtypes = (
    ctypes.POINTER(MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
    wintypes.UINT,
)
_user32.PeekMessageW.restype = wintypes.BOOL
