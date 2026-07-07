#!/usr/bin/env bash
# Laedt das Linux-Binary der Berichtsheft-Suite aus dem GitHub-Release.
#   curl -fsSL https://github.com/xSyntachs/berichtsheft/releases/latest/download/install-linux.sh | bash
set -e
dir="$HOME/Berichtsheft-Suite"; mkdir -p "$dir"
dest="$dir/berichtsheft"
echo "Lade berichtsheft-linux ..."
curl -fL --progress-bar -o "$dest" "https://github.com/xSyntachs/berichtsheft/releases/latest/download/berichtsheft-linux"
chmod +x "$dest"
echo ""
echo "Fertig. Starten mit:  $dest"
