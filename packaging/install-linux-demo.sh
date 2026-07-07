#!/usr/bin/env bash
# Demo-Build (mit Reset und Ausbilder-Werkzeug) aus dem GitHub-Release.
#   curl -fsSL https://github.com/xSyntachs/berichtsheft/releases/latest/download/install-linux-demo.sh | bash
set -e
dir="$HOME/Berichtsheft-Suite"; mkdir -p "$dir"
dest="$dir/berichtsheft-demo"
echo "Lade berichtsheft-linux-demo ..."
curl -fL --progress-bar -o "$dest" "https://github.com/xSyntachs/berichtsheft/releases/latest/download/berichtsheft-linux-demo"
chmod +x "$dest"
echo ""
echo "Fertig. Starten mit:  $dest"
