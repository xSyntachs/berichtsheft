#!/usr/bin/env bash
# Lädt die Berichtsheft-Suite für Linux und macOS aus dem GitHub-Release,
# erkennt Plattform und CPU (arm64/intel) selbst. Über curl geladen gibt es
# kein Quarantäne-Flag, also keinen Gatekeeper-Dialog.
#   curl -fsSL https://github.com/xSyntachs/berichtsheft/releases/latest/download/download.sh | bash
set -e
repo="xSyntachs/berichtsheft"
echo "Berichtsheft-Suite herunterladen"
echo "  [1] Normal"
echo "  [2] Demo (nur zum Testen)"
choice=1
if [ -r /dev/tty ]; then
  read -r -p "Welche Version? [1]: " choice < /dev/tty || choice=1
fi
demo=""
[ "$choice" = "2" ] && demo="-demo"
case "$(uname -s)" in
  Darwin)
    case "$(uname -m)" in
      arm64) bin="berichtsheft-macos${demo}-arm64" ;;   # Apple Silicon
      *)     bin="berichtsheft-macos${demo}-intel" ;;   # Intel
    esac ;;
  *)
    bin="berichtsheft-linux${demo}" ;;
esac
dir="$HOME/Berichtsheft-Suite"; mkdir -p "$dir"
dest="$dir/berichtsheft${demo}"
echo "Lade $bin nach $dest ..."
curl -fL --progress-bar -o "$dest" "https://github.com/$repo/releases/latest/download/$bin"
chmod +x "$dest"
# Über curl geladen gibt es kein Quarantäne-Flag, das hier ist Gürtel und Hosenträger.
command -v xattr >/dev/null && xattr -dr com.apple.quarantine "$dest" 2>/dev/null || true
echo ""
echo "Fertig. Das Programm liegt unter $dest"
if [ -r /dev/tty ]; then
  echo "Es startet jetzt."
  "$dest" < /dev/tty
else
  echo "Starten mit:  $dest"
fi
