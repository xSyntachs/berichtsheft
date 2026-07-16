#!/usr/bin/env python3
"""
apprentio-Uploader für das IHK-Berichtsheft

Liest berichtsheft.json aus einem Export-Ordner des Downloaders und pflegt
jeden einzelnen Tages-Eintrag als Tätigkeitsnachweis in apprentio ein, mit
allem was die Daten hergeben:
  - Datum, Zeitaufwand, Tätigkeitstext
  - Anwesenheit (Anwesend/Urlaub/Feiertag/Abwesend)
  - Ausbildungsort (Ausbildungsstätte/Schule)
  - Lernziel-Verknüpfung, wenn die IHK-Qualifikation im apprentio-Lehrplan
    per Titel auffindbar ist; sonst wandert der Qualifikationsname in den Text

Die richtige Kalenderwoche ergibt sich automatisch: apprentio hat pro Woche
einen Report, dessen Startdatum gegen das Eintragsdatum gemappt wird.
Bereits vorhandene Einträge (gleiches Datum + gleicher Text) werden
übersprungen, das Skript ist also beliebig oft wiederholbar.

Anmeldung: Beim Start werden E-Mail und Passwort abgefragt, das Login-Formular
füllt das Skript selbst aus. Jeder Lauf startet mit frischem Browser.

Setup einmalig:  pip install playwright  &&  playwright install chromium

Nach dem Upload werden die befüllten Wochen automatisch eingereicht (Status
SUBMITTED), abgelehnte Wochen (DECLINED) werden dabei erneut vorgelegt. Der
Ausbilder wird bei genau einem möglichen Kandidaten selbst gewählt, sonst
per Menü ausgewählt. Einreichen ist ENDGÜLTIG, davor kommt eine
Sicherheitsabfrage.

Start:
    python berichtsheft_upload.py    # neuester Export, Upload + Einreichen, keine Flags
"""

import getpass
import html
import json
import re
import time
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

if getattr(sys.stdout, "reconfigure", None):  # echte Umlaute unabhängig von der Konsolen-Codepage
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Im gefrorenen Build liegen Config und Export-Ordner neben der EXE, nicht im
# Temp-Entpackpfad von __file__.
HERE = (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent.parent)   # Dev: Repo-Root, nicht src/
CONFIG_PATH = HERE / "berichtsheft_upload.config.json"

BANNER = r"""
   _   _ ____
  | | | |  _ \
  | | | | |_) |    A P P R E N T I O
  | |_| |  __/     BERICHTSHEFT-UPLOADER
   \___/|_|
"""

PRESENCE = {"ANWESEND": "PRESENT", "ABWESEND": "ABSENT", "KRANK": "ABSENT",
            "URLAUB": "HOLIDAY", "FEIERTAG": "PUBLIC_HOLIDAY"}
LOCATION = {"BETRIEB": "COMPANY", "BERUFSSCHULE": "SCHOOL", "SCHULE": "SCHOOL",
            "HOMEOFFICE": "COMPANY", "UEBERBETRIEBLICH": "COMPANY"}

# Generischer API-Aufruf im Page-Kontext. Laravel-Session läuft über Cookies,
# Mutationen brauchen den XSRF-Token aus dem Cookie.
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


# Batch-Anlage: ein evaluate-Aufruf schickt mehrere POSTs parallel (Promise.all),
# spart pro Eintrag den Python-Browser-Roundtrip. Kein Rate-Limit beobachtet.
BATCH_JS = r"""
async ({ jobs }) => {
  const xsrf = decodeURIComponent((document.cookie.match(/XSRF-TOKEN=([^;]+)/) || [])[1] || '');
  const H = { Accept: 'application/json', 'X-XSRF-TOKEN': xsrf, 'Content-Type': 'application/json' };
  const one = async j => {
    try {
      const r = await fetch('/api/v1/reporting/activities', { method: 'POST', headers: H, body: JSON.stringify(j.body) });
      const t = await r.text();
      let b = null; try { b = JSON.parse(t); } catch {}
      if (r.status === 201 && j.cur_ids.length)
        await fetch(`/api/v1/reporting/activities/${b.data.id}/curriculum-entries`,
                    { method: 'POST', headers: H, body: JSON.stringify({ curriculum_entry_ids: j.cur_ids }) });
      return { status: r.status, err: r.status === 201 ? null : (t || '').slice(0, 120) };
    } catch (e) {
      return { status: -1, err: String(e).slice(0, 120) };
    }
  };
  return Promise.all(jobs.map(one));
}
"""

