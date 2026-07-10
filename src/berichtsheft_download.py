#!/usr/bin/env python3
"""
IHK-Berichtsheft-Downloader für meineihk.service.ihk.de

Zieht das komplette digitale Berichtsheft über die interne JSON-API und legt
zwei Dateien im Ausgabeordner ab:
  - berichtsheft.json  -> alle Wochen strukturiert, plus Stammdaten und Qualifikationen
  - berichtsheft.pdf   -> lesbarer Gesamtbericht über alle Wochen

Anmeldung: Beim Start werden E-Mail, Passwort und der IHK-Standort abgefragt,
den Rest (Cookie-Banner, IHK-Auswahl, SSO-Login) erledigt das Skript selbst.
Jeder Lauf startet mit frischem Browser, nichts wird gespeichert.

Setup einmalig:
    pip install playwright
    playwright install chromium

Start:
    python berichtsheft_download.py    # kompletter Ausbildungszeitraum, keine Flags
"""

import getpass
import json
import re
import sys
import time
from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path

if getattr(sys.stdout, "reconfigure", None):  # echte Umlaute unabhängig von der Konsolen-Codepage
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

APP_URL = ("https://meineihk.service.ihk.de/landing/bildung/ausbildung/dibe/dibe/"
           "berichtsheft/wochenansicht?datum={datum}&rolle=AUSZUBILDENDER")
API = "https://bildung.service.ihk.de"

# Im gefrorenen Build liegen Config und Export neben der EXE, nicht im Temp-Pfad.
HERE = (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent.parent)   # Dev: Repo-Root, nicht src/
CONFIG_PATH = HERE / "berichtsheft_download.config.json"

BANNER = r"""
  ___ _   _ _  __
 |_ _| | | | |/ /
  | || |_| | ' /    C O M M U N A R D O
  | ||  _  | . \    BERICHTSHEFT-DOWNLOADER
 |___|_| |_|_|\_\
"""

WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
ENUM_LABEL = {
    "ANWESEND": "anwesend", "ABWESEND": "abwesend", "KRANK": "krank",
    "URLAUB": "Urlaub", "FEIERTAG": "Feiertag", "FREI": "frei",
    "BETRIEB": "Betrieb", "BERUFSSCHULE": "Berufsschule", "SCHULE": "Schule",
    "UEBERBETRIEBLICH": "Überbetrieblich", "HOMEOFFICE": "Homeoffice",
    "FREIGEGEBEN": "Freigegeben", "EINGEREICHT": "Eingereicht",
    "IN_BEARBEITUNG": "In Bearbeitung", "OFFEN": "Offen", "ABGELEHNT": "Abgelehnt",
}


def label(value):
    if not value:
        return ""
    return ENUM_LABEL.get(value, value.replace("_", " ").title())


def monday(d):
    return d - timedelta(days=d.weekday())


def parse_date(s):
    return datetime.strptime(s[:10], "%Y-%m-%d").date()


def fmt_de(d):
    return d.strftime("%d.%m.%Y")


def fmt_duration(iso):
    """ISO-8601-Dauer wie 'PT3H30M' -> '3:30 h'. Null-Dauer und Leeres -> ''."""
    if not iso:
        return ""
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
    if not m:
        return iso
    h, mi = int(m.group(1) or 0), int(m.group(2) or 0)
    return f"{h}:{mi:02d} h" if h or mi else ""


# Die Auth-Header kommen nicht aus dem sessionStorage (den befüllt die SPA
# nicht zuverlässig), sondern werden aus einem echten API-Request der SPA
# abgehört (siehe make_sniffer). Die JS-Snippets bekommen sie als Argument.
WEEK_JS = r"""
async ({ datum, headers }) => {
  const base = 'https://bildung.service.ihk.de';
  const r = await fetch(`${base}/berichtsheft/erstellen-api/v1/berichtswoche?datum=${datum}`, { headers });
  const t = await r.text();
  return { status: r.status, data: t ? JSON.parse(t) : null };
}
"""

