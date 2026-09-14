"""The core engine: consumes MIDI events, resolves mappings, emits keystrokes."""

import queue
import threading
import time

from . import midiin
from . import winutil
from .keysender import KeySender
from .mapping import MappingSet, note_name, MODE_TAP, MODE_HOLD, VALID_SEND_MODES

ALL_SOUND_OFF = 120
ALL_NOTES_OFF = 123


class Engine:
    """Bridges a MIDI input device to simulated keyboard output.

    Mapping mutations are safe to call from the GUI thread; events from MIDI
    are processed on a worker thread and reported through ``on_event``.
    """

    def __init__(self, mapping_set=None, on_event=None):
        self.mappings = mapping_set if mapping_set is not None else MappingSet()
        self.on_event = on_event

        self._lock = threading.RLock()
        self._queue = queue.Queue()
        self._sender = KeySender()
        self._sender.send_mode = self.mappings.send_mode
        self._midi = None

        self._worker = None
        self._stop = threading.Event()

        self._active = {}          # note -> key currently held for it
        self._key_notes = {}       # key -> set(notes) sharing that key
        self._tap_deadlines = {}   # key -> monotonic time to auto-release

        self._uipi_checked_at = 0.0
        self._uipi_warned = False

    # -- lifecycle ----------------------------------------------------------

    @property
    def is_running(self):
        return self._midi is not None and self._midi.is_running

    @property
    def device_name(self):
        return self._midi.device_name if self._midi is not None else None

    def start(self, device_id):
        """Open *device_id* and start processing. Raises MidiInputError."""
        if self.is_running:
            return
        self._stop.clear()
        self._uipi_checked_at = 0.0
        self._uipi_warned = False
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

        midi = midiin.MidiInput(
            device_id, event_queue=self._queue, on_error=self._midi_error
        )
        midi.start()
        self._midi = midi

        self._worker = threading.Thread(
            target=self._run_worker, name="midi2key-worker", daemon=True
        )
        self._worker.start()
        self._emit({"type": "state", "running": True, "device": midi.device_name})

    def stop(self):
        """Stop the MIDI device, the worker and release every held key."""
        if self._midi is not None:
            self._midi.stop()
            self._midi = None
        self._stop.set()
        if self._worker is not None:
            self._worker.join(2.0)
            self._worker = None
        self.panic()
        self._emit({"type": "state", "running": False, "device": None})

    def panic(self):
        """Release all keys this engine is holding."""
        with self._lock:
            self._active.clear()
            self._key_notes.clear()
            self._tap_deadlines.clear()
        self._sender.release_all()

    # -- mapping management (thread safe) -----------------------------------

    def replace_mappings(self, mapping_set):
        with self._lock:
            self.mappings = mapping_set
        self._sender.send_mode = self.mappings.send_mode

    def upsert(self, note, key, enabled=True):
        with self._lock:
            return self.mappings.upsert(note, key, enabled)

    def remove(self, note):
        with self._lock:
            return self.mappings.remove(note)

    def set_enabled(self, note, enabled):
        with self._lock:
            m = self.mappings.find(note)
            if m is None:
                return False
            m.enabled = enabled
            return True

    def set_device(self, device):
        with self._lock:
            self.mappings.device = device

    def set_velocity_threshold(self, value):
        with self._lock:
            self.mappings.velocity_threshold = int(value)

    def set_mode(self, mode):
        """Switch between tap (press+release on note-on) and hold mode."""
        if mode not in (MODE_TAP, MODE_HOLD):
            return False
        with self._lock:
            if self.mappings.mode == mode:
                return True
            self.mappings.mode = mode
            self._active.clear()
            self._key_notes.clear()
            self._tap_deadlines.clear()
        self._sender.release_all()
        return True

    def set_tap_ms(self, value):
        """Set how long a tap holds the key down (milliseconds)."""
        with self._lock:
            self.mappings.tap_ms = max(0, min(1000, int(value)))

    def set_send_mode(self, mode):
        """Choose how keystrokes are encoded (both / vk / scancode)."""
        if mode not in VALID_SEND_MODES:
            return False
        with self._lock:
            self.mappings.send_mode = mode
        self._sender.send_mode = mode
        return True

    @property
    def send_mode(self):
        with self._lock:
            return self.mappings.send_mode

    @property
    def mode(self):
        with self._lock:
            return self.mappings.mode

    def snapshot(self):
        with self._lock:
            return self.mappings.sorted_mappings()

    def active_notes(self):
        with self._lock:
            return dict(self._active)

    # -- worker -------------------------------------------------------------

    def _run_worker(self):
        while not self._stop.is_set():
            self._flush_releases()
            try:
                event = self._queue.get(timeout=self._next_timeout())
            except queue.Empty:
                continue
            try:
                self._handle(event)
            except Exception as exc:  # pragma: no cover - defensive
                self._error("event handling failed: %s" % exc)

    def _handle(self, event):
        if event.kind == "note_on":
            self._note_on(event)
        elif event.kind == "note_off":
            self._note_off(event)
        elif event.kind == "control_change" and event.data1 in (
            ALL_NOTES_OFF,
            ALL_SOUND_OFF,
        ):
            self._release_all_keys()
            self._emit({"type": "all_notes_off"})

    def _note_on(self, event):
        self._check_target_privilege()
        note = event.data1
        velocity = event.data2
        with self._lock:
            mode = self.mappings.mode
            threshold = self.mappings.velocity_threshold
            key = None if velocity < threshold else self.mappings.get(note)
        if key is None:
            self._emit(
                {
                    "type": "note",
                    "action": "ignore",
                    "note": note,
                    "velocity": velocity,
                    "key": None,
                }
            )
            return

        if mode == MODE_TAP:
            try:
                self._sender.key_down(key)
            except OSError as exc:
                self._error("key down %s failed: %s" % (key, exc))
                return
            with self._lock:
                hold = self.mappings.tap_ms / 1000.0
                self._tap_deadlines[key] = time.monotonic() + hold
            self._emit(
                {
                    "type": "note",
                    "action": "tap",
                    "note": note,
                    "velocity": velocity,
                    "key": key,
                }
            )
            return

        with self._lock:
            if note in self._active:
                return
            already_held = key in self._key_notes and len(self._key_notes[key]) > 0
            self._active[note] = key
            self._key_notes.setdefault(key, set()).add(note)
        try:
            if not already_held:
                self._sender.key_down(key)
        except OSError as exc:
            self._error("key down %s failed: %s" % (key, exc))
            return
        self._emit(
            {
                "type": "note",
                "action": "down",
                "note": note,
                "velocity": velocity,
                "key": key,
            }
        )

    def _check_target_privilege(self):
        """Warn once when the focused app runs with higher integrity (UIPI).

        Windows silently drops input injected by a lower-integrity process, so
        this is the usual reason a game ignores the keys while a normal editor
        accepts them.
        """
        if self._uipi_warned:
            return
        now = time.monotonic()
        if now - self._uipi_checked_at < 2.0:
            return
        self._uipi_checked_at = now
        try:
            mine = winutil.current_integrity()
            target = winutil.foreground_integrity()
        except Exception:
            return
        if mine is None or target is None or target <= mine:
            return
        self._uipi_warned = True
        self._emit(
            {
                "type": "warn",
                "message": (
                    "目标程序以「%s」权限运行，Windows 会拦截模拟按键。"
                    "请点『以管理员重启』，或让该程序以普通权限运行。"
                    % winutil.integrity_label(target)
                ),
            }
        )

    def _note_off(self, event):
        with self._lock:
            if self.mappings.mode == MODE_TAP:
                return
            note = event.data1
            key = self._active.pop(note, None)
            if key is None:
                return
            notes = self._key_notes.get(key)
            if notes is not None:
                notes.discard(note)
                still_held = bool(notes)
                if not still_held:
                    del self._key_notes[key]
            else:
                still_held = False
        if not still_held:
            try:
                self._sender.key_up(key)
            except OSError as exc:
                self._error("key up %s failed: %s" % (key, exc))
        self._emit(
            {
                "type": "note",
                "action": "up",
                "note": note,
                "velocity": event.data2,
                "key": key,
            }
        )

    def _release_all_keys(self):
        with self._lock:
            self._active.clear()
            self._key_notes.clear()
            self._tap_deadlines.clear()
        self._sender.release_all()

    # -- tap release scheduler ---------------------------------------------

    def _next_timeout(self):
        with self._lock:
            if not self._tap_deadlines:
                return 0.1
            soonest = min(self._tap_deadlines.values())
        return max(0.0, min(0.1, soonest - time.monotonic()))

    def _flush_releases(self, now=None):
        with self._lock:
            if not self._tap_deadlines:
                return
            if now is None:
                now = time.monotonic()
            due = [k for k, deadline in self._tap_deadlines.items() if now >= deadline]
            for key in due:
                del self._tap_deadlines[key]
        for key in due:
            try:
                self._sender.key_up(key)
            except OSError as exc:
                self._error("key up %s failed: %s" % (key, exc))

    # -- event reporting ----------------------------------------------------

    def _emit(self, payload):
        if "note" in payload:
            payload.setdefault("note_name", note_name(payload["note"]))
        cb = self.on_event
        if cb is not None:
            try:
                cb(payload)
            except Exception:  # pragma: no cover - defensive
                pass

    def _error(self, message):
        self._emit({"type": "error", "message": message})

    def _midi_error(self, exc):
        self._error("MIDI callback error: %s" % exc)
