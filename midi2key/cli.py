"""Command line entry points for Midi2Key."""

import argparse
import ctypes
import os
import queue
import sys

from . import midiin
from .mapping import MappingSet, note_name
from .presets import PRESETS


def _app_dir():
    """Directory to keep user files in.

    When frozen (PyInstaller) ``__file__`` points inside the temporary
    extraction folder, so use the executable's own folder instead.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ensure_console_output():
    """Give a windowed (no-console) build a stdout/stderr.

    A ``--windowed`` executable has no console, which makes ``--list-devices``
    and ``--monitor`` silent.  Attach to the parent console when launched from
    a terminal, otherwise fall back to NUL.
    """
    if sys.stdout is not None and sys.stderr is not None:
        return
    if sys.stdout is None:
        try:
            if ctypes.windll.kernel32.AttachConsole(-1):
                sys.stdout = open("CONOUT$", "w", buffering=1)
        except Exception:
            pass
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = sys.stdout


PROJECT_ROOT = _app_dir()
DEFAULT_CONFIG = os.path.join(PROJECT_ROOT, "config.json")


def _print_devices():
    devices = midiin.list_devices()
    if not devices:
        print("未检测到 MIDI 输入设备。")
        return 1
    print("MIDI 输入设备:")
    for index, name in devices:
        print("  %d: %s" % (index, name))
    return 0


def _monitor(device_id):
    devices = midiin.list_devices()
    if not devices:
        print("未检测到 MIDI 输入设备。", file=sys.stderr)
        return 1
    if device_id is None:
        device_id = devices[0][0]
    midi = midiin.MidiInput(
        device_id, on_error=lambda e: print("err:", e, file=sys.stderr)
    )
    midi.start()
    print("正在监听设备 %d: %s  (Ctrl+C 退出)" % (device_id, midi.device_name))
    try:
        while True:
            try:
                event = midi.queue.get(timeout=0.5)
            except queue.Empty:
                continue
            print(
                "%-16s ch=%-2d d1=%-3d d2=%-3d"
                % (event.kind, event.channel + 1, event.data1, event.data2)
            )
    except KeyboardInterrupt:
        pass
    finally:
        midi.stop()
    return 0


def _apply_preset(name, config_path, start_note):
    path = config_path or DEFAULT_CONFIG
    existing = MappingSet.load(path)
    preset = PRESETS[name](start_note)
    preset.device = existing.device
    preset.save(path)
    print(
        "已写入预设 '%s'：%d 条映射 (起始音 %d) -> %s"
        % (name, len(preset.mappings), start_note, path)
    )
    for m in preset.sorted_mappings():
        print("  %-4d %-4s -> %s" % (m.note, note_name(m.note), m.key))
    return 0


def main(argv=None):
    _ensure_console_output()
    parser = argparse.ArgumentParser(
        prog="Midi2Key",
        description="把 MIDI 键盘的按键映射为电脑键盘按键。",
    )
    parser.add_argument("--list-devices", action="store_true", help="列出 MIDI 输入设备后退出")
    parser.add_argument("--monitor", action="store_true", help="在控制台实时打印 MIDI 事件")
    parser.add_argument("--device", type=int, default=None, help="设备序号（配合 --monitor）")
    parser.add_argument("--preset", choices=sorted(PRESETS), help="把内置预设写入配置文件后退出")
    parser.add_argument(
        "--start-note",
        type=int,
        default=60,
        help="预设的起始音，默认 60 = C4（配合 --preset）",
    )
    parser.add_argument("--config", default=None, help="配置文件路径")
    args = parser.parse_args(argv)

    if args.list_devices:
        return _print_devices()
    if args.monitor:
        return _monitor(args.device)
    if args.preset:
        return _apply_preset(args.preset, args.config, args.start_note)

    config_path = args.config or DEFAULT_CONFIG

    import tkinter as tk
    from .gui import App

    root = tk.Tk()
    App(root, config_path)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
