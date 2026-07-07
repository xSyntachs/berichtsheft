#!/usr/bin/env python3
"""apprentio-Ausbilderwerkzeug (nur Demo)

Für Prüfer/Ausbilder. Meldet sich mit einem Prüfer-Account an, listet alle
Nachwuchskräfte des Tenants auf, eine wird ausgewählt (oder alle), dann eine
Massenaktion auf deren Wochen:

  - Alle annehmen        eingereichte Wochen (SUBMITTED) -> ANGENOMMEN
  - Alle ablehnen        eingereichte Wochen (SUBMITTED) -> ABGELEHNT
  - Annahme zurücknehmen angenommene Wochen (ACCEPTED)   -> ABGELEHNT

Hinweis: Reviewte Wochen lassen sich serverseitig nicht mehr auf "Erstellend"
zurücksetzen, ein echtes Löschen der Einträge ist deshalb nicht möglich. Das
Zurücknehmen einer Annahme setzt die Woche auf "abgelehnt".

Start:
    python berichtsheft_review.py
    python berichtsheft_review.py --member "Neu" --aktion annehmen --ja
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
CONFIG_PATH = HERE / "berichtsheft_review.config.json"

BANNER = r"""
  ____  _____ _____ _____ _____ _    _
 |  _ \| ____|_   _| ____|_   _| |  | |    A P P R E N T I O
 | |_) |  _|   | | |  _|   | | | |  | |    AUSBILDER-REVIEW
 |  _ <| |___  | | | |___  | | | |__| |
 |_| \_\_____| |_| |_____| |_|  \____/
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

# Massenaktion parallel: mehrere PATCHes in einem evaluate (Promise.all).
PATCH_BATCH_JS = r"""
async ({ jobs }) => {
  const xsrf = decodeURIComponent((document.cookie.match(/XSRF-TOKEN=([^;]+)/) || [])[1] || '');
  const H = { Accept: 'application/json', 'X-XSRF-TOKEN': xsrf, 'Content-Type': 'application/json' };
  const one = async j => {
    try {
      const r = await fetch('/api/v1/reporting/reports/' + j.id, { method: 'PATCH', headers: H, body: JSON.stringify(j.body) });
      return r.status;
    } catch { return -1; }
  };
  return Promise.all(jobs.map(one));
}
"""

BATCH_SIZE = 8

# Aktion -> (Quellzustand, Zielzustand, Label)
ACTIONS = {
    "annehmen": ("SUBMITTED", "ACCEPTED", "eingereichte Wochen annehmen"),
    "ablehnen": ("SUBMITTED", "DECLINED", "eingereichte Wochen ablehnen"),
    "zuruecknehmen": ("ACCEPTED", "DECLINED", "Annahme zurücknehmen (angenommen -> abgelehnt)"),
}


def api(page, method, url, body=None):
    return page.evaluate(API_JS, {"method": method, "url": url, "body": body})


def progress(done, total, label):
    width = 32
    filled = round(width * done / total) if total else width
    bar = "#" * filled + "-" * (width - filled)
    end = "\n" if done >= total else ""
    print(f"\r{label} [{bar}] {done}/{total}", end=end, flush=True)


def ensure_chromium():
    """Sorgt dafür, dass playwright und der Chromium-Browser da sind. Im
    gefrorenen Build ist sys.executable die EXE statt Python, daher wird dort
    der Playwright-Driver direkt gefahren, mit stabilem Browser-Cache."""
    import subprocess
    import sys
    if getattr(sys, "frozen", False):
        import os
        from playwright._impl._driver import compute_driver_executable, get_driver_env
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
    """'firma' -> https://firma.apprentio.de, volle URL bleibt."""
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
    email = cfg.get("email") or input("E-Mail (Prüfer/Ausbilder): ").strip()
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


def me_id(page):
    return api(page, "GET", "/api/v1/users/me")["body"]["data"]["id"]


def members(page):
    r = api(page, "GET", "/api/v1/users?page=1&page_size=1000")
    users = [u["data"] for u in r["body"]["data"]]
    return [u for u in users if u.get("default_role") == "apprentice"]


