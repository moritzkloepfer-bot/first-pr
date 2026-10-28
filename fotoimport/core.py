"""Kernlogik ohne Oberfläche: Handy-Quellen, Importliste, Zielordner, Kopieren."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

IMAGE_EXT = frozenset({".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp"})
VIDEO_EXT = frozenset({".mp4", ".mov", ".3gp", ".m4v", ".mkv", ".avi", ".webm"})
MEDIA_EXT = IMAGE_EXT | VIDEO_EXT

CHUNK = 1024 * 1024


@dataclass(frozen=True)
class Source:
    label: str
    paths: tuple[str, ...]  # relativ zum Speicher des Handys, mehrere Android-Varianten
    exts: frozenset


# Nur die Dateien direkt im Ordner: WhatsApp/.../Sent und Private sind Unterordner
# und fallen damit automatisch weg.
SOURCES = (
    Source("Kamera", ("DCIM/Camera",), MEDIA_EXT),
    Source(
        "WhatsApp",
        (
            "Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Images",
            "WhatsApp/Media/WhatsApp Images",
            "Android/media/com.whatsapp.w4b/WhatsApp Business/Media/WhatsApp Business Images",
        ),
        IMAGE_EXT,
    ),
    Source(
        "WhatsApp",
        (
            "Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Video",
            "WhatsApp/Media/WhatsApp Video",
            "Android/media/com.whatsapp.w4b/WhatsApp Business/Media/WhatsApp Business Video",
        ),
        VIDEO_EXT,
    ),
    Source("Download", ("Download",), IMAGE_EXT),
)
SOURCE_PRIORITY = {"Kamera": 0, "WhatsApp": 1, "Download": 2}


@dataclass
class Item:
    path: Path
    name: str
    size: int
    mtime: float
    source: str
    capture: dt.datetime
    key: str
    maybe_duplicate: bool = False
    selected: bool = True

    @property
    def is_image(self) -> bool:
        return self.path.suffix.lower() in IMAGE_EXT


_STAMP = re.compile(r"(20\d{2})(\d{2})(\d{2})[_-]?(\d{2})(\d{2})(\d{2})")


def capture_time(name: str, mtime: float) -> dt.datetime:
    m = _STAMP.search(name)
    if m:
        try:
            return dt.datetime(*(int(g) for g in m.groups()))
        except ValueError:
            pass
    return dt.datetime.fromtimestamp(mtime)


def make_key(name: str, size: int, mtime: float) -> str:
    day = dt.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
    return f"{name}|{size}|{day}"


def scan_storage(storage: Path) -> list[Item]:
    items: list[Item] = []
    for src in SOURCES:
        for rel in src.paths:
            folder = storage / rel
            try:
                entries = list(os.scandir(folder))
            except OSError:
                continue
            for e in entries:
                if e.name.startswith("."):  # Android-Papierkorb (.trashed-…) und Temporäres
                    continue
                if Path(e.name).suffix.lower() not in src.exts:
                    continue
                try:
                    if not e.is_file():
                        continue
                    st = e.stat()
                except OSError:
                    continue
                items.append(
                    Item(
                        path=Path(e.path),
                        name=e.name,
                        size=st.st_size,
                        mtime=st.st_mtime,
                        source=src.label,
                        capture=capture_time(e.name, st.st_mtime),
                        key=make_key(e.name, st.st_size, st.st_mtime),
                    )
                )
    return items


class State:
    """Merkt sich Hauptordner, Startdatum und bereits importierte Fotos."""

    def __init__(self, path: Path | None = None):
        if path is None:
            home = Path(os.environ.get("FOTOIMPORT_HOME") or Path.home() / ".local/share/fotoimport")
            path = home / "state.json"
        self.path = path
        self.root: str | None = None
        self.start_date: str | None = None  # YYYY-MM-DD
        self.baseline_done = False
        self.imported: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.root = data.get("root")
        self.start_date = data.get("start_date")
        self.baseline_done = bool(data.get("baseline_done"))
        self.imported = dict(data.get("imported", {}))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(
                {
                    "root": self.root,
                    "start_date": self.start_date,
                    "baseline_done": self.baseline_done,
                    "imported": self.imported,
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
        os.replace(tmp, self.path)

    @property
    def configured(self) -> bool:
        return bool(self.root) and Path(self.root).is_dir()

    def configure(self, root: Path, start: dt.date, baseline: bool = True) -> None:
        self.root = str(root)
        self.start_date = start.isoformat()
        self.baseline_done = not baseline
        self.save()


def index_collection(root: Path) -> set[tuple[str, int]]:
    found: set[tuple[str, int]] = set()
    for base, _dirs, files in os.walk(root):
        for f in files:
            try:
                found.add((f, os.stat(os.path.join(base, f)).st_size))
            except OSError:
                pass
    return found


def collect_new(items: Iterable[Item], state: State) -> list[Item]:
    """Filtert auf neue Fotos (Startdatum, Abgleich, schon importiert), markiert Dubletten."""
    items = list(items)
    if state.start_date:
        start = dt.date.fromisoformat(state.start_date)
        items = [i for i in items if dt.date.fromtimestamp(i.mtime) >= start]

    if not state.baseline_done and state.root and Path(state.root).is_dir():
        have = index_collection(Path(state.root))
        for i in items:
            if (i.name, i.size) in have:
                state.imported.setdefault(i.key, "bereits vorhanden")
        state.baseline_done = True
        state.save()

    new = [i for i in items if i.key not in state.imported]
    _mark_duplicates(new)
    new.sort(key=lambda i: i.capture, reverse=True)
    return new


def _mark_duplicates(items: list[Item]) -> None:
    """Gleiche Aufnahmezeit aus verschiedenen Quellen: nur die Kamera-Version bleibt angehakt."""
    groups: dict[str, list[Item]] = {}
    for i in items:
        groups.setdefault(i.capture.strftime("%Y%m%d%H%M%S"), []).append(i)
    for group in groups.values():
        if len({i.source for i in group}) < 2:
            continue
        group.sort(key=lambda i: SOURCE_PRIORITY.get(i.source, 9))
        for i in group[1:]:
            if i.source != group[0].source:
                i.maybe_duplicate = True
                i.selected = False


# ---------------------------------------------------------------- Zielordner

DEFAULT_PAIRS = ["Jan-Feb", "Mär-Apr", "Mai-Jun", "Jul-Aug", "Sep-Okt", "Nov-Dez"]

_MONTH_ALIASES = {
    1: {"jan", "januar"},
    2: {"feb", "februar"},
    3: {"mär", "mrz", "mar", "mae", "märz", "maerz"},
    4: {"apr", "april"},
    5: {"mai", "may"},
    6: {"jun", "juni"},
    7: {"jul", "juli"},
    8: {"aug", "august"},
    9: {"sep", "sept", "september"},
    10: {"okt", "oct", "oktober"},
    11: {"nov", "november"},
    12: {"dez", "dec", "dezember"},
}
_TOKEN_TO_MONTH = {a: m for m, names in _MONTH_ALIASES.items() for a in names}
_PAIR_RE = re.compile(r"^([^\W\d_]+)-([^\W\d_]+)")


def learn_spellings(root: Path) -> dict[int, str]:
    """Liest aus vorhandenen Ordnern (neueste Jahre zuerst), wie sie die Zweimonatsordner schreibt."""
    spelled: dict[int, str] = {}
    try:
        years = sorted((d for d in root.iterdir() if d.is_dir()), key=lambda d: d.name, reverse=True)
    except OSError:
        return spelled
    for year in years:
        try:
            subdirs = list(year.iterdir())
        except OSError:
            continue
        for d in subdirs:
            m = _PAIR_RE.match(d.name)
            if not m or not d.is_dir():
                continue
            first = _TOKEN_TO_MONTH.get(m.group(1).casefold())
            second = _TOKEN_TO_MONTH.get(m.group(2).casefold())
            if first and second == first + 1 and first % 2 == 1:
                spelled.setdefault((first - 1) // 2, f"{m.group(1)}-{m.group(2)}")
    return spelled


def suggest_folder_name(root: Path, today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    idx = (today.month - 1) // 2
    return learn_spellings(root).get(idx, DEFAULT_PAIRS[idx])


def year_dir(root: Path, today: dt.date | None = None) -> Path:
    """Jahresordner, wird bei Bedarf angelegt."""
    d = root / str((today or dt.date.today()).year)
    d.mkdir(parents=True, exist_ok=True)
    return d


def create_folder(parent: Path, name: str) -> Path:
    name = name.strip().replace(os.sep, "-").strip(". ")
    if not name:
        raise ValueError("Der Ordnername ist leer.")
    target = parent / name
    target.mkdir(parents=True, exist_ok=True)
    return target


# ------------------------------------------------------------------- Kopieren


class Cancelled(Exception):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def _same_content(a: Path, b: Path) -> bool:
    return a.stat().st_size == b.stat().st_size and _sha256(a) == _sha256(b)


def resolve_target(dest_dir: Path, name: str, src: Path) -> tuple[Path, bool]:
    """Liefert (Zielpfad, schon_vorhanden). Überschreibt nie: bei Namensgleichheit wird nummeriert."""
    stem, suffix = os.path.splitext(name)
    n = 1
    while True:
        candidate = dest_dir / (name if n == 1 else f"{stem}_{n}{suffix}")
        if not candidate.exists():
            return candidate, False
        if _same_content(src, candidate):
            return candidate, True
        n += 1


@dataclass
class Result:
    copied: int = 0
    existed: int = 0
    failed: list[tuple[str, str]] = None  # (Name, Grund)
    cancelled: bool = False

    def __post_init__(self):
        if self.failed is None:
            self.failed = []


def copy_item(item: Item, dest_dir: Path, progress: Callable[[int], None] | None = None,
              cancelled: Callable[[], bool] | None = None) -> tuple[Path, bool]:
    """Kopiert unter temporärem Namen und benennt erst nach vollständiger Kopie um."""
    target, existed = resolve_target(dest_dir, item.name, item.path)
    if existed:
        return target, True
    part = target.with_name(f".{target.name}.part")
    done = 0
    try:
        with open(item.path, "rb") as src, open(part, "wb") as out:
            while chunk := src.read(CHUNK):
                if cancelled and cancelled():
                    raise Cancelled
                out.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done)
            out.flush()
            os.fsync(out.fileno())
        if done != item.size or part.stat().st_size != done:
            raise OSError("Datei ist nicht vollständig angekommen")
        try:
            os.utime(part, (item.mtime, item.mtime))
        except OSError:
            pass
        os.replace(part, target)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    return target, False


def import_items(items: list[Item], dest_dir: Path, state: State,
                 on_file: Callable[[int, Item], None] | None = None,
                 on_bytes: Callable[[Item, int], None] | None = None,
                 cancelled: Callable[[], bool] | None = None) -> Result:
    dest_dir.mkdir(parents=True, exist_ok=True)
    for stale in dest_dir.glob(".*.part"):  # Reste eines abgebrochenen Laufs
        stale.unlink(missing_ok=True)
    result = Result()
    for n, item in enumerate(items, 1):
        if cancelled and cancelled():
            result.cancelled = True
            break
        if on_file:
            on_file(n, item)
        try:
            target, existed = copy_item(
                item, dest_dir,
                progress=(lambda b, it=item: on_bytes(it, b)) if on_bytes else None,
                cancelled=cancelled,
            )
        except Cancelled:
            result.cancelled = True
            break
        except OSError as e:
            result.failed.append((item.name, str(e)))
            continue
        state.imported[item.key] = str(target)
        state.save()
        if existed:
            result.existed += 1
        else:
            result.copied += 1
    return result