META_JS = r"""
async ({ headers }) => {
  const base = 'https://bildung.service.ihk.de';
  // User-Id steckt im JWT-Payload als sub: "IAM.<id>" (Base64url dekodieren)
  const tok = headers.authorization.split(' ')[1];
  const payload = JSON.parse(atob(tok.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
  const uid = payload.sub.split('.').pop();
  const get = async u => {
    const r = await fetch(u, { headers });
    const t = await r.text();
    let b = null; try { b = JSON.parse(t); } catch {}
    return { status: r.status, body: b };
  };
  return {
    userId: uid,
    stammdaten: await get(`${base}/zuordnung/anwender-api/v1/auszubildender/verzeichnis/stammdaten`),
    azubi: await get(`${base}/zuordnung/anwender-api/v1/anwender/auszubildender?azubiIamUserId=${uid}`),
    qualifikationen: await get(`${base}/zuordnung/berufsbild-api/v1/auszubildende/qualifikationen?azubiIamUserId=${uid}`),
  };
}
"""


def get_meta(page, sniff):
    """Lädt Stammdaten, Zeitraum und Qualifikationen. Das IHK-Backend liefert
    direkt nach dem Login gern 500er, darum mehrere Versuche. Der Zeitraum
    kommt aus den Stammdaten oder ersatzweise aus dem Anwender-Endpoint."""
    for attempt in range(6):
        raw = page.evaluate(META_JS, {"headers": sniff["headers"]})
        ok = lambda k: raw[k]["body"] if raw[k]["status"] == 200 else None
        stamm, azubi, quali = ok("stammdaten"), ok("azubi"), ok("qualifikationen")
        zeitraum = None
        if stamm and stamm.get("ausbildungsverhaeltnis"):
            v = stamm["ausbildungsverhaeltnis"]
            zeitraum = (v.get("ausbildungsbeginn"), v.get("ausbildungsende"))
        elif azubi and azubi.get("ausbildungsZeitraum"):
            z = azubi["ausbildungsZeitraum"]
            zeitraum = (z.get("ausbildungsbeginn"), z.get("ausbildungsende"))
        if zeitraum and zeitraum[0] and zeitraum[1] and quali:
            return {"stammdaten": stamm or {}, "zeitraum": zeitraum,
                    "qualifikationen": quali or {"qualifikationen": []}}
        print(f"IHK-Backend noch nicht bereit, Versuch {attempt + 1}/6 ...")
        page.wait_for_timeout(3000)
    raise SystemExit("Stammdaten nicht ladbar, IHK-Backend meldet Fehler. Skript neu starten.")


def make_sniffer(context):
    """Hört die Auth-Header aus echten API-Requests der SPA ab.

    Die SPA ruft bildung.service.ihk.de mit Bearer-Token und Org-Headern auf,
    sobald die Berichtsheft-Route lädt. Das ist das einzig verlässliche
    Login-Signal, der sessionStorage wird nicht in jedem Tab befüllt.
    """
    sniff = {"headers": None, "stamp": 0.0}

    def on_request(request):
        h = request.headers
        if "bildung.service.ihk.de" in request.url and h.get("authorization"):
            sniff["headers"] = {
                "authorization": h["authorization"],
                "x-organisation-nummer-lang": h.get("x-organisation-nummer-lang", ""),
                "x-ihk-nummer": h.get("x-ihk-nummer", ""),
                "x-ex-abb": h.get("x-ex-abb", "false"),
                "x-bereich-intern-extern": h.get("x-bereich-intern-extern", "extern"),
                "accept": "application/json",
            }
            sniff["stamp"] = time.time()

    context.on("request", on_request)
    return sniff


def on_meineihk(pg):
    return "meineihk.service.ihk.de" in (pg.url or "")


def on_sso(pg):
    return "login.gfi.ihk.de" in (pg.url or "")


def on_report_route(pg):
    return "berichtsheft/wochenansicht" in (pg.url or "")


def _app_page(context):
    return next((p for p in context.pages if on_meineihk(p)), None)


def _pump(context, ms=1000):
    """Wartet UND verarbeitet Playwright-Events. time.sleep() würde die
    request-Events des Sniffers liegen lassen (Sync-API dispatcht nur
    während eines Playwright-Aufrufs), der Sniffer bliebe blind."""
    try:
        (context.pages[0] if context.pages else context.new_page()).wait_for_timeout(ms)
    except Exception:
        time.sleep(ms / 1000)


