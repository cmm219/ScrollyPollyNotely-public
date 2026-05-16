import os, sys, shutil, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

TEST_DATA_DIR = os.path.join(tempfile.gettempdir(), "scrolly_polly_notely_tests")
os.environ["SCROLLY_POLLY_NOTELY_DATA_DIR"] = TEST_DATA_DIR
IMAGE_DIR = os.path.join(TEST_DATA_DIR, "pasted-images")

class TestImageDir(unittest.TestCase):
    def setUp(self):
        if os.path.exists(IMAGE_DIR):
            shutil.rmtree(IMAGE_DIR)

    def test_ensure_image_dir_creates_dir(self):
        import labels
        labels._ensure_image_dir()
        self.assertTrue(os.path.isdir(IMAGE_DIR))

    def test_ensure_image_dir_idempotent(self):
        import labels
        labels._ensure_image_dir()
        labels._ensure_image_dir()
        self.assertTrue(os.path.isdir(IMAGE_DIR))

    def test_config_persists_to_env_data_dir(self):
        if os.path.exists(TEST_DATA_DIR):
            shutil.rmtree(TEST_DATA_DIR)
        import labels
        cfg = labels.load_config()
        cfg["last_session"] = [{"text": "saved in test dir"}]
        labels.save_config(cfg)
        self.assertEqual(labels.CONFIG_PATH, os.path.join(TEST_DATA_DIR, "notes-and-settings.json"))
        self.assertTrue(os.path.exists(labels.CONFIG_PATH))
        loaded = labels.load_config()
        self.assertEqual(loaded["last_session"][0]["text"], "saved in test dir")

    def test_default_config_includes_recovery_settings(self):
        if os.path.exists(TEST_DATA_DIR):
            shutil.rmtree(TEST_DATA_DIR)
        import labels
        cfg = labels.load_config()
        self.assertFalse(cfg["clickthrough_warned"])
        self.assertTrue(cfg["hub_always_on_top"])

import tkinter as tk

_root = None

def get_root():
    global _root
    if _root is None:
        _root = tk.Tk()
        _root.withdraw()
    return _root

class TestStickyLabelAttributes(unittest.TestCase):
    def setUp(self):
        import labels
        self.labels = labels
        root = get_root()
        self.mgr = labels.LabelManager.__new__(labels.LabelManager)
        self.mgr.config = labels.load_config()
        self.mgr.labels = []
        self.mgr.root = root
        self.mgr.frame = tk.Frame(root)

    def _make_label(self):
        return self.labels.StickyLabel(self.mgr, text="Test", x=0, y=0)

    def test_has_image_attributes(self):
        lbl = self._make_label()
        self.assertEqual(lbl._photo_refs, [])
        self.assertEqual(lbl._entry_photo_refs, [])
        self.assertEqual(lbl._images, [])
        self.assertEqual(lbl._image_name_map, {})
        lbl.win.destroy()

    def test_snapshot_includes_images_key(self):
        lbl = self._make_label()
        snap = lbl.snapshot()
        self.assertIn("images", snap)
        self.assertEqual(snap["images"], [])
        lbl.win.destroy()

    def test_snapshot_images_reflects_state(self):
        lbl = self._make_label()
        fake = {"path": "pasted-images/x.png", "original_path": "pasted-images/x.png",
                "width": 100, "height": 80, "position": "1.0"}
        lbl._images = [fake]
        snap = lbl.snapshot()
        self.assertEqual(len(snap["images"]), 1)
        self.assertEqual(snap["images"][0]["path"], "pasted-images/x.png")
        lbl.win.destroy()

