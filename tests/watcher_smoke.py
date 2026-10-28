"""Prüft den Ablauf des Wächters mit simulierten USB- und MTP-Meldungen (braucht GTK und ein X-Display)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gi  # noqa: E402

gi.require_version("Gtk", "3.0")

from fotoimport import phone, watcher  # noqa: E402

usb, mtp, launched = {}, [], []
phone.android_usb_devices = lambda: dict(usb)
phone.mtp_storages = lambda: list(mtp)
w = watcher.Watcher(launch=lambda: launched.append(1))

w.poll()
assert w.dialog is None and not launched, "ohne Handy darf nichts passieren"

usb["1-2"] = "Pixel"  # eingesteckt, nur laden
w.poll()
assert w.dialog is not None and not launched, "Anleitung muss erscheinen"
w.poll()
assert not launched

mtp.append(Path("/x"))  # Dateiübertragung eingeschaltet
w.poll()
assert w.dialog is None and launched == [1], "Import muss starten, Dialog verschwinden"
w.poll()
assert launched == [1], "nur einmal starten"

usb.clear(); mtp.clear()  # Kabel ab
w.poll()
usb["1-2"] = "Pixel"  # wieder eingesteckt, nur laden, diesmal 'später'
w.poll()
assert w.dialog is not None
w._dismiss("1-2")
w.poll()
assert w.dialog is None and launched == [1], "nach 'später' keine Anleitung mehr"

usb.clear(); w.poll(); usb["1-2"] = "Pixel"; mtp.append(Path("/x"))  # schon im Übertragungsmodus
w.poll()
assert launched == [1, 1] and w.dialog is None
print("Wächter-Smoke-Test ok")
