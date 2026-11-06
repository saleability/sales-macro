"""
SALES MACRO
A macro tool: bind any key / mouse button to a sequence of key presses,
mouse clicks, typed text and waits, with your own timing between each step.

Run:  python sales_macro.py   (or double-click "Sales Macro.bat")
"""

import ctypes
import json
import os
import queue
import random
import sys
import threading
import time
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

from pynput import keyboard, mouse
from pynput.keyboard import Key, KeyCode
from pynput.mouse import Button

# --------------------------------------------------------------------------
# BRAND - change these to restyle the whole app
# --------------------------------------------------------------------------
BRAND = {
    "name": "SALES",
    "product": "MACRO",
    "tagline": "Bind it. Time it. Run it.",
    "bg": "#0d0f14",
    "panel": "#151922",
    "panel2": "#1c2130",
    "border": "#262c3d",
    "text": "#e8ebf2",
    "muted": "#8a93a8",
    "accent": "#a855f7",       # Sales purple
    "accent_dark": "#7e22ce",
    "accent_text": "#ffffff",  # text on accent buttons
    "danger": "#ef4444",
    "warn": "#f59e0b",
    "font": "Segoe UI",
    "discord": "https://discord.gg/rMkAf7tW9e",
    "discord_color": "#5865F2",
}