class TestSpawnFromDataImages(unittest.TestCase):
    def setUp(self):
        import labels, shutil
        self.labels = labels
        self.root = get_root()
        self.mgr = labels.LabelManager.__new__(labels.LabelManager)
        self.mgr.config = labels.load_config()
        self.mgr.labels = []
        self.mgr.root = self.root
        self.mgr.frame = tk.Frame(self.root)
        labels._ensure_image_dir()
        self.test_png = os.path.join(labels.IMAGE_DIR, "test_img_100x50.png")
        try:
            from PIL import Image as PilImage
            img = PilImage.new("RGB", (100, 50), color=(255, 0, 0))
            img.save(self.test_png)
        except ImportError:
            self.skipTest("Pillow not installed")

    def tearDown(self):
        if os.path.exists(self.test_png):
            os.remove(self.test_png)

    def test_spawn_from_data_with_image_loads_it(self):
        data = {
            "text": "hello",
            "x": 0, "y": 0,
            "images": [{
                "path": self.test_png,
                "original_path": self.test_png,
                "width": 100, "height": 50,
                "position": "1.5"
            }]
        }
        self.mgr._spawn_from_data(data)
        lbl = self.mgr.labels[-1]
        self.assertEqual(len(lbl._images), 1)
        self.assertEqual(len(lbl._photo_refs), 1)
        lbl.win.destroy()

    def test_spawn_from_data_missing_file_skips(self):
        data = {
            "text": "hello",
            "x": 0, "y": 0,
            "images": [{
                "path": "pasted-images/nonexistent.png",
                "original_path": "pasted-images/nonexistent.png",
                "width": 100, "height": 50,
                "position": "1.0"
            }]
        }
        self.mgr._spawn_from_data(data)
        lbl = self.mgr.labels[-1]
        self.assertEqual(len(lbl._images), 0)
        lbl.win.destroy()


class TestPasteImage(unittest.TestCase):
    def setUp(self):
        import labels
        self.labels = labels
        root = get_root()
        self.mgr = labels.LabelManager.__new__(labels.LabelManager)
        self.mgr.config = labels.load_config()
        self.mgr.labels = []
        self.mgr.root = root
        self.mgr.frame = tk.Frame(root)
        labels._ensure_image_dir()

    def _make_label_in_edit(self):
        lbl = self.labels.StickyLabel(self.mgr, text="Hi", x=0, y=0)
        lbl._entry = tk.Text(lbl.frame, undo=False)
        lbl._entry.insert("1.0", "Hi")
        lbl._entry.pack()
        return lbl

    def test_paste_image_with_no_clipboard_image_returns_none(self):
        try:
            from PIL import ImageGrab
        except ImportError:
            self.skipTest("Pillow not installed")
        import unittest.mock as mock
        lbl = self._make_label_in_edit()
        with mock.patch("labels.ImageGrab.grabclipboard", return_value=None):
            result = lbl._paste_image(None)
        self.assertIsNone(result)
        lbl.win.destroy()

    def test_paste_image_creates_file_and_embeds(self):
        try:
            from PIL import Image as PilImage, ImageGrab
        except ImportError:
            self.skipTest("Pillow not installed")
        import unittest.mock as mock
        lbl = self._make_label_in_edit()
        fake_img = PilImage.new("RGB", (200, 100), color=(0, 128, 0))
        with mock.patch("labels.ImageGrab.grabclipboard", return_value=fake_img):
            result = lbl._paste_image(None)
        self.assertEqual(result, "break")
        self.assertEqual(len(lbl._entry_photo_refs), 1)
        import glob
        pngs = glob.glob(os.path.join(self.labels.IMAGE_DIR, "*.png"))
        self.assertTrue(len(pngs) >= 1)
        for f in pngs:
            os.remove(f)
        lbl.win.destroy()


class TestFinishEditRoundTrip(unittest.TestCase):
    def setUp(self):
        import labels
        self.labels = labels
        root = get_root()
        self.mgr = labels.LabelManager.__new__(labels.LabelManager)
        self.mgr.config = labels.load_config()
        self.mgr.labels = []
        self.mgr.root = root
        self.mgr.frame = tk.Frame(root)
        labels._ensure_image_dir()

    def test_finish_edit_plain_text_round_trips(self):
        lbl = self.labels.StickyLabel(self.mgr, text="hello", x=0, y=0)
        lbl._start_edit(None)
        lbl._entry.delete("1.0", "end")
        lbl._entry.insert("1.0", "world")
        lbl._finish_edit(None)
        self.assertEqual(lbl.label.get("1.0", "end-1c"), "world")
        lbl.win.destroy()

    def test_finish_edit_with_image_preserves_image(self):
        try:
            from PIL import Image as PilImage
        except ImportError:
            self.skipTest("Pillow not installed")
        import unittest.mock as mock
        lbl = self.labels.StickyLabel(self.mgr, text="hi", x=0, y=0)
        lbl._start_edit(None)
        fake_img = PilImage.new("RGB", (50, 30), color=(255, 0, 0))
        with mock.patch("labels.ImageGrab.grabclipboard", return_value=fake_img):
            lbl._paste_image(None)
        lbl._finish_edit(None)
        self.assertEqual(len(lbl._images), 1)
        self.assertEqual(len(lbl._photo_refs), 1)
        for img_dict in lbl._images:
            for key in ("path", "original_path"):
                p = img_dict.get(key, "")
                if os.path.exists(p):
                    os.remove(p)
        lbl.win.destroy()