BATCH_SIZE = 8


def api(page, method, url, body=None):
    return page.evaluate(API_JS, {"method": method, "url": url, "body": body})


def minutes(iso):
    """ISO-8601-Dauer 'PT3H30M' -> 210."""
    if not iso:
        return 0
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
    if not m:
        return 0
    return int(m.group(1) or 0) * 60 + int(m.group(2) or 0)


def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def progress(done, total, label):
    width = 32
    filled = round(width * done / total) if total else width
    bar = "#" * filled + "-" * (width - filled)
    end = "\n" if done >= total else ""
    print(f"\r{label} [{bar}] {done}/{total}", end=end, flush=True)


def find_export():
    runs = sorted((HERE / "Berichtsheft_Export").glob("Berichtsheft_*"))
    if not runs:
        raise SystemExit("Kein Export-Ordner gefunden. Erst berichtsheft_download.py laufen lassen.")
    p = runs[-1]
    j = p / "berichtsheft.json"
    if not j.exists():
        raise SystemExit(f"{j} existiert nicht.")
    return p, json.loads(j.read_text(encoding="utf-8"))


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


def normalize_tenant(v):
    """'xsyntachs' -> https://xsyntachs.apprentio.de, volle URL bleibt."""
    v = (v or "").strip().rstrip("/")
    if not v:
        return ""
    if "://" in v:
        return v
    return "https://" + (v if "." in v else v + ".apprentio.de")


def resolve_tenant():
    cfg = load_config()
    tenant = cfg.get("tenant")
    if not tenant:
        tenant = input("apprentio-Adresse (z.B. firma oder https://firma.apprentio.de): ")
    tenant = normalize_tenant(tenant)
    if tenant and tenant != cfg.get("tenant"):
        cfg["tenant"] = tenant
        save_config(cfg)
    return tenant


def ask_credentials():
    cfg = load_config()
    email = cfg.get("email") or input("E-Mail: ").strip()
    if cfg.get("email") != email:
        cfg["email"] = email
        save_config(cfg)
        print(f"E-Mail in {CONFIG_PATH.name} gespeichert, künftig keine erneute Eingabe. "
              "Passwort bleibt aus Sicherheitsgründen außen vor, bei Bedarf 'password' in die Datei.")
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


def load_reports(page):
    r = api(page, "GET", "/api/v1/reporting/reports?page=1&page_size=1000")
    if r["status"] != 200:
        raise SystemExit(f"Reports nicht lesbar (HTTP {r['status']}). Rechte prüfen.")
    return {item["data"]["from"]: item["data"]["id"] for item in r["body"]["data"]}


def load_curriculum(page):
    r = api(page, "GET", "/api/v1/qualification/curriculum-entries?page=1&page_size=1000")
    if r["status"] != 200:
        return {}
    return {norm(item["data"]["title"]): item["data"]["id"] for item in r["body"]["data"]}


def existing_keys(page, report_id):
    r = api(page, "GET", f"/api/v1/reporting/activities?report_id={report_id}&page=1&page_size=1000")
    if r["status"] != 200:
        return set()
    return {(a["data"]["date_accomplished"], dedup_key(a["data"]["description"]))
            for a in r["body"]["data"]}


