"""Built-in mapping presets."""

from .mapping import Mapping, MappingSet, MODE_TAP

WHITE_KEY_STEPS = (0, 2, 4, 5, 7, 9, 11)

SKY_KEYS = [
    "y", "u", "i", "o", "p",
    "h", "j", "k", "l", "semicolon",
    "n", "m", "comma", "period", "slash",
]


def sky(start_note=60):
    """Sky: Children of the Light PC instrument layout (15 diatonic notes).

    Reads the on-screen 3x5 grid top-row-first, so the top row holds the lowest
    notes and the bottom row the highest::

        Y U I O P    C4 D4 E4 F4 G4
        H J K L ;    A4 B4 C5 D5 E5
        N M , . /    F5 G5 A5 B5 C6

    Only the white keys of *start_note* .. *start_note* + 24 are mapped.
    """
    mappings = []
    for index, key in enumerate(SKY_KEYS):
        octave, degree = divmod(index, 7)
        note = int(start_note) + octave * 12 + WHITE_KEY_STEPS[degree]
        mappings.append(Mapping(note=note, key=key))
    return MappingSet(
        device=None, velocity_threshold=0, mode=MODE_TAP, mappings=mappings
    )


PRESETS = {
    "sky": sky,
}
