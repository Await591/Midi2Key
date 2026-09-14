"""Tkinter GUI for Midi2Key.

The GUI thread never touches MIDI or SendInput directly: the engine reports
events through a thread-safe queue which is drained periodically with
``root.after``.
"""

import os
import queue
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from . import midiin, vk, winutil
from .engine import Engine
from .mapping import (
    MappingSet,
    parse_note,
    note_name,
    MODE_TAP,
    MODE_HOLD,
    SEND_MODE_BOTH,
    SEND_MODE_VK,
    SEND_MODE_SCANCODE,
)
from .presets import PRESETS

MODE_LABELS = {MODE_TAP: "点按", MODE_HOLD: "按住"}
LABEL_TO_MODE = {v: k for k, v in MODE_LABELS.items()}
SEND_MODE_LABELS = {
    SEND_MODE_BOTH: "混合(推荐)",
    SEND_MODE_VK: "虚拟键",
    SEND_MODE_SCANCODE: "扫描码",
}
LABEL_TO_SEND_MODE = {v: k for k, v in SEND_MODE_LABELS.items()}
PRESET_LABELS = {"sky": "光遇"}

KEYSYM_TO_KEY = {
    "space": "space",
    "Return": "enter",
    "KP_Enter": "enter",
    "Escape": "esc",
    "Tab": "tab",
    "BackSpace": "backspace",
    "Caps_Lock": "capslock",
    "Num_Lock": "numlock",
    "Scroll_Lock": "scrolllock",
    "Pause": "pause",
    "Print": "printscreen",
    "Shift_L": "lshift",
    "Shift_R": "rshift",
    "Control_L": "lctrl",
    "Control_R": "rctrl",
    "Alt_L": "lalt",
    "Alt_R": "ralt",
    "Super_L": "lwin",
    "Super_R": "rwin",
    "Menu": "apps",
    "Up": "up",
    "Down": "down",
    "Left": "left",
    "Right": "right",
    "Insert": "insert",
    "Delete": "delete",
    "Home": "home",
    "End": "end",
    "Prior": "pageup",
    "Next": "pagedown",
    "minus": "minus",
    "equal": "equals",
    "bracketleft": "bracketleft",
    "bracketright": "bracketright",
    "backslash": "backslash",
    "semicolon": "semicolon",
    "apostrophe": "quote",
    "grave": "backtick",
    "comma": "comma",
    "period": "period",
    "slash": "slash",
    "KP_Add": "add",
    "KP_Subtract": "subtract",
    "KP_Multiply": "multiply",
    "KP_Divide": "divide",
    "KP_Decimal": "decimal",
    "KP_Separator": "separator",
}
for _i in range(10):
    KEYSYM_TO_KEY["KP_%d" % _i] = "num%d" % _i

MAX_LOG_LINES = 300


def keysym_to_name(keysym):
    """Convert a Tk keysym string to a Midi2Key key name (or None)."""
    if not keysym:
        return None
    if len(keysym) == 1 and keysym.isalpha():
        return keysym.lower()
    if len(keysym) == 1 and keysym.isdigit():
        return keysym
    if keysym.startswith("F") and keysym[1:].isdigit():
        n = int(keysym[1:])
        if 1 <= n <= 24:
            return "f%d" % n
    return KEYSYM_TO_KEY.get(keysym)