class TestTextReflow(unittest.TestCase):
    def setUp(self):
        import labels
        self.labels = labels
        root = get_root()
        self.mgr = labels.LabelManager.__new__(labels.LabelManager)
        self.mgr.config = labels.load_config()
        self.mgr.labels = []
        self.mgr.root = root
        self.mgr.frame = tk.Frame(root)

    def test_label_width_changes_on_window_resize(self):
        lbl = self.labels.StickyLabel(self.mgr, text="hello", x=0, y=0, width=200, height=100)
        lbl.win.update_idletasks()
        w1 = lbl.label.cget("width")
        # Simulate resize to wider
        lbl.win.geometry("400x100+0+0")
        lbl.win.update_idletasks()
        lbl._on_window_resize(None)
        w2 = lbl.label.cget("width")
        self.assertGreater(w2, w1)
        lbl.win.destroy()


class TestOpacity(unittest.TestCase):
    def setUp(self):
        import labels
        self.labels = labels
        root = get_root()
        self.mgr = labels.LabelManager.__new__(labels.LabelManager)
        self.mgr.config = labels.load_config()
        self.mgr.labels = []
        self.mgr.root = root
        self.mgr.frame = tk.Frame(root)

    def test_default_opacity_is_100(self):
        lbl = self.labels.StickyLabel(self.mgr, text="hi", x=0, y=0)
        self.assertEqual(lbl.opacity, 100)
        lbl.win.destroy()

    def test_custom_opacity_applied(self):
        lbl = self.labels.StickyLabel(self.mgr, text="hi", x=0, y=0, opacity=50)
        self.assertEqual(lbl.opacity, 50)
        alpha = lbl.win.attributes("-alpha")
        self.assertAlmostEqual(float(alpha), 0.50, places=1)
        lbl.win.destroy()

    def test_snapshot_includes_opacity(self):
        lbl = self.labels.StickyLabel(self.mgr, text="hi", x=0, y=0, opacity=70)
        snap = lbl.snapshot()
        self.assertEqual(snap["opacity"], 70)
        lbl.win.destroy()

    def test_spawn_from_data_restores_opacity(self):
        data = {"text": "hi", "x": 0, "y": 0, "opacity": 60}
        self.mgr._spawn_from_data(data)
        lbl = self.mgr.labels[-1]
        self.assertEqual(lbl.opacity, 60)
        lbl.win.destroy()