def _wait_headers(context, sniff, seconds, nudge=False, ort=None, creds=None):
    """Wartet auf abgehörte Header. Nebenbei werden Portal-Dialoge abgeräumt
    und (mit creds) ein auftauchendes Keycloak-Formular einmalig ausgefüllt.
    nudge=True stößt die Berichtsheft-Route an, wenn wir woanders auf
    meineihk hängen (z.B. Startseite nach Login). Nie während das
    SSO-Formular offen ist und nie, wenn die Route schon stimmt, ein goto
    mittendrin reißt sonst den Login-Austausch ab."""
    app = APP_URL.format(datum="2025-01-20")
    deadline, last_nudge = time.time() + seconds, time.time()
    kc_state = {}
    while time.time() < deadline:
        if sniff["headers"]:
            return _app_page(context) or context.pages[0]
        sso = next((p for p in context.pages if on_sso(p)), None)
        if sso:
            if creds:
                _fill_keycloak_page(sso, creds[0], creds[1], kc_state)
            last_nudge = time.time()
            _pump(context)
            continue
        if _handle_portal_dialogs(context, ort):
            last_nudge = time.time()
            _pump(context)
            continue
        target = _app_page(context)
        if (nudge and target and not on_report_route(target)
                and time.time() - last_nudge > 15):
            last_nudge = time.time()
            try:
                target.goto(app, wait_until="domcontentloaded")
            except Exception:
                pass
        _pump(context)
    return None


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


def ask_password():
    while True:
        pw = getpass.getpass("Passwort (Eingabe bleibt unsichtbar): ")
        if pw == getpass.getpass("Passwort wiederholen: "):
            return pw
        print("Passwörter stimmen nicht überein, nochmal.")


def ask_credentials():
    cfg = load_config()
    email = cfg.get("email") or input("E-Mail: ").strip()
    ort = cfg.get("ihk_ort") or input("PLZ oder Ort deiner IHK (z.B. 30165 oder Hannover): ").strip()
    if cfg.get("email") != email or cfg.get("ihk_ort") != ort:
        cfg["email"], cfg["ihk_ort"] = email, ort
        save_config(cfg)
        print(f"Gespeichert in {CONFIG_PATH.name}, künftig keine erneute Eingabe. Passwort bleibt "
              "aus Sicherheitsgründen außen vor, bei Bedarf 'password' selbst in die Datei eintragen.")
    pw = cfg.get("password") or ask_password()
    return (email, pw, ort)


def _accept_cookies_upfront(context):
    """Setzt den Consent-Cookie (nur notwendige), damit der Banner gar nicht kommt."""
    try:
        context.add_cookies([{
            "name": "mihk-pub-cookie-consent",
            "value": "%7B%22cookie-consent%22%3Atrue%2C%22econda%22%3Afalse%7D",
            "domain": "meineihk.service.ihk.de", "path": "/",
        }])
    except Exception:
        pass


def _click_if(pg, selector, timeout=1500):
    try:
        loc = pg.locator(selector).first
        if not loc.count():
            return False
        loc.click(timeout=timeout)
        return True
    except Exception:
        return False


def _handle_portal_dialogs(context, ort):
    """Räumt die Portal-Dialoge ab, sobald sie auftauchen: Cookie-Banner,
    IHK-Auswahl (per PLZ/Ort, nur wenn bekannt) und die 'Sie sind zurzeit
    nicht angemeldet'-Bestätigung. Gibt True zurück, wenn etwas behandelt
    wurde. Ohne ort bleibt eine offene IHK-Auswahl dem Nutzer überlassen."""
    pg = _app_page(context)
    if not pg:
        return False
    if _click_if(pg, 'button:has-text("Nur Notwendige")'):
        return True
    try:
        finder = pg.locator("#ihk-finder-input")
        if finder.count() and ort:
            finder.first.fill(ort)
            pg.locator("mat-option").first.click(timeout=8000)
            _click_if(pg, '[role=dialog] button:has-text("IHK wechseln"), dialog button:has-text("IHK wechseln")', 3000)
            pg.wait_for_timeout(1500)
            pg.goto(APP_URL.format(datum="2025-01-20"), wait_until="domcontentloaded")
            return True
    except Exception:
        pass
    return _click_if(pg, '[role=dialog] button:has-text("Anmelden"), dialog button:has-text("Anmelden")')


