"""GTK windows: a desktop widget and a fullscreen screensaver."""

from __future__ import annotations

import sys
import time
from datetime import datetime

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk

from flapclock.clock import ClockFace, format_digits
from flapclock.config import Settings
from flapclock.render import draw_face, widget_size

IDLE_CHOICES = (
    ("關閉", 0),
    ("1 分鐘", 1),
    ("3 分鐘", 3),
    ("5 分鐘", 5),
    ("10 分鐘", 10),
    ("30 分鐘", 30),
)
_MOTION_ARM_SECONDS = 0.45
_MOTION_PIXELS = 14


class FlapclockApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id="dev.flapclock.Clock",
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        self.add_main_option(
            "screensaver",
            ord("s"),
            GLib.OptionFlags.NONE,
            GLib.OptionArg.NONE,
            "只開啟全螢幕螢幕保護程式，有輸入就結束",
            None,
        )
        self.screensaver_only = False
        self.config = Settings.load()
        self.face = ClockFace()
        self.widget: Gtk.Window | None = None
        self.savers: list[Gtk.Window] = []
        self._proxy: Gio.DBusProxy | None = None
        self._proxy_failed = False
        self._watch_id: int | None = None
        self._cookie = 0
        self._saver_on = False
        self._motion_origin: tuple[float, float] | None = None
        self._saver_started = 0.0

    def do_command_line(self, command_line: Gio.ApplicationCommandLine) -> int:
        options = command_line.get_options_dict()
        screensaver = options.contains("screensaver")
        if command_line.get_is_remote():
            if screensaver:
                self.show_saver()
            elif self.widget is not None:
                self.widget.present()
            return 0
        self.screensaver_only = screensaver
        self.activate()
        return 0

    def do_activate(self) -> None:
        if self.widget is None and not self.screensaver_only:
            self.widget = WidgetWindow(self)
            self.widget.show_all()
        if self.screensaver_only:
            self.show_saver()
        else:
            self.arm_idle_watch()
        if getattr(self, "_timer", None) is None:
            self._timer = GLib.timeout_add(16, self._tick)

    def _tick(self) -> bool:
        digits, suffix = format_digits(datetime.now(), self.config.hour24)
        self.face.advance(time.monotonic())
        self.face.update(digits, suffix)
        if self.widget is not None and self.widget.get_visible():
            self.widget.queue_draw()
        for window in self.savers:
            window.queue_draw()
        return True

    def adjust_scale(self, factor: float) -> None:
        self.config.scale = min(2.6, max(0.45, self.config.scale * factor))
        self.config.save()
        if self.widget is not None:
            self.widget.apply_size()

    def set_hour24(self, enabled: bool) -> None:
        self.config.hour24 = enabled
        self.config.save()

    def set_keep_above(self, enabled: bool) -> None:
        self.config.keep_above = enabled
        self.config.save()
        if self.widget is not None:
            self.widget.set_keep_above(enabled)

    def set_idle_minutes(self, minutes: int) -> None:
        self.config.idle_minutes = minutes
        self.config.save()
        if not self._saver_on:
            self.arm_idle_watch()

    def remember_position(self, x: int, y: int) -> None:
        if _is_wayland():
            return
        self.config.x = x
        self.config.y = y
        self.config.save()

    def show_saver(self) -> None:
        if self._saver_on:
            return
        self._saver_on = True
        self._motion_origin = None
        self._saver_started = time.monotonic()
        self._clear_idle_watch()
        if self.widget is not None:
            self.widget.hide()
        screen = Gdk.Screen.get_default()
        count = max(1, screen.get_n_monitors()) if screen is not None else 1
        for index in range(count):
            window = SaverWindow(self, index)
            window.show_all()
            if screen is not None:
                window.fullscreen_on_monitor(screen, index)
            self.savers.append(window)
        if self.savers:
            self.savers[0].present()
            GLib.timeout_add(150, self._grab_input)
            self._cookie = self.inhibit(
                self.savers[0],
                Gtk.ApplicationInhibitFlags.IDLE,
                "Flapclock screensaver is showing",
            )

    def dismiss_saver(self) -> None:
        if not self._saver_on:
            return
        self._saver_on = False
        seat = Gdk.Display.get_default().get_default_seat()
        for window in self.savers:
            gdk_window = window.get_window()
            if gdk_window is not None and seat is not None:
                seat.ungrab()
            window.destroy()
        self.savers.clear()
        if self._cookie:
            self.uninhibit(self._cookie)
            self._cookie = 0
        if self.screensaver_only:
            self.quit()
            return
        if self.widget is not None:
            self.widget.show_all()
        self.arm_idle_watch()

    def note_motion(self, x: float, y: float) -> None:
        if not self._saver_on:
            return
        if time.monotonic() - self._saver_started < _MOTION_ARM_SECONDS:
            self._motion_origin = (x, y)
            return
        if self._motion_origin is None:
            self._motion_origin = (x, y)
            return
        dx = x - self._motion_origin[0]
        dy = y - self._motion_origin[1]
        if dx * dx + dy * dy >= _MOTION_PIXELS * _MOTION_PIXELS:
            self.dismiss_saver()

    def _grab_input(self) -> bool:
        if not self.savers:
            return False
        window = self.savers[0].get_window()
        seat = Gdk.Display.get_default().get_default_seat()
        if window is None or seat is None:
            return False
        cursor = Gdk.Cursor.new_for_display(window.get_display(), Gdk.CursorType.BLANK_CURSOR)
        seat.grab(window, Gdk.SeatCapabilities.ALL, True, cursor, None, None)
        return False

    def arm_idle_watch(self) -> None:
        self._clear_idle_watch()
        if self.screensaver_only or self._saver_on or self.config.idle_minutes <= 0:
            return
        if not self._ensure_idle_proxy():
            return
        milliseconds = self.config.idle_minutes * 60 * 1000
        try:
            result = self._proxy.call_sync(
                "AddIdleWatch",
                GLib.Variant("(t)", (milliseconds,)),
                Gio.DBusCallFlags.NONE,
                -1,
                None,
            )
        except GLib.Error as exc:
            self._proxy_failed = True
            self._proxy = None
            print(f"flapclock: 無法設定閒置監看（{exc}）。", file=sys.stderr)
            return
        self._watch_id = int(result.unpack()[0])

    def _clear_idle_watch(self) -> None:
        if self._watch_id is None or self._proxy is None:
            self._watch_id = None
            return
        try:
            self._proxy.call_sync(
                "RemoveWatch",
                GLib.Variant("(u)", (self._watch_id,)),
                Gio.DBusCallFlags.NONE,
                -1,
                None,
            )
        except GLib.Error:
            pass
        self._watch_id = None

    def _ensure_idle_proxy(self) -> bool:
        if self._proxy is not None:
            return True
        if self._proxy_failed:
            return False
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            self._proxy = Gio.DBusProxy.new_sync(
                bus,
                Gio.DBusProxyFlags.NONE,
                None,
                "org.gnome.Mutter.IdleMonitor",
                "/org/gnome/Mutter/IdleMonitor/Core",
                "org.gnome.Mutter.IdleMonitor",
                None,
            )
            self._proxy.connect("g-signal", self._on_idle_signal)
        except GLib.Error as exc:
            self._proxy_failed = True
            print(
                f"flapclock: 這個工作階段沒有 GNOME 閒置監看（{exc}）。"
                "仍可從選單或 flapclock --screensaver 開啟。",
                file=sys.stderr,
            )
            return False
        return True

    def _on_idle_signal(self, _proxy, _sender, signal: str, params) -> None:
        if signal != "WatchFired" or self._watch_id is None:
            return
        fired = int(params.unpack()[0])
        if fired != self._watch_id:
            return
        self._watch_id = None
        self.show_saver()


