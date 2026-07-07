#!/usr/bin/env bash
# Holt das passende macOS-Binary der Berichtsheft-Suite per curl und macht es
# startklar. Ueber curl geladene Dateien bekommen kein Quarantaene-Flag, also
# blockt Gatekeeper nicht, kein "nicht geoeffnet"-Dialog. Ein Aufruf genuegt:
#   curl -fsSL https://github.com/xSyntachs/berichtsheft/releases/latest/download/install-macos.sh | bash
set -e
repo="xSyntachs/berichtsheft"
case "$(uname -m)" in
  arm64) bin="berichtsheft-macos-arm64" ;;   # Apple Silicon
  *)     bin="berichtsheft-macos-intel" ;;   # Intel
esac
dir="$HOME/Berichtsheft-Suite"
dest="$dir/berichtsheft"
mkdir -p "$dir"
echo "Lade $bin nach $dest ..."
curl -fL --progress-bar -o "$dest" "https://github.com/$repo/releases/latest/download/$bin"
chmod +x "$dest"
xattr -dr com.apple.quarantine "$dest" 2>/dev/null || true   # Guertel und Hosentraeger
echo ""
echo "Fertig. Starten mit diesem Befehl (Menue braucht ein echtes Terminal):"
echo "  $dest"
