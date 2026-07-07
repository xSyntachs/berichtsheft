#!/usr/bin/env python3
"""Berichtsheft-Suite. Ein Start für Download, Upload und Reset.

Direkt:      berichtsheft download|upload|reset [optionen]
Doppelklick: ohne Argumente erscheint ein Auswahlmenü, Navigation mit ↑/↓ oder W/S.

Der Reset ist nur ein Testwerkzeug und erscheint deshalb ausschließlich im
Demo-Build (DEMO = True). Im Release-Build bleibt er verborgen.
"""
import os
import sys

import berichtsheft_download
import berichtsheft_reset
import berichtsheft_review
import berichtsheft_upload

try:
    from _buildcfg import DEMO
except ImportError:
    DEMO = True  # aus dem Quellcode gestartet gilt als Entwicklung, Reset sichtbar

TITLE = "COMMUNARDO"
SUBTITLE = "Berichtsheft-Suite"
_ACCENT = "38;2;0;96;170"   # ruhiges Unternehmensblau
_DIM = "38;2;140;140;150"


def _color():
    return sys.stdout.isatty()


def _paint(text, code):
    return f"\x1b[{code}m{text}\x1b[0m" if _color() else text


def _enable_ansi():
    if sys.platform == "win32":
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.SetConsoleMode(k.GetStdHandle(-11), 7)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        except Exception:
            pass


def _clear():
    if sys.stdout.isatty():
        os.system("cls" if os.name == "nt" else "clear")


def _getkey():
    """Ein Tastendruck, normalisiert zu 'up'/'down'/'enter' oder dem Zeichen."""
    if os.name == "nt":
        import msvcrt
        ch = msvcrt.getch()
        if ch in (b"\x00", b"\xe0"):
            return {b"H": "up", b"P": "down"}.get(msvcrt.getch(), "")
        if ch in (b"\r", b"\n"):
            return "enter"
        if ch == b"\x03":
            raise KeyboardInterrupt
        return ch.decode("latin-1", "ignore").lower()
    import termios
    import tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            return {"[A": "up", "[B": "down"}.get(sys.stdin.read(2), "")
        if ch in ("\r", "\n"):
            return "enter"
        if ch == "\x03":
            raise KeyboardInterrupt
        return ch.lower()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def banner():
    if _color():
        _enable_ansi()
    line = f"  {_paint(TITLE, _ACCENT + ';1')}   {_paint(SUBTITLE, '1')}"
    width = len(TITLE) + 3 + len(SUBTITLE)
    print("\n" + line)
    print("  " + _paint("─" * width, _DIM) + "\n")


TOOLS = {
    "download": (berichtsheft_download.main, "IHK-Heft live als PDFs und JSON herunterladen"),
    "word": (berichtsheft_download.import_docx_interactive, "Berichtsheft aus einer Word-Datei importieren"),
    "upload": (berichtsheft_upload.main, "Export nach apprentio hochladen und einreichen"),
}
if DEMO:
    TOOLS["reset"] = (berichtsheft_reset.main, "Alle apprentio-Tätigkeiten löschen (nur zum Testen)")
    TOOLS["ausbilder"] = (berichtsheft_review.main, "Ausbilder, Wochen annehmen/ablehnen (nur zum Testen)")

ICONS = {"download": "↓", "word": "▤", "upload": "↑", "reset": "↺", "ausbilder": "✓"}


def _menu_interactive():
    banner()
    print("  Was möchtest du tun?")
    print("  " + _paint("↑/↓ oder W/S bewegen, Enter wählt", _DIM) + "\n")
    items = list(TOOLS.items())
    idx, first = 0, True
    while True:
        if not first:
            sys.stdout.write(f"\x1b[{len(items)}A")
        for i, (name, (_, desc)) in enumerate(items):
            pointer = "▸" if i == idx else " "
            icon = ICONS.get(name, "•")
            if i == idx:
                body = _paint(f"{pointer} {icon}  {name:9} {desc}", _ACCENT + ";1")
            else:
                body = f"{pointer} {icon}  " + _paint(f"{name:9}", "1") + " " + _paint(desc, _DIM)
            sys.stdout.write("\x1b[K  " + body + "\n")
        sys.stdout.flush()
        first = False
        k = _getkey()
        if k in ("up", "w"):
            idx = (idx - 1) % len(items)
        elif k in ("down", "s"):
            idx = (idx + 1) % len(items)
        elif k == "enter":
            return items[idx][0]
        elif k.isdigit() and 1 <= int(k) <= len(items):
            return items[int(k) - 1][0]


def _menu_typed():
    banner()
    print("  Was möchtest du tun?\n")
    keys = list(TOOLS)
    for name, (_, desc) in TOOLS.items():
        print(f"    {ICONS.get(name, '•')}   {name:9} {desc}")
    while True:
        w = input("\n  Auswahl (Name oder Zahl): ").strip().lower()
        if w in TOOLS:
            return w
        if w.isdigit() and 1 <= int(w) <= len(keys):
            return keys[int(w) - 1]
        print("  Ungültige Eingabe, nochmal.")


def select():
    if sys.stdin.isatty() and sys.stdout.isatty():
        return _menu_interactive()
    return _menu_typed()


def main():
    interactive = not (len(sys.argv) > 1 and sys.argv[1].lower() in TOOLS)
    if interactive:
        _clear()
        cmd, rest = select(), []
        _clear()
    else:
        cmd, rest = sys.argv[1].lower(), sys.argv[2:]
    sys.argv = ["berichtsheft " + cmd] + rest
    try:
        TOOLS[cmd][0]()
    finally:
        if interactive:
            input("\n  Fertig. Enter zum Schließen. ")


if __name__ == "__main__":
    main()
