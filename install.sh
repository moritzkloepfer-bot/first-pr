#!/bin/sh
# Installiert "Fotos vom Handy holen" für den aktuellen Benutzer (Linux Mint).
# Erneut ausführen = Update. Mit "--deinstallieren" wird alles wieder entfernt.
set -e

HERE=$(cd "$(dirname "$0")" && pwd)
APP="$HOME/.local/opt/fotoimport"
BIN="$HOME/.local/bin"
LAUNCHER="$BIN/fotos-vom-handy"
APPS="$HOME/.local/share/applications"
AUTOSTART="$HOME/.config/autostart"
DESKTOP_DIR=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Schreibtisch")

if [ "$1" = "--deinstallieren" ]; then
    pkill -f "fotoimport waechter" 2>/dev/null || true
    rm -rf "$APP" "$LAUNCHER" "$APPS/fotoimport.desktop" \
        "$AUTOSTART/fotoimport-waechter.desktop" "$DESKTOP_DIR/Fotos vom Handy holen.desktop"
    echo "Entfernt. Die Merkliste importierter Fotos liegt noch in ~/.local/share/fotoimport."
    exit 0
fi

echo "== Benötigte Pakete (Passwort wird ggf. abgefragt) =="
sudo apt-get install -y python3-gi gir1.2-gtk-3.0 gir1.2-gdkpixbuf-2.0 gvfs-backends

echo "== Programm installieren =="
mkdir -p "$APP" "$BIN" "$APPS" "$AUTOSTART"
rm -rf "$APP/fotoimport"
cp -r "$HERE/fotoimport" "$APP/"
find "$APP" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

cat > "$LAUNCHER" <<SCRIPT
#!/bin/sh
PYTHONPATH="$APP" exec /usr/bin/python3 -m fotoimport "\$@"
SCRIPT
chmod +x "$LAUNCHER"

cat > "$APPS/fotoimport.desktop" <<ENTRY
[Desktop Entry]
Type=Application
Name=Fotos vom Handy holen
Comment=Neue Fotos und Videos vom Handy in die Fotosammlung übernehmen
Exec=$LAUNCHER importieren
Icon=camera-photo
Terminal=false
Categories=Graphics;
ENTRY

cat > "$AUTOSTART/fotoimport-waechter.desktop" <<ENTRY
[Desktop Entry]
Type=Application
Name=Fotos vom Handy – Handy-Erkennung
Exec=$LAUNCHER waechter
Icon=camera-photo
Terminal=false
X-GNOME-Autostart-enabled=true
ENTRY

if [ -d "$DESKTOP_DIR" ]; then
    cp "$APPS/fotoimport.desktop" "$DESKTOP_DIR/Fotos vom Handy holen.desktop"
    chmod +x "$DESKTOP_DIR/Fotos vom Handy holen.desktop"
    gio set "$DESKTOP_DIR/Fotos vom Handy holen.desktop" metadata::trusted true 2>/dev/null || true
fi

echo
echo "Der Dateimanager öffnet sich beim Anstecken eines Handys sonst zusätzlich zu unserem Fenster."
printf "Das automatische Öffnen des Dateimanagers beim Anstecken abschalten? [J/n] "
read -r antwort || antwort=n
case "$antwort" in
    [nN]*) ;;
    *) gsettings set org.cinnamon.desktop.media-handling automount-open false 2>/dev/null || true ;;
esac

echo "== Handy-Erkennung starten =="
pkill -f "fotoimport waechter" 2>/dev/null || true
setsid "$LAUNCHER" waechter >/dev/null 2>&1 &

echo
echo "Fertig. Beim ersten Start des Programms (Symbol auf dem Schreibtisch) die Einrichtung durchgehen."