def _kc_debug_dump(sso, state):
    """Einmaliger Struktur-Dump der SSO-Seite für die Fehlersuche."""
    if state.get("dumped"):
        return
    state["dumped"] = True
    try:
        info = sso.evaluate("""() => ({
          url: location.href.slice(0, 90),
          inputs: [...document.querySelectorAll('input')].map(i => ({
            type: i.type, id: i.id, name: i.name, placeholder: i.placeholder,
            sichtbar: !!(i.offsetWidth || i.offsetHeight) })),
          buttons: [...document.querySelectorAll('button, input[type=submit]')].map(b => ({
            text: (b.textContent || b.value || '').trim().slice(0, 25),
            type: b.type, id: b.id })),
          shadowRoots: [...document.querySelectorAll('*')].filter(e => e.shadowRoot).length,
          iframes: document.querySelectorAll('iframe').length,
        })""")
        print("[debug] SSO-Seite:", json.dumps(info, ensure_ascii=False))
    except Exception as e:
        print("[debug] SSO-Dump fehlgeschlagen:", repr(e)[:200])


def _fill_keycloak_page(sso, email, password, state):
    """Das IHK-Keycloak ('BS 2.0') ist zweistufig: Seite 1 nur E-Mail + Weiter,
    Seite 2 das Passwort. Beide Schritte werden einzeln erkannt und ausgefüllt.
    Versuchslimits verhindern Klick-Schleifen und Account-Sperren bei Tippfehlern."""
    _kc_debug_dump(sso, state)
    try:
        pw = sso.locator('input[type="password"]:visible')
        # Das E-Mail-Feld ist eine LUX-Angular-Komponente: dynamische Zufalls-id
        # (lux-form-control-<uuid>), kein name-Attribut. Kandidaten in absteigender
        # Treffsicherheit, der erste füllbare gewinnt.
        email_candidates = [
            sso.get_by_label("E-Mail"),
            sso.locator('input[id^="lux-form-control"]:visible'),
            sso.locator('#username'),
            sso.locator('input[type="email"]:visible'),
            sso.locator('input[type="text"]:visible'),
        ]
        if time.time() - state.get("last_dbg", 0) > 5:
            state["last_dbg"] = time.time()
            print(f"[debug] Felder: passwort={pw.count()} "
                  f"versuche={{u:{state.get('user_tries', 0)}, p:{state.get('pw_tries', 0)}}}")
        if pw.count():
            if state.get("pw_tries", 0) >= 2:
                if not state.get("warned"):
                    state["warned"] = True
                    print("Automatisches Anmelden klappt nicht, bitte im Browser fortsetzen ...")
                return
            pw.first.fill(password)
            state["pw_tries"] = state.get("pw_tries", 0) + 1
            print("[debug] Passwort eingetragen, klicke Submit")
            sso.locator('#kc-login, input[type="submit"], button[type="submit"]').first.click(timeout=3000)
            return
        if state.get("user_tries", 0) >= 3:
            return
        for cand in email_candidates:
            try:
                if not cand.count():
                    continue
                cand.first.fill(email)
                state["user_tries"] = state.get("user_tries", 0) + 1
                print("[debug] E-Mail eingetragen, klicke Weiter")
                sso.locator('button[type="submit"], #kc-login, input[type="submit"], '
                            'button:has-text("Weiter")').first.click(timeout=3000)
                return
            except Exception as e:
                print("[debug] Kandidat fehlgeschlagen:", repr(e)[:120])
    except Exception as e:
        print("[debug] Ausfüllen fehlgeschlagen:", repr(e)[:250])


def wait_for_login(context, sniff, creds):
    email, pw, ort = creds
    _accept_cookies_upfront(context)  # Consent VOR dem ersten Laden setzen
    main = context.pages[0] if context.pages else context.new_page()
    try:
        main.goto(APP_URL.format(datum="2025-01-20"), wait_until="domcontentloaded")
    except Exception:
        pass
    print("Anmeldung läuft automatisch ...")
    page = _wait_headers(context, sniff, 300, nudge=True, ort=ort, creds=(email, pw))
    if page:
        print("Angemeldet.")
        return page
    raise TimeoutError("Login nicht innerhalb von 5 Minuten erkannt.")


