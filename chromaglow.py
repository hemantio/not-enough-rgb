"""
Not Enough RGB -- Smooth RGB Gradient Borders for ALL Windows
Inspired by Logitech G102 LIGHTSYNC

Because there's never enough RGB.

Controls:
  Ctrl+Shift+Q  -- Quit (global hotkey)
  Tray icon      -- Click to quit
"""

import tkinter as tk
import ctypes
import ctypes.wintypes as wintypes
import colorsys
import threading
import sys
import signal
import time
import os
from PIL import Image, ImageDraw
import pystray

# ── CONFIG ─────────────────────────────────────────────
BORDER_WIDTH = 4
SEGMENT_SIZE = 3          # px per segment (3 = smooth + fast)
CYCLE_SPEED = 0.18        # full hue rotations per second (~5.5s per cycle)
BORDER_OPACITY = 0.92
COLOR_SAT = 0.88
COLOR_VAL = 0.95
MAX_WINDOWS = 15
COLOR_MODE = 'spectrum'   # 'spectrum' or 'g102'

# ── DPI ────────────────────────────────────────────────
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# ── WIN32 ──────────────────────────────────────────────
user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_APPWINDOW = 0x00040000
GA_ROOT = 2
DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14
WM_HOTKEY = 0x0312

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

ENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long), ("top", ctypes.c_long),
        ("right", ctypes.c_long), ("bottom", ctypes.c_long),
    ]

# ── PRE-COMPUTED COLOR LUT ─────────────────────────────
COLOR_LUT = []
for _h in range(720):
    hue = _h / 720.0
    if COLOR_MODE == 'g102':
        hue = 0.5 + (hue * 0.4)
    r, g, b = colorsys.hsv_to_rgb(hue % 1.0, COLOR_SAT, COLOR_VAL)
    ri, gi, bi = int(r * 255), int(g * 255), int(b * 255)
    if ri <= 1 and gi <= 1 and bi <= 1:
        ri = 2
    COLOR_LUT.append(f'#{ri:02x}{gi:02x}{bi:02x}')
LUT_SIZE = len(COLOR_LUT)