def resource(rel):
    """Path to a bundled file, both from source and inside the PyInstaller exe."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


APP_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "SalesMacro")
DATA_FILE = os.path.join(APP_DIR, "macros.json")

# --------------------------------------------------------------------------
# Windows niceties: accurate sleep + correct mouse coordinates on HiDPI
# --------------------------------------------------------------------------
if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    try:
        ctypes.windll.winmm.timeBeginPeriod(1)  # 1 ms timer resolution
    except Exception:
        pass

MODIFIERS = {
    "ctrl_l": "ctrl", "ctrl_r": "ctrl", "ctrl": "ctrl",
    "shift_l": "shift", "shift_r": "shift", "shift": "shift",
    "alt_l": "alt", "alt_r": "alt", "alt_gr": "alt", "alt": "alt",
}

MOUSE_NAMES = {
    Button.left: "left", Button.right: "right", Button.middle: "middle",
}
for _n, _label in (("x1", "mouse4"), ("x2", "mouse5")):
    if hasattr(Button, _n):
        MOUSE_NAMES[getattr(Button, _n)] = _label
MOUSE_BY_NAME = {v: k for k, v in MOUSE_NAMES.items()}


MODES = {
    "once": "Press = run (x times)",
    "toggle": "Press = start / press again = stop",
    "hold": "Loop while held",
}


# --------------------------------------------------------------------------
# Key name helpers
# --------------------------------------------------------------------------
def key_to_name(key):
    """pynput key -> stable lowercase string."""
    if isinstance(key, Key):
        return key.name
    if isinstance(key, KeyCode):
        vk = key.vk
        if vk is not None:
            if 0x41 <= vk <= 0x5A:
                return chr(vk).lower()
            if 0x30 <= vk <= 0x39:
                return chr(vk)
            if 0x60 <= vk <= 0x69:
                return f"num{vk - 0x60}"
        if key.char and key.char.isprintable():
            return key.char.lower()
        if vk is not None:
            return f"vk{vk}"
    return str(key)


def name_to_key(name):
    """string -> pynput key for playback."""
    if hasattr(Key, name):
        return Key[name]
    if name.startswith("num") and name[3:].isdigit():
        return KeyCode.from_vk(0x60 + int(name[3:]))
    if name.startswith("vk") and name[2:].isdigit():
        return KeyCode.from_vk(int(name[2:]))
    if len(name) == 1:
        return KeyCode.from_char(name)
    raise ValueError(f"Unknown key: {name}")


def pretty(name):
    if not name:
        return "—"
    return "+".join(p.upper() if len(p) <= 3 else p.replace("_", " ").title() for p in name.split("+"))


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------
def new_macro(name="New Macro"):
    return {"name": name, "hotkey": "", "mode": "once", "repeat": 1,
            "enabled": True, "steps": []}


def default_data():
    demo = new_macro("Example: Double Click")
    demo["hotkey"] = "f6"
    demo["steps"] = [
        {"type": "mouse", "button": "left", "action": "click", "x": None, "y": None, "delay": 60},
        {"type": "mouse", "button": "left", "action": "click", "x": None, "y": None, "delay": 0},
    ]
    return {"settings": {"stop_key": "f12", "jitter": 0, "engine_on": True},
            "macros": [demo]}


def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("settings", {})
        data["settings"].setdefault("stop_key", "f12")
        data["settings"].setdefault("jitter", 0)
        data["settings"].setdefault("engine_on", True)
        data.setdefault("macros", [])
        return data
    except Exception:
        return default_data()


def save_data(data):
    os.makedirs(APP_DIR, exist_ok=True)
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, DATA_FILE)


def describe_step(s):
    t = s["type"]
    if t == "key":
        act = {"tap": "Press", "down": "Hold down", "up": "Release"}[s.get("action", "tap")]
        extra = f"  (hold {s.get('hold', 0)} ms)" if s.get("action", "tap") == "tap" and s.get("hold") else ""
        return "Key", f"{act} {pretty(s['key'])}{extra}"
    if t == "mouse":
        act = {"click": "Click", "double": "Double-click", "down": "Hold", "up": "Release"}[s.get("action", "click")]
        pos = f" at ({s['x']}, {s['y']})" if s.get("x") is not None else " at cursor"
        return "Mouse", f"{act} {pretty(s['button'])}{pos}"
    if t == "move":
        return "Move", f"Move cursor to ({s['x']}, {s['y']})"
    if t == "text":
        txt = s.get("text", "")
        return "Type", f'"{txt[:40]}{"…" if len(txt) > 40 else ""}"'
    if t == "wait":
        return "Wait", "Pause"
    return t, ""


# --------------------------------------------------------------------------
# Engine: listens for hotkeys and plays macros
# --------------------------------------------------------------------------
class Engine:
    def __init__(self, app):
        self.app = app
        self.kb = keyboard.Controller()
        self.ms = mouse.Controller()
        self.pressed_mods = set()
        self.held = set()             # hotkeys currently held (for hold mode)
        self.running = {}             # macro index -> stop Event
        self.lock = threading.Lock()
        self.capture_cb = None        # set while capturing a hotkey
        self.recorder = None          # set while recording
        self.kl = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self.ml = mouse.Listener(on_click=self._on_click)
        self.kl.daemon = self.ml.daemon = True
        self.kl.start()
        self.ml.start()

    # ---- input listeners -------------------------------------------------
    def _combo(self, base):
        mods = [m for m in ("ctrl", "shift", "alt") if m in self.pressed_mods and m != base]
        return "+".join(mods + [base])

    def _on_press(self, key, injected=False):
        if injected:
            return
        name = key_to_name(key)
        mod = MODIFIERS.get(name)
        if self.recorder:
            self.recorder.key(name, True)
        if mod:
            self.pressed_mods.add(mod)
            return
        combo = self._combo(name)
        if self.capture_cb:
            cb, self.capture_cb = self.capture_cb, None
            self.app.post(lambda: cb(combo))
            return
        self._hotkey_down(combo, name)

    def _on_release(self, key, injected=False):
        if injected:
            return
        name = key_to_name(key)
        if self.recorder:
            self.recorder.key(name, False)
        mod = MODIFIERS.get(name)
        if mod:
            self.pressed_mods.discard(mod)
            return
        self._hotkey_up(name)

    def _on_click(self, x, y, button, pressed, injected=False):
        if injected:
            return
        name = MOUSE_NAMES.get(button)
        if not name:
            return
        if self.recorder:
            self.recorder.click(name, pressed, x, y)
        if pressed:
            if self.capture_cb and name not in ("left", "right"):
                cb, self.capture_cb = self.capture_cb, None
                combo = self._combo(name)
                self.app.post(lambda: cb(combo))
                return
            self._hotkey_down(self._combo(name), name)
        else:
            self._hotkey_up(name)

    # ---- hotkey dispatch -------------------------------------------------
    def _hotkey_down(self, combo, base):
        if self.recorder or self.capture_cb:
            return
        data = self.app.data
        if combo == data["settings"].get("stop_key") or base == data["settings"].get("stop_key"):
            self.stop_all()
            return
        if not data["settings"].get("engine_on", True):
            return
        if base in self.held:
            return  # key repeat
        self.held.add(base)
        for i, m in enumerate(data["macros"]):
            if not m.get("enabled", True) or not m.get("hotkey") or not m["steps"]:
                continue
            if m["hotkey"] != combo:
                continue
            mode = m.get("mode", "once")
            if mode == "toggle" and i in self.running:
                self.stop(i)
            elif i not in self.running:
                self.start(i)

    def _hotkey_up(self, base):
        self.held.discard(base)
        for i, m in enumerate(self.app.data["macros"]):
            if m.get("mode") == "hold" and m.get("hotkey", "").split("+")[-1] == base:
                self.stop(i)

    # ---- playback --------------------------------------------------------
    def start(self, idx):
        stop = threading.Event()
        with self.lock:
            self.running[idx] = stop
        macro = json.loads(json.dumps(self.app.data["macros"][idx]))
        threading.Thread(target=self._run, args=(idx, macro, stop), daemon=True).start()
        self.app.post(self.app.refresh_status)

    def stop(self, idx):
        with self.lock:
            ev = self.running.get(idx)
        if ev:
            ev.set()

    def stop_all(self):
        with self.lock:
            for ev in self.running.values():
                ev.set()

    def _sleep(self, ms, stop):
        jitter = self.app.data["settings"].get("jitter", 0) or 0
        if jitter:
            ms = max(0, ms + random.randint(-jitter, jitter))
        end = time.perf_counter() + ms / 1000.0
        while not stop.is_set():
            left = end - time.perf_counter()
            if left <= 0:
                return
            time.sleep(min(left, 0.01))

    def _run(self, idx, macro, stop):
        held_keys, held_btns = set(), set()
        try:
            mode = macro.get("mode", "once")
            count = max(1, int(macro.get("repeat", 1) or 1)) if mode == "once" else None
            n = 0
            while not stop.is_set():
                for step in macro["steps"]:
                    if stop.is_set():
                        break
                    self._do(step, stop, held_keys, held_btns)
                    self._sleep(int(step.get("delay", 0) or 0), stop)
                n += 1
                if count is not None and n >= count:
                    break
        except Exception as e:
            self.app.post(lambda: self.app.set_status(f"Error in macro: {e}", BRAND["danger"]))
        finally:
            for k in held_keys:
                try:
                    self.kb.release(name_to_key(k))
                except Exception:
                    pass
            for b in held_btns:
                try:
                    self.ms.release(MOUSE_BY_NAME[b])
                except Exception:
                    pass
            with self.lock:
                if self.running.get(idx) is stop:
                    del self.running[idx]
            self.app.post(self.app.refresh_status)

    def _do(self, s, stop, held_keys, held_btns):
        t = s["type"]
        if t == "key":
            parts = s["key"].split("+")
            keys = [name_to_key(p) for p in parts]
            act = s.get("action", "tap")
            if act in ("tap", "down"):
                for k in keys:
                    self.kb.press(k)
                held_keys.update(parts)
            if act == "tap":
                self._sleep(int(s.get("hold", 0) or 0), threading.Event())
            if act in ("tap", "up"):
                for k in reversed(keys):
                    self.kb.release(k)
                held_keys.difference_update(parts)
        elif t == "mouse":
            if s.get("x") is not None and s.get("y") is not None:
                self.ms.position = (int(s["x"]), int(s["y"]))
            btn = MOUSE_BY_NAME[s["button"]]
            act = s.get("action", "click")
            if act == "click":
                self.ms.click(btn, 1)
            elif act == "double":
                self.ms.click(btn, 2)
            elif act == "down":
                self.ms.press(btn)
                held_btns.add(s["button"])
            elif act == "up":
                self.ms.release(btn)
                held_btns.discard(s["button"])
        elif t == "move":
            self.ms.position = (int(s["x"]), int(s["y"]))
        elif t == "text":
            self.kb.type(s.get("text", ""))
        # "wait" does nothing; its delay is applied after


class Recorder:
    """Records real key / mouse input into steps with the real timing."""

    def __init__(self, with_mouse=True):
        self.events = []
        self.with_mouse = with_mouse
        self.last = time.perf_counter()
        self.down = set()

    def _add(self, step):
        now = time.perf_counter()
        if self.events:
            self.events[-1]["delay"] = int((now - self.last) * 1000)
        self.last = now
        step["delay"] = 0
        self.events.append(step)

    def key(self, name, pressed):
        if pressed:
            if name in self.down:
                return  # auto-repeat
            self.down.add(name)
        else:
            self.down.discard(name)
        self._add({"type": "key", "key": name, "action": "down" if pressed else "up", "hold": 0})

    def click(self, name, pressed, x, y):
        if not self.with_mouse:
            return
        self._add({"type": "mouse", "button": name, "action": "down" if pressed else "up",
                   "x": int(x), "y": int(y)})

    def steps(self, stop_key):
        ev = list(self.events)
        # drop the stop hotkey and the click on the Stop button
        while ev and ev[-1]["type"] == "key" and ev[-1]["key"] == stop_key:
            ev.pop()
        while ev and ev[-1]["type"] == "mouse" and ev[-1]["button"] == "left":
            ev.pop()
        # collapse down+up pairs into a single tap / click
        out, i = [], 0
        while i < len(ev):
            a = ev[i]
            b = ev[i + 1] if i + 1 < len(ev) else None
            if b and a["action"] == "down" and b["action"] == "up" and a["type"] == b["type"] and \
                    a.get("key", a.get("button")) == b.get("key", b.get("button")):
                if a["type"] == "key":
                    out.append({"type": "key", "key": a["key"], "action": "tap",
                                "hold": a["delay"], "delay": b["delay"]})
                else:
                    out.append({"type": "mouse", "button": a["button"], "action": "click",
                                "x": a["x"], "y": a["y"], "delay": b["delay"] + a["delay"]})
                i += 2
            else:
                out.append(a)
                i += 1
        return out


# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------
B = BRAND
F = B["font"]


def flat_button(parent, text, command, kind="normal", width=None):
    colors = {
        "normal": (B["panel2"], B["text"], B["border"]),
        "accent": (B["accent"], B["accent_text"], B["accent_dark"]),
        "danger": (B["panel2"], B["danger"], B["border"]),
    }[kind]
    bg, fg, hover = colors
    btn = tk.Label(parent, text=text, bg=bg, fg=fg, font=(F, 10, "bold" if kind == "accent" else "normal"),
                   padx=12, pady=6, cursor="hand2")
    if width:
        btn.config(width=width)
    btn.bind("<Enter>", lambda e: btn.config(bg=hover if kind != "accent" else B["accent_dark"],
                                             fg=fg if kind != "accent" else "white"))
    btn.bind("<Leave>", lambda e: btn.config(bg=bg, fg=fg))
    btn.bind("<Button-1>", lambda e: command())
    return btn


class StepDialog(tk.Toplevel):
    """Add / edit a single step."""

    def __init__(self, app, step):
        super().__init__(app.root)
        self.app = app
        self.result = None
        self.step = dict(step)
        self.title("Step")
        self.configure(bg=B["panel"])
        self.resizable(False, False)
        self.transient(app.root)
        self.grab_set()

        t = self.step["type"]
        title = {"key": "Key press", "mouse": "Mouse click", "move": "Move cursor",
                 "text": "Type text", "wait": "Wait"}[t]
        tk.Label(self, text=title, bg=B["panel"], fg=B["accent"], font=(F, 13, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=16, pady=(14, 8))
        self.row = 1
        self.vars = {}

        if t == "key":
            self.vars["key"] = tk.StringVar(value=self.step.get("key", ""))
            self._field("Key", self._key_picker())
            self.vars["action"] = tk.StringVar(value=self.step.get("action", "tap"))
            self._field("Action", self._combo("action", ["tap", "down", "up"]),
                        "tap = press & release   down = hold   up = release")
            self.vars["hold"] = tk.StringVar(value=str(self.step.get("hold", 0)))
            self._field("Hold for (ms)", self._entry("hold"), "Only for 'tap'")
        elif t == "mouse":
            self.vars["button"] = tk.StringVar(value=self.step.get("button", "left"))
            self._field("Button", self._combo("button", ["left", "right", "middle", "mouse4", "mouse5"]))
            self.vars["action"] = tk.StringVar(value=self.step.get("action", "click"))
            self._field("Action", self._combo("action", ["click", "double", "down", "up"]))
            self._position_fields(optional=True)
        elif t == "move":
            self._position_fields(optional=False)
        elif t == "text":
            self.vars["text"] = tk.StringVar(value=self.step.get("text", ""))
            self._field("Text", self._entry("text", 30))

        self.vars["delay"] = tk.StringVar(value=str(self.step.get("delay", 50)))
        self._field("Delay after (ms)" if t != "wait" else "Wait (ms)", self._entry("delay"),
                    "Time before the next step")

        bar = tk.Frame(self, bg=B["panel"])
        bar.grid(row=self.row, column=0, columnspan=3, sticky="e", padx=16, pady=14)
        flat_button(bar, "Cancel", self.destroy).pack(side="left", padx=4)
        flat_button(bar, "Save step", self._save, "accent").pack(side="left", padx=4)
        self.bind("<Return>", lambda e: self._save())
        self.bind("<Escape>", lambda e: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.update_idletasks()
        x = app.root.winfo_rootx() + app.root.winfo_width() // 2 - self.winfo_width() // 2
        y = app.root.winfo_rooty() + app.root.winfo_height() // 2 - self.winfo_height() // 2
        self.geometry(f"+{x}+{y}")
        self.wait_window()

    def destroy(self):
        self.app.engine.capture_cb = None
        super().destroy()

    def _field(self, label, widget, hint=None):
        tk.Label(self, text=label, bg=B["panel"], fg=B["text"], font=(F, 10)).grid(
            row=self.row, column=0, sticky="w", padx=16, pady=4)
        widget.grid(row=self.row, column=1, sticky="w", padx=(0, 16), pady=4)
        if hint:
            tk.Label(self, text=hint, bg=B["panel"], fg=B["muted"], font=(F, 8)).grid(
                row=self.row, column=2, sticky="w", padx=(0, 16))
        self.row += 1

    def _entry(self, key, width=10):
        return tk.Entry(self, textvariable=self.vars[key], width=width, bg=B["panel2"], fg=B["text"],
                        insertbackground=B["text"], relief="flat", font=(F, 10),
                        highlightthickness=1, highlightbackground=B["border"], highlightcolor=B["accent"])

    def _combo(self, key, values):
        return ttk.Combobox(self, textvariable=self.vars[key], values=values, state="readonly", width=12)

    def _key_picker(self):
        f = tk.Frame(self, bg=B["panel"])
        lbl = tk.Label(f, textvariable=self.vars["key"], bg=B["panel2"], fg=B["accent"], width=14,
                       font=(F, 10, "bold"), pady=4)
        lbl.pack(side="left")

        def capture():
            self.vars["key"].set("press a key…")
            self.app.engine.capture_cb = lambda combo: self.vars["key"].set(combo)
        flat_button(f, "Set", capture).pack(side="left", padx=6)
        return f

    def _position_fields(self, optional):
        x, y = self.step.get("x"), self.step.get("y")
        self.vars["x"] = tk.StringVar(value="" if x is None else str(x))
        self.vars["y"] = tk.StringVar(value="" if y is None else str(y))
        f = tk.Frame(self, bg=B["panel"])
        for k in ("x", "y"):
            tk.Label(f, text=k.upper(), bg=B["panel"], fg=B["muted"]).pack(side="left")
            tk.Entry(f, textvariable=self.vars[k], width=6, bg=B["panel2"], fg=B["text"],
                     insertbackground=B["text"], relief="flat").pack(side="left", padx=(2, 8))
        self.pick_lbl = tk.Label(f, text="", bg=B["panel"], fg=B["warn"])

        def pick(n=3):
            if n == 0:
                px, py = self.app.engine.ms.position
                self.vars["x"].set(str(int(px)))
                self.vars["y"].set(str(int(py)))
                self.pick_lbl.config(text="✓")
                return
            self.pick_lbl.config(text=f"move mouse… {n}")
            self.after(1000, lambda: pick(n - 1))
        flat_button(f, "Pick (3s)", pick).pack(side="left")
        self.pick_lbl.pack(side="left", padx=6)
        self._field("Position", f, "Leave empty = current cursor" if optional else None)

    def _int(self, key, allow_empty=False):
        v = self.vars[key].get().strip()
        if v == "" and allow_empty:
            return None
        return int(float(v))

    def _save(self):
        s, t = self.step, self.step["type"]
        try:
            if t == "key":
                k = self.vars["key"].get().strip().lower()
                if not k or k == "press a key…":
                    raise ValueError("Pick a key")
                for p in k.split("+"):
                    name_to_key(p)
                s["key"] = k
                s["action"] = self.vars["action"].get()
                s["hold"] = max(0, self._int("hold"))
            elif t == "mouse":
                s["button"] = self.vars["button"].get()
                s["action"] = self.vars["action"].get()
                s["x"], s["y"] = self._int("x", True), self._int("y", True)
                if (s["x"] is None) != (s["y"] is None):
                    raise ValueError("Fill both X and Y, or neither")
            elif t == "move":
                s["x"], s["y"] = self._int("x"), self._int("y")
            elif t == "text":
                s["text"] = self.vars["text"].get()
            s["delay"] = max(0, self._int("delay"))
        except Exception as e:
            messagebox.showerror("Invalid step", str(e) or "Check the numbers", parent=self)
            return
        self.app.engine.capture_cb = None
        self.result = s
        self.destroy()


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"{B['name']} {B['product']}")
        self.root.configure(bg=B["bg"])
        try:
            self.root.iconbitmap(default=resource(os.path.join("assets", "icon.ico")))
        except Exception:
            pass
        self.root.geometry("1200x680")
        self.root.minsize(1100, 600)
        self.q = queue.Queue()
        self.data = load_data()
        self.sel = 0 if self.data["macros"] else None
        self._style()
        self._build()
        self.engine = Engine(self)
        self.refresh_list()
        self.load_macro()
        self.refresh_status()
        self.root.after(30, self._pump)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    # ---- thread-safe UI calls -------------------------------------------
    def post(self, fn):
        self.q.put(fn)

    def _pump(self):
        while True:
            try:
                fn = self.q.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception:
                pass
        self.root.after(30, self._pump)

    def save(self):
        try:
            save_data(self.data)
        except Exception as e:
            self.set_status(f"Could not save: {e}", B["danger"])

    # ---- styling ---------------------------------------------------------
    def _style(self):
        st = ttk.Style(self.root)
        st.theme_use("clam")
        st.configure("Treeview", background=B["panel"], fieldbackground=B["panel"], foreground=B["text"],
                     rowheight=30, borderwidth=0, font=(F, 10))
        st.configure("Treeview", bordercolor=B["panel"], lightcolor=B["panel"], darkcolor=B["panel"])
        st.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        st.configure("Treeview.Heading", background=B["panel2"], foreground=B["muted"], relief="flat",
                     font=(F, 9, "bold"))
        st.map("Treeview", background=[("selected", B["accent_dark"])], foreground=[("selected", "white")])
        st.map("Treeview.Heading", background=[("active", B["border"])])
        st.configure("TCombobox", fieldbackground=B["panel2"], background=B["panel2"], foreground=B["text"],
                     arrowcolor=B["text"], bordercolor=B["border"])
        st.map("TCombobox", fieldbackground=[("readonly", B["panel2"])], foreground=[("readonly", B["text"])])
        self.root.option_add("*TCombobox*Listbox.background", B["panel2"])
        self.root.option_add("*TCombobox*Listbox.foreground", B["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", B["accent_dark"])
        st.configure("Vertical.TScrollbar", background=B["panel2"], troughcolor=B["panel"],
                     bordercolor=B["panel"], arrowcolor=B["muted"],
                     lightcolor=B["panel2"], darkcolor=B["panel2"], gripcount=0)
        st.map("Vertical.TScrollbar", background=[("active", B["border"])])

    def _label(self, parent, text, size=10, color=None, bold=False, bg=None):
        return tk.Label(parent, text=text, bg=bg or parent["bg"], fg=color or B["text"],
                        font=(F, size, "bold" if bold else "normal"))

    # ---- layout ----------------------------------------------------------
    def _build(self):
        # Header
        head = tk.Frame(self.root, bg=B["bg"])
        head.pack(fill="x", padx=18, pady=(14, 8))
        logo = tk.Frame(head, bg=B["bg"])
        logo.pack(side="left")
        tk.Label(logo, text=B["name"], bg=B["bg"], fg=B["accent"], font=(F, 22, "bold")).pack(side="left")
        tk.Label(logo, text=" " + B["product"], bg=B["bg"], fg=B["text"], font=(F, 22, "bold")).pack(side="left")
        tk.Label(logo, text="   " + B["tagline"], bg=B["bg"], fg=B["muted"], font=(F, 10)).pack(
            side="left", pady=(10, 0))

        right = tk.Frame(head, bg=B["bg"])
        right.pack(side="right")
        self.power = tk.Label(right, font=(F, 10, "bold"), padx=14, pady=6, cursor="hand2")
        self.power.pack(side="right")
        self.power.bind("<Button-1>", lambda e: self.toggle_engine())
        dc = tk.Label(right, text="Join Discord", bg=B["discord_color"], fg="white",
                      font=(F, 10, "bold"), padx=14, pady=6, cursor="hand2")
        dc.pack(side="right", padx=(0, 8))
        dc.bind("<Button-1>", lambda e: webbrowser.open(B["discord"]))
        dc.bind("<Enter>", lambda e: dc.config(bg="#4752C4"))
        dc.bind("<Leave>", lambda e: dc.config(bg=B["discord_color"]))
        self.stop_lbl = tk.Label(right, bg=B["bg"], fg=B["muted"], font=(F, 9), cursor="hand2")
        self.stop_lbl.pack(side="right", padx=12)
        self.stop_lbl.bind("<Button-1>", lambda e: self.set_stop_key())
        jf = tk.Frame(right, bg=B["bg"])
        jf.pack(side="right", padx=8)
        self._label(jf, "Humanize ±ms", 9, B["muted"]).pack(side="left")
        self.jitter_var = tk.StringVar(value=str(self.data["settings"].get("jitter", 0)))
        je = tk.Entry(jf, textvariable=self.jitter_var, width=4, bg=B["panel2"], fg=B["text"], relief="flat",
                      insertbackground=B["text"], justify="center")
        je.pack(side="left", padx=4)
        self.jitter_var.trace_add("write", lambda *a: self._set_jitter())

        body = tk.Frame(self.root, bg=B["bg"])
        body.pack(fill="both", expand=True, padx=18)

        # Left: macro list
        left = tk.Frame(body, bg=B["panel"], width=250, highlightthickness=1, highlightbackground=B["border"])
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        self._label(left, "MACROS", 9, B["muted"], True).pack(anchor="w", padx=14, pady=(12, 6))
        self.mlist = tk.Listbox(left, bg=B["panel"], fg=B["text"], selectbackground=B["accent_dark"],
                                selectforeground="white", relief="flat", highlightthickness=0,
                                font=(F, 11), activestyle="none", borderwidth=0)
        self.mlist.pack(fill="both", expand=True, padx=8)
        self.mlist.bind("<<ListboxSelect>>", self._on_select)
        lb = tk.Frame(left, bg=B["panel"])
        lb.pack(fill="x", padx=8, pady=10)
        flat_button(lb, "+ New", self.add_macro, "accent").pack(side="left", expand=True, fill="x", padx=2)
        flat_button(lb, "Copy", self.dup_macro).pack(side="left", expand=True, fill="x", padx=2)
        flat_button(lb, "Delete", self.del_macro, "danger").pack(side="left", expand=True, fill="x", padx=2)
        lb2 = tk.Frame(left, bg=B["panel"])
        lb2.pack(fill="x", padx=8, pady=(0, 10))
        flat_button(lb2, "Import", self.import_macros).pack(side="left", expand=True, fill="x", padx=2)
        flat_button(lb2, "Export", self.export_macros).pack(side="left", expand=True, fill="x", padx=2)

        # Right: editor
        self.editor = tk.Frame(body, bg=B["bg"])
        self.editor.pack(side="left", fill="both", expand=True, padx=(14, 0))

        card = tk.Frame(self.editor, bg=B["panel"], highlightthickness=1, highlightbackground=B["border"])
        card.pack(fill="x")
        grid = tk.Frame(card, bg=B["panel"])
        grid.pack(fill="x", padx=14, pady=12)

        self._label(grid, "Name", 9, B["muted"]).grid(row=0, column=0, sticky="w")
        self.name_var = tk.StringVar()
        self.name_entry = tk.Entry(grid, textvariable=self.name_var, width=26, bg=B["panel2"], fg=B["text"],
                                   insertbackground=B["text"], relief="flat", font=(F, 11),
                                   highlightthickness=1, highlightbackground=B["border"],
                                   highlightcolor=B["accent"])
        self.name_entry.grid(row=1, column=0, sticky="w", padx=(0, 16), ipady=3)
        self.name_var.trace_add("write", lambda *a: self._edit_field("name", self.name_var.get()))

        self._label(grid, "Bind (hotkey)", 9, B["muted"]).grid(row=0, column=1, sticky="w")
        hk = tk.Frame(grid, bg=B["panel"])
        hk.grid(row=1, column=1, sticky="w", padx=(0, 16))
        self.hotkey_lbl = tk.Label(hk, text="—", bg=B["panel2"], fg=B["accent"], font=(F, 11, "bold"),
                                   width=14, pady=3)
        self.hotkey_lbl.pack(side="left")
        flat_button(hk, "Set", self.capture_hotkey).pack(side="left", padx=(6, 0))
        flat_button(hk, "✕", self.clear_hotkey).pack(side="left", padx=(4, 0))

        self._label(grid, "Mode", 9, B["muted"]).grid(row=0, column=2, sticky="w")
        self.mode_var = tk.StringVar()
        self.mode_box = ttk.Combobox(grid, textvariable=self.mode_var, values=list(MODES.values()),
                                     state="readonly", width=28)
        self.mode_box.grid(row=1, column=2, sticky="w", padx=(0, 16))
        self.mode_box.bind("<<ComboboxSelected>>", self._on_mode)

        self._label(grid, "Repeat", 9, B["muted"]).grid(row=0, column=3, sticky="w")
        self.repeat_var = tk.StringVar()
        self.repeat_entry = tk.Entry(grid, textvariable=self.repeat_var, width=6, bg=B["panel2"], fg=B["text"],
                                     insertbackground=B["text"], relief="flat", font=(F, 11), justify="center")
        self.repeat_entry.grid(row=1, column=3, sticky="w", ipady=3)
        self.repeat_var.trace_add("write", lambda *a: self._set_repeat())

        self.enabled_var = tk.BooleanVar()
        tk.Checkbutton(grid, text="Enabled", variable=self.enabled_var, bg=B["panel"], fg=B["text"],
                       selectcolor=B["panel2"], activebackground=B["panel"], activeforeground=B["text"],
                       font=(F, 10), command=lambda: self._edit_field("enabled", self.enabled_var.get())
                       ).grid(row=1, column=4, sticky="w", padx=(16, 0))

        # Steps toolbar
        tb = tk.Frame(self.editor, bg=B["bg"])
        tb.pack(fill="x", pady=(12, 6))
        self._label(tb, "SEQUENCE", 9, B["muted"], True).pack(side="left")
        self.total_lbl = self._label(tb, "", 9, B["muted"])
        self.total_lbl.pack(side="left", padx=10)
        add = tk.Frame(tb, bg=B["bg"])
        add.pack(side="right")
        for text, t in (("+ Key", "key"), ("+ Click", "mouse"), ("+ Move", "move"),
                        ("+ Text", "text"), ("+ Wait", "wait")):
            flat_button(add, text, lambda t=t: self.add_step(t)).pack(side="left", padx=2)
        self.rec_btn = flat_button(add, "● Record", self.toggle_record, "danger")
        self.rec_btn.pack(side="left", padx=(10, 2))

        # Steps table
        tf = tk.Frame(self.editor, bg=B["panel"], highlightthickness=1, highlightbackground=B["border"])
        tf.pack(fill="both", expand=True)
        cols = ("n", "type", "detail", "delay")
        self.tree = ttk.Treeview(tf, columns=cols, show="headings", selectmode="extended")
        for c, w, txt, anchor in (("n", 44, "#", "center"), ("type", 80, "TYPE", "w"),
                                  ("detail", 420, "ACTION", "w"), ("delay", 140, "DELAY AFTER", "center")):
            self.tree.heading(c, text=txt, anchor=anchor)
            self.tree.column(c, width=w, anchor=anchor, stretch=(c == "detail"))
        sb = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda e: self.edit_step())
        self.tree.bind("<Delete>", lambda e: self.del_step())
        self.tree.tag_configure("odd", background=B["panel2"])

        sbar = tk.Frame(self.editor, bg=B["bg"])
        sbar.pack(fill="x", pady=8)
        for text, cmd, kind in (("Edit", self.edit_step, "normal"), ("▲ Up", lambda: self.move_step(-1), "normal"),
                                ("▼ Down", lambda: self.move_step(1), "normal"),
                                ("Duplicate", self.dup_step, "normal"), ("Delete", self.del_step, "danger"),
                                ("Set all delays", self.set_all_delays, "normal")):
            flat_button(sbar, text, cmd, kind).pack(side="left", padx=(0, 4))
        flat_button(sbar, "▶ Test run", self.test_run, "accent").pack(side="right")

        # Status bar
        self.status = tk.Label(self.root, text="", bg=B["panel"], fg=B["muted"], anchor="w",
                               font=(F, 9), padx=18, pady=6)
        self.status.pack(fill="x", side="bottom")

    # ---- helpers ---------------------------------------------------------
    @property
    def macro(self):
        if self.sel is None or self.sel >= len(self.data["macros"]):
            return None
        return self.data["macros"][self.sel]

    def set_status(self, text, color=None):
        self.status.config(text=text, fg=color or B["muted"])

    def refresh_status(self):
        on = self.data["settings"].get("engine_on", True)
        self.power.config(text="● MACROS ON" if on else "○ MACROS OFF",
                          bg=B["accent"] if on else B["panel2"], fg=B["accent_text"] if on else B["muted"])
        self.stop_lbl.config(text=f"Stop all: {pretty(self.data['settings'].get('stop_key'))}  ✎")
        running = [self.data["macros"][i]["name"] for i in list(self.engine.running)
                   if i < len(self.data["macros"])]
        if self.engine.recorder:
            return
        if running:
            self.set_status("▶ Running: " + ", ".join(running) +
                            f"   —   press {pretty(self.data['settings'].get('stop_key'))} to stop", B["accent"])
        else:
            self.set_status(f"Ready. {len([m for m in self.data['macros'] if m.get('enabled') and m.get('hotkey')])}"
                            f" macro(s) bound. Saved to {DATA_FILE}")

    def refresh_list(self):
        self.mlist.delete(0, "end")
        for m in self.data["macros"]:
            hk = pretty(m.get("hotkey")) if m.get("hotkey") else "unbound"
            dot = "●" if m.get("enabled", True) else "○"
            self.mlist.insert("end", f" {dot}  {m['name']}   [{hk}]")
        if self.sel is not None and self.data["macros"]:
            self.mlist.selection_clear(0, "end")
            self.mlist.selection_set(self.sel)

    def load_macro(self):
        m = self.macro
        self._loading = True
        state = "normal" if m else "disabled"
        for w in (self.name_entry, self.repeat_entry):
            w.config(state=state)
        if m:
            self.name_var.set(m["name"])
            self.hotkey_lbl.config(text=pretty(m.get("hotkey")))
            self.mode_var.set(MODES[m.get("mode", "once")])
            self.repeat_var.set(str(m.get("repeat", 1)))
            self.repeat_entry.config(state="normal" if m.get("mode", "once") == "once" else "disabled")
            self.enabled_var.set(m.get("enabled", True))
        else:
            self.name_var.set("")
            self.hotkey_lbl.config(text="—")
        self._loading = False
        self.refresh_steps()

    def refresh_steps(self, select=None):
        self.tree.delete(*self.tree.get_children())
        m = self.macro
        if not m:
            self.total_lbl.config(text="")
            return
        total = 0
        for i, s in enumerate(m["steps"]):
            typ, det = describe_step(s)
            d = int(s.get("delay", 0) or 0)
            hold = int(s.get("hold", 0) or 0) if s["type"] == "key" and s.get("action") == "tap" else 0
            total += d + hold
            self.tree.insert("", "end", iid=str(i), values=(i + 1, typ, det, f"{d} ms"),
                             tags=("odd",) if i % 2 else ())
        self.total_lbl.config(text=f"{len(m['steps'])} steps  ·  ~{total} ms per run")
        if select:
            sel = [str(i) for i in select if 0 <= i < len(m["steps"])]
            if sel:
                self.tree.selection_set(sel)
                self.tree.see(sel[0])

    def selected_steps(self):
        return sorted(int(i) for i in self.tree.selection())

    def _edit_field(self, key, value):
        if getattr(self, "_loading", False) or not self.macro:
            return
        self.macro[key] = value
        self.save()
        self.refresh_list()

    def _on_select(self, e):
        s = self.mlist.curselection()
        if s:
            self.sel = s[0]
            self.load_macro()

    def _on_mode(self, e):
        rev = {v: k for k, v in MODES.items()}
        mode = rev[self.mode_var.get()]
        self._edit_field("mode", mode)
        self.repeat_entry.config(state="normal" if mode == "once" else "disabled")

    def _set_repeat(self):
        try:
            v = max(1, int(self.repeat_var.get()))
        except ValueError:
            return
        self._edit_field("repeat", v)

    def _set_jitter(self):
        try:
            self.data["settings"]["jitter"] = max(0, int(self.jitter_var.get() or 0))
            self.save()
        except ValueError:
            pass

    # ---- macro actions ---------------------------------------------------
    def add_macro(self):
        self.data["macros"].append(new_macro(f"Macro {len(self.data['macros']) + 1}"))
        self.sel = len(self.data["macros"]) - 1
        self.save()
        self.refresh_list()
        self.load_macro()
        self.name_entry.focus_set()
        self.name_entry.select_range(0, "end")

    def dup_macro(self):
        if not self.macro:
            return
        m = json.loads(json.dumps(self.macro))
        m["name"] += " (copy)"
        m["hotkey"] = ""
        self.data["macros"].insert(self.sel + 1, m)
        self.sel += 1
        self.save()
        self.refresh_list()
        self.load_macro()

    def del_macro(self):
        if not self.macro:
            return
        if not messagebox.askyesno("Delete macro", f"Delete '{self.macro['name']}'?"):
            return
        self.engine.stop_all()
        del self.data["macros"][self.sel]
        self.sel = min(self.sel, len(self.data["macros"]) - 1) if self.data["macros"] else None
        self.save()
        self.refresh_list()
        self.load_macro()

    def capture_hotkey(self):
        if not self.macro:
            return
        self.hotkey_lbl.config(text="press a key…", fg=B["warn"])
        self.set_status("Press any key, key combo (e.g. Ctrl+F1) or side mouse button…  (Esc = cancel)", B["warn"])

        def done(combo):
            self.hotkey_lbl.config(fg=B["accent"])
            if combo == "esc":
                self.load_macro()
                self.refresh_status()
                return
            if combo == self.data["settings"].get("stop_key"):
                messagebox.showwarning("Hotkey", f"{pretty(combo)} is your Stop-all key. Pick another.")
                self.load_macro()
                return
            for i, other in enumerate(self.data["macros"]):
                if i != self.sel and other.get("hotkey") == combo:
                    self.set_status(f"Note: '{other['name']}' also uses {pretty(combo)} – both will run.", B["warn"])
                    break
            else:
                self.refresh_status()
            self._edit_field("hotkey", combo)
            self.hotkey_lbl.config(text=pretty(combo))
        self.engine.capture_cb = done

    def clear_hotkey(self):
        self._edit_field("hotkey", "")
        self.hotkey_lbl.config(text="—")

    def set_stop_key(self):
        self.stop_lbl.config(text="Press new stop key…", fg=B["warn"])

        def done(combo):
            self.stop_lbl.config(fg=B["muted"])
            if combo != "esc":
                self.data["settings"]["stop_key"] = combo
                self.save()
            self.refresh_status()
        self.engine.capture_cb = done

    def toggle_engine(self):
        s = self.data["settings"]
        s["engine_on"] = not s.get("engine_on", True)
        if not s["engine_on"]:
            self.engine.stop_all()
        self.save()
        self.refresh_status()

    def import_macros(self):
        path = filedialog.askopenfilename(filetypes=[("Sales Macro files", "*.json")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            macros = d["macros"] if isinstance(d, dict) else d
            for m in macros:
                m.setdefault("mode", "once"); m.setdefault("repeat", 1)
                m.setdefault("enabled", True); m.setdefault("hotkey", ""); m.setdefault("steps", [])
            self.data["macros"].extend(macros)
            self.save()
            self.refresh_list()
            self.set_status(f"Imported {len(macros)} macro(s).", B["accent"])
        except Exception as e:
            messagebox.showerror("Import failed", str(e))

    def export_macros(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", initialfile="sales-macros.json",
                                            filetypes=[("Sales Macro files", "*.json")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"macros": self.data["macros"]}, f, indent=2)
            self.set_status(f"Exported to {path}", B["accent"])

    # ---- step actions ----------------------------------------------------
    def add_step(self, t):
        if not self.macro:
            return
        defaults = {
            "key": {"type": "key", "key": "", "action": "tap", "hold": 0, "delay": 50},
            "mouse": {"type": "mouse", "button": "left", "action": "click", "x": None, "y": None, "delay": 50},
            "move": {"type": "move", "x": 0, "y": 0, "delay": 20},
            "text": {"type": "text", "text": "", "delay": 50},
            "wait": {"type": "wait", "delay": 500},
        }
        d = StepDialog(self, defaults[t])
        if d.result:
            sel = self.selected_steps()
            pos = sel[-1] + 1 if sel else len(self.macro["steps"])
            self.macro["steps"].insert(pos, d.result)
            self.save()
            self.refresh_steps(select=[pos])

    def edit_step(self):
        sel = self.selected_steps()
        if not sel or not self.macro:
            return
        i = sel[0]
        d = StepDialog(self, self.macro["steps"][i])
        if d.result:
            self.macro["steps"][i] = d.result
            self.save()
            self.refresh_steps(select=[i])

    def del_step(self):
        sel = self.selected_steps()
        if not sel:
            return
        for i in reversed(sel):
            del self.macro["steps"][i]
        self.save()
        self.refresh_steps(select=[min(sel[0], len(self.macro["steps"]) - 1)])

    def dup_step(self):
        sel = self.selected_steps()
        if not sel:
            return
        copies = [json.loads(json.dumps(self.macro["steps"][i])) for i in sel]
        pos = sel[-1] + 1
        self.macro["steps"][pos:pos] = copies
        self.save()
        self.refresh_steps(select=list(range(pos, pos + len(copies))))

    def move_step(self, d):
        sel = self.selected_steps()
        steps = self.macro["steps"] if self.macro else []
        if not sel or (d < 0 and sel[0] == 0) or (d > 0 and sel[-1] == len(steps) - 1):
            return
        order = sel if d < 0 else list(reversed(sel))
        for i in order:
            steps[i], steps[i + d] = steps[i + d], steps[i]
        self.save()
        self.refresh_steps(select=[i + d for i in sel])

    def set_all_delays(self):
        if not self.macro or not self.macro["steps"]:
            return
        sel = self.selected_steps()
        target = sel or range(len(self.macro["steps"]))
        v = simpledialog.askinteger("Set delays", f"Delay after each of {len(target)} step(s) (ms):",
                                    minvalue=0, initialvalue=50, parent=self.root)
        if v is None:
            return
        for i in target:
            self.macro["steps"][i]["delay"] = v
        self.save()
        self.refresh_steps(select=list(sel))

    def test_run(self):
        if not self.macro or not self.macro["steps"]:
            return
        if self.sel in self.engine.running:
            self.engine.stop(self.sel)
            return
        idx = self.sel
        self.set_status(f"Test run starts in 3s – switch to your window. {pretty(self.data['settings']['stop_key'])}"
                        f" stops it.", B["warn"])
        self.root.after(3000, lambda: self.engine.start(idx) if idx < len(self.data["macros"]) else None)

    # ---- recording -------------------------------------------------------
    def toggle_record(self):
        if not self.macro:
            return
        if self.engine.recorder:
            self._stop_record()
            return
        self.engine.recorder = Recorder()
        self.rec_btn.config(text="■ Stop recording")
        stop = pretty(self.data["settings"]["stop_key"])
        self.set_status(f"● RECORDING keys & clicks with real timing… press {stop} or click Stop.", B["danger"])
        self._watch_record()

    def _watch_record(self):
        rec = self.engine.recorder
        if not rec:
            return
        sk = self.data["settings"]["stop_key"]
        if rec.events and rec.events[-1]["type"] == "key" and rec.events[-1]["key"] == sk:
            self._stop_record()
            return
        self.root.after(50, self._watch_record)

    def _stop_record(self):
        rec, self.engine.recorder = self.engine.recorder, None
        self.engine.pressed_mods.clear()
        self.rec_btn.config(text="● Record")
        steps = rec.steps(self.data["settings"]["stop_key"]) if rec else []
        if steps:
            sel = self.selected_steps()
            pos = sel[-1] + 1 if sel else len(self.macro["steps"])
            self.macro["steps"][pos:pos] = steps
            self.save()
            self.refresh_steps(select=list(range(pos, pos + len(steps))))
            self.set_status(f"Recorded {len(steps)} step(s). Edit the delays if you want.", B["accent"])
        else:
            self.refresh_status()

    def _close(self):
        self.engine.stop_all()
        self.save()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