class TestThemeModes(unittest.TestCase):
    def setUp(self):
        import labels
        self.labels = labels
        root = get_root()
        self.mgr = labels.LabelManager.__new__(labels.LabelManager)
        self.mgr.config = {
            "default_bg": labels.DEFAULT_BG,
            "default_fg": labels.DEFAULT_FG,
            "font_size": labels.DEFAULT_FONT_SIZE,
            "default_transparent": False,
            "last_session": [],
            "presets": {},
        }
        self.mgr.labels = []
        self.mgr.root = root
        self.mgr.frame = tk.Frame(root, bg=labels.DEFAULT_BG)
        self.mgr.add_btn = tk.Label(self.mgr.frame, bg=labels.DEFAULT_BG, fg=labels.DEFAULT_FG)
        self.mgr.settings_btn = tk.Label(self.mgr.frame, bg=labels.DEFAULT_BG, fg=labels.DEFAULT_FG)
        self.mgr.close_btn = tk.Label(self.mgr.frame, bg=labels.DEFAULT_BG, fg=labels.DEFAULT_FG)

    def test_light_mode_sets_existing_appearance_fields(self):
        lbl = self.labels.StickyLabel(
            self.mgr, text="hi", x=0, y=0,
            bg=self.labels.DEFAULT_BG, fg=self.labels.DEFAULT_FG,
            transparent=True,
        )
        lbl._apply_light_mode()
        self.assertEqual(lbl.bg, self.labels.LIGHT_BG)
        self.assertEqual(lbl.fg, self.labels.LIGHT_FG)
        self.assertFalse(lbl.transparent)
        self.assertEqual(lbl.label.cget("bg"), self.labels.LIGHT_BG)
        self.assertEqual(lbl.label.cget("fg"), self.labels.LIGHT_FG)
        snap = lbl.snapshot()
        self.assertEqual(snap["bg"], self.labels.LIGHT_BG)
        self.assertEqual(snap["fg"], self.labels.LIGHT_FG)
        self.assertFalse(snap["transparent"])
        lbl.win.destroy()

    def test_light_mode_updates_image_frame_backgrounds(self):
        lbl = self.labels.StickyLabel(
            self.mgr, text="hi", x=0, y=0,
            bg=self.labels.DEFAULT_BG, fg=self.labels.DEFAULT_FG,
        )
        photo = tk.PhotoImage(width=1, height=1)
        lbl._photo_refs.append(photo)
        frame = lbl._make_image_frame(photo, {
            "path": "pasted-images/x.png",
            "original_path": "pasted-images/x.png",
            "width": 1,
            "height": 1,
            "position": "1.0",
        })
        lbl._apply_light_mode()
        self.assertEqual(frame.cget("bg"), self.labels.LIGHT_BG)
        self.assertEqual(frame._img_label.cget("bg"), self.labels.LIGHT_BG)
        grip = [child for child in frame.winfo_children() if child is not frame._img_label][0]
        self.assertEqual(grip.cget("bg"), self.labels.LIGHT_BG)
        self.assertEqual(grip.cget("fg"), self.labels.LIGHT_BG)
        lbl.win.destroy()

    def test_dark_mode_sets_black_and_white(self):
        lbl = self.labels.StickyLabel(
            self.mgr, text="hi", x=0, y=0,
            bg=self.labels.LIGHT_BG, fg=self.labels.LIGHT_FG,
            transparent=True,
        )
        lbl._apply_dark_mode()
        self.assertEqual(lbl.bg, self.labels.DARK_BG)
        self.assertEqual(lbl.fg, self.labels.DARK_FG)
        self.assertFalse(lbl.transparent)
        self.assertEqual(lbl.label.cget("bg"), self.labels.DARK_BG)
        self.assertEqual(lbl.label.cget("fg"), self.labels.DARK_FG)
        lbl.win.destroy()

    def test_light_mode_snapshot_round_trips_through_spawn(self):
        lbl = self.labels.StickyLabel(
            self.mgr, text="hi", x=0, y=0,
            bg=self.labels.DEFAULT_BG, fg=self.labels.DEFAULT_FG,
            transparent=True,
        )
        lbl._apply_light_mode()
        data = lbl.snapshot()
        lbl.win.destroy()

        self.mgr._spawn_from_data(data)
        restored = self.mgr.labels[-1]
        self.assertEqual(restored.bg, self.labels.LIGHT_BG)
        self.assertEqual(restored.fg, self.labels.LIGHT_FG)
        self.assertFalse(restored.transparent)
        self.assertEqual(restored.label.cget("bg"), self.labels.LIGHT_BG)
        self.assertEqual(restored.label.cget("fg"), self.labels.LIGHT_FG)
        restored.win.destroy()

    def test_default_light_mode_reuses_existing_default_fields(self):
        import unittest.mock as mock
        with mock.patch("labels.save_config"):
            self.mgr._set_default_light_mode()
        self.assertEqual(self.mgr.config["default_bg"], self.labels.LIGHT_BG)
        self.assertEqual(self.mgr.config["default_fg"], self.labels.LIGHT_FG)
        self.assertFalse(self.mgr.config["default_transparent"])

    def test_default_dark_mode_reuses_existing_default_fields(self):
        import unittest.mock as mock
        self.mgr.config["default_bg"] = self.labels.LIGHT_BG
        self.mgr.config["default_fg"] = self.labels.LIGHT_FG
        self.mgr.config["default_transparent"] = True
        with mock.patch("labels.save_config"):
            self.mgr._set_default_dark_mode()
        self.assertEqual(self.mgr.config["default_bg"], self.labels.DARK_BG)
        self.assertEqual(self.mgr.config["default_fg"], self.labels.DARK_FG)
        self.assertFalse(self.mgr.config["default_transparent"])

    def test_transparent_mode_uses_non_text_key_color(self):
        lbl = self.labels.StickyLabel(self.mgr, text="hi", x=0, y=0)
        lbl._apply_transparent(True)
        self.assertEqual(lbl.label.cget("bg"), self.labels.TRANSPARENT_KEY)
        self.assertNotEqual(self.labels.TRANSPARENT_KEY.lower(), self.labels.DARK_BG)
        self.assertNotEqual(self.labels.TRANSPARENT_KEY.lower(), self.labels.DARK_FG)
        self.assertNotEqual(self.labels.TRANSPARENT_KEY.lower(), self.labels.LIGHT_BG)
        self.assertNotEqual(self.labels.TRANSPARENT_KEY.lower(), self.labels.LIGHT_FG)
        lbl.win.destroy()

    def test_clickthrough_toggle_tracks_state_and_restores_topmost(self):
        import unittest.mock as mock
        lbl = self.labels.StickyLabel(self.mgr, text="hi", x=0, y=0)
        with mock.patch.object(lbl, "_set_window_clickthrough", return_value=True) as style:
            lbl._apply_clickthrough(True)
            self.assertTrue(lbl.clickthrough)
            lbl._apply_clickthrough(False)
            self.assertFalse(lbl.clickthrough)
        self.assertEqual(style.call_count, 2)
        self.assertEqual(lbl.win.attributes("-topmost"), lbl.ontop)
        lbl.win.destroy()

    def test_disable_all_clickthrough_turns_off_each_note(self):
        import unittest.mock as mock
        lbl = self.labels.StickyLabel(self.mgr, text="hi", x=0, y=0)
        self.mgr.labels.append(lbl)
        with mock.patch.object(lbl, "_set_window_clickthrough", return_value=True):
            lbl._apply_clickthrough(True)
            self.mgr._disable_all_clickthrough()
        self.assertFalse(lbl.clickthrough)
        lbl.win.destroy()

    def test_clickthrough_first_enable_warns_and_can_cancel(self):
        import unittest.mock as mock
        lbl = self.labels.StickyLabel(self.mgr, text="hi", x=0, y=0)
        self.mgr.config["clickthrough_warned"] = False
        with mock.patch("labels.messagebox.askokcancel", return_value=False) as ask, \
             mock.patch.object(lbl, "_set_window_clickthrough", return_value=True) as style:
            lbl._toggle_clickthrough()
        ask.assert_called_once()
        style.assert_not_called()
        self.assertFalse(lbl.clickthrough)
        self.assertFalse(self.mgr.config["clickthrough_warned"])
        lbl.win.destroy()

    def test_clickthrough_first_enable_persists_warning_ack(self):
        import unittest.mock as mock
        lbl = self.labels.StickyLabel(self.mgr, text="hi", x=0, y=0)
        self.mgr.config["clickthrough_warned"] = False
        with mock.patch("labels.messagebox.askokcancel", return_value=True) as ask, \
             mock.patch("labels.save_config") as save, \
             mock.patch.object(lbl, "_set_window_clickthrough", return_value=True) as style:
            lbl._toggle_clickthrough()
        _, kwargs = ask.call_args
        self.assertEqual(kwargs["parent"], lbl.win)
        self.assertTrue(lbl.clickthrough)
        self.assertTrue(self.mgr.config["clickthrough_warned"])
        save.assert_called_once_with(self.mgr.config)
        style.assert_called_once_with(True)
        lbl.win.destroy()

    def test_clickthrough_skips_warning_after_ack(self):
        import unittest.mock as mock
        lbl = self.labels.StickyLabel(self.mgr, text="hi", x=0, y=0)
        self.mgr.config["clickthrough_warned"] = True
        with mock.patch("labels.messagebox.askokcancel") as ask, \
             mock.patch.object(lbl, "_set_window_clickthrough", return_value=True):
            lbl._toggle_clickthrough()
        ask.assert_not_called()
        self.assertTrue(lbl.clickthrough)
        lbl.win.destroy()

    def test_hub_always_on_top_toggle_persists(self):
        import unittest.mock as mock
        self.mgr.hub_ontop = True
        self.mgr.config["hub_always_on_top"] = True
        with mock.patch("labels.save_config") as save:
            self.mgr._toggle_hub_ontop()
        self.assertFalse(self.mgr.hub_ontop)
        self.assertFalse(self.mgr.config["hub_always_on_top"])
        self.assertFalse(bool(self.mgr.root.attributes("-topmost")))
        save.assert_called_once_with(self.mgr.config)

    def test_hub_button_release_click_runs_command(self):
        called = []
        self.mgr._hub_dragged = False
        event = type("E", (), {})()
        self.mgr._release_hub_button(event, lambda e: called.append(e))
        self.assertEqual(called, [event])

    def test_hub_button_release_after_drag_skips_command(self):
        called = []
        self.mgr._hub_dragged = True
        event = type("E", (), {})()
        self.mgr._release_hub_button(event, lambda e: called.append(e))
        self.assertEqual(called, [])

    def test_hub_button_drag_threshold_classifies_motion(self):
        import unittest.mock as mock
        event = type("E", (), {})()
        self.mgr._hub_press_x_root = 100
        self.mgr._hub_press_y_root = 100
        self.mgr._hub_dragged = False

        event.x_root = 100 + self.labels.HUB_DRAG_THRESHOLD_PX
        event.y_root = 100
        self.mgr._on_hub_button_drag(event)
        self.assertFalse(self.mgr._hub_dragged)

        event.x_root = 100 + self.labels.HUB_DRAG_THRESHOLD_PX + 1
        with mock.patch.object(self.mgr, "_on_drag") as drag:
            self.mgr._on_hub_button_drag(event)
        self.assertTrue(self.mgr._hub_dragged)
        drag.assert_called_once_with(event)

    def test_manager_binds_clickthrough_recovery_hotkeys(self):
        import inspect
        source = inspect.getsource(self.labels.LabelManager.__init__)
        self.assertIn('bind_all("<Control-Shift-T>"', source)
        self.assertIn('bind_all("<Control-Shift-t>"', source)


