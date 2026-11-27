from collections import deque
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser
import numpy as np
from PIL import Image, ImageDraw
import matplotlib

matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.patches import Circle

MAX_CIRCLES = 10000
TARGET_SAMPLES = 20480
MAX_VISIBLE_CIRCLES = 40
BASE_HALF_SPAN = 1.35

# Shared dark-themed palette
BG_APP = "#12161F"
BG_CHROME = "#181E2A"
BG_CARD = "#202838"
BG_INPUT = "#293347"
BORDER_SUBTLE = "#2F3A4F"
TEXT_PRIMARY = "#E6EDF7"
TEXT_MUTED = "#9AA7BC"
ACCENT_BLUE = "#3B82F6"
TOOLTIP_BG = "#0F172A"
TOOLTIP_BORDER = "#475569"

GITHUB_URL = "https://github.com/VortexProtocol1633"


class HoverTooltip:
    """Lightweight floating tooltip shown when hovering over Tk/Ttk widgets."""

    def __init__(self, widget: tk.Widget, text: str, delay_ms: int = 300):
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self._after_id: str | None = None
        self._tip_window: tk.Toplevel | None = None

        self.widget.bind("<Enter>", self._schedule_show, add="+")
        self.widget.bind("<Leave>", self._hide, add="+")
        self.widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule_show(self, _event=None):
        self._cancel_timer()
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _cancel_timer(self):
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _show(self):
        self._after_id = None
        if self._tip_window is not None or not self.widget.winfo_exists():
            return

        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6

        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f"+{x}+{y}")
        tip.configure(bg=TOOLTIP_BORDER)

        inner = tk.Frame(tip, bg=TOOLTIP_BG, padx=9, pady=6)
        inner.pack(padx=1, pady=1)

        lbl = tk.Label(
            inner,
            text=self.text,
            bg=TOOLTIP_BG,
            fg=TEXT_PRIMARY,
            font=("TkDefaultFont", 8),
            justify=tk.LEFT,
            wraplength=340,
        )
        lbl.pack()
        self._tip_window = tip

    def _hide(self, _event=None):
        self._cancel_timer()
        if self._tip_window is not None:
            try:
                self._tip_window.destroy()
            except tk.TclError:
                pass
            self._tip_window = None


class DrawingPadPanel(ttk.Frame):
    """Interactive 2D Sketch Pad integrated with Fourier transfer and full hover help."""

    def __init__(self, parent, on_send_to_fourier):
        super().__init__(parent, style="App.TFrame")
        self.on_send_to_fourier = on_send_to_fourier
        self._tooltips: list[HoverTooltip] = []

        self.bg_dark = BG_APP
        self.panel_bg = BG_CHROME
        self.canvas_bg = "#111827"
        self.text_fg = TEXT_PRIMARY
        self.muted_fg = TEXT_MUTED
        self.btn_bg = BG_INPUT
        self.btn_active_bg = "#2563EB"
        self.border_color = BORDER_SUBTLE

        self.tool = "freehand"
        self.ink_color = "#F9FAFB"
        self.brush_size = 3
        self.eraser_size = 16
        self.start_x = None
        self.start_y = None
        self.preview_ids = []
        self.eraser_cursor_id = None
        self.history = []

        self._build_ui()
        self._bind_events()

    def _attach_tip(self, widget: tk.Widget, text: str):
        self._tooltips.append(HoverTooltip(widget, text))

    def _build_ui(self):
        toolbar_shell = tk.Frame(
            self,
            bg=self.panel_bg,
            highlightbackground=self.border_color,
            highlightthickness=1,
        )
        toolbar_shell.pack(side=tk.TOP, fill=tk.X)

        toolbar = tk.Frame(toolbar_shell, bg=self.panel_bg, padx=8, pady=6)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        tools = [
            ("Freehand", "freehand"),
            ("Line", "line"),
            ("Rectangle", "rectangle"),
            ("Square", "square"),
            ("Oval", "oval"),
            ("Circle", "circle"),
            ("Eraser", "eraser"),
        ]

        tool_tips = {
            "freehand": "Freehand Brush: Click and drag to draw smooth custom curves and strokes.",
            "line": "Line Tool: Click and drag to draw a straight line segment between two points.",
            "rectangle": "Rectangle Tool: Click and drag to draw a rectangle with independent width and height.",
            "square": "Square Tool: Click and drag to draw a constrained equal-sided square.",
            "oval": "Oval Tool: Click and drag to draw an ellipse inside a bounding box.",
            "circle": "Circle Tool: Click and drag to draw a constrained circular outline.",
            "eraser": "Eraser Tool: Click and drag to erase strokes; displays a dashed size ring while hovering.",
        }

        tool_hdr_lbl = tk.Label(
            toolbar,
            text="Tool:",
            bg=self.panel_bg,
            fg=self.text_fg,
            font=("TkDefaultFont", 9, "bold"),
        )
        tool_hdr_lbl.pack(side=tk.LEFT, padx=(0, 4))
        self._attach_tip(tool_hdr_lbl, "Select the active drawing or erasing tool for the 2D sketch canvas.")

        self.tool_buttons = {}
        for label, tool_name in tools:
            is_active = tool_name == self.tool
            btn = tk.Button(
                toolbar,
                text=label,
                relief=tk.SUNKEN if is_active else tk.RAISED,
                bg=self.btn_active_bg if is_active else self.btn_bg,
                fg=self.text_fg,
                activebackground="#1D4ED8",
                activeforeground=self.text_fg,
                highlightbackground=self.panel_bg,
                command=lambda t=tool_name: self.select_tool(t),
                padx=8,
                pady=3,
                font=("TkDefaultFont", 8),
            )
            btn.pack(side=tk.LEFT, padx=2)
            self.tool_buttons[tool_name] = btn
            self._attach_tip(btn, tool_tips[tool_name])

        self._add_separator(toolbar)

        brush_lbl = tk.Label(
            toolbar,
            text="Brush:",
            bg=self.panel_bg,
            fg=self.text_fg,
            font=("TkDefaultFont", 9, "bold"),
        )
        brush_lbl.pack(side=tk.LEFT, padx=(0, 4))
        self._attach_tip(brush_lbl, "Stroke thickness setting (1px to 30px) for Freehand and shape tools.")

        self.size_scale = tk.Scale(
            toolbar,
            from_=1,
            to=30,
            orient=tk.HORIZONTAL,
            length=85,
            bg=self.panel_bg,
            fg=self.text_fg,
            troughcolor=self.bg_dark,
            activebackground=self.btn_active_bg,
            highlightthickness=0,
            command=self.update_brush_size,
        )
        self.size_scale.set(self.brush_size)
        self.size_scale.pack(side=tk.LEFT, padx=2)
        self._attach_tip(
            self.size_scale,
            "Drag slider to adjust brush stroke width from 1px (fine) to 30px (thick).",
        )

        eraser_lbl = tk.Label(
            toolbar,
            text="Eraser:",
            bg=self.panel_bg,
            fg=self.text_fg,
            font=("TkDefaultFont", 9, "bold"),
        )
        eraser_lbl.pack(side=tk.LEFT, padx=(8, 4))
        self._attach_tip(eraser_lbl, "Independent eraser radius setting (4px to 60px).")

        self.eraser_scale = tk.Scale(
            toolbar,
            from_=4,
            to=60,
            orient=tk.HORIZONTAL,
            length=90,
            bg=self.panel_bg,
            fg=self.text_fg,
            troughcolor=self.bg_dark,
            activebackground="#DC2626",
            highlightthickness=0,
            command=self.update_eraser_size,
        )
        self.eraser_scale.set(self.eraser_size)
        self.eraser_scale.pack(side=tk.LEFT, padx=2)
        self._attach_tip(
            self.eraser_scale,
            "Drag slider to resize the eraser from 4px to 60px; updates the dashed hover ring live.",
        )

        self._add_separator(toolbar)

        undo_btn = tk.Button(
            toolbar,
            text="Undo (Ctrl+Z)",
            bg=self.btn_bg,
            fg=self.text_fg,
            activebackground="#33415C",
            activeforeground=self.text_fg,
            command=self.undo,
            padx=8,
            pady=3,
            font=("TkDefaultFont", 8),
        )
        undo_btn.pack(side=tk.LEFT, padx=2)
        self._attach_tip(undo_btn, "Revert the most recent stroke, shape, or erase action (Shortcut: Ctrl+Z).")

        clear_btn = tk.Button(
            toolbar,
            text="Clear",
            bg="#7F1D1D",
            fg="#FEF2F2",
            activebackground="#991B1B",
            activeforeground="#FFFFFF",
            command=self.clear_canvas,
            padx=8,
            pady=3,
            font=("TkDefaultFont", 8),
        )
        clear_btn.pack(side=tk.LEFT, padx=2)
        self._attach_tip(clear_btn, "Remove all strokes and shapes from the drawing canvas and clear undo history.")

        save_btn = tk.Button(
            toolbar,
            text="Save PNG",
            bg="#14532D",
            fg="#F0FDF4",
            activebackground="#166534",
            activeforeground="#FFFFFF",
            command=self.save_as_png,
            padx=8,
            pady=3,
            font=("TkDefaultFont", 8),
        )
        save_btn.pack(side=tk.LEFT, padx=2)
        self._attach_tip(
            save_btn,
            "Export the current sketch as a clean white-background black-stroke PNG image (Shortcut: Ctrl+S).",
        )

        fourier_btn = tk.Button(
            toolbar,
            text="Draw with Fourier Circles →",
            bg="#2563EB",
            fg="#FFFFFF",
            activebackground="#3B82F6",
            activeforeground="#FFFFFF",
            command=self.send_to_fourier,
            padx=10,
            pady=3,
            font=("TkDefaultFont", 8, "bold"),
        )
        fourier_btn.pack(side=tk.RIGHT, padx=(6, 0))
        self._attach_tip(
            fourier_btn,
            "Convert your drawn 2D figure into ordered strokes, switch to the Fourier Epicycle tab, and animate it with rotating Fourier circles.",
        )

        self.status_var = tk.StringVar(
            value="Draw your 2D figure below, then click 'Draw with Fourier Circles →' | Tool: Freehand | Brush: 3px"
        )
        status_bar = tk.Label(
            self,
            textvariable=self.status_var,
            bd=1,
            relief=tk.SUNKEN,
            anchor=tk.W,
            bg="#161B26",
            fg=self.muted_fg,
            padx=8,
            pady=3,
            font=("TkDefaultFont", 8),
        )
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self._attach_tip(
            status_bar,
            "Live status bar displaying active tool, brush/eraser sizes, and cursor (x, y) pixel coordinates.",
        )

        self.canvas = tk.Canvas(
            self,
            bg=self.canvas_bg,
            highlightthickness=0,
            cursor="crosshair",
        )
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self._attach_tip(
            self.canvas,
            "2D Drawing Canvas: Left-click and drag to draw shapes or freehand strokes, or erase when Eraser is selected.",
        )

    def _add_separator(self, parent):
        sep = tk.Frame(parent, width=2, height=22, bg=self.border_color)
        sep.pack(side=tk.LEFT, padx=6)

    def _bind_events(self):
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Motion>", self.on_hover)
        self.canvas.bind("<Leave>", self.on_leave)

    def select_tool(self, tool_name: str):
        self.tool = tool_name
        for name, btn in self.tool_buttons.items():
            active = name == tool_name
            btn.config(
                relief=tk.SUNKEN if active else tk.RAISED,
                bg=self.btn_active_bg if active else self.btn_bg,
            )
        if self.tool != "eraser":
            self._clear_eraser_cursor()
        self._update_status()

    def update_brush_size(self, value: str):
        self.brush_size = int(float(value))
        self._update_status()

    def update_eraser_size(self, value: str):
        self.eraser_size = int(float(value))
        self._update_status()

    def _clear_eraser_cursor(self):
        if self.eraser_cursor_id is not None:
            self.canvas.delete(self.eraser_cursor_id)
            self.eraser_cursor_id = None

    def _update_eraser_cursor(self, x: int, y: int):
        if self.tool != "eraser":
            self._clear_eraser_cursor()
            return
        r = self.eraser_size / 2.0
        coords = (x - r, y - r, x + r, y + r)
        if self.eraser_cursor_id is None:
            self.eraser_cursor_id = self.canvas.create_oval(
                *coords,
                outline="#F87171",
                fill="",
                width=1,
                dash=(3, 2),
            )
        else:
            self.canvas.coords(self.eraser_cursor_id, *coords)
            self.canvas.tag_raise(self.eraser_cursor_id)

    def _normalized_box(self, x0: int, y0: int, x1: int, y1: int, square_or_circle: bool = False):
        dx = x1 - x0
        dy = y1 - y0
        if square_or_circle:
            side = max(abs(dx), abs(dy))
            sx = 1 if dx >= 0 else -1
            sy = 1 if dy >= 0 else -1
            x1 = x0 + sx * side
            y1 = y0 + sy * side
        return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)

    def _draw_shape(self, x0: int, y0: int, x1: int, y1: int, dash=None):
        kw = {"width": self.brush_size}
        if dash:
            kw["dash"] = dash

        if self.tool == "line":
            return [self.canvas.create_line(x0, y0, x1, y1, fill=self.ink_color, capstyle=tk.ROUND, **kw)]
        elif self.tool == "rectangle":
            bx0, by0, bx1, by1 = self._normalized_box(x0, y0, x1, y1, square_or_circle=False)
            return [self.canvas.create_rectangle(bx0, by0, bx1, by1, outline=self.ink_color, fill="", **kw)]
        elif self.tool == "square":
            bx0, by0, bx1, by1 = self._normalized_box(x0, y0, x1, y1, square_or_circle=True)
            return [self.canvas.create_rectangle(bx0, by0, bx1, by1, outline=self.ink_color, fill="", **kw)]
        elif self.tool == "oval":
            bx0, by0, bx1, by1 = self._normalized_box(x0, y0, x1, y1, square_or_circle=False)
            return [self.canvas.create_oval(bx0, by0, bx1, by1, outline=self.ink_color, fill="", **kw)]
        elif self.tool == "circle":
            bx0, by0, bx1, by1 = self._normalized_box(x0, y0, x1, y1, square_or_circle=True)
            return [self.canvas.create_oval(bx0, by0, bx1, by1, outline=self.ink_color, fill="", **kw)]
        return []

    def _clear_preview(self):
        for item_id in self.preview_ids:
            self.canvas.delete(item_id)
        self.preview_ids.clear()

    def _create_eraser_dot(self, x: int, y: int):
        r = max(self.eraser_size / 2.0, 1.0)
        dot_id = self.canvas.create_oval(
            x - r, y - r, x + r, y + r, fill=self.canvas_bg, outline=self.canvas_bg
        )
        if self.eraser_cursor_id is not None:
            self.canvas.tag_lower(dot_id, self.eraser_cursor_id)
        return dot_id

    def _create_eraser_segment(self, x0: int, y0: int, x1: int, y1: int):
        seg_id = self.canvas.create_line(
            x0, y0, x1, y1, fill=self.canvas_bg, width=self.eraser_size, capstyle=tk.ROUND, smooth=True
        )
        if self.eraser_cursor_id is not None:
            self.canvas.tag_lower(seg_id, self.eraser_cursor_id)
        return seg_id

    def on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        self._clear_preview()

        if self.tool == "freehand":
            r = max(self.brush_size / 2, 1)
            dot_id = self.canvas.create_oval(
                event.x - r, event.y - r, event.x + r, event.y + r, fill=self.ink_color, outline=self.ink_color
            )
            self.history.append({"ids": [dot_id], "kind": "draw"})
        elif self.tool == "eraser":
            dot_id = self._create_eraser_dot(event.x, event.y)
            self.history.append({"ids": [dot_id], "kind": "erase"})
            self._update_eraser_cursor(event.x, event.y)

    def on_drag(self, event):
        if self.start_x is None or self.start_y is None:
            return

        if self.tool == "freehand":
            seg_id = self.canvas.create_line(
                self.start_x,
                self.start_y,
                event.x,
                event.y,
                fill=self.ink_color,
                width=self.brush_size,
                capstyle=tk.ROUND,
                smooth=True,
            )
            if self.history and self.history[-1]["kind"] == "draw":
                self.history[-1]["ids"].append(seg_id)
            else:
                self.history.append({"ids": [seg_id], "kind": "draw"})
            self.start_x = event.x
            self.start_y = event.y
        elif self.tool == "eraser":
            seg_id = self._create_eraser_segment(self.start_x, self.start_y, event.x, event.y)
            if self.history and self.history[-1]["kind"] == "erase":
                self.history[-1]["ids"].append(seg_id)
            else:
                self.history.append({"ids": [seg_id], "kind": "erase"})
            self.start_x = event.x
            self.start_y = event.y
            self._update_eraser_cursor(event.x, event.y)
        else:
            self._clear_preview()
            self.preview_ids = self._draw_shape(self.start_x, self.start_y, event.x, event.y, dash=(4, 3))

        self._update_status(event.x, event.y)

    def on_release(self, event):
        if self.start_x is None or self.start_y is None:
            return

        if self.tool not in ("freehand", "eraser"):
            self._clear_preview()
            created_ids = self._draw_shape(self.start_x, self.start_y, event.x, event.y)
            if created_ids:
                self.history.append({"ids": created_ids, "kind": "draw"})

        self.start_x = None
        self.start_y = None
        self._update_eraser_cursor(event.x, event.y)
        self._update_status(event.x, event.y)

    def on_hover(self, event):
        self._update_eraser_cursor(event.x, event.y)
        self._update_status(event.x, event.y)

    def on_leave(self, _event):
        self._clear_eraser_cursor()

    def undo(self):
        if not self.history:
            return
        last_action = self.history.pop()
        for item_id in last_action["ids"]:
            self.canvas.delete(item_id)

    def clear_canvas(self):
        self.canvas.delete("all")
        self.history.clear()
        self.preview_ids.clear()
        self.eraser_cursor_id = None

    def render_pil_image(self) -> Image.Image:
        """Rasterize canvas strokes onto a clean white background with black ink."""
        self.canvas.update()
        width = max(self.canvas.winfo_width(), 1)
        height = max(self.canvas.winfo_height(), 1)

        img = Image.new("RGB", (width, height), color="#FFFFFF")
        draw = ImageDraw.Draw(img)

        black = "#000000"
        white = "#FFFFFF"

        for item_id in self.canvas.find_all():
            if item_id in self.preview_ids or item_id == self.eraser_cursor_id:
                continue

            item_type = self.canvas.type(item_id)
            coords = self.canvas.coords(item_id)
            if not coords:
                continue

            width_val = max(int(round(float(self.canvas.itemcget(item_id, "width") or 1))), 1)
            fill_opt = self.canvas.itemcget(item_id, "fill")
            is_eraser = fill_opt == self.canvas_bg
            ink = white if is_eraser else black

            if item_type == "line":
                pts = [(coords[i], coords[i + 1]) for i in range(0, len(coords) - 1, 2)]
                if len(pts) >= 2:
                    draw.line(pts, fill=ink, width=width_val)
                    r = width_val / 2.0
                    for px, py in (pts[0], pts[-1]):
                        draw.ellipse([px - r, py - r, px + r, py + r], fill=ink, outline=ink)
                elif len(pts) == 1:
                    px, py = pts[0]
                    r = max(width_val / 2.0, 1.0)
                    draw.ellipse([px - r, py - r, px + r, py + r], fill=ink, outline=ink)

            elif item_type == "rectangle" and len(coords) >= 4:
                x0, y0, x1, y1 = coords[0], coords[1], coords[2], coords[3]
                draw.rectangle([x0, y0, x1, y1], fill=None, outline=ink, width=width_val)

            elif item_type == "oval" and len(coords) >= 4:
                x0, y0, x1, y1 = coords[0], coords[1], coords[2], coords[3]
                if is_eraser:
                    draw.ellipse([x0, y0, x1, y1], fill=white, outline=white)
                else:
                    draw.ellipse([x0, y0, x1, y1], fill=None, outline=ink, width=width_val)

        return img

    def save_as_png(self):
        file_path = filedialog.asksaveasfilename(
            title="Save Drawing Pad as PNG",
            defaultextension=".png",
            filetypes=[("PNG Image", "*.png")],
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".png"):
            file_path += ".png"

        try:
            img = self.render_pil_image()
            img.save(file_path, format="PNG")
            messagebox.showinfo("Saved", f"Drawing saved as white-background black PNG:\n{file_path}")
        except Exception as exc:
            messagebox.showerror("Save PNG Error", f"Could not save PNG:\n{exc}")

    def send_to_fourier(self):
        img = self.render_pil_image()
        self.on_send_to_fourier(img)

    def _update_status(self, x: int = None, y: int = None):
        coords = f" | ({x}, {y})" if x is not None and y is not None else ""
        self.status_var.set(
            f"Tool: {self.tool.capitalize()} | Brush: {self.brush_size}px | "
            f"Eraser: {self.eraser_size}px{coords}"
        )