def member_reports(page, user_id):
    r = api(page, "GET", "/api/v1/reporting/reports?page=1&page_size=1000")
    return [x["data"] for x in r["body"]["data"] if x["data"]["user_id"] == user_id]


def pick_member(ms):
    print("\nMitglieder:")
    print("  [0] ALLE")
    for i, m in enumerate(ms, 1):
        print(f"  [{i}] {m['full_name']}")
    while True:
        w = input("Auswahl: ").strip()
        if w.isdigit() and 0 <= int(w) <= len(ms):
            return None if int(w) == 0 else ms[int(w) - 1]
        low = w.lower()
        hit = [m for m in ms if low and low in m["full_name"].lower()]
        if len(hit) == 1:
            return hit[0]
        print("Ungültig, Nummer oder eindeutiger Namensteil.")


def pick_action():
    keys = list(ACTIONS)
    print("\nWas tun?")
    for i, k in enumerate(keys, 1):
        print(f"  [{i}] {ACTIONS[k][2]}")
    while True:
        w = input("Auswahl: ").strip().lower()
        if w in ACTIONS:
            return w
        if w.isdigit() and 1 <= int(w) <= len(keys):
            return keys[int(w) - 1]
        print("Ungültig, nochmal.")


def apply_action(page, reports, action, reviewer_id):
    src, dst, _ = ACTIONS[action]
    jobs = [{"id": r["id"], "body": {"id": r["id"], "from": r["from"], "to": r["to"],
                                     "type": r["type"], "state": dst,
                                     "reviewer_id": r.get("reviewer_id") or reviewer_id}}
            for r in reports if r["state"] == src]
    if not jobs:
        print(f"Keine Wochen im Zustand {src}.")
        return
    done, failed = 0, 0
    for start in range(0, len(jobs), BATCH_SIZE):
        chunk = jobs[start:start + BATCH_SIZE]
        for st in page.evaluate(PATCH_BATCH_JS, {"jobs": chunk}):
            if st == 200:
                done += 1
            else:
                failed += 1
        progress(min(start + BATCH_SIZE, len(jobs)), len(jobs), "Bearbeiten")
    print(f"Fertig. {done} Wochen auf {dst}" + (f", {failed} fehlgeschlagen" if failed else "") + ".")


def main():
    ap = argparse.ArgumentParser(description="apprentio-Wochen als Ausbilder annehmen/ablehnen")
    ap.add_argument("--tenant", help="apprentio-Adresse oder Subdomain (sonst Abfrage/Config)")
    ap.add_argument("--member", help="Name(steil) der Nachwuchskraft, sonst Auswahl. 'alle' fuer alle")
    ap.add_argument("--aktion", choices=list(ACTIONS), help="annehmen, ablehnen oder zuruecknehmen")
    ap.add_argument("--ja", action="store_true", help="ohne Rueckfrage ausfuehren")
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
        reviewer_id = me_id(page)

        ms = members(page)
        if not ms:
            print("Keine Nachwuchskräfte gefunden (falsches Konto oder Recht?).")
            browser.close()
            return

        if args.member and args.member.lower() == "alle":
            target = None
        elif args.member:
            hit = [m for m in ms if args.member.lower() in m["full_name"].lower()]
            if len(hit) != 1:
                print(f"'{args.member}' passt auf {len(hit)} Mitglieder, bitte eindeutiger.")
                browser.close()
                return
            target = hit[0]
        else:
            target = pick_member(ms)

        chosen = ms if target is None else [target]
        action = args.aktion or pick_action()
        src, dst, label = ACTIONS[action]

        reports = [r for m in chosen for r in member_reports(page, m["id"]) if r["state"] == src]
        who = "ALLE Mitglieder" if target is None else target["full_name"]
        print(f"\n{label} fuer {who}: {len(reports)} Wochen betroffen.")
        if not reports:
            browser.close()
            return

        if not args.ja:
            if input("Ausfuehren? [ja/nein]: ").strip().lower() != "ja":
                print("Abgebrochen.")
                browser.close()
                return

        apply_action(page, reports, action, reviewer_id)
        browser.close()


if __name__ == "__main__":
    main()