class TestFontFamily(unittest.TestCase):
    def setUp(self):
        import labels
        self.labels = labels
        root = get_root()
        self.mgr = labels.LabelManager.__new__(labels.LabelManager)
        self.mgr.config = {
            "default_bg": labels.DEFAULT_BG,
            "default_fg": labels.DEFAULT_FG,
            "font_family": labels.DEFAULT_FONT_FAMILY,
            "font_size": labels.DEFAULT_FONT_SIZE,
            "default_transparent": False,
            "last_session": [],
            "presets": {},
        }
        self.mgr.labels = []
        self.mgr.root = root
        self.mgr.frame = tk.Frame(root)

    def test_font_family_defaults_to_consolas(self):
        lbl = self.labels.StickyLabel(self.mgr, text="hi", x=0, y=0)
        self.assertEqual(lbl.font_family, self.labels.DEFAULT_FONT_FAMILY)
        snap = lbl.snapshot()
        self.assertEqual(snap["font_family"], self.labels.DEFAULT_FONT_FAMILY)
        lbl.win.destroy()

    def test_apply_font_family_updates_snapshot(self):
        lbl = self.labels.StickyLabel(self.mgr, text="hi", x=0, y=0)
        lbl._apply_font_family("Arial")
        self.assertEqual(lbl.font_family, "Arial")
        snap = lbl.snapshot()
        self.assertEqual(snap["font_family"], "Arial")
        lbl.win.destroy()

    def test_font_family_round_trips_through_spawn(self):
        lbl = self.labels.StickyLabel(self.mgr, text="hi", x=0, y=0)
        lbl._apply_font_family("Arial")
        data = lbl.snapshot()
        lbl.win.destroy()

        self.mgr._spawn_from_data(data)
        restored = self.mgr.labels[-1]
        self.assertEqual(restored.font_family, "Arial")
        self.assertEqual(restored.snapshot()["font_family"], "Arial")
        restored.win.destroy()

    def test_spawn_uses_default_font_family_for_new_notes(self):
        self.mgr.config["font_family"] = "Arial"
        self.mgr.spawn_label(text="hi", x=0, y=0)
        lbl = self.mgr.labels[-1]
        self.assertEqual(lbl.font_family, "Arial")
        lbl.win.destroy()

    def test_duplicate_carries_font_family(self):
        lbl = self.labels.StickyLabel(self.mgr, text="hi", x=0, y=0)
        lbl._apply_font_family("Arial")
        self.mgr.labels.append(lbl)
        lbl._duplicate()
        duplicate = self.mgr.labels[-1]
        self.assertEqual(duplicate.font_family, "Arial")
        lbl.win.destroy()
        duplicate.win.destroy()

    def test_stash_restore_carries_font_family(self):
        import unittest.mock as mock
        lbl = self.labels.StickyLabel(self.mgr, text="hi", x=0, y=0)
        lbl._apply_font_family("Arial")
        self.mgr.labels.append(lbl)
        with mock.patch("labels.save_config"):
            lbl._stash()
            self.mgr._restore_stash(0)
        restored = self.mgr.labels[-1]
        self.assertEqual(restored.font_family, "Arial")
        restored.win.destroy()

    def test_preset_load_carries_font_family(self):
        import unittest.mock as mock
        lbl = self.labels.StickyLabel(self.mgr, text="hi", x=0, y=0)
        lbl._apply_font_family("Arial")
        self.mgr.labels.append(lbl)
        with mock.patch("labels.simpledialog.askstring", return_value="font-test"), \
             mock.patch("labels.save_config"):
            self.mgr._save_preset()
            self.mgr._load_preset("font-test")
        restored = self.mgr.labels[-1]
        self.assertEqual(restored.font_family, "Arial")
        restored.win.destroy()