class App:
    def __init__(self, root, config_path):
        self.root = root
        self.config_path = config_path
        self.mappings = MappingSet.load(config_path)
        self.engine = Engine(self.mappings, on_event=self._on_engine_event)
        self.events = queue.Queue()
        self._note_capture = None
        self._devices = []

        root.title("Midi2Key")
        root.geometry("860x640")
        root.minsize(720, 520)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self._build_ui()
        self.refresh_devices()
        self._refresh_table()
        self._sync_controls()
        if not winutil.is_elevated():
            self._log(
                "提示：若目标程序以管理员运行，模拟按键会被 Windows 拦截，"
                "请点『以管理员重启』。"
            )
        self.root.after(40, self._pump)

    # -- UI construction ----------------------------------------------------

    def _build_ui(self):
        style = ttk.Style()
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass

        top = ttk.Frame(self.root, padding=(10, 8))
        top.pack(fill="x")

        ttk.Label(top, text="MIDI 设备:").grid(row=0, column=0, sticky="w")
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(
            top, textvariable=self.device_var, state="readonly", width=42
        )
        self.device_combo.grid(row=0, column=1, sticky="we", padx=(6, 6))
        self.device_combo.bind("<<ComboboxSelected>>", self._on_device_selected)

        ttk.Button(top, text="刷新", command=self.refresh_devices).grid(
            row=0, column=2, padx=(0, 6)
        )
        self.start_btn = ttk.Button(top, text="开始", command=self.toggle_engine)
        self.start_btn.grid(row=0, column=3)

        top.columnconfigure(1, weight=1)

        mid = ttk.Frame(self.root, padding=(10, 0))
        mid.pack(fill="both", expand=True)

        columns = ("note", "name", "key", "enabled")
        self.tree = ttk.Treeview(mid, columns=columns, show="headings", height=14)
        self.tree.heading("note", text="音符")
        self.tree.heading("name", text="音名")
        self.tree.heading("key", text="目标按键")
        self.tree.heading("enabled", text="启用")
        self.tree.column("note", width=80, anchor="center")
        self.tree.column("name", width=100, anchor="center")
        self.tree.column("key", width=200, anchor="w")
        self.tree.column("enabled", width=70, anchor="center")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<Double-1>", lambda e: self.edit_mapping())

        scroll = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)

        btns = ttk.Frame(mid)
        btns.grid(row=0, column=2, sticky="ns", padx=(8, 0))
        for text, cmd in (
            ("添加", self.add_mapping),
            ("编辑", self.edit_mapping),
            ("删除", self.delete_mapping),
            ("启用/禁用", self.toggle_mapping),
        ):
            ttk.Button(btns, text=text, command=cmd, width=10).pack(
                fill="x", pady=(0, 6)
            )
        ttk.Separator(btns, orient="horizontal").pack(fill="x", pady=6)
        for name in sorted(PRESETS):
            ttk.Button(
                btns,
                text="预设：" + PRESET_LABELS.get(name, name),
                command=lambda n=name: self.apply_preset(n),
                width=10,
            ).pack(fill="x", pady=(0, 6))
        ttk.Separator(btns, orient="horizontal").pack(fill="x", pady=6)
        ttk.Button(btns, text="保存", command=self.save_config, width=10).pack(
            fill="x", pady=(0, 6)
        )
        ttk.Button(btns, text="另存为", command=self.save_config_as, width=10).pack(
            fill="x", pady=(0, 6)
        )
        ttk.Button(btns, text="载入", command=self.load_config, width=10).pack(fill="x")

        mid.rowconfigure(0, weight=1)
        mid.columnconfigure(0, weight=1)

        opts = ttk.Frame(self.root, padding=(10, 6))
        opts.pack(fill="x")
        ttk.Label(opts, text="触发方式:").pack(side="left")
        self.mode_var = tk.StringVar(
            value=MODE_LABELS.get(self.mappings.mode, MODE_LABELS[MODE_TAP])
        )
        self.mode_combo = ttk.Combobox(
            opts,
            textvariable=self.mode_var,
            state="readonly",
            width=6,
            values=list(MODE_LABELS.values()),
        )
        self.mode_combo.pack(side="left", padx=(6, 12))
        self.mode_combo.bind("<<ComboboxSelected>>", self._on_mode_changed)

        ttk.Label(opts, text="按键时长 (ms):").pack(side="left")
        self.tap_ms_var = tk.IntVar(value=self.mappings.tap_ms)
        tap_spin = ttk.Spinbox(
            opts,
            from_=0,
            to=1000,
            increment=5,
            width=5,
            textvariable=self.tap_ms_var,
            command=self._on_tap_ms_changed,
        )
        tap_spin.pack(side="left", padx=(6, 12))
        tap_spin.bind("<FocusOut>", lambda _e: self._on_tap_ms_changed())

        ttk.Label(opts, text="发送方式:").pack(side="left")
        self.send_mode_var = tk.StringVar(
            value=SEND_MODE_LABELS.get(
                self.mappings.send_mode, SEND_MODE_LABELS[SEND_MODE_BOTH]
            )
        )
        self.send_mode_combo = ttk.Combobox(
            opts,
            textvariable=self.send_mode_var,
            state="readonly",
            width=11,
            values=list(SEND_MODE_LABELS.values()),
        )
        self.send_mode_combo.pack(side="left", padx=(6, 12))
        self.send_mode_combo.bind(
            "<<ComboboxSelected>>", self._on_send_mode_changed
        )

        ttk.Label(opts, text="力度阈值 (0-127):").pack(side="left")
        self.velocity_var = tk.IntVar(value=self.mappings.velocity_threshold)
        spin = ttk.Spinbox(
            opts,
            from_=0,
            to=127,
            width=5,
            textvariable=self.velocity_var,
            command=self._on_velocity_changed,
        )
        spin.pack(side="left", padx=(6, 12))
        ttk.Button(opts, text="全部释放 (Panic)", command=self.panic).pack(side="left")

        self.admin_button = None
        if not winutil.is_elevated():
            self.admin_button = ttk.Button(
                opts, text="以管理员重启", command=self.restart_as_admin
            )
            self.admin_button.pack(side="left", padx=(8, 0))

        self.status_var = tk.StringVar(value="已停止")
        ttk.Label(opts, textvariable=self.status_var, foreground="#444").pack(
            side="right"
        )

        log_frame = ttk.LabelFrame(self.root, text="事件日志", padding=(6, 4))
        log_frame.pack(fill="both", expand=False, padx=10, pady=(0, 10))
        self.log = tk.Text(log_frame, height=8, wrap="none", state="disabled")
        self.log.pack(side="left", fill="both", expand=True)
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        log_scroll.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=log_scroll.set)

    # -- devices ------------------------------------------------------------

    def refresh_devices(self):
        self._devices = midiin.list_devices()
        values = ["%d: %s" % (idx, name) for idx, name in self._devices]
        self.device_combo["values"] = values

        if not values:
            self.device_var.set("(未检测到 MIDI 设备)")
            return
        selected = None
        if self.mappings.device:
            for idx, name in self._devices:
                if name == self.mappings.device:
                    selected = "%d: %s" % (idx, name)
                    break
        if selected is None:
            selected = values[0]
            self.mappings.device = self._devices[0][1]
        self.device_var.set(selected)

    def _selected_device_index(self):
        text = self.device_var.get()
        if not text or ":" not in text:
            return None
        try:
            return int(text.split(":", 1)[0].strip())
        except ValueError:
            return None

    def _on_device_selected(self, _event=None):
        index = self._selected_device_index()
        if index is None:
            return
        name = dict(self._devices).get(index)
        with_name = name if name is not None else self.device_var.get()
        self.engine.set_device(with_name)
        if self.engine.is_running:
            self.stop_engine()
            self.start_engine()
        self._save_quiet()

    # -- engine control -----------------------------------------------------

    def toggle_engine(self):
        if self.engine.is_running:
            self.stop_engine()
        else:
            self.start_engine()

    def start_engine(self):
        index = self._selected_device_index()
        if index is None:
            messagebox.showwarning("Midi2Key", "请先选择一个 MIDI 设备。")
            return
        try:
            self.engine.start(index)
        except Exception as exc:
            messagebox.showerror("Midi2Key", "无法启动 MIDI 输入:\n%s" % exc)
            self._sync_controls()
            return
        self._log("已连接: %s" % (self.engine.device_name or "?"))
        self._sync_controls()

    def stop_engine(self):
        if not self.engine.is_running:
            return
        self.engine.stop()
        self._log("已断开")
        self._sync_controls()

    def panic(self):
        self.engine.panic()
        self._log("已释放全部按键")

    def restart_as_admin(self):
        """Relaunch elevated so injected keys reach elevated target apps."""
        if winutil.is_elevated():
            messagebox.showinfo("Midi2Key", "当前已是管理员权限。")
            return
        if not messagebox.askyesno(
            "Midi2Key",
            "以管理员身份重启 Midi2Key？\n\n"
            "当游戏/程序以管理员运行时，Windows 会拦截普通权限进程的模拟按键。\n"
            "（会弹出 UAC 确认框）",
        ):
            return
        try:
            started = winutil.relaunch_as_admin()
        except OSError as exc:
            messagebox.showerror("Midi2Key", "重启失败: %s" % exc)
            return
        if not started:
            self._log("已取消以管理员身份重启")
            return
        self.on_close()

    def _sync_controls(self):
        running = self.engine.is_running
        self.start_btn.configure(text="停止" if running else "开始")
        if running:
            self.status_var.set("运行中: %s" % (self.engine.device_name or "?"))
        else:
            self.status_var.set("已停止")

    # -- mapping table ------------------------------------------------------

    def _refresh_table(self):
        selected = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for m in self.engine.snapshot():
            self.tree.insert(
                "",
                "end",
                iid=str(m.note),
                values=(
                    m.note,
                    note_name(m.note),
                    vk.key_label(m.key) if vk.is_valid_key(m.key) else m.key,
                    "是" if m.enabled else "否",
                ),
            )
        for iid in selected:
            if self.tree.exists(iid):
                self.tree.selection_add(iid)

    def _selected_note(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return int(sel[0])

    def add_mapping(self):
        self._open_edit_dialog(None)

    def edit_mapping(self):
        note = self._selected_note()
        if note is None:
            messagebox.showinfo("Midi2Key", "请先选择一条映射。")
            return
        self._open_edit_dialog(self.engine.mappings.find(note))

    def delete_mapping(self):
        note = self._selected_note()
        if note is None:
            messagebox.showinfo("Midi2Key", "请先选择一条映射。")
            return
        self.engine.remove(note)
        self._refresh_table()
        self._save_quiet()

    def toggle_mapping(self):
        note = self._selected_note()
        if note is None:
            messagebox.showinfo("Midi2Key", "请先选择一条映射。")
            return
        m = self.engine.mappings.find(note)
        if m is not None:
            self.engine.set_enabled(note, not m.enabled)
            self._refresh_table()
            self._save_quiet()

    def _open_edit_dialog(self, mapping):
        dialog = tk.Toplevel(self.root)
        dialog.title("编辑映射" if mapping else "添加映射")
        dialog.transient(self.root)
        dialog.resizable(False, False)

        note_var = tk.StringVar(value=str(mapping.note) if mapping else "")
        key_var = tk.StringVar(value=mapping.key if mapping else "")
        enabled_var = tk.BooleanVar(value=mapping.enabled if mapping else True)

        body = ttk.Frame(dialog, padding=12)
        body.pack(fill="both", expand=True)

        ttk.Label(body, text="MIDI 音符 (0-127):").grid(row=0, column=0, sticky="w")
        note_entry = ttk.Entry(body, textvariable=note_var, width=18)
        note_entry.grid(row=0, column=1, sticky="w", padx=6)
        note_label = ttk.Label(body, text="")
        note_label.grid(row=1, column=1, sticky="w", padx=6)

        capture_btn = ttk.Button(
            body,
            text="捕获 MIDI 音符",
            command=lambda: self._begin_note_capture(dialog, note_var, note_label),
        )
        capture_btn.grid(row=0, column=2, padx=(6, 0))

        ttk.Label(body, text="目标按键:").grid(
            row=2, column=0, sticky="w", pady=(10, 0)
        )
        key_combo = ttk.Combobox(
            body,
            textvariable=key_var,
            values=[vk.key_label(k) for k in vk.sorted_key_names()],
            width=24,
        )
        key_combo.grid(row=2, column=1, sticky="w", padx=6, pady=(10, 0))
        key_combo["state"] = "normal"

        def set_key(name):
            key_var.set(name)
            key_combo.set(name)

        ttk.Button(
            body,
            text="捕获按键",
            command=lambda: self._begin_key_capture(dialog, set_key),
        ).grid(row=2, column=2, padx=(6, 0), pady=(10, 0))

        ttk.Checkbutton(body, text="启用", variable=enabled_var).grid(
            row=3, column=1, sticky="w", padx=6, pady=(10, 0)
        )

        def update_note_label(*_args):
            text = note_var.get().strip()
            if not text:
                note_label.configure(text="")
                return
            try:
                note_label.configure(text="= %s" % note_name(parse_note(text)))
            except ValueError:
                note_label.configure(text="无效音符")

        note_var.trace_add("write", update_note_label)
        update_note_label()

        def on_ok():
            raw_note = note_var.get().strip()
            raw_key = key_var.get().strip()
            if not raw_note:
                messagebox.showwarning("Midi2Key", "请填写或捕获一个 MIDI 音符。")
                return
            try:
                note = parse_note(raw_note)
            except ValueError as exc:
                messagebox.showwarning("Midi2Key", str(exc))
                return
            if not raw_key:
                messagebox.showwarning("Midi2Key", "请选择或捕获一个目标按键。")
                return
            name = raw_key.split("[")[-1].rstrip("]") if "[" in raw_key else raw_key
            if not vk.is_valid_key(name):
                messagebox.showwarning("Midi2Key", "未知按键: %s" % raw_key)
                return
            self.engine.upsert(note, name.lower(), enabled_var.get())
            self._refresh_table()
            self._save_quiet()
            close()

        def close():
            self._note_capture = None
            dialog.destroy()

        buttons = ttk.Frame(body)
        buttons.grid(row=4, column=0, columnspan=3, sticky="e", pady=(16, 0))
        ttk.Button(buttons, text="取消", command=close).pack(side="right")
        ttk.Button(buttons, text="确定", command=on_ok).pack(
            side="right", padx=(0, 8)
        )

        dialog.protocol("WM_DELETE_WINDOW", close)
        note_entry.focus_set()
        self._center(dialog)
        dialog.grab_set()

    def _begin_note_capture(self, dialog, note_var, note_label):
        if not self.engine.is_running:
            messagebox.showinfo(
                "Midi2Key",
                "请先在主窗口点击「开始」连接 MIDI 设备后再捕获音符。",
            )
            return
        note_label.configure(text="正在等待按下 MIDI 键...")

        def on_captured(note):
            note_var.set(str(note))

        self._note_capture = on_captured

    def _begin_key_capture(self, parent, set_key):
        cap = tk.Toplevel(parent)
        cap.title("捕获按键")
        cap.transient(parent)
        cap.resizable(False, False)

        frame = ttk.Frame(cap, padding=16)
        frame.pack(fill="both", expand=True)
        label = ttk.Label(frame, text="请按下一个电脑按键...")
        label.pack()

        def on_key(event):
            name = keysym_to_name(event.keysym)
            if name is None:
                label.configure(text="不支持的按键: %s，请换一个" % event.keysym)
                return "break"
            set_key(name)
            cap.destroy()
            return "break"

        def cancel():
            cap.destroy()

        ttk.Button(frame, text="取消", command=cancel).pack(pady=(12, 0))
        cap.bind("<KeyPress>", on_key)
        self._center(cap)
        cap.grab_set()
        cap.focus_force()

    # -- config -------------------------------------------------------------

    def save_config(self):
        try:
            self.mappings.save(self.config_path)
        except OSError as exc:
            messagebox.showerror("Midi2Key", "保存失败: %s" % exc)
            return
        self._log("已保存配置: %s" % self.config_path)

    def _save_quiet(self):
        try:
            self.mappings.save(self.config_path)
        except OSError:
            pass

    def save_config_as(self):
        path = filedialog.asksaveasfilename(
            title="另存为",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
            initialfile=os.path.basename(self.config_path),
        )
        if not path:
            return
        self.config_path = path
        self.save_config()

    def load_config(self):
        path = filedialog.askopenfilename(
            title="载入配置",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        was_running = self.engine.is_running
        if was_running:
            self.stop_engine()
        self.mappings = MappingSet.load(path)
        self.engine.replace_mappings(self.mappings)
        self.config_path = path
        self.velocity_var.set(self.mappings.velocity_threshold)
        self.tap_ms_var.set(self.mappings.tap_ms)
        self.send_mode_var.set(
            SEND_MODE_LABELS.get(self.mappings.send_mode, SEND_MODE_LABELS[SEND_MODE_BOTH])
        )
        self.mode_var.set(
            MODE_LABELS.get(self.mappings.mode, MODE_LABELS[MODE_TAP])
        )
        self.refresh_devices()
        self._refresh_table()
        self._log("已载入配置: %s" % path)

    def apply_preset(self, name):
        if name not in PRESETS:
            return
        label = PRESET_LABELS.get(name, name)
        if self.mappings.mappings and not messagebox.askyesno(
            "Midi2Key", "用「%s」预设替换当前全部映射？" % label
        ):
            return
        preset = PRESETS[name]()
        preset.device = self.mappings.device
        preset.mode = self.mappings.mode
        preset.velocity_threshold = self.mappings.velocity_threshold
        preset.tap_ms = self.mappings.tap_ms
        preset.send_mode = self.mappings.send_mode
        self.mappings = preset
        self.engine.replace_mappings(preset)
        self._refresh_table()
        self._save_quiet()
        self._log("已应用预设：%s（%d 条映射）" % (label, len(preset.mappings)))

    def _on_velocity_changed(self):
        try:
            value = int(self.velocity_var.get())
        except (tk.TclError, ValueError):
            return
        value = max(0, min(127, value))
        self.engine.set_velocity_threshold(value)

    def _on_mode_changed(self, _event=None):
        mode = LABEL_TO_MODE.get(self.mode_var.get(), MODE_TAP)
        if self.engine.set_mode(mode):
            self._log("触发方式: %s" % MODE_LABELS[mode])
            self._save_quiet()

    def _on_tap_ms_changed(self):
        try:
            value = int(self.tap_ms_var.get())
        except (tk.TclError, ValueError):
            return
        value = max(0, min(1000, value))
        self.engine.set_tap_ms(value)
        self._save_quiet()

    def _on_send_mode_changed(self, _event=None):
        mode = LABEL_TO_SEND_MODE.get(self.send_mode_var.get(), SEND_MODE_BOTH)
        if self.engine.set_send_mode(mode):
            self._log("发送方式: %s" % SEND_MODE_LABELS[mode])
            self._save_quiet()

    # -- engine events ------------------------------------------------------

    def _on_engine_event(self, payload):
        self.events.put(payload)

    def _pump(self):
        budget = 200
        while budget > 0:
            try:
                payload = self.events.get_nowait()
            except queue.Empty:
                break
            self._handle_event(payload)
            budget -= 1
        self.root.after(40, self._pump)

    def _handle_event(self, payload):
        kind = payload.get("type")
        if kind == "note":
            self._handle_note_event(payload)
        elif kind == "error":
            self._log("错误: %s" % payload.get("message"))
        elif kind == "warn":
            message = payload.get("message", "")
            self._log("【警告】%s" % message)
            self.status_var.set(message)
        elif kind == "all_notes_off":
            self._log("收到 All Notes Off，已释放全部按键")
        elif kind == "state":
            pass

    def _handle_note_event(self, payload):
        action = payload.get("action")
        note = payload.get("note")
        key = payload.get("key")
        if action == "ignore":
            self._log(
                "音符 %s (%d) 无映射"
                % (payload.get("note_name", note), note)
            )
            return

        if self._note_capture is not None and action == "down":
            cb = self._note_capture
            self._note_capture = None
            try:
                cb(note)
            except Exception:
                pass
            self._log("已捕获音符 %s (%d)" % (payload.get("note_name", note), note))
            return

        arrow = {"down": "↓ 按下", "up": "↑ 抬起", "tap": "敲击"}.get(action, action)
        self._log(
            "%s  %s (%d)  ->  %s"
            % (arrow, payload.get("note_name", note), note, vk.display_name(key))
        )

    # -- misc ---------------------------------------------------------------

    def _log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        lines = int(self.log.index("end-1c").split(".")[0])
        if lines > MAX_LOG_LINES:
            self.log.delete("1.0", "%d.0" % (lines - MAX_LOG_LINES + 1))
        self.log.see("end")
        self.log.configure(state="disabled")

    def _center(self, window):
        window.update_idletasks()
        px = self.root.winfo_rootx()
        py = self.root.winfo_rooty()
        pw = self.root.winfo_width()
        ph = self.root.winfo_height()
        w = window.winfo_width()
        h = window.winfo_height()
        window.geometry("+%d+%d" % (px + (pw - w) // 2, py + (ph - h) // 2))

    def on_close(self):
        try:
            self.engine.stop()
        finally:
            self._save_quiet()
            self.root.destroy()