def progress(done, total, label):
    width = 32
    filled = round(width * done / total) if total else width
    bar = "#" * filled + "-" * (width - filled)
    end = "\n" if done >= total else ""
    print(f"\r{label} [{bar}] {done}/{total}", end=end, flush=True)


def refresh_session(page, sniff):
    """Token abgelaufen. Route neu laden, die SPA holt einen frischen Token,
    der Sniffer fängt ihn beim nächsten API-Call der App."""
    old_stamp = sniff["stamp"]
    page.goto(APP_URL.format(datum="2025-01-20"), wait_until="domcontentloaded")
    for _ in range(30):
        if sniff["stamp"] > old_stamp:
            return
        page.wait_for_timeout(1000)


def collect_weeks(page, sniff, mondays):
    weeks = []
    total = len(mondays)
    for i, d in enumerate(mondays, 1):
        arg = {"datum": d.isoformat(), "headers": sniff["headers"]}
        r = page.evaluate(WEEK_JS, arg)
        if r["status"] == 401:  # Token abgelaufen -> erneuern und wiederholen
            refresh_session(page, sniff)
            arg["headers"] = sniff["headers"]
            r = page.evaluate(WEEK_JS, arg)
        data = r.get("data")
        if data and data.get("tagesBerichte"):
            weeks.append(data)
        progress(i, total, "Download")
    return weeks


CSS = """
  * { box-sizing: border-box; }
  body { font-family: 'Segoe UI', 'DejaVu Sans', 'Liberation Sans', Arial, sans-serif; color: #1a1a1a; font-size: 11px; margin: 0; padding: 0 24px 18px; }
  .kopf { border-bottom: 2px solid #005a9c; padding: 6px 0 4px; margin-bottom: 6px; }
  .kopf h1 { font-size: 15px; color: #005a9c; margin: 0; }
  .kopf .azubi { font-size: 10px; color: #555; margin-top: 2px; }
  .status { color: #2a7d2a; font-size: 10px; margin: 0 0 10px; }
  .tagkopf { font-weight: 700; margin: 10px 0 4px; display: flex; justify-content: space-between; }
  .tagkopf .an { font-weight: 400; color: #666; }
  .tag ul { margin: 0 0 4px; padding-left: 0; list-style: none; }
  .tag li { display: grid; grid-template-columns: 70px 1fr; gap: 2px 10px; padding: 3px 0; border-bottom: 1px solid #eee; align-items: start; }
  .dauer { color: #005a9c; font-variant-numeric: tabular-nums; }
  .inhalt { grid-column: 2; }
  .q { color: #888; font-size: 9px; font-style: italic; display: block; margin-top: 1px; }
  .rt p { margin: 2px 0; }
  .rt ul { margin: 2px 0; padding-left: 16px; }
  .rt li { margin: 0; }
  .none { color: #aaa; margin: 0; }
  .leer .tagkopf { font-weight: 400; color: #aaa; }
"""


def quali_map(meta):
    return {q["positionsId"]: q["qbezeichnung"]
            for q in meta["qualifikationen"].get("qualifikationen", [])}


def flatten_entries(obj):
    """Ein Eintrag ist entweder konkret (hat 'text') oder ein Wrapper mit
    betrieb/schule-Untereinträgen (Freitext-Hefte). Liefert die konkreten."""
    if not isinstance(obj, dict):
        return []
    if "betrieb" in obj or "schule" in obj:
        return [s for s in (obj.get("betrieb"), obj.get("schule")) if isinstance(s, dict)]
    return [obj]


def clean_html(raw):
    # ponytail: eigene Heft-Daten -> lokales PDF, nur aktive Inhalte raus
    return re.sub(r"(?is)<(script|style)\b[^>]*>.*?</\1>", "", raw)


def is_html_entry(e):
    typus = e.get("typus")
    if typus == "FreitextEintragDto":
        return True
    if typus == "StichpunktEintragDto":
        return False  # Klartext, darf '<>' enthalten (z.B. "Louis <> Hanna")
    return bool(re.search(r"<[a-zA-Z/][^>]*>", e.get("text") or ""))


