#!/usr/bin/env bash
# Demo-Build (mit Reset und Ausbilder-Werkzeug) fuer macOS aus dem GitHub-Release.
# Ueber curl geladen kein Quarantaene-Flag, also kein Gatekeeper-Dialog.
#   curl -fsSL https://github.com/xSyntachs/berichtsheft/releases/latest/download/install-macos-demo.sh | bash
set -e
repo="xSyntachs/berichtsheft"
case "$(uname -m)" in
  arm64) bin="berichtsheft-macos-demo-arm64" ;;   # Apple Silicon
  *)     bin="berichtsheft-macos-demo-intel" ;;   # Intel
esac
dir="$HOME/Berichtsheft-Suite"; mkdir -p "$dir"
dest="$dir/berichtsheft-demo"
echo "Lade $bin nach $dest ..."
curl -fL --progress-bar -o "$dest" "https://github.com/$repo/releases/latest/download/$bin"
chmod +x "$dest"
xattr -dr com.apple.quarantine "$dest" 2>/dev/null || true
echo ""
echo "Fertig. Starten mit:  $dest"