class WidgetWindow(Gtk.Window):
    def __init__(self, app: FlapclockApp) -> None:
        super().__init__(title="Flapclock", application=app, type=Gtk.WindowType.TOPLEVEL)
        self.app = app
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_keep_above(app.config.keep_above)
        self.stick()
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_app_paintable(True)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.connect("screen-changed", self._update_visual)
        self.connect("delete-event", self._on_delete)
        self.connect("configure-event", self._on_configure)
        self._update_visual()

        self.area = Gtk.DrawingArea()
        self.area.connect("draw", self._draw)
        self.area.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.SCROLL_MASK
            | Gdk.EventMask.SMOOTH_SCROLL_MASK
        )
        self.area.connect("button-press-event", self._on_button)
        self.area.connect("scroll-event", self._on_scroll)
        self.add(self.area)
        self.apply_size()
        self._place()
        self._position_source = None

    def _update_visual(self, *_args) -> None:
        screen = self.get_screen()
        visual = screen.get_rgba_visual() if screen is not None else None
        if visual is not None:
            self.set_visual(visual)

    def apply_size(self) -> None:
        width, height = widget_size(self.app.config.scale)
        self.set_size_request(width, height)
        self.resize(width, height)

    def _place(self) -> None:
        if self.app.config.x is not None and self.app.config.y is not None and not _is_wayland():
            self.move(self.app.config.x, self.app.config.y)
            return
        screen = self.get_screen()
        if screen is None:
            return
        monitor = screen.get_primary_monitor()
        geometry = screen.get_monitor_geometry(monitor)
        width, height = widget_size(self.app.config.scale)
        self.move(geometry.x + geometry.width - width - 48, geometry.y + geometry.height - height - 96)

    def _draw(self, _widget, cr) -> bool:
        width = self.get_allocated_width()
        height = self.get_allocated_height()
        draw_face(cr, width, height, self.app.face, transparent_backdrop=True)
        return False

    def _on_button(self, _widget, event) -> bool:
        if event.button == 1 and event.type == Gdk.EventType.BUTTON_PRESS:
            self.begin_move_drag(int(event.button), int(event.x_root), int(event.y_root), event.time)
            return True
        if event.button == 2 and event.type == Gdk.EventType.BUTTON_PRESS:
            self.app.show_saver()
            return True
        if event.button == 3 and event.type == Gdk.EventType.BUTTON_PRESS:
            self._popup(event)
            return True
        return False

    def _on_scroll(self, _widget, event) -> bool:
        direction = 0.0
        if event.direction == Gdk.ScrollDirection.UP:
            direction = 1
        elif event.direction == Gdk.ScrollDirection.DOWN:
            direction = -1
        elif event.direction == Gdk.ScrollDirection.SMOOTH:
            direction = -event.delta_y
        if direction == 0:
            return False
        self.app.adjust_scale(1.08 if direction > 0 else 1 / 1.08)
        return True

    def _popup(self, event) -> None:
        menu = Gtk.Menu()
        hour = Gtk.CheckMenuItem(label="24 小時制")
        hour.set_active(self.app.config.hour24)
        hour.connect("toggled", lambda item: self.app.set_hour24(item.get_active()))
        menu.append(hour)

        above = Gtk.CheckMenuItem(label="保持在最上層")
        above.set_active(self.app.config.keep_above)
        above.connect("toggled", lambda item: self.app.set_keep_above(item.get_active()))
        menu.append(above)

        menu.append(Gtk.SeparatorMenuItem())
        idle_root = Gtk.MenuItem(label="閒置後啟動")
        idle_menu = Gtk.Menu()
        idle_root.set_submenu(idle_menu)
        radios = []
        group = None
        for label, minutes in IDLE_CHOICES:
            item = Gtk.RadioMenuItem(label=label) if group is None else Gtk.RadioMenuItem(label=label, group=group)
            if group is None:
                group = item
            radios.append((item, minutes))
            idle_menu.append(item)
        for item, minutes in radios:
            item.set_active(self.app.config.idle_minutes == minutes)
        for item, minutes in radios:
            item.connect("toggled", self._make_idle_handler(minutes))
        menu.append(idle_root)

        menu.append(Gtk.SeparatorMenuItem())
        start = Gtk.MenuItem(label="立即啟動螢幕保護程式")
        start.connect("activate", lambda *_args: self.app.show_saver())
        menu.append(start)
        quit_item = Gtk.MenuItem(label="結束")
        quit_item.connect("activate", lambda *_args: self.app.quit())
        menu.append(quit_item)
        menu.show_all()
        menu.popup_at_pointer(event)

    def _make_idle_handler(self, minutes: int):
        def handler(item: Gtk.RadioMenuItem) -> None:
            if item.get_active():
                self.app.set_idle_minutes(minutes)
        return handler

    def _on_configure(self, _widget, event) -> bool:
        if _is_wayland():
            return False
        if self._position_source:
            GLib.source_remove(self._position_source)
        x, y = int(event.x), int(event.y)
        self._position_source = GLib.timeout_add(400, self._save_position, x, y)
        return False

    def _save_position(self, x: int, y: int) -> bool:
        self._position_source = None
        self.app.remember_position(x, y)
        return False

    def _on_delete(self, *_args) -> bool:
        self.app.quit()
        return False