def entry_li(e, qlabels):
    raw = (e.get("text") or "").strip()
    if raw and is_html_entry(e):
        body = f"<div class='rt'>{clean_html(raw)}</div>"
    elif raw:
        body = escape(raw)
    else:
        body = "<span class='none'>&mdash;</span>"
    q = qlabels(e)
    q_html = f"<span class='q'>{escape(q)}</span>" if q else ""
    return (f"<li><span class='dauer'>{escape(fmt_duration(e.get('dauer')))}</span>"
            f"<div class='inhalt'>{body}{q_html}</div></li>")


def week_document(meta, week, qmap):
    def quali_labels(eintrag):
        ids = [q.get("berufsbildPositionId") for q in eintrag.get("qualifikationen") or []]
        return ", ".join(qmap.get(i, f"Position {i}") for i in ids if i is not None)

    stamm = meta["stammdaten"]
    verh = stamm.get("ausbildungsverhaeltnis", {})
    azubi = f"{stamm.get('vorname','')} {stamm.get('name','')}".strip()
    beruf = verh.get("berufsbild", {}).get("bezeichnung", "")

    tage = week["tagesBerichte"]
    anfang, ende = parse_date(tage[0]["datum"]), parse_date(tage[-1]["datum"])
    iso_kw = anfang.isocalendar().week
    status = week.get("wochenStatus", {})

    info = []
    if status.get("einreichungsZeitpunkt"):
        info.append(f"Eingereicht am {fmt_de(parse_date(status['einreichungsZeitpunkt']))}")
    if status.get("abbFreigabeZeitpunkt") and status.get("abbName"):
        info.append(f"Freigegeben von {escape(status['abbName'])} am "
                    f"{fmt_de(parse_date(status['abbFreigabeZeitpunkt']))}")
    status_line = (f"<p class='status'>{label(status.get('freigabestatus'))}"
                   + (" &mdash; " + " &middot; ".join(info) if info else "") + "</p>")

    rows = []
    # Datengetrieben statt nach wochenBasis-Enum: Wochentext rendern, wenn er
    # existiert (wochenbasierte Hefte), Tage rendern, wenn sie Inhalt haben.
    we_entries = [e for e in flatten_entries(week.get("wochenEintrag"))
                  if (e.get("text") or "").strip()]
    if we_entries:
        items = "".join(entry_li(e, quali_labels) for e in we_entries)
        rows.append(f"<div class='tag'><div class='tagkopf'>Woche</div><ul>{items}</ul></div>")
    for t in tage:
        entries = [c for e in (t.get("eintraege") or []) for c in flatten_entries(e)]
        if not entries and not t.get("anwesenheit"):
            continue  # nicht erfasste Tage (meist Wochenende) auslassen
        d = parse_date(t["datum"])
        head = (f"<div class='tagkopf'>{WEEKDAYS[d.weekday()]}, {fmt_de(d)}"
                f"<span class='an'>{label(t.get('anwesenheit'))}"
                + (f", {label(t.get('ort'))}" if t.get("ort") else "") + "</span></div>")
        if not entries:
            rows.append(f"<div class='tag leer'>{head}<p class='none'>keine Einträge</p></div>")
            continue
        items = "".join(entry_li(e, quali_labels) for e in entries)
        rows.append(f"<div class='tag'>{head}<ul>{items}</ul></div>")

    azubi_zeile = " &middot; ".join(x for x in (escape(azubi), escape(beruf)) if x)
    return f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<style>{CSS}</style></head><body>
