"""Handy finden: MTP-Laufwerke (gvfs) und angesteckte Android-Geräte per USB."""
from __future__ import annotations

import os
from pathlib import Path

# USB-Hersteller-Kennungen gängiger Android-Hersteller
ANDROID_VENDORS = {
    "18d1": "Google", "04e8": "Samsung", "12d1": "Huawei", "339b": "Honor",
    "2717": "Xiaomi", "22b8": "Motorola", "0fce": "Sony", "1004": "LG",
    "2a70": "OnePlus", "22d9": "Oppo/Realme", "2d95": "Vivo", "0bb4": "HTC",
    "2e04": "Nokia", "0b05": "ASUS", "17ef": "Lenovo", "19d2": "ZTE",
    "2ae5": "Fairphone", "2970": "Nothing", "0502": "Acer", "04dd": "Sharp",
}


def mtp_storages() -> list[Path]:
    """Speicher (z. B. 'Interner gemeinsamer Speicher') aller eingebundenen MTP-Handys."""
    fake = os.environ.get("FOTOIMPORT_FAKE_PHONE")  # zum Testen: Ordner als Handy
    if fake:
        return [Path(fake)] if Path(fake).is_dir() else []
    storages: list[Path] = []
    for base in (Path(f"/run/user/{os.getuid()}/gvfs"), Path.home() / ".gvfs"):
        try:
            mounts = [m for m in base.iterdir() if m.name.startswith("mtp:")]
        except OSError:
            continue
        for mount in mounts:
            try:
                storages += [s for s in mount.iterdir() if s.is_dir()]
            except OSError:
                pass
    return storages


def _read(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def android_usb_devices() -> dict[str, str]:
    """Angesteckte Android-Handys (auch im Modus 'Nur laden'): {USB-Pfad: Beschreibung}."""
    found: dict[str, str] = {}
    try:
        devices = list(Path("/sys/bus/usb/devices").iterdir())
    except OSError:
        return found
    for dev in devices:
        if ":" in dev.name:  # Schnittstellen, keine Geräte
            continue
        vendor = _read(dev / "idVendor").lower()
        if not vendor or vendor == "1d6b":  # USB-Hub des PCs
            continue
        ptp_or_mtp = any(_read(i / "bInterfaceClass") == "06" for i in dev.glob(f"{dev.name}:*"))
        if vendor in ANDROID_VENDORS or ptp_or_mtp:
            found[dev.name] = _read(dev / "product") or ANDROID_VENDORS.get(vendor, vendor)
    return found
