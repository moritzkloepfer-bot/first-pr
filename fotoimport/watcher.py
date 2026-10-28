"""Autostart-Wächter: erkennt angesteckte Android-Handys und führt zur Dateiübertragung."""
from __future__ import annotations

import subprocess
import sys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from . import gui, phone  # noqa: E402

POLL_SECONDS = 2
MTP_ONLY = "mtp"  # Handy hängt schon als Laufwerk da, ohne dass wir es per USB erkannt haben


class Watcher:
    def __init__(self, launch=None):
        self.launch = launch or self._launch_import
        self.sessions: dict[str, str] = {}  # Gerät -> 'hint' | 'launched' | 'dismissed'
        self.dialog: Gtk.Window | None = None

    @staticmethod
    def _launch_import() -> None:
        subprocess.Popen([sys.executable, "-m", "fotoimport", "importieren"],
                         start_new_session=True)

    def poll(self) -> bool:
        devices = set(phone.android_usb_devices())
        storages = phone.mtp_storages()
        if storages and not devices:
            devices = {MTP_ONLY}

        for gone in set(self.sessions) - devices:  # Kabel abgezogen
            del self.sessions[gone]
        if not devices:
            self._close_dialog()
            return True

        for dev in devices:
            state = self.sessions.get(dev)
            if state in ("launched", "dismissed"):
                continue
            if storages:
                self.sessions[dev] = "launched"
                self._close_dialog()
                self.launch()
            elif state is None:
                self.sessions[dev] = "hint"
                self._show_dialog(dev)
        return True

    def _show_dialog(self, dev: str) -> None:
        if self.dialog:
            return
        win = Gtk.Window(title="Handy erkannt")
        win.set_border_width(18)
        win.set_keep_above(True)
        win.set_position(Gtk.WindowPosition.CENTER)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        title = Gtk.Label(xalign=0)
        title.set_markup('<span size="x-large">Handy erkannt</span>')
        box.pack_start(title, False, False, 0)
        box.pack_start(Gtk.Label(
            label="Um Fotos zu holen, muss am Handy die Dateiübertragung eingeschaltet werden:\n\n"
                  + gui.PHONE_STEPS, xalign=0, wrap=True), False, False, 0)
        box.pack_start(Gtk.Label(
            label="Sobald das Handy bereit ist, öffnet sich dieses Fenster von selbst.",
            xalign=0, wrap=True), False, False, 0)
        later = Gtk.Button(label="Nur laden, später")
        later.connect("clicked", lambda _b, d=dev: self._dismiss(d))
        box.pack_end(later, False, False, 0)
        win.add(box)
        win.connect("delete-event", lambda _w, _e, d=dev: self._dismiss(d) or False)
        win.show_all()
        self.dialog = win

    def _dismiss(self, dev: str) -> None:
        self.sessions[dev] = "dismissed"
        self._close_dialog()

    def _close_dialog(self) -> None:
        win, self.dialog = self.dialog, None
        if win:
            win.destroy()


def run() -> int:
    lock = gui.single_instance_lock("fotoimport-waechter")
    if lock is None:
        return 0
    watcher = Watcher()
    GLib.timeout_add_seconds(POLL_SECONDS, watcher.poll)
    Gtk.main()
    return 0
