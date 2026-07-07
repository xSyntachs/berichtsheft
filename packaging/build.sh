#!/usr/bin/env bash
# Baut die Unix-Binaries der Berichtsheft-Suite nativ, Release und Demo, für die
# Plattform auf der es läuft. macOS -> berichtsheft-macos, Linux -> berichtsheft-linux.
# PyInstaller cross-kompiliert nicht, das Mac-Binary muss also auf einem Mac gebaut
# werden, das Linux-Binary auf Linux. Windows-EXE stattdessen über packaging/build.ps1.
# Aufruf: bash packaging/build.sh
set -e
cd "$(dirname "$0")/.."   # Repo-Root, dist/ und build/ landen dort

case "$(uname -s)" in
  Darwin) os="macos" ;;
  *)      os="linux" ;;   # Linux braucht binutils (objdump) für PyInstaller
esac

python3 -m pip install --quiet playwright pyinstaller
pyi="--noconfirm --clean --onefile --paths src --specpath build --collect-all playwright --hidden-import playwright.sync_api"

echo "== $os Release =="
echo 'DEMO = False' > src/_buildcfg.py
python3 -m PyInstaller $pyi --name "berichtsheft-$os" src/berichtsheft.py

echo "== $os Demo =="
echo 'DEMO = True' > src/_buildcfg.py
python3 -m PyInstaller $pyi --name "berichtsheft-$os-demo" src/berichtsheft.py

rm -f src/_buildcfg.py   # Quelllauf zeigt dann wieder den Reset (DEMO-Default)
echo "Fertig. Artefakt berichtsheft-$os in dist/"
