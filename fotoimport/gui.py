"""Import-Fenster: führt in wenigen Schritten vom Handy in den passenden Ordner."""
from __future__ import annotations

import datetime as dt
import fcntl
import os
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, Gio, GLib, Gtk  # noqa: E402

from . import core, phone  # noqa: E402

TITLE = "Fotos vom Handy holen"

PHONE_STEPS = (
    "1. Handy entsperren.\n"
    "2. Am Handy oben herunterwischen.\n"
    "3. Auf die Meldung „USB lädt dieses Gerät“ (oder „Dieses Gerät wird über USB geladen“) tippen.\n"
    "4. „Dateiübertragung“ wählen.\n\n"
    "Klappt es nicht? Dann ein anderes USB-Kabel probieren (manche Kabel können nur laden)."
)

PAGES = ("setup", "wait", "list", "target", "copy", "done")


def single_instance_lock(name: str):
    """Verhindert, dass das Fenster zweimal offen ist. Gibt die Sperre zurück oder None."""
    runtime = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    fh = open(Path(runtime) / f"{name}.lock", "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return None
    return fh


def _label(text: str, markup: bool = False, size: str | None = None) -> Gtk.Label:
    lab = Gtk.Label(xalign=0, wrap=True)
    if markup or size:
        lab.set_markup(text if markup else f'<span size="{size}">{GLib.markup_escape_text(text)}</span>')
    else:
        lab.set_text(text)
    return lab


def _page() -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    box.set_border_width(18)
    return box


class ImportWindow(Gtk.Window):
    def __init__(self, state: core.State, force_setup: bool = False):
        super().__init__(title=TITLE)
        self.state = state
        self.items: list[core.Item] = []
        self.storages: list[Path] = []
        self.dest: Path | None = None
        self.existing_dir: Path | None = None
        self.cancel_flag = threading.Event()
        self.closed = False
        self.set_default_size(720, 560)
        self.connect("destroy", self._on_destroy)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.add(self.stack)
        self._build_setup()
        self._build_wait()
        self._build_list()
        self._build_target()
        self._build_copy()
        self._build_done()

        self.show_all()  # Gtk.Stack wechselt nur zu sichtbaren Seiten
        if force_setup or not state.configured:
            self.show_page("setup")
        else:
            self.start_waiting()

    # ------------------------------------------------------------ Grundgerüst

    def show_page(self, name: str) -> None:
        self.stack.set_visible_child_name(name)

    def _on_destroy(self, *_):
        self.closed = True
        self.cancel_flag.set()

    def _run_in_thread(self, work, done):
        """Arbeit im Hintergrund (Handy ist langsam), Ergebnis wieder im Fenster."""
        def runner():
            try:
                result, error = work(), None
            except Exception as e:  # noqa: BLE001
                result, error = None, e
            if not self.closed:
                GLib.idle_add(done, result, error)
        threading.Thread(target=runner, daemon=True).start()

    # ------------------------------------------------------- 0. Einrichtung

    def _build_setup(self) -> None:
        page = _page()
        page.pack_start(_label("Einrichtung", size="x-large"), False, False, 0)
        page.pack_start(_label(
            "Wo liegt die Fotosammlung, und ab wann sollen Fotos vom Handy als neu gelten? "
            "Alles davor wird nicht angeboten."), False, False, 0)

        page.pack_start(_label("Hauptordner der Fotos:"), False, False, 0)
        self.root_button = Gtk.FileChooserButton(title="Hauptordner wählen",
                                                 action=Gtk.FileChooserAction.SELECT_FOLDER)
        default_root = self.state.root and Path(self.state.root)
        for guess in (default_root, Path.home() / "Bilder", Path.home() / "Pictures", Path.home()):
            if guess and Path(guess).is_dir():
                self.root_button.set_current_folder(str(guess))
                break
        page.pack_start(self.root_button, False, False, 0)

        page.pack_start(_label("Fotos ab diesem Datum importieren:"), False, False, 0)
        self.calendar = Gtk.Calendar()
        past = dt.date.today() - dt.timedelta(days=30)
        self.calendar.select_month(past.month - 1, past.year)
        self.calendar.select_day(past.day)
        page.pack_start(self.calendar, False, False, 0)

        self.baseline_check = Gtk.CheckButton(
            label="Vorhandene Fotos in der Sammlung abgleichen (empfohlen)", active=True)
        page.pack_start(self.baseline_check, False, False, 0)

        save = Gtk.Button(label="Speichern und weiter")
        save.connect("clicked", self._on_setup_save)
        page.pack_end(save, False, False, 0)
        self.stack.add_named(page, "setup")

    def _on_setup_save(self, _btn) -> None:
        root = Path(self.root_button.get_filename() or Path.home())
        y, m, d = self.calendar.get_date()
        self.state.configure(root, dt.date(y, m + 1, d), self.baseline_check.get_active())
        self.start_waiting()

    # ------------------------------------------------------- 1. Handy suchen

    def _build_wait(self) -> None:
        page = _page()
        self.wait_title = _label("", size="x-large")
        page.pack_start(self.wait_title, False, False, 0)
        spinner = Gtk.Spinner()
        spinner.start()
        page.pack_start(spinner, False, False, 0)
        self.wait_text = _label("")
        page.pack_start(self.wait_text, False, False, 0)
        self.stack.add_named(page, "wait")

    def start_waiting(self) -> None:
        self.wait_title.set_markup('<span size="x-large">Handy suchen …</span>')
        self.wait_text.set_text(
            "Bitte das Handy mit dem Kabel an den Computer anschließen.\n\n" + PHONE_STEPS)
        self.show_page("wait")
        GLib.timeout_add_seconds(2, self._poll_phone)

    def _poll_phone(self) -> bool:
        if self.closed or self.stack.get_visible_child_name() != "wait":
            return False
        storages = phone.mtp_storages()
        if not storages:
            return True
        self.storages = storages
        self.wait_title.set_markup('<span size="x-large">Handy gefunden – suche neue Fotos …</span>')
        self.wait_text.set_text("Das kann bei vielen Fotos einen Moment dauern.")
        self._run_in_thread(self._scan, self._on_scanned)
        return False

    def _scan(self) -> list[core.Item]:
        items = [i for s in self.storages for i in core.scan_storage(s)]
        return core.collect_new(items, self.state)

    def _on_scanned(self, items, error) -> bool:
        if error is not None:
            self.wait_text.set_text(f"Das Handy konnte nicht gelesen werden:\n{error}\n\n" + PHONE_STEPS)
            GLib.timeout_add_seconds(3, self._retry_after_error)
            return False
        self.items = items
        if not items:
            self._show_done("Keine neuen Fotos oder Videos auf dem Handy. Alles ist schon importiert.")
            return False
        self._fill_list()
        self.show_page("list")
        return False

    def _retry_after_error(self) -> bool:
        if not self.closed:
            self.start_waiting()
        return False

    # ------------------------------------------------------ 2. Auswahl

    def _build_list(self) -> None:
        page = _page()
        self.list_title = _label("", size="large")
        page.pack_start(self.list_title, False, False, 0)
        page.pack_start(_label(
            "Mit Häkchen = wird importiert. Fotos, die vermutlich doppelt sind, sind nicht angehakt."),
            False, False, 0)

        # Spalten: angehakt, Vorschau, Name, Herkunft, Datum, Hinweis, Index
        self.store = Gtk.ListStore(bool, GdkPixbuf.Pixbuf, str, str, str, str, int)
        view = Gtk.TreeView(model=self.store)
        toggle = Gtk.CellRendererToggle()
        toggle.connect("toggled", self._on_row_toggled)
        view.append_column(Gtk.TreeViewColumn("Import", toggle, active=0))
        view.append_column(Gtk.TreeViewColumn("Vorschau", Gtk.CellRendererPixbuf(), pixbuf=1))
        for title, col in (("Datei", 2), ("Herkunft", 3), ("Datum", 4), ("Hinweis", 5)):
            view.append_column(Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=col))
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.add(view)
        page.pack_start(scroll, True, True, 0)

        row = Gtk.Box(spacing=8)
        for text, value in (("Alle auswählen", True), ("Keine auswählen", False)):
            b = Gtk.Button(label=text)
            b.connect("clicked", lambda _b, v=value: self._select_all(v))
            row.pack_start(b, False, False, 0)
        self.next_button = Gtk.Button(label="Weiter")
        self.next_button.connect("clicked", self._on_list_next)
        row.pack_end(self.next_button, False, False, 0)
        page.pack_end(row, False, False, 0)
        self.stack.add_named(page, "list")

        self.placeholder = Gtk.IconTheme.get_default().load_icon("image-x-generic", 48, 0) \
            if Gtk.IconTheme.get_default().has_icon("image-x-generic") else None

    def _fill_list(self) -> None:
        self.store.clear()
        for idx, it in enumerate(self.items):
            self.store.append([
                it.selected, self.placeholder, it.name, it.source,
                it.capture.strftime("%d.%m.%Y %H:%M"),
                "möglicherweise doppelt" if it.maybe_duplicate else "", idx,
            ])
        self._update_counts()
        threading.Thread(target=self._load_thumbnails, daemon=True).start()

    def _load_thumbnails(self) -> None:
        for row_no, it in enumerate(self.items):
            if self.closed:
                return
            if not it.is_image:
                continue
            try:
                pix = GdkPixbuf.Pixbuf.new_from_file_at_size(str(it.path), 64, 64)
                pix = pix.apply_embedded_orientation() or pix
            except GLib.Error:
                continue  # z. B. HEIC ohne Unterstützung: Platzhalter bleibt
            GLib.idle_add(self._set_thumbnail, row_no, pix)

    def _set_thumbnail(self, row_no: int, pix) -> bool:
        if not self.closed:
            self.store[row_no][1] = pix
        return False

    def _on_row_toggled(self, _renderer, path) -> None:
        row = self.store[path]
        row[0] = not row[0]
        self.items[row[6]].selected = row[0]
        self._update_counts()

    def _select_all(self, value: bool) -> None:
        for row in self.store:
            row[0] = value
            self.items[row[6]].selected = value
        self._update_counts()

    def _selected(self) -> list[core.Item]:
        return [i for i in self.items if i.selected]

    def _update_counts(self) -> None:
        n = len(self._selected())
        self.list_title.set_markup(
            f'<span size="large">{len(self.items)} neue Fotos und Videos gefunden, '
            f"{n} ausgewählt</span>")
        self.next_button.set_sensitive(n > 0)

    def _on_list_next(self, _btn) -> None:
        self._prepare_target()
        self.show_page("target")

    # ------------------------------------------------------ 3. Ziel

    def _build_target(self) -> None:
        page = _page()
        page.pack_start(_label("Wohin sollen die Fotos?", size="x-large"), False, False, 0)

        self.radio_existing = Gtk.RadioButton.new_with_label_from_widget(
            None, "In einen bestehenden Ordner")
        page.pack_start(self.radio_existing, False, False, 0)
        row = Gtk.Box(spacing=8)
        row.set_margin_start(28)
        self.existing_label = _label("")
        self.existing_label.set_line_wrap(False)
        self.existing_label.set_ellipsize(3)  # Pango.EllipsizeMode.MIDDLE
        row.pack_start(self.existing_label, True, True, 0)
        choose = Gtk.Button(label="Ordner wählen …")
        choose.connect("clicked", self._on_choose_existing)
        row.pack_start(choose, False, False, 0)
        page.pack_start(row, False, False, 0)

        self.radio_new = Gtk.RadioButton.new_with_label_from_widget(
            self.radio_existing, "Neuen Ordner anlegen")
        page.pack_start(self.radio_new, False, False, 0)
        self.new_hint = _label("")
        self.new_hint.set_margin_start(28)
        page.pack_start(self.new_hint, False, False, 0)
        self.new_entry = Gtk.Entry()
        self.new_entry.set_margin_start(28)
        self.new_entry.connect("changed", lambda *_: self.radio_new.set_active(True))
        page.pack_start(self.new_entry, False, False, 0)

        row = Gtk.Box(spacing=8)
        back = Gtk.Button(label="Zurück")
        back.connect("clicked", lambda _b: self.show_page("list"))
        row.pack_start(back, False, False, 0)
        self.go_button = Gtk.Button(label="Importieren")
        self.go_button.connect("clicked", self._on_go)
        row.pack_end(self.go_button, False, False, 0)
        page.pack_end(row, False, False, 0)
        self.stack.add_named(page, "target")

    def _prepare_target(self) -> None:
        root = Path(self.state.root)
        year = core.year_dir(root)  # legt den Jahresordner an, falls er fehlt
        self.year_path = year
        self.existing_dir = year
        self.existing_label.set_text(str(year))
        self.new_entry.set_text(core.suggest_folder_name(root))
        self.radio_existing.set_active(True)
        self.new_hint.set_text(f"Wird angelegt in: {year}")
        self.go_button.set_label(f"{len(self._selected())} Dateien importieren")

    def _on_choose_existing(self, _btn) -> None:
        dialog = Gtk.FileChooserDialog(
            title="Zielordner wählen", parent=self, action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons("Abbrechen", Gtk.ResponseType.CANCEL, "Diesen Ordner wählen", Gtk.ResponseType.OK)
        dialog.set_current_folder(str(self.existing_dir or self.year_path))
        if dialog.run() == Gtk.ResponseType.OK:
            self.existing_dir = Path(dialog.get_filename())
            self.existing_label.set_text(str(self.existing_dir))
            self.radio_existing.set_active(True)
        dialog.destroy()

    def _on_go(self, _btn) -> None:
        try:
            if self.radio_new.get_active():
                self.dest = core.create_folder(self.year_path, self.new_entry.get_text())
            else:
                self.dest = self.existing_dir
        except (ValueError, OSError) as e:
            dialog = Gtk.MessageDialog(parent=self, message_type=Gtk.MessageType.WARNING,
                                       buttons=Gtk.ButtonsType.OK,
                                       text="Der Ordner konnte nicht angelegt werden.")
            dialog.format_secondary_text(str(e))
            dialog.run()
            dialog.destroy()
            return
        self._start_copy()

    # ------------------------------------------------------ 4. Kopieren

    def _build_copy(self) -> None:
        page = _page()
        page.pack_start(_label("Fotos werden kopiert …", size="x-large"), False, False, 0)
        self.progress = Gtk.ProgressBar(show_text=True)
        page.pack_start(self.progress, False, False, 0)
        self.copy_label = _label("")
        page.pack_start(self.copy_label, False, False, 0)
        page.pack_start(_label("Bitte das Kabel nicht abziehen, bis „Fertig“ erscheint."), False, False, 0)
        cancel = Gtk.Button(label="Abbrechen")
        cancel.connect("clicked", lambda _b: self.cancel_flag.set())
        page.pack_end(cancel, False, False, 0)
        self.stack.add_named(page, "copy")

    def _start_copy(self) -> None:
        items = self._selected()
        prefix = [0]
        for it in items:
            prefix.append(prefix[-1] + it.size)
        total = prefix[-1] or 1
        position = {id(it): n for n, it in enumerate(items)}
        self.cancel_flag.clear()
        self.show_page("copy")

        def on_file(n, item):
            GLib.idle_add(self._copy_ui, n, len(items), item.name, prefix[n - 1] / total)

        def on_bytes(item, b):
            GLib.idle_add(self._copy_bytes, (prefix[position[id(item)]] + b) / total)

        def work():
            return core.import_items(items, self.dest, self.state, on_file=on_file,
                                     on_bytes=on_bytes, cancelled=self.cancel_flag.is_set)

        self._run_in_thread(work, self._on_copied)

    def _copy_ui(self, n, count, name, fraction) -> bool:
        self.copy_label.set_text(f"Datei {n} von {count}: {name}")
        self._copy_bytes(fraction)
        return False

    def _copy_bytes(self, fraction: float) -> bool:
        self.progress.set_fraction(min(fraction, 1.0))
        self.progress.set_text(f"{int(min(fraction, 1.0) * 100)} %")
        return False

    def _on_copied(self, result, error) -> bool:
        if error is not None:
            self._show_done(f"Beim Kopieren ist ein Fehler aufgetreten:\n{error}", ok=False)
            return False
        lines = []
        if result.cancelled:
            lines.append("Abgebrochen. Beim nächsten Mal geht es mit den übrigen Fotos weiter.")
        else:
            lines.append("Fertig!")
        lines.append(f"{result.copied} Dateien kopiert nach:\n{self.dest}")
        if result.existed:
            lines.append(f"{result.existed} waren schon vorhanden und wurden nicht noch einmal kopiert.")
        if result.failed:
            lines.append(f"{len(result.failed)} Dateien konnten nicht kopiert werden:")
            lines += [f"  • {n}: {why}" for n, why in result.failed[:8]]
        self._show_done("\n\n".join(lines), ok=not result.failed, folder=self.dest)
        return False

    # ------------------------------------------------------ 5. Fertig

    def _build_done(self) -> None:
        page = _page()
        self.done_label = _label("")
        page.pack_start(self.done_label, False, False, 0)
        row = Gtk.Box(spacing=8)
        self.open_button = Gtk.Button(label="Ordner öffnen")
        self.open_button.connect("clicked", self._on_open_folder)
        row.pack_start(self.open_button, False, False, 0)
        close = Gtk.Button(label="Schließen")
        close.connect("clicked", lambda _b: self.destroy())
        row.pack_end(close, False, False, 0)
        page.pack_end(row, False, False, 0)
        self.stack.add_named(page, "done")

    def _show_done(self, text: str, ok: bool = True, folder: Path | None = None) -> None:
        self.done_label.set_markup(
            f'<span size="large">{GLib.markup_escape_text(text)}</span>')
        self._folder = folder
        self.open_button.set_visible(folder is not None)
        self.show_page("done")
        self.show_all()

    def _on_open_folder(self, _btn) -> None:
        if self._folder:
            Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(str(self._folder)).get_uri(), None)


def run(force_setup: bool = False) -> int:
    lock = single_instance_lock("fotoimport-gui")
    if lock is None:
        return 0  # Fenster ist schon offen
    win = ImportWindow(core.State(), force_setup=force_setup)
    win.connect("destroy", Gtk.main_quit)
    Gtk.main()
    return 0
