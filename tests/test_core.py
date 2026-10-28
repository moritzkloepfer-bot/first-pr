import datetime as dt
from pathlib import Path  # noqa: F401

import pytest
from helpers import make_phone

from fotoimport import core


@pytest.fixture
def state(tmp_path):
    return core.State(tmp_path / "state" / "state.json")


def test_scan_finds_only_wanted_files(tmp_path):
    names = {i.name for i in core.scan_storage(make_phone(tmp_path))}
    assert names == {"IMG_20261015_101500.jpg", "VID_20261016_120000.mp4",
                     "IMG-20261015-WA0001.jpg", "VID-20261017-WA0003.mp4", "bild.png"}


def test_capture_time_from_filename():
    assert core.capture_time("IMG_20261015_101500.jpg", 0) == dt.datetime(2026, 10, 15, 10, 15, 0)
    assert core.capture_time("foo.jpg", 86400).year == 1970


def test_new_items_exclude_imported_and_old(tmp_path, state):
    root = tmp_path / "Bilder"
    root.mkdir()
    state.configure(root, dt.date.today(), baseline=False)
    items = core.scan_storage(make_phone(tmp_path))
    new = core.collect_new(items, state)
    assert len(new) == 5
    state.imported[new[0].key] = "x"
    assert len(core.collect_new(items, state)) == 4
    state.start_date = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    assert core.collect_new(items, state) == []


def test_baseline_marks_existing_collection(tmp_path, state):
    root = tmp_path / "Bilder"
    (root / "2026" / "Jan-Feb").mkdir(parents=True)
    (root / "2026/Jan-Feb/IMG_20261015_101500.jpg").write_bytes(b"a" * 100)
    state.configure(root, dt.date.today(), baseline=True)
    new = core.collect_new(core.scan_storage(make_phone(tmp_path)), state)
    assert "IMG_20261015_101500.jpg" not in {i.name for i in new}
    assert state.baseline_done


def test_possible_duplicates_deselected(tmp_path, state):
    storage = make_phone(tmp_path)
    (storage / "Download" / "IMG_20261015_101500.png").write_bytes(b"d")
    state.configure(tmp_path, dt.date.today(), baseline=False)
    new = {i.name: i for i in core.collect_new(core.scan_storage(storage), state)}
    assert not new["IMG_20261015_101500.jpg"].maybe_duplicate
    assert new["IMG_20261015_101500.png"].maybe_duplicate
    assert not new["IMG_20261015_101500.png"].selected


def test_two_month_names(tmp_path):
    assert core.suggest_folder_name(tmp_path, dt.date(2026, 10, 28)) == "Sep-Okt"
    (tmp_path / "2025" / "Mrz-Apr Italien").mkdir(parents=True)
    assert core.suggest_folder_name(tmp_path, dt.date(2026, 3, 5)) == "Mrz-Apr"
    assert core.suggest_folder_name(tmp_path, dt.date(2026, 1, 5)) == "Jan-Feb"


def test_year_dir_created(tmp_path):
    d = core.year_dir(tmp_path, dt.date(2027, 1, 1))
    assert d == tmp_path / "2027" and d.is_dir()


def test_create_folder_sanitizes(tmp_path):
    assert core.create_folder(tmp_path, " Mär/Apr ").name == "Mär-Apr"
    with pytest.raises(ValueError):
        core.create_folder(tmp_path, "  ..  ")


def test_import_copies_never_overwrites_and_resumes(tmp_path, state):
    storage = make_phone(tmp_path)
    state.configure(tmp_path, dt.date.today(), baseline=False)
    items = core.collect_new(core.scan_storage(storage), state)
    dest = tmp_path / "Ziel"
    dest.mkdir()
    (dest / "IMG_20261015_101500.jpg").write_bytes(b"VERSCHIEDEN")  # gleicher Name, anderer Inhalt
    (dest / ".kaputt.jpg.part").write_bytes(b"rest")

    res = core.import_items(items, dest, state)
    assert res.copied == 5 and not res.failed
    assert (dest / "IMG_20261015_101500.jpg").read_bytes() == b"VERSCHIEDEN"
    assert (dest / "IMG_20261015_101500_2.jpg").read_bytes() == b"a" * 100
    assert not list(dest.glob(".*.part"))

    assert core.collect_new(core.scan_storage(storage), state) == []
    # gleicher Inhalt, nochmal erzwungen: nicht doppelt kopiert
    res = core.import_items(items[:1], dest, state)
    assert res.existed == 1 and res.copied == 0


def test_cancel_leaves_no_partial_file(tmp_path, state):
    storage = make_phone(tmp_path)
    state.configure(tmp_path, dt.date.today(), baseline=False)
    items = core.collect_new(core.scan_storage(storage), state)
    dest = tmp_path / "Ziel"
    res = core.import_items(items, dest, state, cancelled=lambda: True)
    assert res.cancelled and not list(dest.iterdir())
