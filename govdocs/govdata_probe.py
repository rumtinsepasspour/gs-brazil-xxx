"""Standalone GovData.de probe — stdlib only, no venv, writes nothing.
GovData is the German federal open-data portal, running CKAN (same API as
data.gov / data.gov.uk). Tests whether AA / BPA / chancellery publications
are catalogued there on an UNGATED host, and in a shape a collector can use.
Run:  python3 govdata_probe.py"""
import json, urllib.request, urllib.parse, urllib.error

BASE = "https://www.govdata.de/ckan/api/3/action"

def call(action, params):
    url = f"{BASE}/{action}?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "govdocs-monitor/0.1 (policy research; contact: rumtin.sepasspour@globalshieldpolicy.org)"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        return e.code, body[:600]
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"

def run(label, action, params, show_hits=6):
    print("=" * 68); print(label); print("=" * 68)
    status, data = call(action, params)
    if status != 200:
        print(f"  {status} — {str(data)[:400]}"); print(); return
    if not isinstance(data, dict) or not data.get("success"):
        print(f"  200 but not a CKAN success envelope: {str(data)[:300]}"); print(); return
    res = data["result"]
    # search results carry 'count' + 'results'; some actions return a bare list
    if isinstance(res, dict) and "results" in res:
        print(f"  200 OK  count={res.get('count')}  returned={len(res['results'])}")
        for ds in res["results"][:show_hits]:
            title = ds.get("title", "")[:70]
            org = (ds.get("organization") or {}).get("title", "")
            nres = len(ds.get("resources", []))
            fmts = ",".join(sorted({r.get("format","") for r in ds.get("resources", [])}))[:40]
            print(f"    · {title}")
            print(f"        org={org}  resources={nres} [{fmts}]")
    elif isinstance(res, list):
        print(f"  200 OK  list of {len(res)} — sample: {res[:12]}")
    else:
        print(f"  200 OK  {str(res)[:300]}")
    print()

# 1. Is the API even here and ungated? Ask how many datasets exist total.
run("1: CKAN reachable? (package_search q=*)", "package_search", {"q": "*:*", "rows": "0"})

# 2. Datasets from the Auswärtiges Amt (free-text; org slugs tested in #5).
run("2: free-text 'Auswärtiges Amt'", "package_search",
    {"q": "Auswärtiges Amt", "rows": "6"})

# 3. Bundeskanzleramt / Bundesregierung press + publications.
run("3: free-text 'Bundesregierung Bericht'", "package_search",
    {"q": "Bundesregierung Bericht", "rows": "6"})

# 4. Recent datasets sorted by modified date — is this a live feed or a graveyard?
run("4: newest datasets (sort by metadata_modified desc)", "package_search",
    {"q": "*:*", "sort": "metadata_modified desc", "rows": "6"})

# 5. List organisations — do the gated agencies publish here at all, and under what slug?
print("=" * 68); print("5: organisations containing 'amt'/'ministerium'/'regierung'"); print("=" * 68)
status, data = call("organization_list", {"all_fields": "false"})
if status == 200 and isinstance(data, dict) and data.get("success"):
    orgs = data["result"]
    hits = [o for o in orgs if any(k in o.lower() for k in
            ("auswaert", "auswärt", "kanzler", "regierung", "ministerium", "bmz", "presse"))]
    print(f"  {len(orgs)} orgs total; {len(hits)} matching:")
    for o in hits[:40]:
        print(f"    {o}")
else:
    print(f"  {status} — {str(data)[:300]}")
print()