class FourierAnalyzerPanel(ttk.Frame):
    """2D Fourier Epicycle Analyzer with comprehensive hover tooltips on every control."""

    def __init__(self, parent, root: tk.Tk, on_switch_to_draw):
        super().__init__(parent, style="App.TFrame")
        self.root = root
        self.on_switch_to_draw = on_switch_to_draw

        self._tooltips: list[HoverTooltip] = []

        self.contour_points: np.ndarray | None = None
        self.eval_points: np.ndarray | None = None

        self.freqs_arr: np.ndarray = np.empty(0)
        self.coeffs_arr: np.ndarray = np.empty(0, dtype=complex)
        self.amps_arr: np.ndarray = np.empty(0)
        self.total_energy: float = 0.0

        self.center_points: list[complex] = []
        self.center_models: list[dict] = []

        self.bg_rgb_array: np.ndarray | None = None
        self.bg_extent: list[float] = [-1.0, 1.0, -1.0, 1.0]

        self.zoom_factor: float = 1.0
        self.pan_center_x: float = 0.0
        self.pan_center_y: float = 0.0
        self._drag_last_data: tuple[float, float] | None = None
        self._press_xy: tuple[float, float] | None = None
        self._did_pan: bool = False
        self._syncing_zoom: bool = False

        self.max_available_k: int = MAX_CIRCLES
        self.recommended_k: int = 50
        self.current_k: int = 50

        self.is_playing: bool = True
        self._after_id: str | None = None
        self._slider_debounce_id: str | None = None
        self._syncing_controls: bool = False

        self.num_frames: int = 240
        self.frame_idx: int = 0
        self._anim_mode: str = "single"
        self._frame_tips_list: list[np.ndarray] = []
        self._frame_centers_list: list[np.ndarray] = []
        self._frame_amps_list: list[np.ndarray] = []
        self._frame_seq_active_idx: list[int] = []
        self._frame_seq_tips: np.ndarray = np.zeros(self.num_frames, dtype=complex)
        self._frame_weights: np.ndarray = np.ones((1, self.num_frames), dtype=float)

        self.fig = None
        self.ax = None
        self.canvas = None
        self.bg_image_artist = None
        self.target_line = None
        self.center_markers_plot = None
        self.center_labels_texts: list = []
        self.drawn_lines: list = []
        self.radius_lines: list = []
        self.tip_dots: list = []
        self.circles: list[Circle] = []

        self._build_ui()
        self._load_default_shape("star")

    def _attach_tip(self, widget: tk.Widget, text: str):
        self._tooltips.append(HoverTooltip(widget, text))

    def _build_ui(self):
        # 1. Top Playback & Circle Controls
        top_shell = tk.Frame(
            self,
            bg=BG_CHROME,
            highlightbackground=BORDER_SUBTLE,
            highlightthickness=1,
        )
        top_shell.pack(side=tk.TOP, fill=tk.X)

        top_bar = ttk.Frame(top_shell, style="TopBar.TFrame", padding=(10, 6))
        top_bar.pack(side=tk.TOP, fill=tk.X)

        self.play_btn = ttk.Button(top_bar, text="Pause", width=7, command=self.toggle_play)
        self.play_btn.pack(side=tk.LEFT, padx=(0, 4))
        self._attach_tip(
            self.play_btn,
            "Pause or resume the Fourier epicycle animation at the current frame without resetting the trace.",
        )

        self.stop_btn = ttk.Button(top_bar, text="Stop", width=7, command=self.stop_drawing)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 4))
        self._attach_tip(
            self.stop_btn,
            "Stop animation completely and reset the traced curve back to frame 0.",
        )

        restart_btn = ttk.Button(top_bar, text="Restart", width=7, command=self.restart_animation)
        restart_btn.pack(side=tk.LEFT, padx=(0, 10))
        self._attach_tip(
            restart_btn,
            "Jump back to frame 0 and immediately play the Fourier drawing cycle from the start.",
        )

        self.stop_on_complete_var = tk.BooleanVar(value=False)
        stop_comp_chk = ttk.Checkbutton(
            top_bar,
            text="Stop After Completion",
            style="TopCheck.TCheckbutton",
            variable=self.stop_on_complete_var,
        )
        stop_comp_chk.pack(side=tk.LEFT, padx=(0, 12))
        self._attach_tip(
            stop_comp_chk,
            "When checked, automatically pauses at the end of one full cycle (frame 239) instead of looping.",
        )

        ttk.Separator(top_bar, orient=tk.VERTICAL, style="Dark.TSeparator").pack(
            side=tk.LEFT, fill=tk.Y, padx=(0, 12)
        )

        circles_lbl = ttk.Label(top_bar, text="Circles:")
        circles_lbl.pack(side=tk.LEFT, padx=(0, 6))
        self._attach_tip(
            circles_lbl,
            "Number of sorted Fourier frequency components (rotating circles) used to reconstruct the figure.",
        )

        self.k_var = tk.IntVar(value=50)
        self.k_scale = ttk.Scale(
            top_bar,
            from_=1,
            to=MAX_CIRCLES,
            orient=tk.HORIZONTAL,
            style="TopBar.Horizontal.TScale",
            command=self._on_slider_change,
        )
        self.k_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self._attach_tip(
            self.k_scale,
            "Slide to increase or decrease active Fourier circles; more circles capture finer details and sharper corners.",
        )

        self.k_spin = ttk.Spinbox(
            top_bar,
            from_=1,
            to=MAX_CIRCLES,
            increment=1,
            textvariable=self.k_var,
            width=6,
            command=self._on_spinbox_change,
        )
        self.k_spin.pack(side=tk.LEFT, padx=(0, 4))
        self.k_spin.bind("<Return>", lambda _e: self._on_spinbox_change())
        self._attach_tip(
            self.k_spin,
            "Type an exact circle count or use the up/down arrows, then press Enter to apply.",
        )

        self.k_max_label = ttk.Label(top_bar, text=f"/ {MAX_CIRCLES}", width=7)
        self.k_max_label.pack(side=tk.LEFT, padx=(0, 8))
        self._attach_tip(
            self.k_max_label,
            "Maximum number of Fourier circles available for the currently loaded figure.",
        )

        use_rec_btn = ttk.Button(top_bar, text="Use Recommended", command=self._apply_recommended_k)
        use_rec_btn.pack(side=tk.LEFT, padx=(0, 8))
        self._attach_tip(
            use_rec_btn,
            "Apply the auto-estimated circle count calculated for your selected Target Accuracy (%).",
        )

        save_png_btn = ttk.Button(
            top_bar,
            text="Save PNG",
            style="Accent.TButton",
            command=self.save_output_png,
        )
        save_png_btn.pack(side=tk.LEFT)
        self._attach_tip(
            save_png_btn,
            "Render the completed Fourier reconstruction at 200 DPI and save it as a PNG file (Shortcut: Ctrl+S).",
        )

        # 2. Body: Left Sidebar + Drawing Canvas
        body = ttk.Frame(self, style="App.TFrame")
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        sidebar_shell = tk.Frame(
            body,
            bg=BG_CHROME,
            width=340,
            highlightbackground=BORDER_SUBTLE,
            highlightthickness=1,
        )
        sidebar_shell.pack(side=tk.LEFT, fill=tk.Y)
        sidebar_shell.pack_propagate(False)

        sidebar = ttk.Frame(sidebar_shell, style="Sidebar.TFrame", padding=(8, 8))
        sidebar.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # A. Figure Source (Draw or Load Image + Presets)
        src_group = ttk.Labelframe(sidebar, text="Figure Source (Draw or Upload)", style="SideGroup.TLabelframe")
        src_group.pack(side=tk.TOP, fill=tk.X, pady=(0, 7))
        self._attach_tip(
            src_group,
            "Choose a 2D figure source: sketch one in the Draw 2D Figure tab, upload a JPG/PNG, or pick a preset shape.",
        )

        src_top_row = ttk.Frame(src_group, style="Card.TFrame")
        src_top_row.pack(side=tk.TOP, fill=tk.X, pady=(0, 5))
        src_top_row.columnconfigure(0, weight=1)
        src_top_row.columnconfigure(1, weight=1)

        draw_new_btn = ttk.Button(src_top_row, text="Draw 2D Figure...", command=self.on_switch_to_draw)
        draw_new_btn.grid(row=0, column=0, sticky="ew", padx=(0, 2))
        self._attach_tip(
            draw_new_btn,
            "Open the 2D Sketch Pad tab to draw freehand or geometric shapes and convert them into Fourier circles.",
        )

        load_img_btn = ttk.Button(src_top_row, text="Upload JPG / PNG...", command=self.load_image)
        load_img_btn.grid(row=0, column=1, sticky="ew", padx=(2, 0))
        self._attach_tip(
            load_img_btn,
            "Upload a JPG or PNG image with dark strokes on a light background to trace contours and compute Fourier harmonics.",
        )

        preset_row = ttk.Frame(src_group, style="Card.TFrame")
        preset_row.pack(side=tk.TOP, fill=tk.X)
        preset_tips = {
            "star": "Load the built-in 5-pointed star contour preset.",
            "heart": "Load the built-in parametric heart contour preset.",
            "spiral": "Load the built-in spiral contour preset.",
        }
        for idx, (label, kind) in enumerate([("Star", "star"), ("Heart", "heart"), ("Spiral", "spiral")]):
            preset_row.columnconfigure(idx, weight=1)
            padx_val = (0, 2) if idx == 0 else ((2, 2) if idx == 1 else (2, 0))
            btn = ttk.Button(preset_row, text=label, command=lambda k=kind: self._load_default_shape(k))
            btn.grid(row=0, column=idx, sticky="ew", padx=padx_val)
            self._attach_tip(btn, preset_tips[kind])

        # B. Multiple Center Points & 3 Methods
        centers_group = ttk.Labelframe(sidebar, text="Multiple Center Points & Methods", style="SideGroup.TLabelframe")
        centers_group.pack(side=tk.TOP, fill=tk.X, pady=(0, 7))
        self._attach_tip(
            centers_group,
            "Anchor one or multiple center points (C1, C2, ...) to test regional, blended, or budget-split Fourier epicycles.",
        )

        self.add_center_mode_var = tk.BooleanVar(value=False)
        add_c_chk = ttk.Checkbutton(
            centers_group,
            text="Click Canvas to Place Center Point",
            variable=self.add_center_mode_var,
        )
        add_c_chk.pack(side=tk.TOP, anchor="w", pady=(0, 4))
        self._attach_tip(
            add_c_chk,
            "Enable click-to-add mode: clicking (without dragging) on the canvas places a new center anchor point.",
        )

        c_btn_row = ttk.Frame(centers_group, style="Card.TFrame")
        c_btn_row.pack(side=tk.TOP, fill=tk.X, pady=(0, 6))
        c_btn_row.columnconfigure(0, weight=1)
        c_btn_row.columnconfigure(1, weight=1)
        c_btn_row.columnconfigure(2, weight=1)

        auto3_btn = ttk.Button(c_btn_row, text="Auto-3", command=lambda: self.auto_place_centers(3))
        auto3_btn.grid(row=0, column=0, sticky="ew", padx=(0, 2))
        self._attach_tip(auto3_btn, "Automatically place 3 evenly spaced anchor centers along the figure contour.")

        auto5_btn = ttk.Button(c_btn_row, text="Auto-5", command=lambda: self.auto_place_centers(5))
        auto5_btn.grid(row=0, column=1, sticky="ew", padx=2)
        self._attach_tip(auto5_btn, "Automatically place 5 evenly spaced anchor centers along the figure contour.")

        clear_c_btn = ttk.Button(c_btn_row, text="Clear", command=self.clear_centers)
        clear_c_btn.grid(row=0, column=2, sticky="ew", padx=(2, 0))
        self._attach_tip(clear_c_btn, "Remove all placed center points and revert to a single global Fourier center.")

        self.centers_count_label = ttk.Label(
            centers_group, text="Center Points: 0 (Single Global)", style="Muted.TLabel"
        )
        self.centers_count_label.pack(side=tk.TOP, anchor="w", pady=(0, 5))
        self._attach_tip(self.centers_count_label, "Displays the active center count and multi-center mode.")

        method_hdr = ttk.Label(centers_group, text="Multi-Center Method:", style="Card.TLabel")
        method_hdr.pack(side=tk.TOP, anchor="w")
        self._attach_tip(method_hdr, "Choose how multiple center anchors compute and combine epicycles (when 2+ centers exist).")

        self.center_method_var = tk.StringVar(value="partitioned")

        rb_part = ttk.Radiobutton(
            centers_group,
            text="1. Partitioned (Nearest-Anchor)",
            variable=self.center_method_var,
            value="partitioned",
            command=self._on_center_method_changed,
        )
        rb_part.pack(side=tk.TOP, anchor="w")
        self._attach_tip(
            rb_part,
            "Partitioned: Splits contour points by nearest anchor center and fits regional Fourier epicycles to each subset.",
        )

        rb_weight = ttk.Radiobutton(
            centers_group,
            text="2. Weighted (Blended Local)",
            variable=self.center_method_var,
            value="weighted",
            command=self._on_center_method_changed,
        )
        rb_weight.pack(side=tk.TOP, anchor="w")
        self._attach_tip(
            rb_weight,
            "Weighted: Computes local harmonics relative to each anchor and smoothly blends tip positions using Gaussian distance weights.",
        )

        rb_mroot = ttk.Radiobutton(
            centers_group,
            text="3. Multi-Root (Budget Split)",
            variable=self.center_method_var,
            value="multi_root",
            command=self._on_center_method_changed,
        )
        rb_mroot.pack(side=tk.TOP, anchor="w", pady=(0, 5))
        self._attach_tip(
            rb_mroot,
            "Multi-Root: Distributes the total circle budget across anchor centers proportionally to spectral energy or contour length.",
        )

        self.method_opts_frame = ttk.Frame(centers_group, style="Card.TFrame")
        self.method_opts_frame.pack(side=tk.TOP, fill=tk.X)

        self.order_row = ttk.Frame(self.method_opts_frame, style="Card.TFrame")
        order_lbl = ttk.Label(self.order_row, text="Order:", style="Muted.TLabel")
        order_lbl.pack(side=tk.LEFT, padx=(0, 4))
        self._attach_tip(order_lbl, "Playback ordering across multi-center epicycle groups.")

        self.order_var = tk.StringVar(value="simultaneous")
        rb_sim = ttk.Radiobutton(
            self.order_row,
            text="Simultaneous",
            variable=self.order_var,
            value="simultaneous",
            command=self._rebuild_for_centers,
        )
        rb_sim.pack(side=tk.LEFT, padx=(0, 6))
        self._attach_tip(rb_sim, "Simultaneous: Animates epicycles for all center points concurrently.")

        rb_seq = ttk.Radiobutton(
            self.order_row,
            text="Sequential",
            variable=self.order_var,
            value="sequential",
            command=self._rebuild_for_centers,
        )
        rb_seq.pack(side=tk.LEFT)
        self._attach_tip(rb_seq, "Sequential: Animates one center anchor's segment after another across the cycle.")

        self.weighted_opts_frame = ttk.Frame(self.method_opts_frame, style="Card.TFrame")
        w_hdr = ttk.Frame(self.weighted_opts_frame, style="Card.TFrame")
        w_hdr.pack(side=tk.TOP, fill=tk.X)
        sigma_lbl = ttk.Label(w_hdr, text="Blend Sigma:", style="Muted.TLabel")
        sigma_lbl.pack(side=tk.LEFT)
        self._attach_tip(sigma_lbl, "Gaussian bandwidth (0.10–1.50) controlling how smoothly weights transition between centers.")
        self.sigma_label = ttk.Label(w_hdr, text="0.45", style="Muted.TLabel")
        self.sigma_label.pack(side=tk.RIGHT)
        self._attach_tip(self.sigma_label, "Current Blend Sigma value.")

        self.blend_sigma_var = tk.DoubleVar(value=0.45)
        sigma_scale = ttk.Scale(
            self.weighted_opts_frame,
            from_=0.10,
            to=1.50,
            orient=tk.HORIZONTAL,
            variable=self.blend_sigma_var,
            style="Card.Horizontal.TScale",
            command=self._on_sigma_change,
        )
        sigma_scale.pack(side=tk.TOP, fill=tk.X, pady=(1, 4))
        self._attach_tip(
            sigma_scale,
            "Lower values localize blending near each anchor; higher values create wider smooth transitions.",
        )

        w_chain_row = ttk.Frame(self.weighted_opts_frame, style="Card.TFrame")
        w_chain_row.pack(side=tk.TOP, fill=tk.X)
        epi_lbl = ttk.Label(w_chain_row, text="Epicycles:", style="Muted.TLabel")
        epi_lbl.pack(side=tk.LEFT, padx=(0, 4))
        self._attach_tip(epi_lbl, "Choose which center's circles and radius lines are displayed during weighted blending.")

        self.weighted_chain_var = tk.StringVar(value="dominant")
        rb_dom = ttk.Radiobutton(
            w_chain_row,
            text="Dominant",
            variable=self.weighted_chain_var,
            value="dominant",
            command=self._rebuild_for_centers,
        )
        rb_dom.pack(side=tk.LEFT, padx=(0, 6))
        self._attach_tip(rb_dom, "Dominant: Shows circles and radius vectors for the center with the highest weight at each frame.")

        rb_all = ttk.Radiobutton(
            w_chain_row,
            text="All",
            variable=self.weighted_chain_var,
            value="all",
            command=self._rebuild_for_centers,
        )
        rb_all.pack(side=tk.LEFT)
        self._attach_tip(rb_all, "All: Displays circles and radius vectors for every center point simultaneously.")

        self.multi_root_opts_frame = ttk.Frame(self.method_opts_frame, style="Card.TFrame")
        mr_row = ttk.Frame(self.multi_root_opts_frame, style="Card.TFrame")
        mr_row.pack(side=tk.TOP, fill=tk.X)
        split_lbl = ttk.Label(mr_row, text="Split By:", style="Muted.TLabel")
        split_lbl.pack(side=tk.LEFT, padx=(0, 4))
        self._attach_tip(split_lbl, "Criterion used to divide total circles across multi-root anchors.")

        self.budget_split_var = tk.StringVar(value="energy")
        rb_eng = ttk.Radiobutton(
            mr_row,
            text="Energy",
            variable=self.budget_split_var,
            value="energy",
            command=self._rebuild_for_centers,
        )
        rb_eng.pack(side=tk.LEFT, padx=(0, 6))
        self._attach_tip(rb_eng, "Energy: Allocates more circles to anchor regions with greater harmonic energy.")

        rb_len = ttk.Radiobutton(
            mr_row,
            text="Arc Length",
            variable=self.budget_split_var,
            value="length",
            command=self._rebuild_for_centers,
        )
        rb_len.pack(side=tk.LEFT)
        self._attach_tip(rb_len, "Arc Length: Allocates circles proportionally to the number of contour points assigned to each anchor.")

        self._refresh_method_options_visibility()

        # C. Auto-Estimation
        est_group = ttk.Labelframe(sidebar, text="Circle Auto-Estimation", style="SideGroup.TLabelframe")
        est_group.pack(side=tk.TOP, fill=tk.X, pady=(0, 7))
        self._attach_tip(
            est_group,
            "Automatically calculate how many Fourier circles are needed to reach a target energy percentage.",
        )

        acc_row = ttk.Frame(est_group, style="Card.TFrame")
        acc_row.pack(side=tk.TOP, fill=tk.X, pady=(0, 5))
        acc_lbl = ttk.Label(acc_row, text="Target Accuracy (%):", style="Card.TLabel")
        acc_lbl.pack(side=tk.LEFT)
        self._attach_tip(acc_lbl, "Desired cumulative Fourier energy accuracy (50.0% to 99.99%).")

        self.accuracy_var = tk.DoubleVar(value=99.0)
        acc_spin = ttk.Spinbox(
            acc_row,
            from_=50.0,
            to=99.99,
            increment=0.5,
            textvariable=self.accuracy_var,
            width=7,
            command=lambda: self._recompute_recommended_k(apply_k=True),
        )
        acc_spin.pack(side=tk.RIGHT)
        acc_spin.bind("<Return>", lambda _e: self._recompute_recommended_k(apply_k=True))
        self._attach_tip(acc_spin, "Enter or step the target accuracy percentage and press Enter to recalculate.")

        est_btn = ttk.Button(
            est_group,
            text="Estimate Required Circles",
            style="Accent.TButton",
            command=lambda: self._recompute_recommended_k(apply_k=True),
        )
        est_btn.pack(side=tk.TOP, fill=tk.X)
        self._attach_tip(
            est_btn,
            "Compute the minimum circle count needed for the target accuracy and apply it immediately.",
        )

        # D. Circles, Lines & Background Overlay
        vis_group = ttk.Labelframe(sidebar, text="Circles, Lines & Overlay", style="SideGroup.TLabelframe")
        vis_group.pack(side=tk.TOP, fill=tk.X, pady=(0, 7))
        self._attach_tip(
            vis_group,
            "Control visibility of epicycle circles, connecting radius lines, and uploaded/drawn reference background images.",
        )

        chk_row = ttk.Frame(vis_group, style="Card.TFrame")
        chk_row.pack(side=tk.TOP, fill=tk.X, pady=(0, 3))
        self.show_circles_var = tk.BooleanVar(value=True)
        show_c_chk = ttk.Checkbutton(
            chk_row,
            text="Show Circles",
            variable=self.show_circles_var,
            command=self._on_display_options_changed,
        )
        show_c_chk.pack(side=tk.LEFT, padx=(0, 12))
        self._attach_tip(
            show_c_chk,
            "Show or hide rotating epicycle circle outlines (up to 40 visible circles for clarity), even while paused or stopped.",
        )

        self.show_lines_var = tk.BooleanVar(value=True)
        show_l_chk = ttk.Checkbutton(
            chk_row,
            text="Show Lines",
            variable=self.show_lines_var,
            command=self._on_display_options_changed,
        )
        show_l_chk.pack(side=tk.LEFT)
        self._attach_tip(
            show_l_chk,
            "Show or hide connecting harmonic radius vectors from center to tip, even while paused or stopped.",
        )

        self.show_bg_var = tk.BooleanVar(value=True)
        show_bg_chk = ttk.Checkbutton(
            vis_group,
            text="Show Background Image",
            variable=self.show_bg_var,
            command=self._update_bg_overlay,
        )
        show_bg_chk.pack(side=tk.TOP, anchor="w", pady=(0, 2))
        self._attach_tip(
            show_bg_chk,
            "Toggle the uploaded image or rasterized sketch behind the Fourier epicycle trace.",
        )

        alpha_hdr = ttk.Frame(vis_group, style="Card.TFrame")
        alpha_hdr.pack(side=tk.TOP, fill=tk.X)
        alpha_lbl = ttk.Label(alpha_hdr, text="BG Transparency", style="Muted.TLabel")
        alpha_lbl.pack(side=tk.LEFT)
        self._attach_tip(alpha_lbl, "Opacity percentage of the background reference image.")
        self.bg_alpha_label = ttk.Label(alpha_hdr, text="30%", style="Muted.TLabel")
        self.bg_alpha_label.pack(side=tk.RIGHT)
        self._attach_tip(self.bg_alpha_label, "Current background image opacity.")

        self.bg_alpha_var = tk.DoubleVar(value=0.30)
        bg_alpha_scale = ttk.Scale(
            vis_group,
            from_=0.0,
            to=1.0,
            orient=tk.HORIZONTAL,
            variable=self.bg_alpha_var,
            style="Card.Horizontal.TScale",
            command=lambda _v: self._on_bg_alpha_change(),
        )
        bg_alpha_scale.pack(side=tk.TOP, fill=tk.X)
        self._attach_tip(
            bg_alpha_scale,
            "Slide from 0% (transparent) to 100% (opaque) to adjust reference image visibility.",
        )

        # E. Zoom & View
        zoom_group = ttk.Labelframe(sidebar, text="Zoom & Pan", style="SideGroup.TLabelframe")
        zoom_group.pack(side=tk.TOP, fill=tk.X, pady=(0, 7))
        self._attach_tip(
            zoom_group,
            "Inspect fine epicycle details by zooming (25%–400%), dragging to pan, or resetting the camera view.",
        )

        zoom_hdr = ttk.Frame(zoom_group, style="Card.TFrame")
        zoom_hdr.pack(side=tk.TOP, fill=tk.X)
        zoom_lbl = ttk.Label(zoom_hdr, text="Zoom Level", style="Muted.TLabel")
        zoom_lbl.pack(side=tk.LEFT)
        self._attach_tip(zoom_lbl, "Current camera zoom magnification.")
        self.zoom_label = ttk.Label(zoom_hdr, text="100%", style="StatValue.TLabel")
        self.zoom_label.pack(side=tk.RIGHT)
        self._attach_tip(self.zoom_label, "Current zoom percentage.")

        self.zoom_var = tk.DoubleVar(value=100.0)
        self.zoom_scale = ttk.Scale(
            zoom_group,
            from_=25.0,
            to=400.0,
            orient=tk.HORIZONTAL,
            variable=self.zoom_var,
            style="Card.Horizontal.TScale",
            command=self._on_zoom_slider_change,
        )
        self.zoom_scale.pack(side=tk.TOP, fill=tk.X, pady=(1, 4))
        self._attach_tip(self.zoom_scale, "Drag to zoom between 25% and 400% around the current pan center.")

        z_btn_row = ttk.Frame(zoom_group, style="Card.TFrame")
        z_btn_row.pack(side=tk.TOP, fill=tk.X)
        reset_view_btn = ttk.Button(z_btn_row, text="Reset View", command=self.reset_view)
        reset_view_btn.pack(side=tk.LEFT, padx=(0, 8))
        self._attach_tip(reset_view_btn, "Reset zoom back to 100% and recenter the view at (0, 0).")
        pan_hint_lbl = ttk.Label(z_btn_row, text="Wheel: Zoom • Drag: Pan", style="Muted.TLabel")
        pan_hint_lbl.pack(side=tk.LEFT)
        self._attach_tip(pan_hint_lbl, "Scroll mouse wheel over the canvas to zoom; left-drag to pan across the figure.")

        # F. Metrics
        stats_group = ttk.Labelframe(sidebar, text="Analysis Metrics", style="SideGroup.TLabelframe")
        stats_group.pack(side=tk.BOTTOM, fill=tk.X)
        self._attach_tip(
            stats_group,
            "Quantitative accuracy metrics comparing the Fourier circle approximation against the target contour.",
        )

        self.rec_metric_label = ttk.Label(stats_group, text="Recommended: --", style="StatValue.TLabel")
        self.rec_metric_label.pack(side=tk.TOP, anchor="w", pady=(0, 2))
        self._attach_tip(self.rec_metric_label, "Recommended number of circles to reach your selected target accuracy.")

        self.cur_metric_label = ttk.Label(stats_group, text="Active Circles: --", style="Card.TLabel")
        self.cur_metric_label.pack(side=tk.TOP, anchor="w", pady=(0, 2))
        self._attach_tip(self.cur_metric_label, "Active Fourier circle count relative to total available harmonics.")

        self.energy_metric_label = ttk.Label(stats_group, text="Energy Captured: --%", style="Card.TLabel")
        self.energy_metric_label.pack(side=tk.TOP, anchor="w", pady=(0, 2))
        self._attach_tip(
            self.energy_metric_label,
            "Percentage of total contour squared-amplitude energy represented by the active circles.",
        )

        self.rmse_metric_label = ttk.Label(stats_group, text="RMSE: --", style="Muted.TLabel")
        self.rmse_metric_label.pack(side=tk.TOP, anchor="w")
        self._attach_tip(
            self.rmse_metric_label,
            "Root-Mean-Square Error (lower is closer) between the reference contour and reconstructed path.",
        )

        # 3. Main Drawing Canvas
        canvas_frame = ttk.Frame(body, style="App.TFrame", padding=(8, 8, 8, 8))
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.fig = Figure(figsize=(8, 6), dpi=100, facecolor="#FFFFFF")
        self.ax = self.fig.add_axes([0.0, 0.0, 1.0, 1.0])
        self.ax.set_facecolor("#FFFFFF")
        self.ax.set_aspect("equal", adjustable="datalim")
        self.ax.set_autoscale_on(False)
        self.ax.axis("off")

        (self.target_line,) = self.ax.plot([], [], color="#CBD5E1", linestyle="--", linewidth=1.2, zorder=2)
        (self.center_markers_plot,) = self.ax.plot(
            [], [], "D", color="#0F766E", markeredgecolor="#FFFFFF", markeredgewidth=1.0, markersize=7, zorder=7
        )

        trace_colors = ["#DC2626", "#7C3AED", "#0284C7", "#059669", "#DB2777", "#D97706"]
        self.drawn_lines = []
        self.radius_lines = []
        self.tip_dots = []
        for idx in range(16):
            col = trace_colors[idx % len(trace_colors)]
            (dl,) = self.ax.plot([], [], color=col, linewidth=2.3, zorder=5)
            (rl,) = self.ax.plot([], [], color="#1E3A8A", linewidth=1.3, alpha=0.9, zorder=4)
            (td,) = self.ax.plot([], [], "o", color="#EA580C", markersize=5, zorder=6)
            self.drawn_lines.append(dl)
            self.radius_lines.append(rl)
            self.tip_dots.append(td)

        self.circles = []
        for _ in range(MAX_VISIBLE_CIRCLES):
            c = Circle(
                (0, 0),
                0.0,
                fill=True,
                facecolor="#3B82F6",
                alpha=0.14,
                edgecolor="#1D4ED8",
                linewidth=1.6,
                zorder=3,
            )
            c.set_visible(False)
            self.ax.add_patch(c)
            self.circles.append(c)

        self._apply_camera_limits(redraw=False)

        self.canvas = FigureCanvasTkAgg(self.fig, master=canvas_frame)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self._attach_tip(
            self.canvas.get_tk_widget(),
            "Epicycle Simulation View: Scroll to zoom, drag to pan, or click to add a center anchor when enabled.",
        )

        self.canvas.mpl_connect("scroll_event", self._on_scroll_zoom)
        self.canvas.mpl_connect("button_press_event", self._on_mouse_press)
        self.canvas.mpl_connect("motion_notify_event", self._on_mouse_drag)
        self.canvas.mpl_connect("button_release_event", self._on_mouse_release)

    def cleanup(self):
        self._stop_timer()
        if self._slider_debounce_id is not None:
            try:
                self.root.after_cancel(self._slider_debounce_id)
            except tk.TclError:
                pass

    # ------------------------------------------------------------------
    # Multi-center UI & placement
    # ------------------------------------------------------------------
    def _refresh_method_options_visibility(self):
        mode = self.center_method_var.get()
        for child in (self.order_row, self.weighted_opts_frame, self.multi_root_opts_frame):
            child.pack_forget()

        if mode == "partitioned":
            self.order_row.pack(side=tk.TOP, fill=tk.X, pady=(2, 0))
        elif mode == "weighted":
            self.weighted_opts_frame.pack(side=tk.TOP, fill=tk.X, pady=(2, 0))
        elif mode == "multi_root":
            self.multi_root_opts_frame.pack(side=tk.TOP, fill=tk.X, pady=(2, 0))
            self.order_row.pack(side=tk.TOP, fill=tk.X, pady=(4, 0))

    def _on_center_method_changed(self):
        self._refresh_method_options_visibility()
        self._rebuild_for_centers()

    def _on_sigma_change(self, val_str: str):
        self.sigma_label.config(text=f"{float(val_str):.2f}")
        if self._slider_debounce_id is not None:
            self.root.after_cancel(self._slider_debounce_id)
        self._slider_debounce_id = self.root.after(50, self._rebuild_for_centers)

    def _update_center_markers(self):
        for txt in self.center_labels_texts:
            txt.remove()
        self.center_labels_texts.clear()

        if not self.center_points:
            self.center_markers_plot.set_data([], [])
        else:
            xs = [c.real for c in self.center_points]
            ys = [c.imag for c in self.center_points]
            self.center_markers_plot.set_data(xs, ys)
            for idx, c in enumerate(self.center_points):
                lbl = self.ax.text(
                    c.real + 0.03,
                    c.imag + 0.03,
                    f"C{idx + 1}",
                    fontsize=8,
                    fontweight="bold",
                    color="#0F766E",
                    zorder=8,
                )
                self.center_labels_texts.append(lbl)

        if len(self.center_points) <= 1:
            self.centers_count_label.config(
                text=f"Center Points: {len(self.center_points)} (Single Global)"
            )
        else:
            self.centers_count_label.config(
                text=f"Center Points: {len(self.center_points)} ({self.center_method_var.get()})"
            )

    def add_center_point(self, pt: complex):
        self.center_points.append(pt)
        self._update_center_markers()
        self._rebuild_for_centers()

    def auto_place_centers(self, count: int):
        if self.contour_points is None or len(self.contour_points) == 0:
            return
        indices = np.linspace(0, len(self.contour_points) - 1, count, dtype=int)
        self.center_points = [complex(self.contour_points[i]) for i in indices]
        self._update_center_markers()
        self._rebuild_for_centers()

    def clear_centers(self):
        self.center_points.clear()
        self.center_models.clear()
        self._update_center_markers()
        self._compute_fourier_harmonics()
        self._recompute_recommended_k(apply_k=True)

    # ------------------------------------------------------------------
    # Save final output as PNG
    # ------------------------------------------------------------------
    def save_output_png(self):
        if self.contour_points is None or len(self.coeffs_arr) == 0:
            messagebox.showwarning("Nothing to Save", "No figure is currently loaded.")
            return

        file_path = filedialog.asksaveasfilename(
            title="Save Final Fourier Figure as PNG",
            defaultextension=".png",
            initialfile=f"fourier_{self.current_k}_circles.png",
            filetypes=[("PNG Image", "*.png"), ("All files", "*.*")],
        )
        if not file_path:
            return

        if self.is_playing:
            self.is_playing = False
            self._stop_timer()
            self.play_btn.config(text="Play")

        try:
            prev_frame = self.frame_idx
            self._render_frame(self.num_frames - 1)
            self.canvas.draw()
            self.fig.savefig(file_path, dpi=200, facecolor=self.fig.get_facecolor())
            self.frame_idx = prev_frame
            self._render_frame(prev_frame)
            messagebox.showinfo("Saved", f"Saved PNG output to:\n{file_path}")
        except Exception as exc:
            messagebox.showerror("Save Error", f"Could not save PNG:\n{exc}")

    # ------------------------------------------------------------------
    # Zoom & Pan + Click-to-place center
    # ------------------------------------------------------------------
    def _apply_camera_limits(self, redraw: bool = True):
        half_span = BASE_HALF_SPAN / max(0.25, self.zoom_factor)
        self.ax.set_xlim(self.pan_center_x - half_span, self.pan_center_x + half_span)
        self.ax.set_ylim(self.pan_center_y - half_span, self.pan_center_y + half_span)
        if redraw and self.canvas is not None:
            self.canvas.draw_idle()

    def _set_zoom(self, zoom_pct: float):
        clamped_pct = max(25.0, min(400.0, float(zoom_pct)))
        self.zoom_factor = clamped_pct / 100.0
        self._syncing_zoom = True
        try:
            self.zoom_var.set(clamped_pct)
        finally:
            self._syncing_zoom = False
        self.zoom_label.config(text=f"{int(round(clamped_pct))}%")
        self._apply_camera_limits()

    def _on_zoom_slider_change(self, val_str: str):
        if self._syncing_zoom:
            return
        self._set_zoom(float(val_str))

    def reset_view(self):
        self.pan_center_x = 0.0
        self.pan_center_y = 0.0
        self._set_zoom(100.0)

    def _on_scroll_zoom(self, event):
        if event.inaxes != self.ax:
            return
        curr_pct = self.zoom_factor * 100.0
        step = 15.0 if event.button == "up" or (hasattr(event, "step") and event.step > 0) else -15.0
        self._set_zoom(curr_pct + step)

    def _on_mouse_press(self, event):
        if event.inaxes == self.ax and event.button == 1 and event.xdata is not None and event.ydata is not None:
            self._drag_last_data = (float(event.xdata), float(event.ydata))
            self._press_xy = (float(event.xdata), float(event.ydata))
            self._did_pan = False

    def _on_mouse_drag(self, event):
        if self._drag_last_data is None or event.inaxes != self.ax:
            return
        if event.xdata is None or event.ydata is None:
            return
        cx, cy = float(event.xdata), float(event.ydata)
        dx = cx - self._drag_last_data[0]
        dy = cy - self._drag_last_data[1]
        if abs(dx) > 1e-4 or abs(dy) > 1e-4:
            self._did_pan = True
        self.pan_center_x -= dx
        self.pan_center_y -= dy
        self._drag_last_data = (cx - dx, cy - dy)
        self._apply_camera_limits()

    def _on_mouse_release(self, event):
        was_click = not self._did_pan and self._press_xy is not None
        self._drag_last_data = None
        self._press_xy = None
        if was_click and self.add_center_mode_var.get() and event.inaxes == self.ax:
            if event.xdata is not None and event.ydata is not None:
                self.add_center_point(complex(float(event.xdata), float(event.ydata)))

    # ------------------------------------------------------------------
    # Stroke extraction & resampling
    # ------------------------------------------------------------------
    @staticmethod
    def _resample_1d(xp: np.ndarray, fp: np.ndarray, x_new: np.ndarray) -> np.ndarray:
        if len(xp) == 1:
            return np.full_like(x_new, fp[0], dtype=float)
        keep = np.concatenate([[True], np.diff(xp) > 1e-12])
        xp_clean = xp[keep]
        fp_clean = fp[keep]
        if len(xp_clean) == 1:
            return np.full_like(x_new, fp_clean[0], dtype=float)
        return np.interp(x_new, xp_clean, fp_clean)

    def _load_default_shape(self, kind: str = "star"):
        self.bg_rgb_array = None
        t = np.linspace(0, 2 * np.pi, TARGET_SAMPLES, endpoint=False)
        if kind == "heart":
            x = 16 * np.sin(t) ** 3
            y = 13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t)
        elif kind == "spiral":
            r = 0.2 + 0.8 * (t / (2 * np.pi))
            x = r * np.cos(4 * t)
            y = r * np.sin(4 * t)
        else:
            angles = np.linspace(0, 2 * np.pi, 11)
            radii = np.array([1.0, 0.42] * 5 + [1.0])
            poly_x = radii * np.cos(angles - np.pi / 2)
            poly_y = radii * np.sin(angles - np.pi / 2)
            dists = np.hypot(np.diff(poly_x), np.diff(poly_y))
            cum = np.concatenate([[0.0], np.cumsum(dists)])
            u = np.linspace(0, cum[-1], TARGET_SAMPLES, endpoint=False)
            x = self._resample_1d(cum, poly_x, u)
            y = self._resample_1d(cum, poly_y, u)

        self._process_points(np.column_stack([x, y]))

    def load_pil_image(self, pil_img: Image.Image) -> bool:
        """Process any PIL Image (uploaded JPG/PNG or hand-drawn canvas) into Fourier epicycles."""
        img_rgb = pil_img.convert("RGB")
        img_rgb.thumbnail((700, 700), Image.Resampling.LANCZOS)
        rgb = np.array(img_rgb, dtype=np.uint8)
        gray = np.array(img_rgb.convert("L"), dtype=np.float32)

        mask = gray < 165
        ys, xs = np.where(mask)
        if len(xs) < 10:
            messagebox.showwarning(
                "No Strokes Detected",
                "Could not find dark stroke pixels on a light background. Draw a figure or load a clearer image.",
            )
            return False

        raw_x = xs.astype(float)
        raw_y = -ys.astype(float)
        mean_pt = np.array([np.mean(raw_x), np.mean(raw_y)])
        centered_raw = np.column_stack([raw_x, raw_y]) - mean_pt
        max_span = float(np.max(np.linalg.norm(centered_raw, axis=1)))
        if max_span <= 0:
            max_span = 1.0

        h, w, _ = rgb.shape
        self.bg_rgb_array = rgb
        self.bg_extent = [
            (0.0 - mean_pt[0]) / max_span,
            (float(w) - mean_pt[0]) / max_span,
            (-float(h) - mean_pt[1]) / max_span,
            (0.0 - mean_pt[1]) / max_span,
        ]

        pts = self._extract_all_strokes_ordered(mask, target_samples=TARGET_SAMPLES)
        self._process_points(pts, pre_normalized=False, custom_norm=(mean_pt, max_span))
        self.is_playing = True
        self.play_btn.config(text="Pause")
        self._start_timer_if_playing()
        return True

    def load_image(self):
        path = filedialog.askopenfilename(
            title="Select 2D Figure (JPG or PNG)",
            filetypes=[
                ("Image files (JPG, PNG)", "*.png *.jpg *.jpeg"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return

        try:
            pil_img = Image.open(path)
            self.load_pil_image(pil_img)
        except Exception as exc:
            messagebox.showerror("Error Loading Image", str(exc))

    def _trace_component_two_ended(self, coords: np.ndarray) -> np.ndarray:
        m = len(coords)
        if m <= 2:
            return coords
        if m > 4500:
            step = max(1, m // 4500)
            coords = coords[::step]
            m = len(coords)

        visited = np.zeros(m, dtype=bool)
        chain = deque()
        visited[0] = True
        chain.append(coords[0])
        head = coords[0]
        tail = coords[0]
        remaining = m - 1

        while remaining > 0:
            unvis_idx = np.flatnonzero(~visited)
            unvis_pts = coords[unvis_idx]
            d_head = np.sum((unvis_pts - head) ** 2, axis=1)
            d_tail = np.sum((unvis_pts - tail) ** 2, axis=1)
            min_h_pos = int(np.argmin(d_head))
            min_t_pos = int(np.argmin(d_tail))
            if d_head[min_h_pos] <= d_tail[min_t_pos]:
                pick_idx = int(unvis_idx[min_h_pos])
                pt = coords[pick_idx]
                chain.appendleft(pt)
                head = pt
            else:
                pick_idx = int(unvis_idx[min_t_pos])
                pt = coords[pick_idx]
                chain.append(pt)
                tail = pt
            visited[pick_idx] = True
            remaining -= 1

        return np.asarray(chain, dtype=float)

    def _extract_all_strokes_ordered(self, mask: np.ndarray, target_samples: int = TARGET_SAMPLES) -> np.ndarray:
        h, w = mask.shape
        visited_grid = np.zeros((h, w), dtype=bool)
        ys_all, xs_all = np.where(mask)
        components: list[np.ndarray] = []
        neighbors_8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]

        for y0, x0 in zip(ys_all, xs_all):
            if visited_grid[y0, x0]:
                continue
            q = deque([(int(y0), int(x0))])
            visited_grid[y0, x0] = True
            comp_pts: list[tuple[float, float]] = []
            while q:
                cy, cx = q.popleft()
                comp_pts.append((float(cx), -float(cy)))
                for dy, dx in neighbors_8:
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not visited_grid[ny, nx]:
                        visited_grid[ny, nx] = True
                        q.append((ny, nx))
            if len(comp_pts) >= 2 or len(components) == 0:
                components.append(self._trace_component_two_ended(np.asarray(comp_pts, dtype=float)))

        if not components:
            return np.column_stack([xs_all.astype(float), -ys_all.astype(float)])

        remaining_comps = list(components)
        merged_segments: list[np.ndarray] = [remaining_comps.pop(0)]

        while remaining_comps:
            curr_end = merged_segments[-1][-1]
            best_c_idx = 0
            best_dist_sq = np.inf
            best_reverse = False
            for idx, comp in enumerate(remaining_comps):
                d_start = float(np.sum((comp[0] - curr_end) ** 2))
                d_end = float(np.sum((comp[-1] - curr_end) ** 2))
                if d_start <= best_dist_sq:
                    best_dist_sq = d_start
                    best_c_idx = idx
                    best_reverse = False
                if d_end < best_dist_sq:
                    best_dist_sq = d_end
                    best_c_idx = idx
                    best_reverse = True
            chosen = remaining_comps.pop(best_c_idx)
            if best_reverse:
                chosen = chosen[::-1]
            merged_segments.append(chosen)

        full_path = np.vstack(merged_segments)
        if len(full_path) < 2:
            return full_path
        seg = np.hypot(np.diff(full_path[:, 0]), np.diff(full_path[:, 1]))
        cum = np.concatenate([[0.0], np.cumsum(seg)])
        if cum[-1] <= 1e-12:
            return full_path
        u = np.linspace(0.0, cum[-1], target_samples, endpoint=False)
        return np.column_stack([
            self._resample_1d(cum, full_path[:, 0], u),
            self._resample_1d(cum, full_path[:, 1], u),
        ])

    def _process_points(
        self,
        pts: np.ndarray,
        pre_normalized: bool = False,
        custom_norm: tuple[np.ndarray, float] | None = None,
    ):
        if pre_normalized:
            centered = pts
        elif custom_norm is not None:
            mean_pt, max_span = custom_norm
            centered = (pts - mean_pt) / max_span
        else:
            centered = pts - np.mean(pts, axis=0)
            max_span = float(np.max(np.linalg.norm(centered, axis=1)))
            if max_span > 0:
                centered = centered / max_span

        self.contour_points = centered[:, 0] + 1j * centered[:, 1]
        step = max(1, len(self.contour_points) // 1024)
        self.eval_points = self.contour_points[::step]

        self.center_points.clear()
        self._update_center_markers()
        self.target_line.set_data(self.contour_points.real, self.contour_points.imag)
        self._update_bg_overlay(redraw=False)
        self._compute_fourier_harmonics()
        self._recompute_recommended_k(apply_k=True)

    # ------------------------------------------------------------------
    # Background & display toggles
    # ------------------------------------------------------------------
    def _on_bg_alpha_change(self):
        pct = int(round(self.bg_alpha_var.get() * 100))
        self.bg_alpha_label.config(text=f"{pct}%")
        self._update_bg_overlay()

    def _update_bg_overlay(self, redraw: bool = True):
        if self.bg_image_artist is not None:
            self.bg_image_artist.remove()
            self.bg_image_artist = None

        if self.show_bg_var.get() and self.bg_rgb_array is not None:
            alpha = float(self.bg_alpha_var.get())
            if alpha > 0.0:
                self.bg_image_artist = self.ax.imshow(
                    self.bg_rgb_array,
                    extent=self.bg_extent,
                    alpha=alpha,
                    zorder=1,
                )

        if redraw and self.canvas is not None:
            self.canvas.draw_idle()

    def _on_display_options_changed(self):
        if self.canvas is not None and len(self._frame_tips_list) > 0:
            self._render_frame(self.frame_idx)

    # ------------------------------------------------------------------
    # Fourier harmonics (Single & Multi-Center)
    # ------------------------------------------------------------------
    @staticmethod
    def _dft_sorted(z_local: np.ndarray, cap_k: int = MAX_CIRCLES):
        n = len(z_local)
        if n == 0:
            return np.empty(0, dtype=complex), np.empty(0), np.empty(0), 0.0
        coeffs = np.fft.fft(z_local) / n
        freqs = np.fft.fftfreq(n) * n
        amps = np.abs(coeffs)
        order = np.argsort(-amps)
        m = min(cap_k, len(order))
        idx = order[:m]
        c_s = coeffs[idx]
        f_s = freqs[idx]
        a_s = amps[idx]
        return c_s, f_s, a_s, float(np.sum(a_s ** 2))

    def _compute_fourier_harmonics(self):
        if self.contour_points is None:
            return
        self.coeffs_arr, self.freqs_arr, self.amps_arr, self.total_energy = self._dft_sorted(
            self.contour_points, MAX_CIRCLES
        )
        self.max_available_k = max(1, len(self.coeffs_arr))
        self.k_scale.configure(to=self.max_available_k)
        self.k_spin.configure(to=self.max_available_k)
        self.k_max_label.config(text=f"/ {self.max_available_k}")

        self.center_models.clear()
        if len(self.center_points) > 1:
            z = self.contour_points
            centers_arr = np.array(self.center_points, dtype=complex)
            dists = np.abs(z[:, None] - centers_arr[None, :])
            nearest_c = np.argmin(dists, axis=1)

            for m_idx, anchor in enumerate(self.center_points):
                part_pts = z[nearest_c == m_idx]
                if len(part_pts) < 4:
                    part_pts = z
                local_signal = z - anchor
                c_loc, f_loc, a_loc, e_loc = self._dft_sorted(local_signal, MAX_CIRCLES)
                c_part, f_part, a_part, e_part = self._dft_sorted(part_pts - anchor, MAX_CIRCLES)
                self.center_models.append({
                    "anchor": anchor,
                    "part_count": int(np.sum(nearest_c == m_idx)),
                    "c_loc": c_loc,
                    "f_loc": f_loc,
                    "a_loc": a_loc,
                    "e_loc": e_loc,
                    "c_part": c_part,
                    "f_part": f_part,
                    "a_part": a_part,
                    "e_part": e_part,
                })

    def _rebuild_for_centers(self):
        self._compute_fourier_harmonics()
        self._recompute_recommended_k(apply_k=False)
        self._set_current_k(self.current_k)

    def _recompute_recommended_k(self, apply_k: bool = False):
        if len(self.amps_arr) == 0 or self.contour_points is None:
            return

        target_pct = max(50.0, min(99.99, float(self.accuracy_var.get())))
        target_ratio = target_pct / 100.0

        if self.total_energy == 0:
            rec_k = 1
        else:
            cum_energy = np.cumsum(self.amps_arr ** 2) / self.total_energy
            idx = int(np.searchsorted(cum_energy, target_ratio))
            rec_k = max(1, min(self.max_available_k, idx + 1))

        self.recommended_k = rec_k
        if apply_k:
            self._set_current_k(self.recommended_k)
        else:
            self._update_metrics_label()

    def _apply_recommended_k(self):
        self._set_current_k(self.recommended_k)

    def _set_current_k(self, k: int):
        k = max(1, min(int(k), self.max_available_k))
        self._syncing_controls = True
        try:
            self.k_var.set(k)
            self.k_scale.set(k)
        finally:
            self._syncing_controls = False

        self.current_k = k
        self._precompute_frames()
        self._update_metrics_label()
        self.frame_idx = 0
        self._render_frame(0)

    def _on_slider_change(self, val_str: str):
        if self._syncing_controls:
            return
        k = max(1, min(int(float(val_str)), self.max_available_k))
        self._syncing_controls = True
        try:
            self.k_var.set(k)
        finally:
            self._syncing_controls = False

        if self._slider_debounce_id is not None:
            self.root.after_cancel(self._slider_debounce_id)
        self._slider_debounce_id = self.root.after(40, lambda target_k=k: self._apply_slider_k(target_k))

    def _apply_slider_k(self, k: int):
        self._slider_debounce_id = None
        if k != self.current_k:
            self.current_k = k
            self._precompute_frames()
            self._update_metrics_label()
            self.frame_idx = 0
            self._render_frame(0)

    def _on_spinbox_change(self):
        if self._syncing_controls:
            return
        try:
            k = int(self.k_var.get())
        except (tk.TclError, ValueError):
            k = self.current_k
        self._set_current_k(k)

    def _update_metrics_label(self):
        if len(self.amps_arr) == 0 or self.eval_points is None:
            return
        captured = (
            100.0 * float(np.sum(self.amps_arr[: self.current_k] ** 2)) / self.total_energy
            if self.total_energy > 0
            else 100.0
        )
        if len(self._frame_tips_list) > 0:
            recon = self._frame_tips_list[0]
            step = max(1, len(self.eval_points) // max(1, len(recon)))
            ref = self.eval_points[::step][: len(recon)]
            rmse = float(np.sqrt(np.mean(np.abs(ref - recon[: len(ref)]) ** 2)))
        else:
            rmse = 0.0

        self.rec_metric_label.config(
            text=f"Recommended: {self.recommended_k} ({self.accuracy_var.get():.2f}% target)"
        )
        self.cur_metric_label.config(text=f"Active Circles: {self.current_k} / {self.max_available_k}")
        self.energy_metric_label.config(text=f"Energy Captured: {captured:.3f}%")
        self.rmse_metric_label.config(text=f"RMSE: {rmse:.5f}")

    # ------------------------------------------------------------------
    # Frame precomputation across Single + 3 Multi-Center Modes
    # ------------------------------------------------------------------
    @staticmethod
    def _eval_epicycles(coeffs: np.ndarray, freqs: np.ndarray, t_vec: np.ndarray, anchor: complex, vis_cap: int):
        f_num = len(t_vec)
        k_use = len(coeffs)
        if k_use == 0:
            return np.full(f_num, anchor, dtype=complex), np.full((f_num, 1), anchor, dtype=complex)
        vectors = coeffs[None, :] * np.exp(1j * 2 * np.pi * t_vec[:, None] * freqs[None, :])
        tips = anchor + np.sum(vectors, axis=1)
        vis_k = min(k_use, vis_cap)
        if vis_k > 1:
            prefix = anchor + np.cumsum(vectors[:, : vis_k - 1], axis=1)
            centers = np.column_stack([np.full(f_num, anchor, dtype=complex), prefix])
        else:
            centers = np.full((f_num, 1), anchor, dtype=complex)
        return tips, centers

    def _precompute_frames(self):
        t_vec = np.linspace(0.0, 1.0, self.num_frames, endpoint=False)
        k = self.current_k

        self._frame_tips_list = []
        self._frame_centers_list = []
        self._frame_amps_list = []
        self._frame_seq_active_idx = []

        if len(self.center_points) <= 1:
            self._anim_mode = "single"
            anchor = self.center_points[0] if len(self.center_points) == 1 else 0j
            c_use = self.coeffs_arr[:k]
            f_use = self.freqs_arr[:k]
            a_use = self.amps_arr[:k]
            tips, centers = self._eval_epicycles(c_use, f_use, t_vec, anchor, MAX_VISIBLE_CIRCLES)
            self._frame_tips_list = [tips]
            self._frame_centers_list = [centers]
            self._frame_amps_list = [a_use[: min(len(a_use), MAX_VISIBLE_CIRCLES)]]

        else:
            method = self.center_method_var.get()
            order = self.order_var.get()
            m_count = len(self.center_models)

            if method == "partitioned":
                per_c = max(1, k // m_count)
                if order == "simultaneous":
                    self._anim_mode = "simultaneous"
                    for cm in self.center_models:
                        c_u = cm["c_part"][:per_c]
                        f_u = cm["f_part"][:per_c]
                        a_u = cm["a_part"][:per_c]
                        tips, centers = self._eval_epicycles(
                            c_u, f_u, t_vec, cm["anchor"], max(1, MAX_VISIBLE_CIRCLES // m_count)
                        )
                        self._frame_tips_list.append(tips)
                        self._frame_centers_list.append(centers)
                        self._frame_amps_list.append(a_u[: centers.shape[1]])
                else:
                    self._anim_mode = "sequential"
                    seg_len = max(1, self.num_frames // m_count)
                    seq_tips = np.zeros(self.num_frames, dtype=complex)
                    for idx, cm in enumerate(self.center_models):
                        start_i = idx * seg_len
                        end_i = self.num_frames if idx == m_count - 1 else min(self.num_frames, (idx + 1) * seg_len)
                        if start_i >= end_i:
                            continue
                        local_t = np.linspace(0.0, 1.0, end_i - start_i, endpoint=False)
                        tips, _ = self._eval_epicycles(
                            cm["c_part"][:per_c], cm["f_part"][:per_c], local_t, cm["anchor"], MAX_VISIBLE_CIRCLES
                        )
                        seq_tips[start_i:end_i] = tips
                        self._frame_seq_active_idx.extend([idx] * (end_i - start_i))
                    self._frame_seq_tips = seq_tips

            elif method == "weighted":
                self._anim_mode = "weighted"
                sigma = max(0.05, float(self.blend_sigma_var.get()))
                per_c = max(1, k // m_count)
                raw_tips = []
                raw_centers = []
                raw_amps = []
                for cm in self.center_models:
                    tips, centers = self._eval_epicycles(
                        cm["c_loc"][:per_c], cm["f_loc"][:per_c], t_vec, cm["anchor"], max(1, MAX_VISIBLE_CIRCLES // m_count)
                    )
                    raw_tips.append(tips)
                    raw_centers.append(centers)
                    raw_amps.append(cm["a_loc"][: centers.shape[1]])

                tips_stack = np.vstack(raw_tips)
                anchors_arr = np.array([cm["anchor"] for cm in self.center_models], dtype=complex)[:, None]
                d_sq = np.abs(tips_stack - anchors_arr) ** 2
                weights = np.exp(-d_sq / (2.0 * sigma * sigma)) + 1e-9
                weights /= np.sum(weights, axis=0, keepdims=True)

                blended_tip = np.sum(weights * tips_stack, axis=0)
                self._frame_tips_list = [blended_tip]
                self._frame_centers_list = raw_centers
                self._frame_amps_list = raw_amps
                self._frame_weights = weights

            else:
                split_by = self.budget_split_var.get()
                if split_by == "energy":
                    scores = np.array([cm["e_part"] for cm in self.center_models], dtype=float)
                else:
                    scores = np.array([float(cm["part_count"]) for cm in self.center_models], dtype=float)
                if np.sum(scores) <= 0:
                    scores = np.ones(m_count, dtype=float)
                allocs = np.maximum(1, np.floor(k * (scores / np.sum(scores))).astype(int))

                if order == "simultaneous":
                    self._anim_mode = "simultaneous"
                    for cm, k_sub in zip(self.center_models, allocs):
                        tips, centers = self._eval_epicycles(
                            cm["c_part"][:k_sub], cm["f_part"][:k_sub], t_vec, cm["anchor"], max(1, MAX_VISIBLE_CIRCLES // m_count)
                        )
                        self._frame_tips_list.append(tips)
                        self._frame_centers_list.append(centers)
                        self._frame_amps_list.append(cm["a_part"][: centers.shape[1]])
                else:
                    self._anim_mode = "sequential"
                    seg_len = max(1, self.num_frames // m_count)
                    seq_tips = np.zeros(self.num_frames, dtype=complex)
                    for idx, (cm, k_sub) in enumerate(zip(self.center_models, allocs)):
                        start_i = idx * seg_len
                        end_i = self.num_frames if idx == m_count - 1 else min(self.num_frames, (idx + 1) * seg_len)
                        if start_i >= end_i:
                            continue
                        local_t = np.linspace(0.0, 1.0, end_i - start_i, endpoint=False)
                        tips, _ = self._eval_epicycles(
                            cm["c_part"][:k_sub], cm["f_part"][:k_sub], local_t, cm["anchor"], MAX_VISIBLE_CIRCLES
                        )
                        seq_tips[start_i:end_i] = tips
                        self._frame_seq_active_idx.extend([idx] * (end_i - start_i))
                    self._frame_seq_tips = seq_tips

        self._start_timer_if_playing()

    def _render_frame(self, idx: int):
        idx = idx % self.num_frames

        for dl in self.drawn_lines:
            dl.set_data([], [])
        for rl in self.radius_lines:
            rl.set_data([], [])
            rl.set_visible(False)
        for td in self.tip_dots:
            td.set_data([], [])
        for patch in self.circles:
            patch.set_visible(False)

        show_c = self.show_circles_var.get()
        show_l = self.show_lines_var.get()
        circle_slot = 0

        if self._anim_mode == "single":
            tips = self._frame_tips_list[0][: idx + 1]
            self.drawn_lines[0].set_data(tips.real, tips.imag)
            curr_tip = self._frame_tips_list[0][idx]
            self.tip_dots[0].set_data([curr_tip.real], [curr_tip.imag])

            centers = self._frame_centers_list[0][idx]
            amps = self._frame_amps_list[0]
            if show_l:
                self.radius_lines[0].set_visible(True)
                self.radius_lines[0].set_data(list(centers.real) + [curr_tip.real], list(centers.imag) + [curr_tip.imag])
            if show_c:
                for i in range(len(centers)):
                    if circle_slot >= MAX_VISIBLE_CIRCLES:
                        break
                    p = self.circles[circle_slot]
                    p.set_visible(True)
                    p.center = (float(centers[i].real), float(centers[i].imag))
                    p.radius = float(amps[i])
                    circle_slot += 1

        elif self._anim_mode == "simultaneous":
            for m_i, tips_full in enumerate(self._frame_tips_list):
                dl = self.drawn_lines[m_i % len(self.drawn_lines)]
                td = self.tip_dots[m_i % len(self.tip_dots)]
                rl = self.radius_lines[m_i % len(self.radius_lines)]

                sub_tips = tips_full[: idx + 1]
                dl.set_data(sub_tips.real, sub_tips.imag)
                curr_tip = tips_full[idx]
                td.set_data([curr_tip.real], [curr_tip.imag])

                centers = self._frame_centers_list[m_i][idx]
                amps = self._frame_amps_list[m_i]
                if show_l:
                    rl.set_visible(True)
                    rl.set_data(list(centers.real) + [curr_tip.real], list(centers.imag) + [curr_tip.imag])
                if show_c:
                    for i in range(len(centers)):
                        if circle_slot >= MAX_VISIBLE_CIRCLES:
                            break
                        p = self.circles[circle_slot]
                        p.set_visible(True)
                        p.center = (float(centers[i].real), float(centers[i].imag))
                        p.radius = float(amps[i])
                        circle_slot += 1

        elif self._anim_mode == "sequential":
            sub_tips = self._frame_seq_tips[: idx + 1]
            self.drawn_lines[0].set_data(sub_tips.real, sub_tips.imag)
            curr_tip = self._frame_seq_tips[idx]
            self.tip_dots[0].set_data([curr_tip.real], [curr_tip.imag])

            active_m = self._frame_seq_active_idx[idx] if idx < len(self._frame_seq_active_idx) else 0
            cm = self.center_models[active_m]
            seg_denom = max(1, self.num_frames // len(self.center_models))
            t_local = np.array([(idx % seg_denom) / seg_denom])
            k_sub = max(1, self.current_k // len(self.center_models))
            _, centers_l = self._eval_epicycles(
                cm["c_part"][:k_sub], cm["f_part"][:k_sub], t_local, cm["anchor"], MAX_VISIBLE_CIRCLES
            )
            c_row = centers_l[0]
            a_row = cm["a_part"][: len(c_row)]
            if show_l:
                self.radius_lines[0].set_visible(True)
                self.radius_lines[0].set_data(list(c_row.real) + [curr_tip.real], list(c_row.imag) + [curr_tip.imag])
            if show_c:
                for i in range(len(c_row)):
                    if circle_slot >= MAX_VISIBLE_CIRCLES:
                        break
                    p = self.circles[circle_slot]
                    p.set_visible(True)
                    p.center = (float(c_row[i].real), float(c_row[i].imag))
                    p.radius = float(a_row[i])
                    circle_slot += 1

        elif self._anim_mode == "weighted":
            blended_sub = self._frame_tips_list[0][: idx + 1]
            self.drawn_lines[0].set_data(blended_sub.real, blended_sub.imag)
            curr_tip = self._frame_tips_list[0][idx]
            self.tip_dots[0].set_data([curr_tip.real], [curr_tip.imag])

            w_col = self._frame_weights[:, idx]
            if self.weighted_chain_var.get() == "dominant":
                dom_m = int(np.argmax(w_col))
                centers = self._frame_centers_list[dom_m][idx]
                amps = self._frame_amps_list[dom_m]
                if show_l:
                    self.radius_lines[0].set_visible(True)
                    self.radius_lines[0].set_data(list(centers.real) + [curr_tip.real], list(centers.imag) + [curr_tip.imag])
                if show_c:
                    for i in range(len(centers)):
                        if circle_slot >= MAX_VISIBLE_CIRCLES:
                            break
                        p = self.circles[circle_slot]
                        p.set_visible(True)
                        p.center = (float(centers[i].real), float(centers[i].imag))
                        p.radius = float(amps[i])
                        circle_slot += 1
            else:
                for m_i in range(len(self._frame_centers_list)):
                    centers = self._frame_centers_list[m_i][idx]
                    amps = self._frame_amps_list[m_i]
                    rl = self.radius_lines[m_i % len(self.radius_lines)]
                    if show_l:
                        rl.set_visible(True)
                        rl.set_data(list(centers.real) + [centers[-1].real], list(centers.imag) + [centers[-1].imag])
                    if show_c:
                        for i in range(len(centers)):
                            if circle_slot >= MAX_VISIBLE_CIRCLES:
                                break
                            p = self.circles[circle_slot]
                            p.set_visible(True)
                            p.center = (float(centers[i].real), float(centers[i].imag))
                            p.radius = float(amps[i])
                            circle_slot += 1

        self.canvas.draw_idle()

    def _tick(self):
        self._after_id = None
        if not self.is_playing:
            return

        self._render_frame(self.frame_idx)

        if self.frame_idx == self.num_frames - 1 and self.stop_on_complete_var.get():
            self.is_playing = False
            self._stop_timer()
            self.play_btn.config(text="Play")
            return

        self.frame_idx = (self.frame_idx + 1) % self.num_frames
        self._after_id = self.root.after(20, self._tick)

    def _start_timer_if_playing(self):
        self._stop_timer()
        if self.is_playing:
            self._after_id = self.root.after(20, self._tick)

    def _stop_timer(self):
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
            self._after_id = None

    def toggle_play(self):
        if self.is_playing:
            self.is_playing = False
            self._stop_timer()
            self.play_btn.config(text="Play")
        else:
            if self.frame_idx >= self.num_frames - 1:
                self.frame_idx = 0
            self.is_playing = True
            self.play_btn.config(text="Pause")
            self._start_timer_if_playing()

    def stop_drawing(self):
        self.is_playing = False
        self._stop_timer()
        self.play_btn.config(text="Play")
        self.frame_idx = 0
        self._render_frame(0)

    def restart_animation(self):
        self.frame_idx = 0
        self._render_frame(0)
        self.is_playing = True
        self.play_btn.config(text="Pause")
        self._start_timer_if_playing()


class UnifiedFourierStudioApp:
    """Unified application combining 2D Sketch Pad, Image Upload, and Fourier Epicycle Drawing."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("2D Fourier Epicycle Drawing Studio")
        self.root.geometry("1420x920")
        self.root.minsize(1160, 760)
        self.root.configure(bg=BG_APP)
        self._tooltips: list[HoverTooltip] = []

        self._configure_styles()
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _attach_tip(self, widget: tk.Widget, text: str):
        self._tooltips.append(HoverTooltip(widget, text))

    def _configure_styles(self):
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure("App.TFrame", background=BG_APP)
        style.configure("TopBar.TFrame", background=BG_CHROME)
        style.configure("Sidebar.TFrame", background=BG_CHROME)
        style.configure("Card.TFrame", background=BG_CARD)
        style.configure("Dark.TSeparator", background=BORDER_SUBTLE)

        style.configure(
            "SideGroup.TLabelframe",
            background=BG_CARD,
            bordercolor=BORDER_SUBTLE,
            relief="solid",
            borderwidth=1,
            padding=(8, 6),
        )
        style.configure(
            "SideGroup.TLabelframe.Label",
            background=BG_CARD,
            foreground=TEXT_PRIMARY,
            font=("TkDefaultFont", 9, "bold"),
        )

        style.configure("TLabel", background=BG_CHROME, foreground=TEXT_PRIMARY, font=("TkDefaultFont", 9))
        style.configure("Card.TLabel", background=BG_CARD, foreground=TEXT_PRIMARY, font=("TkDefaultFont", 9))
        style.configure("Muted.TLabel", background=BG_CARD, foreground=TEXT_MUTED, font=("TkDefaultFont", 8))
        style.configure(
            "StatValue.TLabel", background=BG_CARD, foreground=TEXT_PRIMARY, font=("TkDefaultFont", 9, "bold")
        )

        style.configure("TCheckbutton", background=BG_CARD, foreground=TEXT_PRIMARY, font=("TkDefaultFont", 9))
        style.map("TCheckbutton", background=[("active", BG_CARD)], foreground=[("active", TEXT_PRIMARY)])

        style.configure("TopCheck.TCheckbutton", background=BG_CHROME, foreground=TEXT_PRIMARY, font=("TkDefaultFont", 9))
        style.map("TopCheck.TCheckbutton", background=[("active", BG_CHROME)], foreground=[("active", TEXT_PRIMARY)])

        style.configure("TRadiobutton", background=BG_CARD, foreground=TEXT_PRIMARY, font=("TkDefaultFont", 8))
        style.map("TRadiobutton", background=[("active", BG_CARD)], foreground=[("active", "#FFFFFF")])

        style.configure(
            "TButton",
            background=BG_INPUT,
            foreground=TEXT_PRIMARY,
            bordercolor=BORDER_SUBTLE,
            lightcolor=BG_INPUT,
            darkcolor=BG_INPUT,
            padding=(7, 3),
            font=("TkDefaultFont", 8),
        )
        style.map(
            "TButton",
            background=[("active", "#33415C"), ("pressed", "#1E2636")],
            foreground=[("active", "#FFFFFF")],
        )

        style.configure(
            "Accent.TButton",
            background="#2563EB",
            foreground="#FFFFFF",
            bordercolor="#3B82F6",
            lightcolor="#2563EB",
            darkcolor="#1D4ED8",
            padding=(8, 3),
            font=("TkDefaultFont", 8, "bold"),
        )
        style.map(
            "Accent.TButton",
            background=[("active", "#3B82F6"), ("pressed", "#1D4ED8")],
            foreground=[("active", "#FFFFFF")],
        )

        style.configure(
            "TSpinbox",
            fieldbackground=BG_INPUT,
            background=BG_INPUT,
            foreground=TEXT_PRIMARY,
            arrowcolor=TEXT_PRIMARY,
            bordercolor=BORDER_SUBTLE,
            insertcolor=TEXT_PRIMARY,
        )

        style.configure(
            "TopBar.Horizontal.TScale",
            background=BG_CHROME,
            troughcolor=BG_INPUT,
            bordercolor=BORDER_SUBTLE,
            lightcolor=ACCENT_BLUE,
            darkcolor=ACCENT_BLUE,
        )
        style.configure(
            "Card.Horizontal.TScale",
            background=BG_CARD,
            troughcolor=BG_INPUT,
            bordercolor=BORDER_SUBTLE,
            lightcolor=ACCENT_BLUE,
            darkcolor=ACCENT_BLUE,
        )

        style.configure("Dark.TNotebook", background=BG_APP, borderwidth=0)
        style.configure(
            "Dark.TNotebook.Tab",
            background=BG_CHROME,
            foreground=TEXT_MUTED,
            padding=(14, 6),
            font=("TkDefaultFont", 9, "bold"),
        )
        style.map(
            "Dark.TNotebook.Tab",
            background=[("selected", BG_CARD), ("active", "#232B3B")],
            foreground=[("selected", "#FFFFFF"), ("active", TEXT_PRIMARY)],
        )

    def _build_ui(self):
        # Copyright Footer with clickable GitHub hyperlink
        footer = tk.Frame(
            self.root,
            bg="#0E121A",
            highlightbackground=BORDER_SUBTLE,
            highlightthickness=1,
            padx=12,
            pady=5,
        )
        footer.pack(side=tk.BOTTOM, fill=tk.X)

        footer_inner = tk.Frame(footer, bg="#0E121A")
        footer_inner.pack(anchor=tk.CENTER)

        tk.Label(
            footer_inner,
            text="© Made by Md Masrur Masuk Shopnil  |  ",
            bg="#0E121A",
            fg=TEXT_MUTED,
            font=("TkDefaultFont", 9),
        ).pack(side=tk.LEFT)

        link_lbl = tk.Label(
            footer_inner,
            text=GITHUB_URL,
            bg="#0E121A",
            fg="#60A5FA",
            font=("TkDefaultFont", 9, "underline"),
            cursor="hand2",
        )
        link_lbl.pack(side=tk.LEFT)
        link_lbl.bind("<Button-1>", lambda _e: webbrowser.open_new_tab(GITHUB_URL))
        link_lbl.bind("<Enter>", lambda _e: link_lbl.config(fg="#93C5FD"))
        link_lbl.bind("<Leave>", lambda _e: link_lbl.config(fg="#60A5FA"))
        self._attach_tip(link_lbl, f"Click to open {GITHUB_URL} in your browser.")

        # Main Mode Tabs: Fourier Epicycle Drawing vs Draw 2D Figure
        self.notebook = ttk.Notebook(self.root, style="Dark.TNotebook")
        self.notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self._attach_tip(
            self.notebook,
            "Switch between 'Fourier Epicycle Drawing' (animate uploaded, drawn, or preset shapes) and 'Draw 2D Figure' (sketch pad).",
        )

        self.draw_panel = DrawingPadPanel(self.notebook, on_send_to_fourier=self._handle_drawn_figure)
        self.fourier_panel = FourierAnalyzerPanel(
            self.notebook, root=self.root, on_switch_to_draw=self._switch_to_draw_tab
        )

        self.notebook.add(self.fourier_panel, text="  Fourier Epicycle Drawing  ")
        self.notebook.add(self.draw_panel, text="  Draw 2D Figure  ")

        # Keyboard shortcuts routed to active tab
        self.root.bind("<Control-z>", self._on_ctrl_z)
        self.root.bind("<Command-z>", self._on_ctrl_z)
        self.root.bind("<Control-s>", self._on_ctrl_s)
        self.root.bind("<Command-s>", self._on_ctrl_s)

    def _switch_to_draw_tab(self):
        self.notebook.select(self.draw_panel)

    def _handle_drawn_figure(self, pil_img: Image.Image):
        if self.fourier_panel.load_pil_image(pil_img):
            self.notebook.select(self.fourier_panel)

    def _on_ctrl_z(self, _event=None):
        if self.notebook.select() == str(self.draw_panel):
            self.draw_panel.undo()

    def _on_ctrl_s(self, _event=None):
        if self.notebook.select() == str(self.draw_panel):
            self.draw_panel.save_as_png()
        else:
            self.fourier_panel.save_output_png()

    def _on_close(self):
        self.fourier_panel.cleanup()
        self.root.destroy()


def main():
    root = tk.Tk()
    UnifiedFourierStudioApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()