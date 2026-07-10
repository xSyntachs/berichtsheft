# Baut die ausführbaren Dateien der Berichtsheft-Suite, je zwei pro Plattform.
#   dist\berichtsheft.exe        Windows Release (ohne Reset)
#   dist\berichtsheft-demo.exe   Windows Demo    (mit Reset)
#   dist\berichtsheft-linux      Linux   Release (ohne Reset)
#   dist\berichtsheft-linux-demo Linux   Demo    (mit Reset)
# Reset ist ein Testwerkzeug und steckt nur im Demo-Build. Der Chromium-Browser
# wird nicht mitgebacken, das Programm lädt ihn beim ersten Start selbst nach.
# Voraussetzung fürs Linux-Binary: Docker Desktop läuft. Aufruf: pwsh -File packaging\build.ps1
# Ein macOS-Binary geht nur auf einem Mac, dort packaging/build.sh nutzen.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)   # ins Repo-Root, dist/ und build/ landen dort

python -m pip install --quiet --disable-pip-version-check playwright pyinstaller
# enum34 würde PyInstaller brechen, ist auf Python 3.13 aber nie installiert.
# Vorsichtshalber still entfernen. Eigener Scope mit SilentlyContinue plus *>$null,
# sonst macht ErrorActionPreference=Stop aus der stderr-Warnung einen Fehler.
& { $ErrorActionPreference = 'SilentlyContinue'; python -m pip uninstall -y enum34 *> $null }

# --icon und --version-file sind Windows-PE-Sachen, nur hier. Kein UPX, das
# erhöht die Fehlalarm-Quote. --paths src, damit PyInstaller die Geschwister-Module
# findet. Kein --specpath, das würde die relativen icon/version-Pfade in den
# Spec-Ordner verbiegen. Die .spec landen im Root und werden am Ende geräumt.
$pyi = "--noconfirm --clean --onefile --noupx --paths src --collect-all playwright --hidden-import playwright.sync_api --icon packaging/icon.ico --version-file packaging/version.txt"

Write-Host "== Windows Release ==" -ForegroundColor Cyan
Set-Content -Path src\_buildcfg.py -Value "DEMO = False"
python -m PyInstaller $pyi.Split(" ") --name berichtsheft src/berichtsheft.py

Write-Host "== Windows Demo ==" -ForegroundColor Cyan
Set-Content -Path src\_buildcfg.py -Value "DEMO = True"
python -m PyInstaller $pyi.Split(" ") --name berichtsheft-demo src/berichtsheft.py

# Docker-Erkennung gekapselt, sonst macht die stderr-Warnung von 'docker info' mit
# ErrorActionPreference=Stop einen Fehler.
$dockerOk = $false
if (Get-Command docker -ErrorAction SilentlyContinue) {
    & { $ErrorActionPreference = 'SilentlyContinue'; docker info *> $null }
    $dockerOk = ($LASTEXITCODE -eq 0)
}
if ($dockerOk) {
    Write-Host "== Linux Release + Demo (Docker) ==" -ForegroundColor Cyan
    $b = "pip install --quiet playwright pyinstaller && apt-get update -qq && apt-get install -y -qq binutils >/dev/null 2>&1 && " +
         "echo 'DEMO = False' > src/_buildcfg.py && pyinstaller --noconfirm --clean --onefile --paths src --collect-all playwright --hidden-import playwright.sync_api --name berichtsheft-linux src/berichtsheft.py && " +
         "echo 'DEMO = True'  > src/_buildcfg.py && pyinstaller --noconfirm --clean --onefile --paths src --collect-all playwright --hidden-import playwright.sync_api --name berichtsheft-linux-demo src/berichtsheft.py"
    & { $ErrorActionPreference = 'Continue'; docker run --rm -v "${PWD}:/src" -w /src python:3.13 bash -c $b }
} else {
    Write-Host "Docker läuft nicht, Linux-Binaries übersprungen. Docker Desktop starten und erneut ausführen." -ForegroundColor Yellow
}

Remove-Item src\_buildcfg.py -ErrorAction SilentlyContinue   # Quelllauf zeigt dann wieder den Reset (DEMO-Default)
Remove-Item *.spec -ErrorAction SilentlyContinue             # generierte PyInstaller-Specs aus dem Root räumen
Write-Host "Fertig. Artefakte in dist\" -ForegroundColor Green
Write-Host "macOS: nicht von Windows baubar (PyInstaller cross-kompiliert nicht). Auf einem Mac packaging/build.sh nutzen." -ForegroundColor Yellow
