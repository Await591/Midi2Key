"""Mapping model: MIDI note -> computer key, plus config load/save."""

import json
import os
from dataclasses import dataclass, field
from typing import Optional

CONFIG_VERSION = 1

MODE_TAP = "tap"
MODE_HOLD = "hold"
VALID_MODES = (MODE_TAP, MODE_HOLD)

SEND_MODE_BOTH = "both"
SEND_MODE_VK = "vk"
SEND_MODE_SCANCODE = "scancode"
VALID_SEND_MODES = (SEND_MODE_BOTH, SEND_MODE_VK, SEND_MODE_SCANCODE)

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

_FLAT_TO_SHARP = {
    "DB": "C#",
    "EB": "D#",
    "GB": "F#",
    "AB": "G#",
    "BB": "A#",
    "CB": "B",
    "FB": "E",
    "E#": "F",
    "B#": "C",
}


def note_name(note):
    """MIDI note number -> scientific pitch name (60 -> 'C4')."""
    note = int(note)
    return "%s%d" % (NOTE_NAMES[note % 12], note // 12 - 1)


def parse_note(text):
    """Parse a note name ('C4', 'C#4', 'Db4') or a number into 0..127."""
    if isinstance(text, int):
        note = text
    else:
        s = str(text).strip()
        if not s:
            raise ValueError("empty note")
        if s.lstrip("+-").isdigit():
            note = int(s)
        else:
            letters = s[0].upper()
            rest = s[1:].strip()
            accidental = ""
            if rest[:1] in ("#", "b", "B"):
                accidental = rest[0].upper()
                rest = rest[1:].strip()
            token = (letters + accidental).upper()
            token = _FLAT_TO_SHARP.get(token, token)
            if token not in NOTE_NAMES:
                raise ValueError("bad note name: %r" % text)
            if not rest.lstrip("+-").isdigit():
                raise ValueError("bad octave in note: %r" % text)
            octave = int(rest)
            note = (octave + 1) * 12 + NOTE_NAMES.index(token)
    if not 0 <= note <= 127:
        raise ValueError("note out of range 0..127: %r" % text)
    return note


@dataclass
class Mapping:
    note: int
    key: str
    enabled: bool = True

    def to_dict(self):
        return {"note": self.note, "key": self.key, "enabled": self.enabled}

    @classmethod
    def from_dict(cls, data):
        return cls(
            note=int(data["note"]),
            key=str(data["key"]),
            enabled=bool(data.get("enabled", True)),
        )


@dataclass
class MappingSet:
    device: Optional[str] = None
    velocity_threshold: int = 0
    mode: str = MODE_TAP
    tap_ms: int = 50
    send_mode: str = SEND_MODE_BOTH
    mappings: list = field(default_factory=list)

    def get(self, note):
        """Return the target key for *note*, or None if unmapped/disabled."""
        for m in self.mappings:
            if m.note == note and m.enabled:
                return m.key
        return None

    def find(self, note):
        """Return the Mapping for *note* (enabled or not), or None."""
        for m in self.mappings:
            if m.note == note:
                return m
        return None

    def upsert(self, note, key, enabled=True):
        """Add or update the mapping for *note*."""
        existing = self.find(note)
        if existing is not None:
            existing.key = key
            existing.enabled = enabled
            return existing
        m = Mapping(note=note, key=key, enabled=enabled)
        self.mappings.append(m)
        self.mappings.sort(key=lambda x: x.note)
        return m

    def remove(self, note):
        """Remove the mapping for *note*. Returns True if removed."""
        before = len(self.mappings)
        self.mappings = [m for m in self.mappings if m.note != note]
        return len(self.mappings) != before

    def sorted_mappings(self):
        return sorted(self.mappings, key=lambda m: m.note)

    def to_dict(self):
        return {
            "version": CONFIG_VERSION,
            "device": self.device,
            "velocity_threshold": int(self.velocity_threshold),
            "mode": self.mode if self.mode in VALID_MODES else MODE_TAP,
            "tap_ms": max(0, min(1000, int(self.tap_ms))),
            "send_mode": self.send_mode if self.send_mode in VALID_SEND_MODES else SEND_MODE_BOTH,
            "mappings": [m.to_dict() for m in self.sorted_mappings()],
        }

    @classmethod
    def from_dict(cls, data):
        mappings = []
        for item in data.get("mappings", []):
            try:
                mappings.append(Mapping.from_dict(item))
            except (KeyError, TypeError, ValueError):
                continue
        mappings.sort(key=lambda m: m.note)
        mode = data.get("mode", MODE_TAP)
        if mode not in VALID_MODES:
            mode = MODE_TAP
        send_mode = data.get("send_mode", SEND_MODE_BOTH)
        if send_mode not in VALID_SEND_MODES:
            send_mode = SEND_MODE_BOTH
        return cls(
            device=data.get("device"),
            velocity_threshold=int(data.get("velocity_threshold", 0)),
            mode=mode,
            tap_ms=int(data.get("tap_ms", 50)),
            send_mode=send_mode,
            mappings=mappings,
        )

    @classmethod
    def load(cls, path):
        """Load a config file, falling back to defaults if missing/invalid."""
        if not os.path.exists(path):
            return default_config()
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return default_config()
        if not isinstance(data, dict):
            return default_config()
        return cls.from_dict(data)

    def save(self, path):
        """Write the config file atomically (UTF-8 JSON)."""
        directory = os.path.dirname(os.path.abspath(path))
        if directory and not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, path)


def default_config():
    """A friendly piano-style layout: C4..C5 on the home-row keys."""
    keys = ["a", "w", "s", "e", "d", "f", "t", "g", "y", "h", "u", "j", "k"]
    mappings = [Mapping(note=60 + i, key=keys[i]) for i in range(len(keys))]
    return MappingSet(
        device=None, velocity_threshold=0, mode=MODE_TAP, mappings=mappings
    )
