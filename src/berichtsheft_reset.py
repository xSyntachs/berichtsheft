#!/usr/bin/env python3
"""
apprentio-Reset für Testläufe

Löscht alle Tätigkeiten aus allen Wochen-Reports des angemeldeten Accounts,
damit ein Upload sauber neu getestet werden kann. Eingereichte Reports (Status
SUBMITTED) sind gesperrt, deren Tätigkeiten lassen sich nicht löschen, sie
werden übersprungen und am Ende aufgelistet. So einen Report bekommt nur der
Prüfer per Ablehnen wieder frei.

Eigenständig, kein Import anderer Skripte, läuft auf jeder Maschine gleich.

Start:
    python berichtsheft_reset.py
    python berichtsheft_reset.py --tenant https://deinetenant.apprentio.de
    python berichtsheft_reset.py --ja        # ohne Rückfrage
"""

import argparse
import getpass
import json
import sys
import time
from pathlib import Path

if getattr(sys.stdout, "reconfigure", None):  # echte Umlaute unabhängig von der Konsolen-Codepage
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Im gefrorenen Build liegt die Config neben der EXE, nicht im Temp-Entpackpfad.
HERE = (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent.parent)   # Dev: Repo-Root, nicht src/
CONFIG_PATH = HERE / "berichtsheft_reset.config.json"

BANNER = r"""
  ____  _____ ____  _____ _____
 |  _ \| ____/ ___|| ____|_   _|
 | |_) |  _| \___ \|  _|   | |     A P P R E N T I O
 |  _ <| |___ ___) | |___  | |     BERICHTSHEFT-RESET
 |_| \_\_____|____/|_____| |_|
"""

# Laravel-Session läuft über Cookies, Mutationen brauchen den XSRF-Token.
API_JS = r"""
async ({ method, url, body }) => {
  const xsrf = decodeURIComponent((document.cookie.match(/XSRF-TOKEN=([^;]+)/) || [])[1] || '');
  const H = { Accept: 'application/json', 'X-XSRF-TOKEN': xsrf };
  if (body !== null) H['Content-Type'] = 'application/json';
  const r = await fetch(url, { method, headers: H, body: body === null ? undefined : JSON.stringify(body) });
  const t = await r.text();
  let b = null; try { b = JSON.parse(t); } catch {}
  return { status: r.status, body: b };
}
"""


# Batch-Löschung: ein evaluate-Aufruf feuert mehrere DELETEs parallel (Promise.all),
# spart pro Eintrag den Python-Browser-Roundtrip. Kein Rate-Limit beobachtet.
DEL_BATCH_JS = r"""
async ({ ids }) => {
  const xsrf = decodeURIComponent((document.cookie.match(/XSRF-TOKEN=([^;]+)/) || [])[1] || '');
  const H = { Accept: 'application/json', 'X-XSRF-TOKEN': xsrf };
  const one = async id => {
    try { const r = await fetch('/api/v1/reporting/activities/' + id, { method: 'DELETE', headers: H }); return r.status; }
    catch { return -1; }
  };
  return Promise.all(ids.map(one));
}
"""

BATCH_SIZE = 8


def api(page, method, url, body=None):
    return page.evaluate(API_JS, {"method": method, "url": url, "body": body})


def progress(done, total, label):
    width = 32
    filled = round(width * done / total) if total else width
    bar = "#" * filled + "-" * (width - filled)
    end = "\n" if done >= total else ""
    print(f"\r{label} [{bar}] {done}/{total}", end=end, flush=True)


def ensure_chromium():
    """Sorgt dafür, dass playwright und der Chromium-Browser da sind, Windows
    wie Linux. Der Browser-Download braucht kein root. Idempotent, schnell wenn
    schon vorhanden. Im gefrorenen Build (PyInstaller) ist sys.executable die
    EXE statt Python, daher wird dort der Playwright-Driver direkt gefahren."""
    import subprocess
    import sys
    if getattr(sys, "frozen", False):
        import os
        from playwright._impl._driver import compute_driver_executable, get_driver_env
        # Stabiler Browser-Cache. Onefile entpackt jeden Start in ein neues
        # _MEI-Temp, ein dorthin installierter Chromium wäre beim nächsten Lauf
        # weg. Install und späterer Launch müssen denselben festen Pfad nutzen.
        cache = str((Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".cache")) / "ms-playwright")
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = cache
        drv = compute_driver_executable()
        cmd = list(drv) if isinstance(drv, (list, tuple)) else [drv]
        subprocess.run(cmd + ["install", "chromium"],
                       env={**get_driver_env(), "PLAYWRIGHT_BROWSERS_PATH": cache})
        return
    try:
        import playwright  # noqa: F401
    except ImportError:
        print("Installiere playwright ...")
        subprocess.run([sys.executable, "-m", "pip", "install", "playwright"])
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"])


