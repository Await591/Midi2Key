"""Virtual-Key code table for Windows SendInput.

Maps human friendly, lowercase key names to Win32 Virtual-Key codes and
back again, plus the set of keys that require the KEYEVENTF_EXTENDEDKEY flag.
"""

NAME_TO_VK = {}
VK_TO_NAME = {}
DISPLAY = {}

EXTENDED_VKS = set()


def _add(name, vk, display=None, extended=False):
    NAME_TO_VK[name] = vk
    VK_TO_NAME[vk] = name
    DISPLAY[name] = display or name.upper()
    if extended:
        EXTENDED_VKS.add(vk)


# Letters
for _i in range(26):
    _ch = chr(ord("a") + _i)
    _add(_ch, ord("A") + _i, _ch.upper())

# Digits
for _i in range(10):
    _add(str(_i), ord("0") + _i, str(_i))

# Function keys
for _i in range(1, 25):
    _add("f%d" % _i, 0x6F + _i, "F%d" % _i)

# Editing / navigation
_add("backspace", 0x08, "Backspace")
_add("tab", 0x09, "Tab")
_add("enter", 0x0D, "Enter")
_add("esc", 0x1B, "Esc")
_add("space", 0x20, "Space")
_add("pageup", 0x21, "Page Up", extended=True)
_add("pagedown", 0x22, "Page Down", extended=True)
_add("end", 0x23, "End", extended=True)
_add("home", 0x24, "Home", extended=True)
_add("left", 0x25, "Left", extended=True)
_add("up", 0x26, "Up", extended=True)
_add("right", 0x27, "Right", extended=True)
_add("down", 0x28, "Down", extended=True)
_add("insert", 0x2D, "Insert", extended=True)
_add("delete", 0x2E, "Delete", extended=True)
_add("printscreen", 0x2C, "Print Screen", extended=True)
_add("apps", 0x5D, "Menu", extended=True)

# Locks / system
_add("capslock", 0x14, "Caps Lock")
_add("numlock", 0x90, "Num Lock", extended=True)
_add("scrolllock", 0x91, "Scroll Lock")
_add("pause", 0x13, "Pause")

# Modifiers (generic names use the left variant)
_add("shift", 0x10, "Shift")
_add("ctrl", 0x11, "Ctrl")
_add("alt", 0x12, "Alt")
_add("lshift", 0xA0, "Left Shift")
_add("rshift", 0xA1, "Right Shift")
_add("lctrl", 0xA2, "Left Ctrl")
_add("rctrl", 0xA3, "Right Ctrl", extended=True)
_add("lalt", 0xA4, "Left Alt")
_add("ralt", 0xA5, "Right Alt", extended=True)
_add("lwin", 0x5B, "Left Win", extended=True)
_add("rwin", 0x5C, "Right Win", extended=True)

# Numpad
for _i in range(10):
    _add("num%d" % _i, 0x60 + _i, "Num %d" % _i)
_add("multiply", 0x6A, "Num *")
_add("add", 0x6B, "Num +")
_add("separator", 0x6C, "Num ,")
_add("subtract", 0x6D, "Num -")
_add("decimal", 0x6E, "Num .")
_add("divide", 0x6F, "Num /", extended=True)

# OEM punctuation
_add("semicolon", 0xBA, "; :")
_add("equals", 0xBB, "= +")
_add("comma", 0xBC, ", <")
_add("minus", 0xBD, "- _")
_add("period", 0xBE, ". >")
_add("slash", 0xBF, "/ ?")
_add("backtick", 0xC0, "` ~")
_add("bracketleft", 0xDB, "[ {")
_add("backslash", 0xDC, "\\ |")
_add("bracketright", 0xDD, "] }")
_add("quote", 0xDE, "' \"")


def is_valid_key(name):
    """Return True if *name* is a known key name."""
    return isinstance(name, str) and name.lower() in NAME_TO_VK


def vk_code(name):
    """Return the Virtual-Key code for *name* or raise ValueError."""
    try:
        return NAME_TO_VK[name.lower()]
    except (KeyError, AttributeError):
        raise ValueError("unknown key name: %r" % (name,))


def name_for_vk(vk):
    """Return the canonical key name for a virtual-key code, or None."""
    return VK_TO_NAME.get(vk)


def display_name(name):
    """Return a human readable label for *name*."""
    return DISPLAY.get(name.lower(), name)


def is_extended(vk):
    """Return True if *vk* needs KEYEVENTF_EXTENDEDKEY."""
    return vk in EXTENDED_VKS


def key_names():
    """Return all canonical key names in a stable, display friendly order."""
    return list(DISPLAY.keys())


def sorted_key_names():
    """Return key names ordered by (display label, name) for combo boxes."""
    return sorted(DISPLAY.keys(), key=lambda n: (DISPLAY[n].lower(), n))


def key_label(name):
    """Return 'Display (name)' used by the GUI combo boxes."""
    return "%s  [%s]" % (display_name(name), name)