def clean_description(text):
    """Entschärft den HTML-Text vor dem Upload. Inline-Bilder (oft riesige
    base64-Data-URIs) und aktive Inhalte raus, dann harte Längengrenze, sonst
    quittiert der apprentio-Server sehr große Beschreibungen mit HTTP 500."""
    text = re.sub(r"(?is)<img\b[^>]*>", "", text)
    text = re.sub(r"(?is)<(script|style)\b[^>]*>.*?</\1>", "", text)
    text = re.sub(r"data:[^\"')\s]+", "", text)
    if len(text) > 50_000:
        text = text[:50_000] + " …[gekürzt]"
    return text


def flatten_entries(obj):
    """Ein Eintrag ist entweder konkret (hat 'text') oder ein Wrapper mit
    betrieb/schule-Untereinträgen (Freitext-Hefte). Liefert die konkreten."""
    if not isinstance(obj, dict):
        return []
    if "betrieb" in obj or "schule" in obj:
        return [s for s in (obj.get("betrieb"), obj.get("schule")) if isinstance(s, dict)]
    return [obj]


def _quali_ids(e):
    return [q.get("berufsbildPositionId") for q in e.get("qualifikationen") or []]


def dedup_key(s):
    """Vergleichsschlüssel für den Dedup. apprentio schreibt die description
    als HTML zurück, escapt < > & und schließt Tags (aus 'a -> b' wird
    'a -&gt; b', aus '<code>' wird '<code></code>'). Gesendeter Rohtext und
    gespeicherte Fassung sind also nie zeichengleich. Tags raus, Entities
    auflösen, dann normalisieren, damit beide Seiten auf denselben Kern
    fallen und ein Eintrag beim Wiederholungslauf nicht erneut angelegt wird."""
    return norm(html.unescape(re.sub(r"<[^>]+>", " ", s or "")))


def apply_default_hours(jobs, default_min):
    """Tage ohne echte Stunden auf default_min auffüllen, gleichmäßig auf die
    Einträge des Tages verteilt. Tage mit echter Dauer bleiben unangetastet.
    default_min <= 0 lässt die Stunden wie in den Daten (faithful)."""
    if default_min <= 0:
        return
    for group in _group_by_day(jobs).values():
        if sum(j["minutes"] for j in group) == 0:
            share = default_min // len(group)
            for k, j in enumerate(group):
                j["minutes"] = share + (default_min - share * len(group) if k == 0 else 0)


def _group_by_day(jobs):
    groups = defaultdict(list)
    for j in jobs:
        groups[(j["report_id"], j["date"])].append(j)
    return groups


def _werktage(tage):
    """Anwesende Werktage (Mo-Fr) einer Woche, ersatzweise der erste Tag."""
    wt = [t for t in tage if t.get("anwesenheit")
          and datetime.strptime(t["datum"], "%Y-%m-%d").weekday() < 5]
    return wt or tage[:1]


def iter_entries(week):
    """Liefert (datum, anwesenheit, ort, text, dauer_iso, quali_ids) je Eintrag.
    Text kann HTML sein (FreitextEintragDto), apprentio speichert das direkt.
    Wrapper (betrieb/schule) werden flachgemacht. Ein Wochenheft (Text nur im
    wochenEintrag) wird auf die anwesenden Werktage verteilt, weil apprentio
    tagesbasiert ist, so entsteht ein Eintrag je Arbeitstag."""
    tage = week.get("tagesBerichte") or []
    we = [e for e in flatten_entries(week.get("wochenEintrag")) if (e.get("text") or "").strip()]
    for e in we:
        for t in _werktage(tage):
            yield (t["datum"], t.get("anwesenheit"), e.get("ort") or t.get("ort"),
                   e.get("text"), e.get("dauer"), _quali_ids(e))
    for tag in tage:
        for raw in tag.get("eintraege") or []:
            for e in flatten_entries(raw):
                if (e.get("text") or "").strip():
                    yield (tag["datum"], tag.get("anwesenheit"), e.get("ort") or tag.get("ort"),
                           e.get("text"), e.get("dauer"), _quali_ids(e))