class TestEditModeContextMenu(unittest.TestCase):
    def setUp(self):
        import labels
        self.labels = labels
        root = get_root()
        self.mgr = labels.LabelManager.__new__(labels.LabelManager)
        self.mgr.config = labels.load_config()
        self.mgr.labels = []
        self.mgr.root = root
        self.mgr.frame = tk.Frame(root)

    def test_edit_mode_has_right_click_menu_binding(self):
        lbl = self.labels.StickyLabel(self.mgr, text="hi", x=0, y=0)
        lbl._start_edit(type("E", (), {"x": 0, "y": 0, "x_root": 0, "y_root": 0})())
        self.assertTrue(lbl._entry.bind("<Button-3>"))
        lbl.win.destroy()

    def test_entry_select_all_selects_text(self):
        lbl = self.labels.StickyLabel(self.mgr, text="hello", x=0, y=0)
        lbl._start_edit(type("E", (), {"x": 0, "y": 0, "x_root": 0, "y_root": 0})())
        lbl._entry_select_all()
        selected = lbl._entry.get("sel.first", "sel.last")
        self.assertEqual(selected, "hello")
        lbl.win.destroy()


class TestImageGripResize(unittest.TestCase):
    def setUp(self):
        import labels
        self.labels = labels
        root = get_root()
        self.mgr = labels.LabelManager.__new__(labels.LabelManager)
        self.mgr.config = labels.load_config()
        self.mgr.labels = []
        self.mgr.root = root
        self.mgr.frame = tk.Frame(root)
        labels._ensure_image_dir()

    def _paste_image(self, lbl, w=100, h=60):
        try:
            from PIL import Image as PilImage
        except ImportError:
            self.skipTest("Pillow not installed")
        import unittest.mock as mock
        evt = type('E', (), {'x':0,'y':0,'x_root':0,'y_root':0})()
        lbl._start_edit(evt)
        lbl.win.update_idletasks()
        fake = PilImage.new("RGB", (w, h), color=(255, 0, 0))
        with mock.patch("labels.ImageGrab.grabclipboard", return_value=fake):
            lbl._paste_image(None)
        lbl._finish_edit(None)
        lbl.win.update_idletasks()

    def test_image_embedded_as_window(self):
        lbl = self.labels.StickyLabel(self.mgr, text="test", x=0, y=0)
        self._paste_image(lbl)
        windows = list(lbl.label.dump("1.0", "end", window=True))
        self.assertTrue(len(windows) >= 1, "Expected window_create embed")
        lbl.win.destroy()

    def test_image_frame_has_grip(self):
        lbl = self.labels.StickyLabel(self.mgr, text="test", x=0, y=0)
        self._paste_image(lbl)
        self.assertTrue(len(lbl._image_frames) >= 1)
        frame = lbl._image_frames[0]
        children = frame.winfo_children()
        self.assertEqual(len(children), 2)  # image label + grip
        lbl.win.destroy()

    def test_image_survives_edit_roundtrip_with_windows(self):
        lbl = self.labels.StickyLabel(self.mgr, text="test", x=0, y=0)
        self._paste_image(lbl)
        count_before = len(lbl._images)
        evt = type('E', (), {'x':0,'y':0,'x_root':0,'y_root':0})()
        lbl._start_edit(evt)
        lbl.win.update_idletasks()
        lbl._finish_edit(None)
        lbl.win.update_idletasks()
        self.assertEqual(len(lbl._images), count_before)
        lbl.win.destroy()

    def tearDown(self):
        import glob
        for f in glob.glob(os.path.join(self.labels.IMAGE_DIR, "*.png")):
            os.remove(f)