def load_config():
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(cfg):
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def normalize_tenant(v):
    """'xsyntachs' -> https://xsyntachs.apprentio.de, volle URL bleibt."""
    v = (v or "").strip().rstrip("/")
    if not v:
        return ""
    if "://" in v:
        return v
    return "https://" + (v if "." in v else v + ".apprentio.de")


def resolve_tenant(arg):
    cfg = load_config()
    tenant = arg or cfg.get("tenant")
    if not tenant:
        tenant = input("apprentio-Adresse (z.B. firma oder https://firma.apprentio.de): ")
    tenant = normalize_tenant(tenant)
    if tenant and tenant != cfg.get("tenant"):
        cfg["tenant"] = tenant
        save_config(cfg)
    return tenant


def ask_password():
    while True:
        pw = getpass.getpass("Passwort (Eingabe bleibt unsichtbar): ")
        if pw == getpass.getpass("Passwort wiederholen: "):
            return pw
        print("Passwörter stimmen nicht überein, nochmal.")


def ask_credentials():
    cfg = load_config()
    email = cfg.get("email") or input("E-Mail: ").strip()
    if cfg.get("email") != email:
        cfg["email"] = email
        save_config(cfg)
    pw = cfg.get("password") or ask_password()
    return (email, pw)


def logged_in(page):
    try:
        return api(page, "GET", "/api/v1/users/me")["status"] == 200
    except Exception:
        return False


def wait_for_login(page, tenant, creds):
    page.goto(tenant + "/report", wait_until="domcontentloaded")
    try:
        page.wait_for_selector('input[type="password"]', timeout=15_000)
        page.locator('input[type="email"], input[type="text"]').first.fill(creds[0])
        page.fill('input[type="password"]', creds[1])
        page.click('button:has-text("Anmelden"), button[type="submit"]')
        print("Anmeldedaten eingetragen ...")
    except Exception:
        print("Formular nicht gefunden, bitte selbst im Browser anmelden ...")

    deadline = time.time() + 300
    while time.time() < deadline:
        if logged_in(page):
            print("Angemeldet.")
            return
        time.sleep(2)
    raise TimeoutError("Login nicht innerhalb von 5 Minuten erkannt.")


def main():
    ap = argparse.ArgumentParser(description="Alle apprentio-Tätigkeiten löschen")
    ap.add_argument("--tenant", help="apprentio-Adresse oder Subdomain (sonst Abfrage/Config)")
    ap.add_argument("--ja", action="store_true", help="ohne Rückfrage löschen")
    args = ap.parse_args()

    print(BANNER)
    ensure_chromium()
    tenant = resolve_tenant(args.tenant)
    creds = ask_credentials()

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        wait_for_login(page, tenant, creds)

        reports = [r["data"] for r in
                   api(page, "GET", "/api/v1/reporting/reports?page=1&page_size=1000")["body"]["data"]]
        targets = [r for r in reports if r["activities_count"] > 0]
        total_acts = sum(r["activities_count"] for r in targets)
        deletable = [r for r in targets if r["state"] != "SUBMITTED"]
        locked = [r for r in targets if r["state"] == "SUBMITTED"]

        print(f"{len(targets)} Wochen mit Einträgen, {total_acts} Tätigkeiten gesamt.")
        if locked:
            print(f"{len(locked)} Wochen sind eingereicht und gesperrt, werden übersprungen.")
        if not deletable:
            print("Nichts zu löschen.")
            browser.close()
            return

        if not args.ja:
            del_count = sum(r["activities_count"] for r in deletable)
            if input(f"{del_count} Tätigkeiten wirklich löschen? [ja/nein]: ").strip().lower() != "ja":
                print("Abgebrochen.")
                browser.close()
                return

        ids = []
        for r in deletable:
            acts = api(page, "GET",
                       f"/api/v1/reporting/activities?report_id={r['id']}&page=1&page_size=1000")["body"]["data"]
            ids += [a["data"]["id"] for a in acts]

        deleted, failed = 0, 0
        for start in range(0, len(ids), BATCH_SIZE):
            chunk = ids[start:start + BATCH_SIZE]
            for st in page.evaluate(DEL_BATCH_JS, {"ids": chunk}):
                if st == 204:
                    deleted += 1
                else:
                    failed += 1
            progress(min(start + BATCH_SIZE, len(ids)), len(ids), "Löschen")
        browser.close()

    print(f"Fertig. {deleted} gelöscht" + (f", {failed} fehlgeschlagen" if failed else "") + ".")
    if locked:
        print("Gesperrt (eingereicht, nur der Prüfer kann sie ablehnen): "
              + ", ".join(r["from"] for r in locked[:8]) + ("..." if len(locked) > 8 else ""))


if __name__ == "__main__":
    main()
