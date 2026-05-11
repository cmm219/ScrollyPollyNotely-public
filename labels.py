"""
Scrolly Polly Notely — floating notes with text and image support.
Usage: python labels.py
"""

import tkinter as tk
from tkinter import colorchooser, simpledialog
import tkinter.font as tkfont
import json
import os
import socket
import threading
import uuid

try:
    from PIL import ImageGrab, ImageTk
except ImportError:
    ImageGrab = None
    ImageTk = None

APP_NAME = "ScrollyPollyNotely"


def _get_data_dir():
    override = os.environ.get("SCROLLY_POLLY_NOTELY_DATA_DIR")
    if override:
        return os.path.abspath(os.path.expanduser(override))

    if os.name == "nt":
        base_dir = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base_dir, APP_NAME)

    base_dir = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base_dir, APP_NAME)


DATA_DIR = _get_data_dir()
IMAGE_DIR = os.path.join(DATA_DIR, "pasted-images")

def _ensure_image_dir():
    os.makedirs(IMAGE_DIR, exist_ok=True)


def _embed_images_into_widget(widget, images, photo_refs_out):
    """Embed image dicts into a tk.Text widget. Appends PhotoImage refs to photo_refs_out.
    Images on the same line are inserted in column order with per-line offset accounting.
    widget must already contain the plain text content before this is called.
    """
    try:
        from PIL import ImageTk
    except ImportError:
        return

    per_line_count = {}
    for img_dict in images:
        path = img_dict.get("path", "")
        if not os.path.exists(path):
            import sys
            print(f"[ScrollyPollyNotely] image not found, skipping: {path}", file=sys.stderr)
            continue
        try:
            photo = ImageTk.PhotoImage(file=path)
        except Exception as e:
            import sys
            print(f"[ScrollyPollyNotely] failed to load image {path}: {e}", file=sys.stderr)
            continue

        plain_pos = img_dict.get("position", "end")
        if plain_pos == "end" or plain_pos is None:
            insert_idx = "end"
        else:
            try:
                line, col = plain_pos.split(".")
                count = per_line_count.get(line, 0)
                insert_idx = f"{line}.{int(col) + count}"
                per_line_count[line] = count + 1
            except (ValueError, AttributeError):
                insert_idx = "end"

        photo_refs_out.append(photo)

        if hasattr(widget, '_sticky_label_ref'):
            sl = widget._sticky_label_ref
            frame = sl._make_image_frame(photo, img_dict)
            widget.window_create(insert_idx, window=frame)
        else:
            widget.image_create(insert_idx, image=photo)


def _extract_image_records(widget):
    """Walk a tk.Text widget dump and return (text_segments, image_records).
    image_records: list of {"tcl_name": str, "plain_pos": "line.col"} in dump order.
    plain_pos uses plain-text coordinate space (images count as 0 width).
    """
    text_segments = []
    image_records = []
    img_count_per_line = {}

    for item_type, value, index in widget.dump("1.0", "end", all=True):
        if item_type == "text":
            text_segments.append(value)
        elif item_type == "image":
            line, col = index.split(".")
            preceding = img_count_per_line.get(line, 0)
            plain_col = int(col) - preceding
            img_count_per_line[line] = preceding + 1
            image_records.append({
                "tcl_name": value,
                "plain_pos": f"{line}.{plain_col}",
            })
        elif item_type == "window":
            line, col = index.split(".")
            preceding = img_count_per_line.get(line, 0)
            plain_col = int(col) - preceding
            img_count_per_line[line] = preceding + 1
            image_records.append({
                "tcl_name": value,
                "plain_pos": f"{line}.{plain_col}",
                "is_window": True,
            })

    return text_segments, image_records