<div class='kopf'><h1>KW {iso_kw} &mdash; {fmt_de(anfang)} bis {fmt_de(ende)}</h1>
<div class='azubi'>{azubi_zeile}</div></div>
{status_line}{''.join(rows)}</body></html>"""


# -- Import aus einem Word-Berichtsheft ------------------------------------
# Alternative Quelle zum IHK-Download, falls das Heft in einer .docx geführt
# wird. Format: je Woche ein Absatz "N. Ausbildungswoche (DD.MM.-DD.MM.YYYY)",
# darunter je Tätigkeit ein Absatz. Ohne Tage und ohne Stunden, das ist der
# Wochenheft-Fall. Die Tätigkeiten werden reihum auf Mo-Fr verteilt, die
# Stunden füllt der Uploader später auf (apply_default_hours).

_DASH = "–—-"   # en-dash, em-dash, Bindestrich, als Datums-Trenner
_SCHUL_KW = re.compile(r"^\s*(berufsschule|lernfeld|lf\s*\d|schule)\b", re.I)


def ensure_docx():
    try:
        import docx  # noqa: F401
    except ImportError:
        import subprocess
        print("Installiere python-docx ...")
        subprocess.run([sys.executable, "-m", "pip", "install", "python-docx"])


def week_monday(text):
    """Montag der Woche aus einem Header-Absatz, sonst None. Das Startdatum kann
    das Jahr weglassen (steht dann nur beim Enddatum), bei Jahreswechsel liegt
    der Start ein Jahr davor."""
    if "Ausbildungswoche" not in text:
        return None
    m = re.search(rf"(\d{{1,2}})\.(\d{{1,2}})\.(\d{{4}})?\s*[{_DASH}]\s*(\d{{1,2}})\.(\d{{1,2}})\.(\d{{4}})", text)
    if not m:
        return None
    d1, m1, y1, _, m2, y2 = m.groups()
    year = int(y1) if y1 else int(y2) - (int(m1) > int(m2))
    return monday(date(year, int(m1), int(d1)))


def _docx_week(mon, eintraege):
    """Eine Woche im IHK-Schema. Mo-Fr, Tätigkeiten reihum verteilt, Ort per
    Stichwort (Berufsschule/Lernfeld -> Schule, sonst Betrieb)."""
    tage = [{"datum": (mon + timedelta(days=i)).isoformat(),
             "anwesenheit": "ANWESEND", "ort": None, "eintraege": []}
            for i in range(5)]
    for i, text in enumerate(eintraege):
        ort = "BERUFSSCHULE" if _SCHUL_KW.search(text) else "BETRIEB"
        tage[i % 5]["eintraege"].append(
            {"typus": "StichpunktEintragDto", "text": text, "dauer": None,
             "ort": ort, "qualifikationen": []})
    return {"tagesBerichte": [t for t in tage if t["eintraege"]]}


def import_docx(path):
    """Liest ein Word-Berichtsheft und liefert dieselbe Struktur wie der
    IHK-Download. Ohne Stammdaten und Qualifikationen, die kennt die docx nicht."""
    ensure_docx()
    import docx
    doc = docx.Document(path)
    wochen, mon, eintraege = [], None, []
    for p in doc.paragraphs:
        t = p.text.strip()
        if not t:
            continue
        m = week_monday(t)
        if m:
            if mon and eintraege:
                wochen.append(_docx_week(mon, eintraege))
            mon, eintraege = m, []
        elif "Ausbildungswoche" in t:
            continue                              # Header ohne parsbares Datum
        elif mon and re.search(r"[^\W\d_]", t):   # nur Absätze mit Buchstaben
            eintraege.append(t)
    if mon and eintraege:
        wochen.append(_docx_week(mon, eintraege))
    return {"stammdaten": {}, "qualifikationen": {"qualifikationen": []}, "wochen": wochen}


def render_pdfs(page, run_dir, meta, weeks):
    """Rendert je Woche eine PDF nach run_dir, gibt die Dateigrößen zurück.
    Geteilt von IHK-Download und Word-Import."""
    qmap = quali_map(meta)
    sizes = []
    for i, w in enumerate(weeks, 1):
        montag = parse_date(w["tagesBerichte"][0]["datum"])
        name = f"{montag.isoformat()}_KW{montag.isocalendar().week:02d}.pdf"
        page.set_content(week_document(meta, w, qmap), wait_until="load")
        page.pdf(path=str(run_dir / name), format="A4", print_background=True,
                 margin={"top": "12mm", "bottom": "12mm", "left": "10mm", "right": "10mm"})
        sizes.append((run_dir / name).stat().st_size)
        progress(i, len(weeks), "PDF     ")
    return sizes


def run_docx_import(path, out_dir):
    """Importiert eine Word-Datei, schreibt die berichtsheft.json wie der
    IHK-Download und rendert je Woche eine PDF (headless Chromium)."""
    out_dir = Path(out_dir)
    data = import_docx(str(path))
    run_dir = out_dir / datetime.now().strftime("Berichtsheft_%Y-%m-%d_%H-%M-%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "berichtsheft.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    weeks = data["wochen"]
    tage = sum(len(w["tagesBerichte"]) for w in weeks)
    print(f"\n{len(weeks)} Wochen ({tage} Tage) aus {Path(path).name} gelesen. Rendere PDFs ...")

    ensure_chromium()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        sizes = render_pdfs(browser.new_page(), run_dir, data, weeks)
        browser.close()

    print(f"\nFertig. JSON und {len(weeks)} PDFs in {run_dir}")
    print("Jetzt hochladen mit dem Menüpunkt 'upload'.")
    if sizes and max(sizes) < 8_000:
        print("WARNUNG: PDFs verdächtig klein, auf Linux fehlen vermutlich System-Schriften.")
        print("Beheben mit:  python -m playwright install --with-deps chromium")


def import_docx_interactive():
    """Menüpunkt Word-Import. Sucht die .docx selbst, lässt bei mehreren
    Treffern wählen, importiert ohne Login und ohne Browser."""
    print(BANNER)
    seen, files = set(), []
    for base in (HERE, Path.cwd()):
        for f in sorted(base.glob("*.docx")):
            if not f.name.startswith("~$") and f.resolve() not in seen:
                seen.add(f.resolve())
                files.append(f)
    if not files:
        print("Keine Word-Datei (.docx) gefunden.")
        print(f"Lege dein Berichtsheft als .docx hier ab und starte erneut:\n  {HERE}")
        return
    if len(files) == 1:
        path = files[0]
        print(f"Word-Datei: {path.name}")
    else:
        print("\n  Welche Word-Datei importieren?\n")
        for i, f in enumerate(files, 1):
            print(f"    [{i}] {f.name}")
        while True:
            w = input("\n  Auswahl (Zahl): ").strip()
            if w.isdigit() and 1 <= int(w) <= len(files):
                path = files[int(w) - 1]
                break
            print("  Ungültige Eingabe, nochmal.")
    run_docx_import(path, HERE / "Berichtsheft_Export")


def main():
    print(BANNER)
    out_dir = HERE / "Berichtsheft_Export"
    out_dir.mkdir(parents=True, exist_ok=True)

    ensure_chromium()
    creds = ask_credentials()

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        context.new_page()

        sniff = make_sniffer(context)
        page = wait_for_login(context, sniff, creds)
        meta = get_meta(page, sniff)

        beginn = parse_date(meta["zeitraum"][0])
        ende = min(date.today(), parse_date(meta["zeitraum"][1]))

        mondays = []
        cur = monday(beginn)
        while cur <= monday(ende):
            mondays.append(cur)
            cur += timedelta(weeks=1)

        print(f"Lade {len(mondays)} Wochen von {fmt_de(mondays[0])} bis {fmt_de(mondays[-1])} ...")
        weeks = collect_weeks(page, sniff, mondays)
        print(f"{len(weeks)} Wochen mit Einträgen gefunden.")
        browser.close()

        run_dir = out_dir / datetime.now().strftime("Berichtsheft_%Y-%m-%d_%H-%M-%S")
        run_dir.mkdir(parents=True, exist_ok=True)

        (run_dir / "berichtsheft.json").write_text(
            json.dumps({"stammdaten": meta["stammdaten"],
                        "qualifikationen": meta["qualifikationen"],
                        "wochen": weeks}, ensure_ascii=False, indent=2),
            encoding="utf-8")

        # page.pdf() läuft nur im headless-Chromium, daher separate Instanz.
        pdf_browser = p.chromium.launch(headless=True)
        pdf_sizes = render_pdfs(pdf_browser.new_page(), run_dir, meta, weeks)
        pdf_browser.close()

    print(f"Fertig. {len(weeks)} PDFs in {run_dir}")
    # Winzige PDFs = Text wurde nicht gerendert, auf Linux fehlen dann meist
    # die System-Schriften für das Playwright-Chromium.
    if pdf_sizes and max(pdf_sizes) < 8_000:
        print("WARNUNG: Die PDFs sind verdächtig klein, vermutlich fehlen System-Schriften.")
        print("Auf Linux beheben mit:  python -m playwright install --with-deps chromium")
        print("oder:  sudo apt install fonts-liberation fontconfig")


if __name__ == "__main__":
    main()