def pick_reviewer(cands):
    print("\nAusbilder:in wählen (gilt für alle Wochen dieses Laufs):")
    for i, c in enumerate(cands, 1):
        print(f"  [{i}] {c.get('full_name')}")
    while True:
        w = input("Auswahl: ").strip()
        if w.isdigit() and 1 <= int(w) <= len(cands):
            return cands[int(w) - 1]
        low = w.lower()
        hit = [c for c in cands if low and low in (c.get("full_name") or "").lower()]
        if len(hit) == 1:
            return hit[0]
        print("Ungültig, Nummer oder eindeutiger Namensteil.")


def submit_reports(page):
    """Reicht alle befüllten Wochen ein (Status SUBMITTED), offene (CREATING)
    wie abgelehnte (DECLINED, erneutes Vorlegen). Achtung, das ist endgültig,
    ein eingereichter Report lässt sich nur vom Prüfer per Ablehnen wieder
    öffnen. Der Ausbilder wird einmal pro Lauf bestimmt: bei genau einem
    Kandidaten automatisch, sonst per Menü."""
    reports = [r["data"] for r in
               api(page, "GET", "/api/v1/reporting/reports?page=1&page_size=1000")["body"]["data"]]
    offen = [r for r in reports if r["state"] in ("CREATING", "DECLINED") and r["activities_count"] > 0]
    if not offen:
        print("Keine offenen Wochen zum Einreichen.")
        return
    done, errors, no_reviewer, reviewer = 0, [], [], None
    for i, r in enumerate(offen, 1):
        cands = [c["data"] for c in api(page, "GET",
                 "/api/v1/users-location-independent-simple?"
                 f"f%5Bpossible_reviewers_for_report%5D={r['id']}")["body"]["data"]]
        if reviewer and any(c["id"] == reviewer["id"] for c in cands):
            cand = reviewer
        elif len(cands) == 1:
            cand = cands[0]
        elif cands:
            cand = pick_reviewer(cands)
        else:
            no_reviewer.append(r["from"])
            continue
        reviewer = cand
        body = {"id": r["id"], "from": r["from"], "to": r["to"], "type": r["type"],
                "state": "SUBMITTED", "reviewer_id": cand["id"]}
        st = api(page, "PATCH", f"/api/v1/reporting/reports/{r['id']}", body)["status"]
        if st == 200:
            done += 1
        else:
            errors.append((r["from"], st))
        progress(i, len(offen), "Einreich")
    print(f"{done} Wochen eingereicht" + (f", {len(errors)} fehlgeschlagen" if errors else "") + ".")
    if no_reviewer:
        print(f"{len(no_reviewer)} Wochen ohne möglichen Ausbilder übersprungen: "
              + ", ".join(no_reviewer[:6]))


