# Fotos vom Handy holen

Kleines Programm für Linux Mint, mit dem neue Fotos und Videos von einem Android-Handy
(per USB-Kabel, „Dateiübertragung“) in die vorhandene Fotosammlung übernommen werden –
ohne Terminal, in wenigen Klicks.

## Ablauf für die Nutzerin

1. Handy mit dem Kabel anschließen. Die Handy-Erkennung (läuft im Hintergrund) zeigt, was am
   Handy zu tun ist („Dateiübertragung“ wählen). Alternativ das Symbol
   **Fotos vom Handy holen** auf dem Schreibtisch starten.
2. Neue Fotos und Videos werden mit Vorschau angezeigt. Einzelne lassen sich abwählen.
3. Ziel wählen: ein **bestehender Ordner** (voreingestellt: Jahresordner, z. B. `~/Bilder/2026`)
   oder ein **neuer Ordner** (Vorschlag: aktueller Zweimonatsname, z. B. `Sep-Okt`).
4. Importieren. Die Originale bleiben auf dem Handy.

## Was wird gesucht?

| Quelle | Ordner auf dem Handy | Inhalt |
|---|---|---|
| Kamera | `DCIM/Camera` | Fotos und Videos |
| WhatsApp | `…/WhatsApp Images`, `…/WhatsApp Video` (ohne `Sent`, `Private`) | Fotos und Videos |
| Download | `Download` | nur Bilder |

Screenshots werden nicht angeboten.

## Verhalten

- **Neu-Erkennung:** Importierte Fotos werden in `~/.local/share/fotoimport/state.json` gemerkt
  (Name, Größe, Datum) und nicht noch einmal angeboten.
- **Erster Start:** Einrichtung mit Hauptordner und Startdatum. Fotos vor dem Startdatum gelten
  als erledigt; außerdem wird die Sammlung nach gleichnamigen Dateien gleicher Größe abgeglichen.
  Erneut aufrufen: `fotos-vom-handy einrichten`.
- **Zweimonatsordner:** Das Programm teilt nie selbst nach Datum auf, sie wählt den Ordner. Die
  Schreibweise der Monatskürzel (`Mär-Apr`, `Mrz-Apr`, …) wird aus den vorhandenen Ordnern gelernt.
- **Sicherheit:** Es wird nie überschrieben (bei gleichem Namen: `_2`, `_3`, …), nie vom Handy
  gelöscht, und es entstehen keine halben Dateien (Kopie unter temporärem Namen, dann Umbenennen).
- **Dubletten:** Fotos aus verschiedenen Quellen mit gleicher Aufnahmezeit (aus dem Dateinamen,
  sonst dem Änderungsdatum) werden als „möglicherweise doppelt“ markiert und nicht angehakt.
  Bearbeitete oder verkleinerte Kopien (z. B. von WhatsApp) mit anderem Zeitstempel werden nicht
  erkannt.

## Installation (einmal, vor Ort)

```bash
git clone https://github.com/moritzkloepfer-bot/first-pr.git
cd first-pr
./install.sh
```

Das Skript installiert benötigte Pakete (GTK, gvfs), legt das Symbol „Fotos vom Handy holen“ auf
dem Schreibtisch an und richtet den Autostart der Handy-Erkennung ein. Update: `git pull`, dann
`./install.sh` erneut. Entfernen: `./install.sh --deinstallieren`.

## Entwicklung

```bash
python3 -m pytest tests                        # Kernlogik
xvfb-run -a python3 tests/gui_smoke.py         # Fenster einmal durchklicken (GTK nötig)
xvfb-run -a python3 tests/watcher_smoke.py     # Handy-Erkennung mit simulierten Ereignissen
```

`FOTOIMPORT_FAKE_PHONE=/pfad/zum/ordner` lässt das Programm einen normalen Ordner als Handy-Speicher
verwenden, `FOTOIMPORT_HOME` verlegt die Merkliste.
