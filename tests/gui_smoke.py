"""Klickt das Import-Fenster einmal komplett durch (braucht GTK und ein X-Display, z. B. xvfb-run)."""
import datetime as dt
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import make_phone  # noqa: E402

tmp = Path(tempfile.mkdtemp())
os.environ["FOTOIMPORT_HOME"] = str(tmp / "home")
os.environ["FOTOIMPORT_FAKE_PHONE"] = str(make_phone(tmp))
root = tmp / "Bilder"
root.mkdir()

import gi  # noqa: E402

gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk  # noqa: E402

from fotoimport import core, gui  # noqa: E402

state = core.State()
state.configure(root, dt.date.today(), baseline=False)
win = gui.ImportWindow(state)
win.connect("destroy", Gtk.main_quit)
win.show_all()


def pump(seconds, until=None):
    end = GLib.get_monotonic_time() + seconds * 1_000_000
    while GLib.get_monotonic_time() < end:
        while Gtk.events_pending():
            Gtk.main_iteration()
        if until and until():
            return True
    return until is None


def page():
    return win.stack.get_visible_child_name()


assert pump(8, lambda: page() == "list"), f"Liste nicht erreicht, Seite: {page()}"
assert len(win.items) == 5, len(win.items)
win._on_list_next(None)
assert page() == "target"
year = dt.date.today().year
assert (root / str(year)).is_dir(), "Jahresordner wurde nicht angelegt"
win.new_entry.set_text("Test-Ereignis")
assert win.radio_new.get_active()
win._on_go(None)
assert pump(8, lambda: page() == "done"), f"Fertig nicht erreicht, Seite: {page()}"
target = root / str(year) / "Test-Ereignis"
files = sorted(p.name for p in target.iterdir())
print("kopiert:", files)
assert len(files) == 5
print(win.done_label.get_text())
print("GUI-Smoke-Test ok")