def main():
    print(BANNER)
    export_dir, data = find_export()
    weeks = data["wochen"]
    quali_name = {q["positionsId"]: q["qbezeichnung"]
                  for q in data["qualifikationen"].get("qualifikationen", [])}
    print(f"Export: {export_dir}  ({len(weeks)} Wochen)")

    tenant = resolve_tenant()
    std_pro_tag = load_config().get("stunden_pro_tag", 8)
    print(f"Stunden pro Tag ohne echte Dauer: {std_pro_tag}"
          + (" (faithful, keine Auffüllung)" if std_pro_tag <= 0 else ""))
    ensure_chromium()
    creds = ask_credentials()

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        wait_for_login(page, tenant, creds)

        my_id = api(page, "GET", "/api/v1/users/me")["body"]["data"]["id"]
        reports = load_reports(page)
        curriculum = load_curriculum(page)
        print(f"{len(reports)} apprentio-Wochen, {len(curriculum)} Lernziele gefunden.")

        # Alle Einträge flach einsammeln und gegen Reports mappen
        jobs, skipped_weeks = [], []
        for w in weeks:
            week_from = w["tagesBerichte"][0]["datum"]
            report_id = reports.get(week_from)
            if not report_id:
                skipped_weeks.append(week_from)
                continue
            for datum, anw, ort, text, dauer, quali_ids in iter_entries(w):
                text = clean_description(text.strip())
                if not text:
                    continue
                cur_ids, unmatched = [], []
                for qid in quali_ids:
                    name = quali_name.get(qid)
                    cid = curriculum.get(norm(name)) if name else None
                    if cid:
                        cur_ids.append(cid)
                    elif name:
                        unmatched.append(name)
                if unmatched:  # Info erhalten, auch ohne Lehrplan-Treffer
                    text += "\n[Qualifikation: " + ", ".join(unmatched) + "]"
                jobs.append({"report_id": report_id, "date": datum, "text": text,
                             "minutes": minutes(dauer), "presence": PRESENCE.get(anw),
                             "location": LOCATION.get(ort), "cur_ids": cur_ids})

        apply_default_hours(jobs, std_pro_tag * 60)

        # Duplikate gegen den Bestand filtern (Wiederholungsläufe)
        seen = {}
        for rid in {j["report_id"] for j in jobs}:
            seen[rid] = existing_keys(page, rid)
        todo = [j for j in jobs if (j["date"], dedup_key(j["text"])) not in seen[j["report_id"]]]
        dupes = len(jobs) - len(todo)

        print(f"{len(jobs)} Einträge gesamt, {dupes} schon vorhanden, {len(todo)} neu.")

        def job_body(j):
            body = {"description": j["text"], "minutes_used": j["minutes"],
                    "date_accomplished": j["date"], "report_id": j["report_id"],
                    "user_id": my_id}
            if j["presence"]:
                body["presence"] = j["presence"]
            if j["location"]:
                body["location"] = j["location"]
            return body

        failed = []
        for start in range(0, len(todo), BATCH_SIZE):
            chunk = todo[start:start + BATCH_SIZE]
            payload = [{"body": job_body(j), "cur_ids": j["cur_ids"]} for j in chunk]
            for j, r in zip(chunk, page.evaluate(BATCH_JS, {"jobs": payload})):
                if r["status"] != 201:
                    failed.append(j)
            progress(min(start + BATCH_SIZE, len(todo)), len(todo), "Upload  ")

        # Transiente Fehler (z.B. 500 unter Parallellast) einzeln wiederholen.
        errors = []
        if failed:
            print(f"{len(failed)} Fehler, Einzel-Wiederholung ...")
            for i, j in enumerate(failed, 1):
                r = api(page, "POST", "/api/v1/reporting/activities", job_body(j))
                if r["status"] == 201:
                    if j["cur_ids"]:
                        aid = r["body"]["data"]["id"]
                        api(page, "POST", f"/api/v1/reporting/activities/{aid}/curriculum-entries",
                            {"curriculum_entry_ids": j["cur_ids"]})
                else:
                    detail = ((r["body"] or {}).get("error") or {}).get("errors") or r["body"]
                    errors.append((j["date"], r["status"], f"{len(j['text'])} Zeichen: {str(detail)[:300]}"))
                progress(i, len(failed), "Retry   ")

        print(f"Fertig. {len(todo) - len(errors)} angelegt, {dupes} übersprungen.")
        for d, s, msg in errors[:10]:
            print(f"FEHLER {d}: HTTP {s} {msg}")
        if len(errors) > 10:
            print(f"... und {len(errors) - 10} weitere Fehler.")

        print("\nEinreichen ist ENDGÜLTIG, eingereichte Wochen kann nur der "
              "Prüfer per Ablehnen wieder öffnen.")
        if input("Alle befüllten Wochen jetzt einreichen? [ja/nein]: ").strip().lower() == "ja":
            submit_reports(page)
        else:
            print("Einreichen übersprungen, Wochen bleiben auf 'Erstellend'.")

        browser.close()
    if skipped_weeks:
        print(f"{len(skipped_weeks)} Wochen ohne apprentio-Report (außerhalb Zeitraum): "
              + ", ".join(skipped_weeks[:5]) + ("..." if len(skipped_weeks) > 5 else ""))


if __name__ == "__main__":
    main()