class ReadOnlyText(tk.Text):
    """Text widget that allows scrolling and selection but blocks editing."""
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._readonly = True

    def insert(self, *args, **kwargs):
        if self._readonly:
            return
        super().insert(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self._readonly:
            return
        super().delete(*args, **kwargs)

    def set_readonly(self, value=True):
        self._readonly = value

    def set_text(self, text):
        self.set_readonly(False)
        super().delete("1.0", "end")
        super().insert("1.0", text)
        self.set_readonly(True)

CONFIG_PATH = os.path.join(DATA_DIR, "notes-and-settings.json")

DEFAULT_BG = "#1e1e2e"
DEFAULT_FG = "#cdd6f4"
LIGHT_BG = "#ffffff"
LIGHT_FG = "#000000"
DARK_BG = "#000000"
DARK_FG = "#ffffff"
DEFAULT_FONT_FAMILY = "Consolas"
DEFAULT_FONT_SIZE = 11
LABEL_PADX = 12
LABEL_PADY = 4
TRANSPARENT_KEY = "#010101"
MAX_W = 400
MAX_H = 300


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    return {
        "default_bg": DEFAULT_BG,
        "default_fg": DEFAULT_FG,
        "font_family": DEFAULT_FONT_FAMILY,
        "font_size": DEFAULT_FONT_SIZE,
        "default_transparent": False,
        "last_session": [],
        "presets": {},
    }


def save_config(cfg):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def _show_font_family_picker(parent, anchor, title, bg, fg, current_family, font_size, apply_callback, sample_text):
    popup = tk.Toplevel(parent)
    popup.title(title)
    popup.attributes("-topmost", True)
    popup.geometry(f"340x410+{anchor.winfo_x()}+{anchor.winfo_y() + anchor.winfo_height() + 5}")

    frame = tk.Frame(popup, bg=bg, padx=10, pady=10)
    frame.pack(fill="both", expand=True)

    tk.Label(frame, text=title, bg=bg, fg=fg,
             font=(DEFAULT_FONT_FAMILY, 10, "bold")).pack(anchor="w")

    search_var = tk.StringVar()
    search = tk.Entry(frame, textvariable=search_var, bg="#ffffff", fg="#000000",
                      insertbackground="#000000", relief="flat")
    search.pack(fill="x", pady=(6, 8))

    list_frame = tk.Frame(frame, bg=bg)
    list_frame.pack(fill="both", expand=True)
    scrollbar = tk.Scrollbar(list_frame)
    scrollbar.pack(side="right", fill="y")
    fonts = tk.Listbox(
        list_frame,
        activestyle="none",
        exportselection=False,
        yscrollcommand=scrollbar.set,
        bg="#ffffff",
        fg="#000000",
        selectbackground="#2d5f9a",
        selectforeground="#ffffff",
        relief="flat",
        height=12,
    )
    fonts.pack(side="left", fill="both", expand=True)
    scrollbar.config(command=fonts.yview)

    sample = tk.Label(frame, text=sample_text, bg=bg, fg=fg,
                      font=(current_family, max(font_size, 12), "bold"))
    sample.pack(fill="x", pady=(8, 6))

    all_families = sorted(set(tkfont.families(parent)), key=str.lower)
    if current_family not in all_families:
        all_families.insert(0, current_family)

    def refresh(*_):
        query = search_var.get().strip().lower()
        fonts.delete(0, "end")
        for family in all_families:
            if not query or query in family.lower():
                fonts.insert("end", family)
        matches = fonts.get(0, "end")
        if current_family in matches:
            idx = matches.index(current_family)
            fonts.selection_set(idx)
            fonts.see(idx)
        elif matches:
            fonts.selection_set(0)

    def selected_family():
        selection = fonts.curselection()
        if not selection:
            return None
        return fonts.get(selection[0])

    def preview(*_):
        family = selected_family()
        if family:
            sample.config(font=(family, max(font_size, 12), "bold"))

    def apply_and_close(event=None):
        family = selected_family()
        if family:
            apply_callback(family)
        popup.destroy()
        return "break"

    def cancel(event=None):
        popup.destroy()
        return "break"

    button_row = tk.Frame(frame, bg=bg)
    button_row.pack(fill="x")
    tk.Button(button_row, text="OK", command=apply_and_close).pack(side="right")
    tk.Button(button_row, text="Cancel", command=cancel).pack(side="right", padx=(0, 6))

    search_var.trace_add("write", refresh)
    fonts.bind("<<ListboxSelect>>", preview)
    fonts.bind("<Double-Button-1>", apply_and_close)
    popup.bind("<Return>", apply_and_close)
    popup.bind("<Escape>", cancel)
    refresh()
    preview()
    search.focus_set()


class StickyLabel:
    def __init__(self, manager, text="Label", x=100, y=100, bg=None, fg=None,
                 transparent=None, font_size=None, width=None, height=None,
                 clickthrough=False, ontop=True, images=None, opacity=None,
                 font_family=None):
        self.manager = manager
        cfg = manager.config

        self.bg = bg or cfg["default_bg"]
        self.fg = fg or cfg["default_fg"]
        self.font_family = font_family or cfg.get("font_family", DEFAULT_FONT_FAMILY)
        self.font_size = font_size or cfg.get("font_size", DEFAULT_FONT_SIZE)
        self.transparent = transparent if transparent is not None else cfg.get("default_transparent", False)
        self.clickthrough = clickthrough
        self.ontop = ontop
        self.opacity = opacity if opacity is not None else 100

        self.win = tk.Toplevel(manager.root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", self.ontop)
        self.win.attributes("-alpha", self.opacity / 100)
        geo = f"+{x}+{y}"
        if width and height:
            geo = f"{width}x{height}+{x}+{y}"
        self.win.geometry(geo)

        self.frame = tk.Frame(self.win, bg=self.bg, cursor="fleur")
        self.frame.pack(fill="both", expand=True)

        self.label = ReadOnlyText(
            self.frame,
            font=self._font_tuple(),
            bg=self.bg,
            fg=self.fg,
            padx=LABEL_PADX,
            pady=LABEL_PADY,
            cursor="fleur",
            wrap="word",
            relief="flat",
            width=1,
            height=1,
        )
        self._drag_x = 0
        self._drag_y = 0
        self._resize_start_x = 0
        self._resize_start_y = 0
        self._resize_start_w = 0
        self._resize_start_h = 0
        self._entry = None
        self._photo_refs = []
        self._entry_photo_refs = []
        self._images = []
        self._image_name_map = {}
        self._image_frames = []
        self._img_rs_x = 0
        self._img_rs_w = 0
        self._img_rs_h = 0

        self.label.set_text(text)
        self.label._sticky_label_ref = self
        self.label.pack(fill="both", expand=True)

        if images:
            _embed_images_into_widget(self.label, images, self._photo_refs)
            self._images = [dict(d) for d in images if os.path.exists(d.get("path", ""))]

        self._apply_checklist_tags()

        # Auto-size window to content (up to MAX_W x MAX_H)
        self.win.update_idletasks()
        if not (width and height):
            lines = int(self.label.index("end-1c").split(".")[0])
            new_w = 250
            new_h = min((lines * 20) + 8, MAX_H)
            self.win.geometry(f"{new_w}x{new_h}+{x}+{y}")

        self.grip = tk.Label(
            self.frame,
            text="",
            bg=self.bg,
            fg=self.bg,
            width=2,
            height=1,
            cursor="size_nw_se",
        )
        self.grip.place(relx=1.0, rely=1.0, anchor="se")

        if self.transparent:
            self._apply_transparent(True)

        if self.clickthrough:
            self._apply_clickthrough(True)

        self.label.bind("<Button-1>", self._on_checklist_click)
        self.label.bind("<B1-Motion>", self._on_drag)
        self.label.bind("<MouseWheel>", self._on_mousewheel)
        self.label.bind("<Enter>", lambda e: self.label.focus_set())
        self.frame.bind("<Button-1>", self._start_drag)
        self.frame.bind("<B1-Motion>", self._on_drag)
        self.label.bind("<Double-Button-1>", self._start_edit)
        self.label.bind("<Control-Delete>", lambda e: self._close())
        self.frame.bind("<Control-Delete>", lambda e: self._close())
        self.label.bind("<Button-3>", self._show_menu)
        self.frame.bind("<Button-3>", self._show_menu)
        self.grip.bind("<Button-1>", self._start_resize)
        self.grip.bind("<B1-Motion>", self._on_resize)
        self.win.bind("<Configure>", self._on_window_resize)

    def _font_tuple(self, size=None, family=None):
        return (family or self.font_family, size or self.font_size, "bold")

    def _make_image_frame(self, photo, img_dict):
        frame = tk.Frame(self.label, bg=self.bg, cursor="arrow")
        img_label = tk.Label(frame, image=photo, bg=self.bg, cursor="arrow")
        img_label.pack()

        grip = tk.Label(frame, text="", bg=self.bg, fg=self.bg,
                        width=1, height=1, cursor="size_nw_se")
        grip.place(relx=1.0, rely=1.0, anchor="se")

        frame._photo = photo
        frame._img_dict = img_dict
        frame._img_label = img_label

        grip.bind("<Button-1>", lambda e: self._img_grip_start(e, frame))
        grip.bind("<B1-Motion>", lambda e: self._img_grip_drag(e, frame))
        grip.bind("<ButtonRelease-1>", lambda e: self._img_grip_end(e, frame))
        img_label.bind("<Button-3>", self._show_menu)

        self._image_frames.append(frame)
        return frame

    def _img_grip_start(self, event, frame):
        self._img_rs_x = event.x_root
        self._img_rs_w = frame._img_dict["width"]
        self._img_rs_h = frame._img_dict["height"]

    def _img_grip_drag(self, event, frame):
        if ImageTk is None:
            return
        try:
            from PIL import Image as PilImage
        except ImportError:
            return
        dx = event.x_root - self._img_rs_x
        new_w = max(20, self._img_rs_w + dx)
        ratio = new_w / self._img_rs_w
        new_h = max(10, int(self._img_rs_h * ratio))
        try:
            orig = PilImage.open(frame._img_dict["original_path"])
            resized = orig.resize((new_w, new_h))
            photo = ImageTk.PhotoImage(resized)
            frame._img_label.config(image=photo)
            frame._photo = photo
            frame._pending_w = new_w
            frame._pending_h = new_h
        except Exception:
            pass

    def _img_grip_end(self, event, frame):
        if not hasattr(frame, '_pending_w'):
            return
        new_w = frame._pending_w
        new_h = frame._pending_h
        img_dict = frame._img_dict

        orig_filename = os.path.basename(img_dict["original_path"])
        uid = orig_filename.replace("img_", "").replace(".png", "")
        new_path = os.path.join(IMAGE_DIR, f"img_{uid}_{new_w}x{new_h}.png")
        try:
            from PIL import Image as PilImage
            orig = PilImage.open(img_dict["original_path"])
            resized = orig.resize((new_w, new_h))
            resized.save(new_path)
        except Exception:
            return

        img_dict["path"] = new_path
        img_dict["width"] = new_w
        img_dict["height"] = new_h

        for i, ref in enumerate(self._photo_refs):
            if ref is getattr(frame, '_orig_photo', None):
                self._photo_refs[i] = frame._photo
                break

        if hasattr(frame, '_pending_w'):
            del frame._pending_w
        if hasattr(frame, '_pending_h'):
            del frame._pending_h

    def _on_window_resize(self, event):
        """Reflow text to match window width."""
        if self._entry:
            return
        pixel_w = self.win.winfo_width()
        font = self.label.cget("font")
        char_w = self.label.tk.call("font", "measure", font, "0")
        if char_w > 0:
            chars = max(10, (pixel_w - 2 * LABEL_PADX) // char_w)
            self.label.config(width=chars)

    def _apply_checklist_tags(self):
        """Scan text for checklist patterns and apply visual tags."""
        self.label.tag_remove("checked", "1.0", "end")
        self.label.tag_remove("unchecked", "1.0", "end")
        self.label.tag_config("checked", overstrike=True, foreground="#666666")

        content = self.label.get("1.0", "end-1c")
        for i, line in enumerate(content.split("\n"), start=1):
            if line.startswith("- [x] "):
                start = f"{i}.0"
                end = f"{i}.end"
                self.label.tag_add("checked", start, end)
            elif line.startswith("- [ ] "):
                start = f"{i}.0"
                end = f"{i}.end"
                self.label.tag_add("unchecked", start, end)

    def _toggle_checklist_item(self, index):
        """Toggle a checklist item at the given line index."""
        line_num = index.split(".")[0]
        line_start = f"{line_num}.0"
        line_end = f"{line_num}.end"
        line_text = self.label.get(line_start, line_end)

        if line_text.startswith("- [ ] "):
            new_line = "- [x] " + line_text[6:]
        elif line_text.startswith("- [x] "):
            new_line = "- [ ] " + line_text[6:]
        else:
            return False

        full_text = self.label.get("1.0", "end-1c")
        lines = full_text.split("\n")
        line_idx = int(line_num) - 1
        if line_idx < len(lines):
            lines[line_idx] = new_line

        # Sort: non-checklist first, then unchecked, then checked
        other = [l for l in lines if not l.startswith("- [ ]") and not l.startswith("- [x]")]
        unchecked = [l for l in lines if l.startswith("- [ ]")]
        checked = [l for l in lines if l.startswith("- [x]")]
        sorted_lines = other + unchecked + checked

        self.label.set_text("\n".join(sorted_lines))
        self._apply_checklist_tags()

        # Re-embed images if any (set_text wipes them)
        if self._images:
            for f in self._image_frames:
                f.destroy()
            self._image_frames = []
            new_refs = []
            _embed_images_into_widget(self.label, self._images, new_refs)
            self._photo_refs = new_refs

        return True

    def _on_checklist_click(self, event):
        """Handle click on checklist items. Falls through to drag if not a checklist line."""
        self.win.lift()
        idx = self.label.index(f"@{event.x},{event.y}")
        line_num = idx.split(".")[0]
        line_start = f"{line_num}.0"
        line_text = self.label.get(line_start, f"{line_num}.end")

        if line_text.startswith("- [ ] ") or line_text.startswith("- [x] "):
            self._toggle_checklist_item(idx)
            return "break"

        self._start_drag(event)
        return "break"

    def snapshot(self):
        self.win.update_idletasks()
        return {
            "text": self.label.get("1.0", "end-1c"),
            "x": self.win.winfo_x(),
            "y": self.win.winfo_y(),
            "width": self.win.winfo_width(),
            "height": self.win.winfo_height(),
            "bg": self.bg,
            "fg": self.fg,
            "font_family": self.font_family,
            "font_size": self.font_size,
            "transparent": self.transparent,
            "clickthrough": self.clickthrough,
            "ontop": self.ontop,
            "images": list(self._images),
            "opacity": self.opacity,
        }

    def _apply_transparent(self, on):
        if on:
            self.win.config(bg=TRANSPARENT_KEY)
            self.frame.config(bg=TRANSPARENT_KEY)
            self.label.config(bg=TRANSPARENT_KEY)
            self.grip.config(bg=TRANSPARENT_KEY, fg=TRANSPARENT_KEY)
            self.win.attributes("-transparentcolor", TRANSPARENT_KEY)
        else:
            self.win.config(bg=self.bg)
            self.frame.config(bg=self.bg)
            self.label.config(bg=self.bg)
            self.grip.config(bg=self.bg, fg=self.bg)
            self.win.attributes("-transparentcolor", "")
            self.win.attributes("-alpha", self.opacity / 100)

    def _apply_clickthrough(self, on):
        if on:
            self.label.bind("<Button-1>", self._passthrough_click)
            self.label.bind("<B1-Motion>", lambda e: None)
            self.frame.bind("<Button-1>", self._passthrough_click)
            self.frame.bind("<B1-Motion>", lambda e: None)
        else:
            self.label.bind("<Button-1>", self._on_checklist_click)
            self.label.bind("<B1-Motion>", self._on_drag)
            self.frame.bind("<Button-1>", self._start_drag)
            self.frame.bind("<B1-Motion>", self._on_drag)

    def _passthrough_click(self, event):
        import ctypes
        self.win.withdraw()
        self.win.update_idletasks()
        ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)  # LEFTDOWN
        ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)  # LEFTUP
        self.win.after(80, self.win.deiconify)

    def _toggle_transparent(self):
        self.transparent = not self.transparent
        self._apply_transparent(self.transparent)

    def _apply_image_frame_bg(self):
        for frame in self._image_frames:
            if not frame.winfo_exists():
                continue
            frame.config(bg=self.bg)
            if hasattr(frame, "_img_label") and frame._img_label.winfo_exists():
                frame._img_label.config(bg=self.bg)
            for child in frame.winfo_children():
                if child is not getattr(frame, "_img_label", None):
                    child.config(bg=self.bg, fg=self.bg)

    def _apply_theme(self, bg, fg):
        self.bg = bg
        self.fg = fg
        self.transparent = False
        self.win.attributes("-transparentcolor", "")
        self.win.config(bg=self.bg)
        self.frame.config(bg=self.bg)
        self.label.config(bg=self.bg, fg=self.fg)
        self.grip.config(bg=self.bg, fg=self.bg)
        self._apply_image_frame_bg()
        self.win.attributes("-alpha", self.opacity / 100)

    def _apply_light_mode(self):
        self._apply_theme(LIGHT_BG, LIGHT_FG)

    def _apply_dark_mode(self):
        self._apply_theme(DARK_BG, DARK_FG)

    def _toggle_clickthrough(self):
        self.clickthrough = not self.clickthrough
        self._apply_clickthrough(self.clickthrough)

    def _toggle_ontop(self):
        self.ontop = not self.ontop
        self.win.attributes("-topmost", self.ontop)

    def _start_resize(self, event):
        self.win.update_idletasks()
        self._resize_start_x = event.x_root
        self._resize_start_y = event.y_root
        self._resize_start_w = self.win.winfo_width()
        self._resize_start_h = self.win.winfo_height()

    def _on_resize(self, event):
        dx = event.x_root - self._resize_start_x
        dy = event.y_root - self._resize_start_y
        new_w = max(60, self._resize_start_w + dx)
        new_h = max(24, self._resize_start_h + dy)
        self.win.geometry(f"{new_w}x{new_h}")

    def _start_drag(self, event):
        self.win.lift()
        self._drag_x = event.x_root - self.win.winfo_x()
        self._drag_y = event.y_root - self.win.winfo_y()
        return "break"

    def _on_drag(self, event):
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self.win.geometry(f"+{x}+{y}")
        return "break"

    def _on_mousewheel(self, event):
        self.label.yview_scroll(int(-1*(event.delta/120)), "units")
        return "break"

    def _start_edit(self, event):
        if self._entry:
            return "break"

        # Rebuild image name map from current label state
        self._image_name_map = {}
        photo_by_name = {str(p): p for p in self._photo_refs}
        for img_frame in self._image_frames:
            photo_by_name[str(img_frame._photo)] = img_frame._photo

        for item_type, value, index in self.label.dump("1.0", "end", all=True):
            if item_type == "image" and value in photo_by_name:
                for img_dict in self._images:
                    if self._image_name_map.get(value) is None:
                        self._image_name_map[value] = img_dict
                        break
            elif item_type == "window":
                for img_frame in self._image_frames:
                    if str(img_frame) == value:
                        tcl_name = str(img_frame._photo)
                        for img_dict in self._images:
                            if self._image_name_map.get(tcl_name) is None:
                                self._image_name_map[tcl_name] = img_dict
                                break
                        break

        self.label.pack_forget()
        self._entry = tk.Text(
            self.frame,
            font=self._font_tuple(),
            bg=self.bg,
            fg=self.fg,
            insertbackground=self.fg,
            relief="flat",
            height=1,
            width=20,
            wrap="word",
            undo=False,
        )

        # Reconstruct entry content from label dump to preserve image positions
        self._entry_photo_refs = []
        for item_type, value, index in self.label.dump("1.0", "end", all=True):
            if item_type == "text":
                self._entry.insert("end", value)
            elif item_type == "image":
                photo = photo_by_name.get(value)
                if photo:
                    self._entry_photo_refs.append(photo)
                    self._entry.image_create("end", image=photo)
            elif item_type == "window":
                for img_frame in self._image_frames:
                    if str(img_frame) == value:
                        photo = img_frame._photo
                        if photo:
                            self._entry_photo_refs.append(photo)
                            self._entry.image_create("end", image=photo)
                        break

        self._entry.pack(padx=LABEL_PADX, pady=LABEL_PADY, fill="both", expand=True)
        self._entry.focus_set()
        self._entry.tag_add("sel", "1.0", "end")
        self._entry.bind("<Return>", self._finish_edit)
        self._entry.bind("<Shift-Return>", self._soft_newline)
        self._entry.bind("<Escape>", self._cancel_edit)
        self._entry.bind("<FocusOut>", self._finish_edit)
        self._entry.bind("<KeyRelease>", self._resize_entry)
        self._entry.bind("<Control-v>", self._paste_image)
        return "break"

    def _finish_edit(self, event=None):
        if not self._entry:
            if event:
                return "break"
            return

        # Step 1: Extract content from entry widget
        text_segments, image_records = _extract_image_records(self._entry)
        plain_text = "".join(text_segments).strip()

        # Step 2: Build new PhotoImage objects for self.label
        new_photo_refs = []
        new_images = []

        if ImageTk is not None:
            for rec in image_records:
                img_dict = self._image_name_map.get(rec["tcl_name"])
                if img_dict is None:
                    continue
                path = img_dict.get("path", "")
                if not os.path.exists(path):
                    continue
                try:
                    photo = ImageTk.PhotoImage(file=path)
                except Exception:
                    continue
                new_photo_refs.append(photo)
                new_images.append({
                    "path": img_dict["path"],
                    "original_path": img_dict["original_path"],
                    "width": img_dict["width"],
                    "height": img_dict["height"],
                    "position": rec["plain_pos"],
                })

        # Step 3: Commit to self.label
        if plain_text:
            self.label.set_text(plain_text)

        # Clear old image frames
        for f in self._image_frames:
            f.destroy()
        self._image_frames = []

        # Re-embed images as window frames
        per_line_count = {}
        for img_dict, photo in zip(new_images, new_photo_refs):
            plain_pos = img_dict["position"]
            try:
                line, col = plain_pos.split(".")
                count = per_line_count.get(line, 0)
                insert_idx = f"{line}.{int(col) + count}"
                per_line_count[line] = count + 1
            except (ValueError, AttributeError):
                insert_idx = "end"
            frame = self._make_image_frame(photo, img_dict)
            self.label.window_create(insert_idx, window=frame)

        # Atomically replace refs
        self._photo_refs = new_photo_refs
        self._images = new_images

        # Step 4: Cleanup
        self._entry_photo_refs = []
        self._entry.destroy()
        self._entry = None

        self.label.pack(padx=0, pady=0, fill="both", expand=True)

        self._apply_checklist_tags()

        if event:
            return "break"

    def _cancel_edit(self, event=None):
        if self._entry:
            self._entry_photo_refs = []
            self._entry.destroy()
            self._entry = None
            self.label.pack(padx=0, pady=0, fill="both", expand=True)

    def _soft_newline(self, event):
        self._entry.insert("insert", "\n")
        return "break"

    def _resize_entry(self, event):
        if self._entry:
            self._entry.update_idletasks()
            lines = int(self._entry.index("end-1c").split(".")[0])
            self._entry.config(height=max(1, min(lines, 10)))

    def _paste_image(self, event):
        if ImageGrab is None:
            return None

        img = ImageGrab.grabclipboard()
        if img is None or not hasattr(img, "size"):
            return None

        _ensure_image_dir()
        uid = uuid.uuid4().hex[:12]
        original_path = os.path.join(IMAGE_DIR, f"img_{uid}.png")
        img.save(original_path)

        max_w = max(50, self.win.winfo_width() - 2 * LABEL_PADX)
        if img.width > max_w:
            ratio = max_w / img.width
            new_w = max_w
            new_h = max(1, int(img.height * ratio))
            display_img = img.resize((new_w, new_h))
        else:
            new_w, new_h = img.width, img.height
            display_img = img

        display_path = os.path.join(IMAGE_DIR, f"img_{uid}_{new_w}x{new_h}.png")
        display_img.save(display_path)

        photo = ImageTk.PhotoImage(display_img)
        tcl_name = str(photo)
        self._entry_photo_refs.append(photo)

        new_dict = {
            "path": display_path,
            "original_path": original_path,
            "width": new_w,
            "height": new_h,
            "position": None,
        }
        self._image_name_map[tcl_name] = new_dict
        self._entry.image_create("insert", image=photo)
        return "break"

    def _resize_image_by_entry(self, img_dict):
        if ImageTk is None:
            return
        try:
            from PIL import Image as PilImage
        except ImportError:
            return

        new_w = simpledialog.askinteger(
            "Resize Image", "New width (px):",
            initialvalue=img_dict["width"], minvalue=10, maxvalue=MAX_W
        )
        if new_w is None:
            return

        orig = PilImage.open(img_dict["original_path"])
        new_h = max(1, int(orig.height * new_w / orig.width))

        orig_filename = os.path.basename(img_dict["original_path"])
        uid = orig_filename.replace("img_", "").replace(".png", "")
        new_path = os.path.join(IMAGE_DIR, f"img_{uid}_{new_w}x{new_h}.png")
        resized = orig.resize((new_w, new_h))
        resized.save(new_path)

        new_photo = ImageTk.PhotoImage(resized)

        # Find and replace the embed in self.label
        for item_type, value, idx in self.label.dump("1.0", "end", image=True):
            for i, ref in enumerate(self._photo_refs):
                if str(ref) == value:
                    self.label.set_readonly(False)
                    self.label.delete(idx)
                    self.label.set_readonly(True)
                    self.label.image_create(idx, image=new_photo)
                    self._photo_refs[i] = new_photo
                    img_dict["path"] = new_path
                    img_dict["width"] = new_w
                    img_dict["height"] = new_h
                    return

    def _resize_image(self, ex, ey):
        idx = self.label.index(f"@{ex},{ey}")
        end_idx = self.label.index(f"{idx}+1c")
        dump = list(self.label.dump(idx, end_idx, image=True))
        if not dump:
            return
        tcl_name = dump[0][1]
        for i, photo in enumerate(self._photo_refs):
            if str(photo) == tcl_name and i < len(self._images):
                self._resize_image_by_entry(self._images[i])
                return
        if self._images:
            self._resize_image_by_entry(self._images[0])

    def _delete_image(self, idx):
        win_dump = list(self.label.dump(idx, self.label.index(f"{idx}+1c"), window=True))
        img_dump = list(self.label.dump(idx, self.label.index(f"{idx}+1c"), image=True))

        if win_dump:
            win_path = win_dump[0][1]
            self.label.set_readonly(False)
            self.label.delete(idx)
            self.label.set_readonly(True)
            for i, frame in enumerate(self._image_frames):
                if str(frame) == win_path:
                    if i < len(self._images):
                        self._images.pop(i)
                    if i < len(self._photo_refs):
                        self._photo_refs.pop(i)
                    self._image_frames.pop(i)
                    frame.destroy()
                    break
        elif img_dump:
            tcl_name = img_dump[0][1]
            self.label.set_readonly(False)
            self.label.delete(idx)
            self.label.set_readonly(True)
            for i, ref in enumerate(self._photo_refs):
                if str(ref) == tcl_name:
                    self._photo_refs.pop(i)
                    if i < len(self._images):
                        self._images.pop(i)
                    break

    def _show_menu(self, event):
        menu = tk.Menu(self.win, tearoff=0)
        # Image hit-test
        idx = self.label.index(f"@{event.x},{event.y}")
        end_idx = self.label.index(f"{idx}+1c")
        img_dump = list(self.label.dump(idx, end_idx, image=True))
        win_dump = list(self.label.dump(idx, end_idx, window=True))
        if img_dump or win_dump:
            ex, ey = event.x, event.y
            menu.add_command(label="Resize image...", command=lambda: self._resize_image(ex, ey))
            menu.add_command(label="Delete image", command=lambda: self._delete_image(idx))
            menu.add_separator()
        menu.add_command(label="Background color...", command=self._pick_bg)
        menu.add_command(label="Text color...", command=self._pick_fg)
        menu.add_command(label="Light mode", command=self._apply_light_mode)
        menu.add_command(label="Dark mode", command=self._apply_dark_mode)
        menu.add_command(label="Font family...", command=self._pick_font_family)
        menu.add_command(label="Font size...", command=self._pick_font_size)
        menu.add_command(label="Opacity...", command=self._pick_opacity)
        trans_label = "✓ Transparent background" if self.transparent else "Transparent background"
        menu.add_command(label=trans_label, command=self._toggle_transparent)
        ct_label = "✓ Click-through" if self.clickthrough else "Click-through"
        menu.add_command(label=ct_label, command=self._toggle_clickthrough)
        ot_label = "✓ Always on top" if self.ontop else "Always on top"
        menu.add_command(label=ot_label, command=self._toggle_ontop)
        menu.add_separator()
        menu.add_command(label="Duplicate", command=self._duplicate)
        menu.add_command(label="Stash & close", command=self._stash)
        menu.add_command(label="Close", command=self._close)
        menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def _pick_bg(self):
        color = colorchooser.askcolor(initialcolor=self.bg, title="Background Color")
        if color[1]:
            self.bg = color[1]
            if not self.transparent:
                self.label.config(bg=self.bg)
                self.frame.config(bg=self.bg)
                self.grip.config(bg=self.bg, fg=self.bg)
                self._apply_image_frame_bg()

    def _pick_fg(self):
        color = colorchooser.askcolor(initialcolor=self.fg, title="Text Color")
        if color[1]:
            self.fg = color[1]
            self.label.config(fg=self.fg)

    def _apply_font_family(self, family):
        if not family:
            return
        self.font_family = family
        self.label.config(font=self._font_tuple())
        if self._entry:
            self._entry.config(font=self._font_tuple())

    def _pick_font_family(self):
        _show_font_family_picker(
            self.manager.root,
            self.win,
            "Font family",
            self.bg,
            self.fg,
            self.font_family,
            self.font_size,
            self._apply_font_family,
            "The quick brown fox 123",
        )

    def _pick_font_size(self):
        size = simpledialog.askinteger("Font Size", "Enter font size:", initialvalue=self.font_size, minvalue=6, maxvalue=72)
        if size:
            self.font_size = size
            self.label.config(font=self._font_tuple())
            if self._entry:
                self._entry.config(font=self._font_tuple())

    def _pick_opacity(self):
        popup = tk.Toplevel(self.manager.root)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.geometry(f"+{self.win.winfo_x()}+{self.win.winfo_y() + self.win.winfo_height() + 5}")

        frame = tk.Frame(popup, bg=self.bg, padx=10, pady=10)
        frame.pack()

        tk.Label(frame, text="Opacity", bg=self.bg, fg=self.fg,
                 font=("Consolas", 9)).pack()

        scale = tk.Scale(frame, from_=20, to=100, orient="horizontal",
                         resolution=5, length=150, bg=self.bg, fg=self.fg,
                         highlightthickness=0, troughcolor="#333333")
        scale.set(self.opacity)
        scale.config(command=lambda val: self.win.attributes("-alpha", int(val) / 100))
        scale.pack()

        def close(e=None):
            self.opacity = scale.get()
            self.win.attributes("-alpha", self.opacity / 100)
            popup.destroy()

        ok_btn = tk.Label(frame, text=" OK ", bg="#333333", fg=self.fg,
                          font=("Consolas", 9, "bold"), cursor="hand2")
        ok_btn.pack(pady=(5, 0))
        ok_btn.bind("<Button-1>", close)
        popup.bind("<Escape>", close)

    def _duplicate(self):
        x = self.win.winfo_x() + 30
        y = self.win.winfo_y() + 30
        self.manager.spawn_label(
            text=self.label.get("1.0", "end-1c"), x=x, y=y, bg=self.bg, fg=self.fg,
            transparent=self.transparent, font_size=self.font_size,
            font_family=self.font_family,
            clickthrough=self.clickthrough,
            images=list(self._images),
        )

    def _stash(self):
        import datetime
        data = self.snapshot()
        data["stashed_on"] = datetime.date.today().strftime("%#m/%#d")
        if "stash" not in self.manager.config:
            self.manager.config["stash"] = []
        self.manager.config["stash"].append(data)
        save_config(self.manager.config)
        self._close()

    def _close(self):
        self.win.destroy()
        if self in self.manager.labels:
            self.manager.labels.remove(self)


class LabelManager:
    def __init__(self):
        self.config = load_config()
        self.labels = []

        self.root = tk.Tk()
        self.root.title("Pane Labels")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 1.0)

        bg = self.config["default_bg"]
        fg = self.config["default_fg"]

        self.frame = tk.Frame(self.root, bg=bg)
        self.frame.pack()

        self.add_btn = tk.Label(self.frame, text=" + ", bg=bg, fg=fg,
                                font=("Consolas", 12, "bold"), padx=6, pady=2, cursor="hand2")
        self.add_btn.pack(side="left")
        self.add_btn.bind("<Button-1>", lambda e: self.spawn_label())

        self.settings_btn = tk.Label(self.frame, text=" \u2699 ", bg=bg, fg=fg,
                                     font=("Consolas", 12), padx=6, pady=2, cursor="hand2")
        self.settings_btn.pack(side="left")
        self.settings_btn.bind("<Button-1>", lambda e: self._show_settings_menu(e))

        self.close_btn = tk.Label(self.frame, text=" \u00d7 ", bg=bg, fg=fg,
                                  font=("Consolas", 12, "bold"), padx=6, pady=2, cursor="hand2")
        self.close_btn.pack(side="left")
        self.close_btn.bind("<Button-1>", lambda e: self._quit())

        # Hub right-click — presets
        self.frame.bind("<Button-3>", self._show_hub_menu)
        self.add_btn.bind("<Button-3>", self._show_hub_menu)
        self.settings_btn.bind("<Button-3>", self._show_hub_menu)
        self.close_btn.bind("<Button-3>", self._show_hub_menu)

        self.frame.bind("<Button-1>", self._start_drag)
        self.frame.bind("<B1-Motion>", self._on_drag)

        # Plus key hotkey to create new label
        self.root.bind("<plus>", lambda e: self.spawn_label())
        self.root.bind("<KP_Add>", lambda e: self.spawn_label())

        self._drag_x = 0
        self._drag_y = 0

        threading.Thread(target=self._socket_listener, daemon=True).start()

        self.root.geometry("+10+10")

        # Restore last session
        for ldata in self.config.get("last_session", []):
            self._spawn_from_data(ldata)

    def _socket_listener(self):
        port = self.config.get("socket_port", 47210)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", port))
            s.listen()
            while True:
                try:
                    conn, _ = s.accept()
                    with conn:
                        data = conn.recv(4096).decode("utf-8", errors="replace").strip()
                        if data:
                            self.root.after(0, lambda t=data: self.spawn_label(text=t))
                except Exception:
                    break

    def _start_drag(self, event):
        self._drag_x = event.x_root - self.root.winfo_x()
        self._drag_y = event.y_root - self.root.winfo_y()

    def _on_drag(self, event):
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self.root.geometry(f"+{x}+{y}")

    def spawn_label(self, text="Label", x=None, y=None, bg=None, fg=None,
                    transparent=None, font_size=None, width=None, height=None,
                    clickthrough=False, ontop=True, images=None, opacity=None,
                    font_family=None):
        if x is None:
            x = self.root.winfo_x() + 50
        if y is None:
            y = self.root.winfo_y() + 50
        label = StickyLabel(self, text=text, x=x, y=y, bg=bg, fg=fg,
                            transparent=transparent, font_size=font_size,
                            font_family=font_family,
                            width=width, height=height, clickthrough=clickthrough, ontop=ontop,
                            images=images, opacity=opacity)
        self.labels.append(label)

    def _spawn_from_data(self, d):
        self.spawn_label(
            text=d.get("text", "Label"),
            x=d.get("x", 100), y=d.get("y", 100),
            bg=d.get("bg"), fg=d.get("fg"),
            transparent=d.get("transparent", False),
            font_family=d.get("font_family"),
            font_size=d.get("font_size"),
            width=d.get("width"), height=d.get("height"),
            clickthrough=d.get("clickthrough", False),
            ontop=d.get("ontop", True),
            images=d.get("images", []),
            opacity=d.get("opacity"),
        )

    def _get_snapshots(self):
        return [l.snapshot() for l in self.labels]

    # --- Hub right-click menu (presets) ---
    def _show_hub_menu(self, event):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Save preset...", command=self._save_preset)

        presets = self.config.get("presets", {})
        if presets:
            load_menu = tk.Menu(menu, tearoff=0)
            del_menu = tk.Menu(menu, tearoff=0)
            for name in sorted(presets.keys()):
                load_menu.add_command(label=name, command=lambda n=name: self._load_preset(n))
                del_menu.add_command(label=name, command=lambda n=name: self._delete_preset(n))
            menu.add_cascade(label="Load preset", menu=load_menu)
            menu.add_cascade(label="Delete preset", menu=del_menu)

        stash = self.config.get("stash", [])
        if stash:
            menu.add_separator()
            stash_menu = tk.Menu(menu, tearoff=0)
            for i, item in enumerate(stash):
                label = f"{item.get('text', 'Label')} ({item.get('stashed_on', '?')})"
                stash_menu.add_command(label=label, command=lambda idx=i: self._restore_stash(idx))
            stash_menu.add_separator()
            stash_menu.add_command(label="Clear stash", command=self._clear_stash)
            menu.add_cascade(label="Stash", menu=stash_menu)

        menu.tk_popup(event.x_root, event.y_root)

    def _save_preset(self):
        name = simpledialog.askstring("Save Preset", "Preset name:")
        if name:
            if "presets" not in self.config:
                self.config["presets"] = {}
            self.config["presets"][name] = self._get_snapshots()
            save_config(self.config)

    def _load_preset(self, name):
        self._close_all()
        for d in self.config["presets"].get(name, []):
            self._spawn_from_data(d)

    def _delete_preset(self, name):
        if name in self.config.get("presets", {}):
            del self.config["presets"][name]
            save_config(self.config)

    def _restore_stash(self, idx):
        stash = self.config.get("stash", [])
        if idx < len(stash):
            item = stash.pop(idx)
            item.pop("stashed_on", None)
            self.config["stash"] = stash
            save_config(self.config)
            self._spawn_from_data(item)

    def _clear_stash(self):
        self.config["stash"] = []
        save_config(self.config)

    # --- Gear settings menu ---
    def _show_settings_menu(self, event):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Default background...", command=self._set_default_bg)
        menu.add_command(label="Default text color...", command=self._set_default_fg)
        menu.add_command(label="Default font family...", command=self._set_default_font_family)
        menu.add_command(label="Default light mode", command=self._set_default_light_mode)
        menu.add_command(label="Default dark mode", command=self._set_default_dark_mode)
        trans_label = "✓ Default: transparent background" if self.config.get("default_transparent") else "Default: transparent background"
        menu.add_command(label=trans_label, command=self._toggle_default_transparent)
        menu.add_separator()
        menu.add_command(label="Close all labels", command=self._close_all)
        menu.tk_popup(event.x_root, event.y_root)

    def _toggle_default_transparent(self):
        self.config["default_transparent"] = not self.config.get("default_transparent", False)
        save_config(self.config)

    def _set_default_bg(self):
        color = colorchooser.askcolor(initialcolor=self.config["default_bg"], title="Default Background")
        if color[1]:
            self.config["default_bg"] = color[1]
            save_config(self.config)
            self._update_hub_colors()

    def _set_default_fg(self):
        color = colorchooser.askcolor(initialcolor=self.config["default_fg"], title="Default Text Color")
        if color[1]:
            self.config["default_fg"] = color[1]
            save_config(self.config)
            self._update_hub_colors()

    def _set_default_font_family(self):
        font_size = self.config.get("font_size", DEFAULT_FONT_SIZE)
        current = self.config.get("font_family", DEFAULT_FONT_FAMILY)

        def apply_default(family):
            self.config["font_family"] = family
            save_config(self.config)

        _show_font_family_picker(
            self.root,
            self.root,
            "Default font family",
            self.config["default_bg"],
            self.config["default_fg"],
            current,
            font_size,
            apply_default,
            "New notes will use this font",
        )

    def _set_default_theme(self, bg, fg):
        self.config["default_bg"] = bg
        self.config["default_fg"] = fg
        self.config["default_transparent"] = False
        save_config(self.config)
        self._update_hub_colors()

    def _set_default_light_mode(self):
        self._set_default_theme(LIGHT_BG, LIGHT_FG)

    def _set_default_dark_mode(self):
        self._set_default_theme(DARK_BG, DARK_FG)

    def _update_hub_colors(self):
        bg = self.config["default_bg"]
        fg = self.config["default_fg"]
        self.frame.config(bg=bg)
        self.add_btn.config(bg=bg, fg=fg)
        self.settings_btn.config(bg=bg, fg=fg)
        self.close_btn.config(bg=bg, fg=fg)

    def _close_all(self):
        for label in self.labels[:]:
            label._close()

    def _quit(self):
        # Auto-save session on close
        self.config["last_session"] = self._get_snapshots()
        save_config(self.config)
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    LabelManager().run()