class SaverWindow(Gtk.Window):
    def __init__(self, app: FlapclockApp, monitor: int) -> None:
        super().__init__(title="Flapclock", application=app, type=Gtk.WindowType.TOPLEVEL)
        self.app = app
        self.monitor = monitor
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.area = Gtk.DrawingArea()
        self.area.connect("draw", self._draw)
        self.add(self.area)
        mask = (
            Gdk.EventMask.KEY_PRESS_MASK
            | Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )
        self.add_events(mask)
        self.area.add_events(mask)
        self.connect("key-press-event", self._dismiss)
        self.connect("button-press-event", self._dismiss)
        self.connect("motion-notify-event", self._motion)
        self.area.connect("button-press-event", self._dismiss)
        self.area.connect("motion-notify-event", self._motion)
        self.connect("realize", self._blank_cursor)
        self.connect("delete-event", self._dismiss)

    def _draw(self, _widget, cr) -> bool:
        draw_face(
            cr,
            self.get_allocated_width(),
            self.get_allocated_height(),
            self.app.face,
            transparent_backdrop=False,
        )
        return False

    def _blank_cursor(self, *_args) -> None:
        gdk_window = self.get_window()
        if gdk_window is None:
            return
        cursor = Gdk.Cursor.new_for_display(gdk_window.get_display(), Gdk.CursorType.BLANK_CURSOR)
        gdk_window.set_cursor(cursor)
        child = self.area.get_window()
        if child is not None:
            child.set_cursor(cursor)

    def _motion(self, _widget, event) -> bool:
        self.app.note_motion(event.x_root, event.y_root)
        return True

    def _dismiss(self, *_args) -> bool:
        self.app.dismiss_saver()
        return True


def _is_wayland() -> bool:
    display = Gdk.Display.get_default()
    if display is None:
        return False
    name = display.get_name() or ""
    return "wayland" in name.lower()