class TestChecklist(unittest.TestCase):
    def setUp(self):
        import labels
        self.labels = labels
        root = get_root()
        self.mgr = labels.LabelManager.__new__(labels.LabelManager)
        self.mgr.config = labels.load_config()
        self.mgr.labels = []
        self.mgr.root = root
        self.mgr.frame = tk.Frame(root)

    def test_checked_items_get_tag(self):
        lbl = self.labels.StickyLabel(self.mgr, text="- [x] done\n- [ ] todo", x=0, y=0)
        lbl.win.update_idletasks()
        ranges = lbl.label.tag_ranges("checked")
        self.assertTrue(len(ranges) > 0, "Expected 'checked' tag on completed item")
        lbl.win.destroy()

    def test_toggle_unchecked_to_checked(self):
        lbl = self.labels.StickyLabel(self.mgr, text="- [ ] task", x=0, y=0)
        lbl.win.update_idletasks()
        lbl._toggle_checklist_item("1.0")
        text = lbl.label.get("1.0", "end-1c")
        self.assertIn("- [x]", text)
        lbl.win.destroy()

    def test_toggle_checked_to_unchecked(self):
        lbl = self.labels.StickyLabel(self.mgr, text="- [x] done", x=0, y=0)
        lbl.win.update_idletasks()
        lbl._toggle_checklist_item("1.0")
        text = lbl.label.get("1.0", "end-1c")
        self.assertIn("- [ ]", text)
        lbl.win.destroy()

    def test_checked_items_sort_to_bottom(self):
        lbl = self.labels.StickyLabel(
            self.mgr,
            text="- [ ] alpha\n- [ ] beta\n- [ ] gamma",
            x=0, y=0
        )
        lbl.win.update_idletasks()
        # Check the first item
        lbl._toggle_checklist_item("1.0")
        text = lbl.label.get("1.0", "end-1c")
        lines = text.strip().split("\n")
        # "alpha" should now be checked and at the bottom
        self.assertTrue(lines[-1].startswith("- [x]"), f"Last line should be checked, got: {lines[-1]}")
        self.assertIn("alpha", lines[-1])
        lbl.win.destroy()


if __name__ == "__main__":
    unittest.main()
