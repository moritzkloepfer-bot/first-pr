import os
import time
from pathlib import Path


def make_phone(tmp: Path) -> Path:
    storage = tmp / "phone"
    cam = storage / "DCIM/Camera"
    wa = storage / "Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Images"
    wav = storage / "Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Video"
    dl = storage / "Download"
    for d in (cam, wa, wa / "Sent", wav, dl):
        d.mkdir(parents=True)
    now = time.time()
    (cam / "IMG_20261015_101500.jpg").write_bytes(b"a" * 100)
    (cam / "VID_20261016_120000.mp4").write_bytes(b"v" * 200)
    (cam / ".trashed-1-IMG.jpg").write_bytes(b"x")
    (wa / "IMG-20261015-WA0001.jpg").write_bytes(b"w" * 50)
    (wa / "Sent" / "IMG-20261015-WA0002.jpg").write_bytes(b"s" * 50)
    (wav / "VID-20261017-WA0003.mp4").write_bytes(b"w" * 300)
    (dl / "bild.png").write_bytes(b"p" * 10)
    (dl / "rechnung.pdf").write_bytes(b"pdf")
    for n, p in enumerate(sorted(storage.rglob("*"))):
        if p.is_file():
            os.utime(p, (now + n, now + n))  # verschiedene Zeiten, sonst wären alle 'Dubletten'
    return storage
