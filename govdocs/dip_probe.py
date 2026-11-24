"""Standalone DIP API probe v2 — stdlib only, no venv, writes nothing.
Prints the API's own error body on failure so we can see what it wants.
Run:  python3 dip_probe.py"""
import json, urllib.request, urllib.parse, urllib.error

KEY = "OSOegLs.PR2lwJ1dwCeje9vTj7FPOt3hvpYKtwKkhw"  # public key, valid to 05/2026
BASE = "https://search.dip.bundestag.de/api/v1"

def call(path, params):
    params = dict(params); params["apikey"] = KEY
    url = f"{BASE}/{path}?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try: body = json.dumps(json.loads(body), ensure_ascii=False, indent=2)
        except Exception: pass
        return e.code, body

def run(label, path, params):
    print("=" * 68); print(label); print(f"  {path}  {params}"); print("=" * 68)
    status, data = call(path, params)
    if status == 200 and isinstance(data, dict):
        docs = data.get("documents", [])
        print(f"  200 OK  numFound={data.get('numFound')}  returned={len(docs)}")
        if docs:
            print("  FIELDS:", ", ".join(sorted(docs[0].keys())))
            for ex in docs[:6]:
                t = (ex.get("titel") or "")[:72]
                dat = ex.get("datum") or ex.get("aktualisiert") or ""
                res = ex.get("ressort") or ex.get("herausgeber") or ""
                if isinstance(res, list): res = ",".join(res)
                print(f"    [{dat}] {t}  <{res}>")
    else:
        print(f"  {status} — response body:")
        print("  " + str(data)[:800].replace("\n", "\n  "))
    print()

# A: barest possible call — just the key. Proves reachability + key validity.
run("A: bare list, no filters", "drucksache", {})
# B: add format=json only
run("B: format=json only", "drucksache", {"format": "json"})
# C: try the documented date param from the info PDF (f.datum.start/.end)
run("C: date window", "drucksache", {"f.datum.start": "2026-08-01", "f.datum.end": "2026-09-06"})
# D: originator filter guesses — see which (if any) the API accepts
run("D: urheber filter", "drucksache", {"f.urheber": "Auswärtiges Amt"})
run("E: vorgang + ressort", "vorgang", {"f.ressort": "Auswärtiges Amt"})