class ChromaGlow:
    def __init__(self):
        self.running = True
        self.my_hwnd = None
        self.hue_offset = 0.0
        self.last_time = time.perf_counter()
        self.pool = []
        self.pool_idx = 0
        self.prev_used = 0
        self.tray_icon = None

        self.excluded = {
            'Progman', 'WorkerW', 'Shell_TrayWnd',
            'Shell_SecondaryTrayWnd', 'Windows.UI.Core.CoreWindow',
            'ForegroundStaging', 'MultitaskingViewFrame',
            'Windows.Internal.Shell.TabProxyWindow',
        }

        self._build_overlay()
        self._make_click_through()
        self._start_hotkey()
        self._build_systray()

        print()
        print("  [*] Not Enough RGB is ACTIVE")
        print(f"  Border: {BORDER_WIDTH}px | Segment: {SEGMENT_SIZE}px")
        print(f"  System tray icon active")
        print("  Right-click tray icon or Ctrl+Shift+Q to quit")
        print()

        self._tick()
        self.root.mainloop()

    # ── Overlay Window ─────────────────────────────────

    def _build_overlay(self):
        self.root = tk.Tk()
        self.root.title('NotEnoughRGB')
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', BORDER_OPACITY)

        vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        vw = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        vh = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        self.sx, self.sy = vx, vy
        self.sw, self.sh = vw, vh

        self.TKEY = '#010101'
        self.root.config(bg=self.TKEY)
        self.root.attributes('-transparentcolor', self.TKEY)
        self.root.geometry(f'{vw}x{vh}+{vx}+{vy}')

        self.canvas = tk.Canvas(
            self.root, highlightthickness=0,
            bg=self.TKEY, bd=0, width=vw, height=vh
        )
        self.canvas.pack()

    # ── System Tray Icon ───────────────────────────────

    def _create_tray_icon_image(self):
        """Create a 64x64 RGB gradient circle icon."""
        size = 64
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Draw gradient-colored ring
        center = size // 2
        for angle in range(360):
            import math
            hue = angle / 360.0
            r, g, b = colorsys.hsv_to_rgb(hue, 0.9, 0.95)
            ri, gi, bi = int(r * 255), int(g * 255), int(b * 255)
            rad = math.radians(angle)
            for thickness in range(6, 12):
                px = int(center + thickness * 2.2 * math.cos(rad))
                py = int(center + thickness * 2.2 * math.sin(rad))
                if 0 <= px < size and 0 <= py < size:
                    draw.point((px, py), fill=(ri, gi, bi, 255))
        # Fill center with dark
        draw.ellipse([18, 18, size-18, size-18], fill=(15, 15, 25, 255))
        # Draw RGB text
        try:
            draw.text((center - 10, center - 6), "RGB", fill=(200, 200, 255, 255))
        except Exception:
            pass
        return img

    def _build_systray(self):
        """Create a proper Windows system tray icon."""
        icon_image = self._create_tray_icon_image()

        self.paused = False

        def toggle_pause(icon, item):
            self.paused = not self.paused
            if self.paused:
                icon.title = 'Not Enough RGB (PAUSED)'
                self.root.after(0, self._hide_all_borders)
            else:
                icon.title = 'Not Enough RGB'

        def get_toggle_text(item):
            return 'Start' if self.paused else 'Stop'

        def toggle_startup(icon, item):
            if self._is_in_startup():
                self._remove_from_startup()
            else:
                self._add_to_startup()

        menu = pystray.Menu(
            pystray.MenuItem('Not Enough RGB', None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(get_toggle_text, toggle_pause, default=True),
            pystray.MenuItem('Start with Windows',
                             toggle_startup,
                             checked=lambda item: self._is_in_startup()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Quit', lambda: self.root.after(0, self._quit)),
        )

        self.tray_icon = pystray.Icon(
            'not_enough_rgb',
            icon_image,
            'Not Enough RGB',
            menu
        )

        # Run tray icon in background thread
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    # -- Startup Management --

    def _get_startup_path(self):
        """Path to the shortcut in Windows Startup folder."""
        startup = os.path.join(
            os.environ.get('APPDATA', ''),
            'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup'
        )
        return os.path.join(startup, 'Not Enough RGB.lnk')

    def _get_script_path(self):
        """Get the .pyw script path."""
        folder = os.path.dirname(os.path.abspath(__file__))
        pyw = os.path.join(folder, 'not_enough_rgb.pyw')
        if os.path.exists(pyw):
            return pyw
        return os.path.abspath(__file__)

    def _is_in_startup(self):
        """Check if startup shortcut exists."""
        return os.path.exists(self._get_startup_path())

    def _add_to_startup(self):
        """Create a shortcut in Windows Startup folder."""
        try:
            import subprocess
            shortcut_path = self._get_startup_path()
            script_path = self._get_script_path()
            pythonw = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
            if not os.path.exists(pythonw):
                pythonw = sys.executable

            # Use PowerShell to create .lnk shortcut
            ps_cmd = (
                f'$ws = New-Object -ComObject WScript.Shell; '
                f'$sc = $ws.CreateShortcut("{shortcut_path}"); '
                f'$sc.TargetPath = "{pythonw}"; '
                f'$sc.Arguments = "\"{script_path}\""; '
                f'$sc.WorkingDirectory = "{os.path.dirname(script_path)}"; '
                f'$sc.Description = "Not Enough RGB - RGB Gradient Borders"; '
                f'$sc.Save()'
            )
            subprocess.run(['powershell', '-Command', ps_cmd],
                           capture_output=True, timeout=10)
        except Exception:
            pass

    def _remove_from_startup(self):
        """Remove the startup shortcut."""
        try:
            path = self._get_startup_path()
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

    def _hide_all_borders(self):
        """Hide all border segments when paused."""
        for j in range(self.prev_used):
            if j < len(self.pool):
                self.canvas.coords(self.pool[j], -10, -10, -10, -10)
        self.prev_used = 0

    # ── Click-Through ──────────────────────────────────

    def _make_click_through(self):
        self.root.update_idletasks()
        inner = self.root.winfo_id()
        self.my_hwnd = user32.GetAncestor(inner, GA_ROOT)
        style = user32.GetWindowLongW(self.my_hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(
            self.my_hwnd, GWL_EXSTYLE,
            style | WS_EX_LAYERED | WS_EX_TRANSPARENT
            | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        )

    # ── Hotkey ─────────────────────────────────────────

    def _start_hotkey(self):
        def listen():
            user32.RegisterHotKey(None, 1, 0x0002 | 0x0004, 0x51)
            msg = wintypes.MSG()
            while self.running:
                ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret <= 0:
                    break
                if msg.message == WM_HOTKEY and msg.wParam == 1:
                    self.running = False
                    self.root.after(0, self._quit)
                    break
            user32.UnregisterHotKey(None, 1)
        threading.Thread(target=listen, daemon=True).start()

    # ── Window Enumeration ─────────────────────────────

    def _get_class(self, hwnd):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buf, 256)
        return buf.value

    def _is_real_window(self, hwnd):
        if not user32.IsWindowVisible(hwnd):
            return False
        if user32.IsIconic(hwnd):
            return False
        cls = self._get_class(hwnd)
        if cls in self.excluded:
            return False
        cloaked = ctypes.c_int(0)
        dwmapi.DwmGetWindowAttribute(
            hwnd, DWMWA_CLOAKED,
            ctypes.byref(cloaked), ctypes.sizeof(cloaked)
        )
        if cloaked.value:
            return False
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if not (ex & WS_EX_APPWINDOW):
                return False
        return True

    def _enum_windows(self):
        """Get all visible windows in Z-order (front to back)."""
        results = []

        def callback(hwnd, _):
            if len(results) >= MAX_WINDOWS:
                return True
            if hwnd == self.my_hwnd:
                return True
            if not self._is_real_window(hwnd):
                return True

            rect = RECT()
            hr = dwmapi.DwmGetWindowAttribute(
                hwnd, DWMWA_EXTENDED_FRAME_BOUNDS,
                ctypes.byref(rect), ctypes.sizeof(rect)
            )
            if hr != 0:
                user32.GetWindowRect(hwnd, ctypes.byref(rect))

            x = rect.left - self.sx
            y = rect.top - self.sy
            w = rect.right - rect.left
            h = rect.bottom - rect.top

            if w > 60 and h > 40:
                results.append((x, y, w, h))
            return True

        cb = ENUMPROC(callback)
        user32.EnumWindows(cb, 0)
        return results

    # ── Interval-Based Occlusion (fast!) ───────────────

    def _visible_ranges(self, start, end, fixed_min, fixed_max,
                        is_horizontal, occluders):
        """Compute which parts of an edge are NOT hidden behind front windows.

        Instead of checking each segment individually (slow), we compute
        visible intervals once per edge (fast).

        Returns: list of (range_start, range_end) visible intervals.
        """
        blocked = []
        for (ox, oy, ow, oh) in occluders:
            if is_horizontal:
                # Does this occluder cover the Y position of this border?
                if oy < fixed_max and oy + oh > fixed_min:
                    bs = max(start, ox)
                    be = min(end, ox + ow)
                    if bs < be:
                        blocked.append((bs, be))
            else:
                # Does this occluder cover the X position of this border?
                if ox < fixed_max and ox + ow > fixed_min:
                    bs = max(start, oy)
                    be = min(end, oy + oh)
                    if bs < be:
                        blocked.append((bs, be))

        if not blocked:
            return [(start, end)]

        # Sort and merge blocked intervals
        blocked.sort()
        merged = [list(blocked[0])]
        for bs, be in blocked[1:]:
            if bs <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], be)
            else:
                merged.append([bs, be])

        # Visible = total range minus blocked
        visible = []
        pos = start
        for bs, be in merged:
            if pos < bs:
                visible.append((pos, bs))
            pos = max(pos, be)
        if pos < end:
            visible.append((pos, end))

        return visible

    # ── Pool ───────────────────────────────────────────

    def _ensure_pool(self, needed):
        while len(self.pool) < needed:
            self.pool.append(
                self.canvas.create_rectangle(-10, -10, -10, -10,
                                             fill='#000', outline='', width=0)
            )

    # ── Render One Window Border ───────────────────────

    def _draw_border(self, x, y, w, h, occluders):
        bw = BORDER_WIDTH
        perimeter = 2.0 * (w + h)
        lut_off = int(self.hue_offset * LUT_SIZE) % LUT_SIZE

        # ── TOP EDGE ──
        vis = self._visible_ranges(x, x + w, y, y + bw, True, occluders)
        edge_dist_base = 0.0
        for (vs, ve) in vis:
            seg_count = max(1, int((ve - vs) / SEGMENT_SIZE))
            seg_w = (ve - vs) / seg_count
            for i in range(seg_count):
                sx1 = vs + i * seg_w
                dist = (sx1 - x) + edge_dist_base
                li = (lut_off + int(dist / perimeter * LUT_SIZE)) % LUT_SIZE

                p = self.pool_idx
                self.canvas.coords(self.pool[p], sx1, y, sx1 + seg_w, y + bw)
                self.canvas.itemconfig(self.pool[p], fill=COLOR_LUT[li])
                self.pool_idx += 1

        # ── RIGHT EDGE ──
        vis = self._visible_ranges(y, y + h, x + w - bw, x + w, False, occluders)
        edge_dist_base = w
        for (vs, ve) in vis:
            seg_count = max(1, int((ve - vs) / SEGMENT_SIZE))
            seg_h = (ve - vs) / seg_count
            for i in range(seg_count):
                sy1 = vs + i * seg_h
                dist = (sy1 - y) + edge_dist_base
                li = (lut_off + int(dist / perimeter * LUT_SIZE)) % LUT_SIZE

                p = self.pool_idx
                self.canvas.coords(self.pool[p], x + w - bw, sy1, x + w, sy1 + seg_h)
                self.canvas.itemconfig(self.pool[p], fill=COLOR_LUT[li])
                self.pool_idx += 1

        # ── BOTTOM EDGE (right to left for continuous flow) ──
        vis = self._visible_ranges(x, x + w, y + h - bw, y + h, True, occluders)
        edge_dist_base = w + h
        for (vs, ve) in vis:
            seg_count = max(1, int((ve - vs) / SEGMENT_SIZE))
            seg_w = (ve - vs) / seg_count
            for i in range(seg_count):
                sx1 = vs + i * seg_w
                # Reverse direction: distance measured from right edge
                dist = (x + w - sx1 - seg_w) + edge_dist_base
                li = (lut_off + int(dist / perimeter * LUT_SIZE)) % LUT_SIZE

                p = self.pool_idx
                self.canvas.coords(self.pool[p], sx1, y + h - bw, sx1 + seg_w, y + h)
                self.canvas.itemconfig(self.pool[p], fill=COLOR_LUT[li])
                self.pool_idx += 1

        # ── LEFT EDGE (bottom to top for continuous flow) ──
        vis = self._visible_ranges(y, y + h, x, x + bw, False, occluders)
        edge_dist_base = 2 * w + h
        for (vs, ve) in vis:
            seg_count = max(1, int((ve - vs) / SEGMENT_SIZE))
            seg_h = (ve - vs) / seg_count
            for i in range(seg_count):
                sy1 = vs + i * seg_h
                dist = (y + h - sy1 - seg_h) + edge_dist_base
                li = (lut_off + int(dist / perimeter * LUT_SIZE)) % LUT_SIZE

                p = self.pool_idx
                self.canvas.coords(self.pool[p], x, sy1, x + bw, sy1 + seg_h)
                self.canvas.itemconfig(self.pool[p], fill=COLOR_LUT[li])
                self.pool_idx += 1

    # ── Main Loop ──────────────────────────────────────

    def _tick(self):
        if not self.running:
            return

        # Skip rendering when paused (but keep loop alive for instant resume)
        if self.paused:
            self.last_time = time.perf_counter()
            self.root.after(50, self._tick)
            return

        now = time.perf_counter()
        dt = now - self.last_time
        self.last_time = now

        # Time-based animation (consistent speed regardless of frame rate)
        self.hue_offset = (self.hue_offset + CYCLE_SPEED * dt) % 1.0

        # Enumerate all windows (Z-order: front to back)
        windows = self._enum_windows()

        # Estimate pool size needed
        total = 0
        for (_, _, w, h) in windows:
            total += (max(1, w // SEGMENT_SIZE) + max(1, h // SEGMENT_SIZE)) * 2
        self._ensure_pool(total + 200)

        old_used = self.prev_used
        self.pool_idx = 0

        # Draw borders with occlusion: window[i]'s occluders = windows[0..i-1]
        for i, (wx, wy, ww, wh) in enumerate(windows):
            self._draw_border(wx, wy, ww, wh, windows[:i])

        # Hide items from previous frame that are no longer used
        limit = max(self.pool_idx, old_used)
        for j in range(self.pool_idx, limit):
            if j < len(self.pool):
                self.canvas.coords(self.pool[j], -10, -10, -10, -10)
        self.prev_used = self.pool_idx

        # Schedule next frame ASAP (after(1) = as fast as tkinter allows)
        self.root.after(1, self._tick)

    def _quit(self):
        print("  [*] Not Enough RGB stopped.")
        self.running = False
        try:
            if self.tray_icon:
                self.tray_icon.stop()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass
        sys.exit(0)


if __name__ == '__main__':
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
    print()
    print("  Not Enough RGB -- Because there's never enough.")
    print()
    try:
        ChromaGlow()
    except KeyboardInterrupt:
        print("  [*] Stopped.")
    except Exception as e:
        print(f"  [!] Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
