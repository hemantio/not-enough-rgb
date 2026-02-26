#  Not Enough RGB

> _Because there's never enough RGB._

A Windows desktop overlay that draws **smooth, continuously cycling RGB gradient borders** around **all your open windows** — inspired by the **Logitech G102 LIGHTSYNC** mouse.

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python)
![Windows](https://img.shields.io/badge/Windows-10%2F11-0078D6?logo=windows)
![License](https://img.shields.io/badge/License-MIT-green)

## ✨ Features

- **Smooth gradient borders** on ALL visible windows simultaneously
- **Pixel-smooth rendering** — 3px segments, no blocky colors
- **Flowing gradient** that cycles continuously around each window's perimeter
- **Z-order occlusion** — borders behind front windows are automatically hidden (no wallhack vibes)
- **Instant window tracking** — borders follow windows as you move/resize them
- **System tray icon** — right-click to Stop/Start or Quit
- **No console window** — runs silently via `.pyw`
- **Zero external UI** — just pure RGB on your existing apps
- **Pre-computed color LUT** — 720 colors for maximum performance

## 📸 How It Works

The app creates a full-screen transparent, click-through overlay covering your entire desktop. It enumerates all visible windows using the Win32 API, computes visible border intervals (accounting for Z-order occlusion), and renders gradient segments using a tkinter Canvas with a pre-allocated item pool.

## 🚀 Quick Start

### Requirements

- Python 3.11+
- Windows 10/11

### Install Dependencies

```bash
pip install pystray Pillow
```

### Run

```bash
# With console (for debugging)
python chromaglow.py

# Without console (recommended)
pythonw not_enough_rgb.pyw
# Or just double-click not_enough_rgb.pyw
```

## 🎮 Controls

| Control                    | Action                 |
| -------------------------- | ---------------------- |
| **System tray → Stop**     | Pause the RGB borders  |
| **System tray → Start**    | Resume the RGB borders |
| **System tray → Quit**     | Terminate completely   |
| **Ctrl+Shift+Q**           | Global hotkey to quit  |
| **Double-click tray icon** | Toggle Start/Stop      |

## ⚙️ Configuration

Edit the `CONFIG` section at the top of `chromaglow.py`:

```python
BORDER_WIDTH = 4          # Border thickness in pixels
SEGMENT_SIZE = 3          # Gradient smoothness (lower = smoother)
CYCLE_SPEED = 0.18        # Rotations per second (~5.5s per cycle)
BORDER_OPACITY = 0.92     # Border visibility (0-1)
COLOR_SAT = 0.88          # Color saturation
COLOR_VAL = 0.95          # Color brightness
MAX_WINDOWS = 15          # Max windows to border
COLOR_MODE = 'spectrum'   # 'spectrum' (full rainbow) or 'g102' (cyan-purple)
```

## 🔧 Technical Details

- **Rendering**: tkinter Canvas with pre-allocated rectangle pool
- **Window Detection**: Win32 `EnumWindows` in Z-order
- **Occlusion**: Interval-based visible range computation per edge
- **Click-through**: `WS_EX_TRANSPARENT | WS_EX_LAYERED` window styles
- **DPI Aware**: `SetProcessDpiAwareness(2)` for correct coordinates
- **Color Engine**: Pre-computed 720-entry HSV→Hex lookup table
- **Animation**: Time-based via `perf_counter()` for consistent speed

## 🎨 Inspiration

The [Logitech G102 LIGHTSYNC](https://www.logitechg.com/en-us/products/gaming-mice/g102-lightsync-rgb-gaming-mouse.html) mouse has a beautiful RGB light ring that continuously cycles through the color spectrum. **Not Enough RGB** brings that same aesthetic to your entire Windows desktop.

## 🗺️ Roadmap

- [ ] **OpenRGB Integration** — Sync window border colors with all your physical RGB hardware (keyboard, mouse, RAM, fans) via [OpenRGB](https://openrgb.org/) SDK
- [ ] **Logitech GHUB Sync** — Direct integration with Logitech devices (G102, G Pro, etc.)
- [ ] **Audio Reactive Mode** — Border colors react to music/system audio
- [ ] **Per-App Color Profiles** — Assign specific gradient themes to specific apps
- [ ] **Multi-Monitor Awareness** — Independent color zones per monitor
- [ ] **Wallpaper Engine Integration** — Sync with animated wallpapers

## 📄 License

MIT License — do whatever you want with it.

---

_Made with  and an unhealthy obsession with RGB._
