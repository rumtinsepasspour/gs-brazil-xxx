#!/usr/bin/env python3
"""govdocs — new-document monitor for German federal government sources.

Commands:
  probe      Fetch every enabled source, report health + sample matches. No state written.
  init       Baseline run: record everything currently visible as 'seen', report nothing.
  run        Daily run: diff against seen, record new items, emit a markdown digest.
  miss       Log a document the system failed to surface; diagnose which source should
             have caught it (filter gap vs source gap).
  extract    Fetch pages for new items and extract title/date/type via the Claude API.
  translate  Translate titles + summaries into English via the Claude API
             (newest untranslated rows first; a daily token cap guards spend).

State lives in state.db (SQLite). Sources live in registry.yaml.

In-place attachment detection: sitemap sources with `watch_documents: true`
track each page's <lastmod>. When a page's lastmod changes, the page is
fetched and its document links (.pdf/.docx/...) are diffed — so a new file
added to an EXISTING page is caught, not just new pages. Limits: depends on
the site publishing truthful lastmod values, and a file silently REPLACED at
the same URL is still invisible.
"""

import argparse
import datetime as dt
import json
import os
import re
import sqlite3
import urllib.request
import sys
import time
import urllib.robotparser
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse

import requests
import yaml
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("GOVDOCS_DB", os.path.join(ROOT, "state.db"))
REGISTRY_PATH = os.environ.get("GOVDOCS_REGISTRY", os.path.join(ROOT, "registry.yaml"))
DIGEST_DIR = os.environ.get("GOVDOCS_DIGESTS", os.path.join(ROOT, "digests"))
ENV_FILE = os.path.expanduser("~/.govdocs_de.env")


def _load_env_file():
    """Credentials live in ~/.govdocs_de.env (KEY=VALUE lines) — OUTSIDE the
    project folder, so nothing that gets published, deployed or zipped can
    ever contain the API key. Values already exported in the shell win."""
    for path in (ENV_FILE, os.path.join(ROOT, ".env")):
        if not os.path.exists(path):
            continue
        try:
            for line in open(path):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
        except OSError:
            pass


_load_env_file()

MAX_CHILD_SITEMAPS = 100
DOC_PATTERN = r"\.(pdf|docx?|xlsx?|pptx?|csv|rtf|odt)(\?|$)"
COLLAPSE_THRESHOLD = 10  # digest: collapse >N attachments from one page

# anchor texts that are navigation chrome, not titles (treated as missing)
JUNK_ANCHORS = {"view", "read more", "download", "more", "learn more",
                "find out more", "details", "mehr", "mehr erfahren",
                "mehr lesen", "weiterlesen", "zur meldung", "zum artikel",
                "zum thema", "zum download", "herunterladen", "ansehen",
                "öffnen", "weiter", "hier", "pdf"}


# ---------------------------------------------------------------- registry

def load_registry():
    with open(REGISTRY_PATH) as f:
        reg = yaml.safe_load(f)
    defaults = reg.get("defaults", {})
    # defaults.exclude patterns apply to EVERY source (German federal sites
    # share chrome: Gebärdensprache/Leichte-Sprache mirrors, Mediathek,
    # search pages...) — merged ahead of each source's own excludes.
    common_exclude = [re.compile(p) for p in defaults.get("exclude", [])]
    sources = [s for s in reg.get("sources", []) if s.get("enabled", True)]
    for s in sources:
        s["_include"] = [re.compile(p) for p in s.get("include", [])]
        s["_exclude"] = common_exclude + [re.compile(p)
                                          for p in s.get("exclude", [])]
    return defaults, sources


# ---------------------------------------------------------------- state

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen (
  source_id TEXT, url TEXT, first_seen TEXT,
  PRIMARY KEY (source_id, url));
CREATE TABLE IF NOT EXISTS items (
  url TEXT PRIMARY KEY, source_id TEXT, agency TEXT, first_seen TEXT,
  title TEXT, doc_date TEXT, doc_type TEXT, parent_url TEXT,
  extracted INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS lastmod (
  source_id TEXT, url TEXT, lastmod TEXT,
  PRIMARY KEY (source_id, url));
CREATE TABLE IF NOT EXISTS runs (
  ts TEXT, source_id TEXT, ok INTEGER, note TEXT,
  collected INTEGER, matched INTEGER, new INTEGER);
CREATE TABLE IF NOT EXISTS http_cache (
  url TEXT PRIMARY KEY, etag TEXT, last_modified TEXT);
CREATE TABLE IF NOT EXISTS misses (
  url TEXT, noted TEXT, note TEXT, diagnosis TEXT);
CREATE TABLE IF NOT EXISTS filestate (
  url TEXT PRIMARY KEY, etag TEXT, content_length TEXT,
  last_modified TEXT, checked TEXT);
CREATE TABLE IF NOT EXISTS filechanges (
  url TEXT, detected TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS pagechanges (
  url TEXT, source_id TEXT, old_lastmod TEXT, new_lastmod TEXT, detected TEXT);
CREATE TABLE IF NOT EXISTS translate_spend (
  day TEXT PRIMARY KEY, tokens_in INTEGER, tokens_out INTEGER, calls INTEGER);
CREATE TABLE IF NOT EXISTS scannedpages (
  source_id TEXT, url TEXT, first_scanned TEXT, PRIMARY KEY (source_id, url));
"""


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    # migrate databases created before the attachment feature
    cols = {r[1] for r in conn.execute("PRAGMA table_info(items)")}
    for col in ("parent_url", "relevance", "topic", "summary",
                "title_en", "summary_en", "tr_src"):
        if col not in cols:
            conn.execute(f"ALTER TABLE items ADD COLUMN {col} TEXT")
    return conn


# ---------------------------------------------------------------- fetching

class Fetcher:
    """Polite HTTP: named UA, per-host rate limit, robots.txt, conditional GET."""

    def __init__(self, defaults, conn=None):
        self.session = requests.Session()
        self.ua = defaults.get("user_agent", "govdocs-monitor/0.1")
        self.session.headers["User-Agent"] = self.ua
        self.delay = float(defaults.get("rate_limit_seconds", 2))
        self.timeout = float(defaults.get("timeout_seconds", 30))
        self._last_hit = {}       # host -> monotonic ts
        self._robots_cache = {}   # host -> (verdict, note)
        self.conn = conn          # for conditional-GET cache; may be None (probe)

    def _throttle(self, host):
        prev = self._last_hit.get(host, 0)
        wait = self.delay - (time.monotonic() - prev)
        if wait > 0:
            time.sleep(wait)
        self._last_hit[host] = time.monotonic()

    def _robots(self, host):
        """Returns (verdict, note): verdict is a parser, None (no rules), or 'blocked'."""
        if host not in self._robots_cache:
            self._throttle(host)
            try:
                r = self.session.get(
                    f"{self._scheme(host)}://{host}/robots.txt",
                    timeout=self.timeout)
                if r.status_code == 200:
                    rp = urllib.robotparser.RobotFileParser()
                    rp.parse(r.text.splitlines())
                    self._robots_cache[host] = (rp, "ok")
                elif r.status_code in (401, 403):
                    self._robots_cache[host] = (
                        None,
                        f"robots.txt request refused (HTTP {r.status_code}); "
                        f"per RFC 9309 an unavailable robots.txt imposes no "
                        f"restrictions — proceeding")
                else:
                    self._robots_cache[host] = (None, f"no robots.txt "
                                                f"(HTTP {r.status_code})")
            except Exception as e:
                self._robots_cache[host] = (None, f"robots.txt unreachable ({e})")
        return self._robots_cache[host]

    @staticmethod
    def _scheme(host):
        return "http" if host.startswith(("localhost", "127.0.0.1")) else "https"

    def _robots_ok(self, url):
        """Returns (allowed: bool, note: str)."""
        verdict, note = self._robots(urlparse(url).netloc)
        if verdict == "blocked":
            return False, note
        if verdict is None:
            return True, note
        try:
            if verdict.can_fetch(self.ua, url):
                return True, "ok"
            return False, "disallowed by robots.txt rules"
        except Exception:
            return True, "ok"

    def get(self, url, conditional=False, skip_robots=False):
        """Returns (response|None, note). None response = skipped or 304."""
        if not skip_robots:
            allowed, rnote = self._robots_ok(url)
            if not allowed:
                return None, rnote
        headers = {}
        if conditional and self.conn is not None:
            row = self.conn.execute(
                "SELECT etag, last_modified FROM http_cache WHERE url=?", (url,)
            ).fetchone()
            if row:
                if row[0]:
                    headers["If-None-Match"] = row[0]
                if row[1]:
                    headers["If-Modified-Since"] = row[1]
        self._throttle(urlparse(url).netloc)
        r = self.session.get(url, headers=headers, timeout=self.timeout)
        if r.status_code == 304:
            return None, "not modified (304)"
        r.raise_for_status()
        if conditional and self.conn is not None:
            self.conn.execute(
                "INSERT OR REPLACE INTO http_cache VALUES (?,?,?)",
                (url, r.headers.get("ETag"), r.headers.get("Last-Modified")),
            )
        return r, "ok"


# ---------------------------------------------------------------- collectors
# Each collector returns (results, note) where results is a list of
# (url, title_or_None, lastmod_or_None). A None results value means
# "unchanged, skip diff".

def _parse_sitemap(content):
    """Returns (root_tag, entries) with entries = [(loc, lastmod|None), ...].
    Handles gzipped sitemaps (.xml.gz) transparently — several German
    federal sites (bundesregierung.de, bmz.de, bmvg.de) serve them."""
    if content[:2] == b"\x1f\x8b":
        import gzip
        content = gzip.decompress(content)
    root = ET.fromstring(content)
    root_tag = root.tag.split("}")[-1]
    entries = []
    for el in root:
        if el.tag.split("}")[-1] not in ("url", "sitemap"):
            continue
        loc, lastmod = None, None
        for child in el:
            t = child.tag.split("}")[-1]
            if t == "loc" and child.text:
                loc = child.text.strip()
            elif t == "lastmod" and child.text:
                lastmod = child.text.strip()
        if loc:
            entries.append((loc, lastmod))
    return root_tag, entries


def collect_sitemap(fetcher, source):
    # Sitemaps are a site's published machine interface, exactly like RSS
    # feeds (see collect_rss): sites routinely declare them in robots.txt
    # inside paths the same file disallows for page-crawling (BMFTR puts its
    # sitemap under a disallowed /SiteGlobals/). The declaration IS the
    # permission, so sitemap fetches skip the robots gate; every content
    # page fetch stays robots-checked as before.
    r, note = fetcher.get(source["url"], conditional=True, skip_robots=True)
    if r is None:
        return (None, note) if "304" in note else ([], note)
    root_tag, entries = _parse_sitemap(r.content)
    if root_tag == "sitemapindex":
        child_filter = source.get("sitemap_filter")
        children = [loc for loc, _ in entries]
        if child_filter:
            children = [u for u in children if re.search(child_filter, u)]
        results, errs = [], 0
        for child in children[:MAX_CHILD_SITEMAPS]:
            try:
                cr, cn = fetcher.get(child, conditional=True, skip_robots=True)
                if cr is None:
                    continue  # unchanged child: its URLs are already in `seen`
                _, child_entries = _parse_sitemap(cr.content)
                results.extend((loc, None, lm) for loc, lm in child_entries)
            except Exception:
                errs += 1
        note = (f"sitemap index, {len(children)} children"
                + (f", {errs} failed" if errs else ""))
        return results, note
    return ([(loc, None, lm) for loc, lm in entries],
            f"plain sitemap, {len(entries)} urls")


def _render_page(url, fetcher):
    """Fetch a page with a headless browser so script-hydrated content is
    visible. Used only for sources marked render: true. Honest client: a
    real browser engine with its own identity, still robots-checked and
    throttled like everything else."""
    from playwright.sync_api import sync_playwright
    fetcher._throttle(urlparse(url).netloc)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            resp = page.goto(url, wait_until="load",
                             timeout=int(fetcher.timeout * 1000))
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass  # analytics-noisy pages never go idle; use what we have
            # trigger lazy-loaded grids, then let them settle
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2500)
            return page.content(), (resp.status if resp else None)
        finally:
            browser.close()


def collect_crawl(fetcher, source):
    """Bounded same-site BFS from seed pages: builds the sitemap an estate
    refuses to publish. Stays within `scope` path prefixes, follows links at
    most `depth` hops from a seed, fetches at most `page_cap` pages per run
    (politely, robots-respected). Every in-scope link discovered — content
    page or document file — is a candidate item; document files are never
    crawled into."""
    seeds = source.get("seeds") or [source["url"]]
    scope = source.get("scope") or []
    depth_max = int(source.get("depth", 2))
    cap = int(source.get("page_cap", 150))
    host = urlparse(seeds[0]).netloc
    docpat = re.compile(DOC_PATTERN, re.I)
    excl = [re.compile(p) for p in source.get("crawl_exclude", [])]

    def in_scope(u):
        p = urlparse(u)
        if p.netloc != host:
            return False
        if any(x.search(p.path) for x in excl):
            return False
        return (any(p.path.startswith(pref) for pref in scope)
                if scope else True)

    queue = [(u, 0) for u in seeds]
    visited, results, seen_urls = set(), [], set()
    fetched = 0
    while queue and fetched < cap:
        page, d = queue.pop(0)
        if page in visited:
            continue
        visited.add(page)
        try:
            r, _n = fetcher.get(page, conditional=False)
        except Exception:
            continue
        fetched += 1
        if r is None:
            continue
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = urljoin(page, a["href"]).split("#")[0]
            if href in seen_urls or not href.startswith("http"):
                continue
            if not in_scope(href):
                continue
            seen_urls.add(href)
            text = " ".join(a.get_text().split()) or None
            results.append((href, text, None))
            if not docpat.search(href) and d + 1 <= depth_max:
                queue.append((href, d + 1))
    note = (f"crawled {fetched} pages, discovered {len(results)} "
            f"in-scope links")
    if queue:
        note += f" ({len(queue)} frontier pages beyond page_cap)"
    return results, note


def collect_listing(fetcher, source):
    if source.get("render"):
        allowed, rnote = fetcher._robots_ok(source["url"])
        if not allowed:
            return [], rnote
        try:
            html, status = _render_page(source["url"], fetcher)
        except ImportError:
            return [], ("render: true needs playwright — one-time setup: "
                        "./venv/bin/python -m pip install playwright && "
                        "./venv/bin/playwright install chromium")
        except Exception as e:
            return [], f"render failed: {type(e).__name__}: {e}"
        prefix = f"rendered (HTTP {status}) " if status else "rendered "
    else:
        r, note = fetcher.get(source["url"], conditional=False)
        if r is None:
            return [], note
        html = r.text
        prefix = ""
    soup = BeautifulSoup(html, "html.parser")
    anchors = soup.find_all("a", href=True)
    pat = re.compile(source.get("link_include", "."))
    docpat = re.compile(DOC_PATTERN, re.I)
    seen_urls, results = set(), []
    for a in anchors:
        href = urljoin(source["url"], a["href"]).split("#")[0]
        if href in seen_urls or not href.startswith("http"):
            continue
        # document files on a watched page are always captured, whatever
        # the link pattern — a PDF linked from a watched index is a document
        if pat.search(href) or docpat.search(href):
            seen_urls.add(href)
            title = a.get_text(" ", strip=True) or None
            results.append((href, title, None))
    note = f"{prefix}page {len(html)//1024} kB, {len(anchors)} links on page"
    if not results and anchors:
        samples, seen_h = [], set()
        for a in anchors:
            href = urljoin(source["url"], a["href"]).split("#")[0]
            if href.startswith("http") and href not in seen_h:
                seen_h.add(href)
                samples.append(href)
            if len(samples) >= 6:
                break
        note += " — no matches; sample links: " + " ; ".join(samples)
    return results, note


def collect_rss(fetcher, source):
    import feedparser  # deferred: only needed for rss sources
    # Feeds are a site's published machine interface; feed readers do not
    # consult robots.txt for them, and neither do we.
    r, note = fetcher.get(source["url"], conditional=True, skip_robots=True)
    if r is None:
        return (None, note) if "304" in note else ([], note)
    feed = feedparser.parse(r.content)
    if feed.bozo and not feed.entries:
        return [], f"feed parse error: {feed.bozo_exception}"
    results = []
    for e in feed.entries:
        if not e.get("link"):
            continue
        pub = e.get("published_parsed") or e.get("updated_parsed")
        pdate = time.strftime("%Y-%m-%d", pub) if pub else None
        results.append((e.link, e.get("title"), pdate))
    return results, (f"{note}; feed format {feed.version or 'unrecognised'}, "
                     f"{len(feed.entries)} entries")


COLLECTORS = {"sitemap": collect_sitemap, "listing": collect_listing, "rss": collect_rss,
              "crawl": collect_crawl}


def apply_filters(source, results):
    inc, exc = source["_include"], source["_exclude"]
    out = []
    for tup in results:
        path = urlparse(tup[0]).path
        if inc and not any(p.search(path) for p in inc):
            continue
        if any(p.search(path) for p in exc):
            continue
        out.append(tup)
    return out


def collect(fetcher, source):
    kind = source["kind"]
    if kind not in COLLECTORS:
        return [], f"unknown kind: {kind}"
    return COLLECTORS[kind](fetcher, source)


# ------------------------------------------------- in-place attachment watch

def watch_documents(conn, fetcher, s, matched, now, baseline):
    """For sitemap sources with watch_documents: detect pages whose lastmod
    changed, fetch them, and diff their document links. Returns
    [(file_url, anchor_title, parent_page), ...] of newly seen files.

    First-scan discipline: the FIRST time a page is scanned we record every
    attachment it carries into `seen` WITHOUT reporting any — that scan just
    establishes the page's baseline. Only attachments that appear on a
    LATER scan (i.e. genuinely added after we already knew the page) are
    reported as new. Without this, the first scan of any changed page dumps
    its entire back-catalogue of old PDFs into the digest as if brand new."""
    sid = s["id"]
    stored = dict(conn.execute(
        "SELECT url, lastmod FROM lastmod WHERE source_id=?", (sid,)))
    changed_full = [(tup[0], stored[tup[0]], tup[2]) for tup in matched
                    if tup[2] and stored.get(tup[0]) and stored[tup[0]] != tup[2]]
    changed = [c[0] for c in changed_full]
    conn.executemany(
        "INSERT OR REPLACE INTO lastmod VALUES (?,?,?)",
        [(sid, tup[0], tup[2]) for tup in matched if tup[2]])
    if baseline:
        return []
    if changed_full:
        conn.executemany(
            "INSERT INTO pagechanges VALUES (?,?,?,?,?)",
            [(u, sid, old, new_lm, now) for u, old, new_lm in changed_full])
    cap = int(s.get("doc_fetch_cap", 40))
    flap_limit = max(150, len(matched) // 5)
    if len(changed) > flap_limit:
        print(f"[{sid}] doc-watch: {len(changed)} of {len(matched)} pages "
              f"'changed' — lastmod flapping; attachment scan suspended for "
              f"this source today. If persistent, set watch_documents: false "
              f"in the registry.", file=sys.stderr)
        changed = []
    elif len(changed) > cap:
        print(f"[{sid}] doc-watch: {len(changed)} changed pages, scanning "
              f"first {cap} (doc_fetch_cap) — if this recurs daily the site's "
              f"lastmod values are flapping", file=sys.stderr)
    pat = re.compile(s.get("doc_pattern", DOC_PATTERN), re.I)
    found = []
    for page in changed[:cap]:
        # Has this page been scanned before? A page we've recorded attachments
        # for already has a row in scannedpages; its first scan is silent.
        first_scan = conn.execute(
            "SELECT 1 FROM scannedpages WHERE source_id=? AND url=?",
            (sid, page)).fetchone() is None
        try:
            r, _ = fetcher.get(page)
            if r is None:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = urljoin(page, a["href"]).split("#")[0]
                if not href.startswith("http") or not pat.search(href):
                    continue
                cur = conn.execute(
                    "INSERT OR IGNORE INTO seen VALUES (?,?,?)", (sid, href, now))
                # report only if newly-seen AND the page was already known
                if cur.rowcount and not first_scan:
                    found.append((href, a.get_text(" ", strip=True) or None, page))
            # mark the page scanned so future scans can report genuine additions
            conn.execute(
                "INSERT OR IGNORE INTO scannedpages VALUES (?,?,?)",
                (sid, page, now))
        except Exception as e:
            print(f"[{sid}] doc-watch failed for {page}: {e}", file=sys.stderr)
    return found


def load_topics():
    path = os.path.join(ROOT, "topics.yaml")
    if not os.path.exists(path):
        return []
    data = yaml.safe_load(open(path)) or {}
    out = []
    for t in data.get("topics", []):
        out.append(t["name"] if isinstance(t, dict) else str(t))
    return out


# ---------------------------------------------------------------- commands

def _path_summary(results, n=10):
    from collections import Counter
    c = Counter()
    for tup in results:
        segs = urlparse(tup[0]).path.strip("/").split("/")
        c["/" + "/".join(segs[:2])] += 1
    return c.most_common(n)


def cmd_probe(args):
    defaults, sources = load_registry()
    fetcher = Fetcher(defaults, conn=None)  # no cache: always fetch fresh
    if args.only:
        sources = [s for s in sources if s["id"] in args.only]
    failures = 0
    for s in sources:
        tag = "verified" if s.get("verified") else "UNVERIFIED"
        try:
            results, note = collect(fetcher, s)
            results = results or []
            matched = apply_filters(s, results)
            print(f"[{s['id']}] ({tag}) {note} — collected {len(results)}, "
                  f"matched {len(matched)}")
            for tup in matched[:3]:
                print(f"    {tup[0]}" + (f"  [{tup[1]}]" if tup[1] else ""))
            if s["kind"] == "sitemap" and matched:
                with_lm = sum(1 for t in matched if t[2])
                pct = 100 * with_lm // len(matched)
                wd = "ON" if s.get("watch_documents") else "off"
                print(f"    lastmod present on {pct}% of matched URLs "
                      f"(attachment watch {wd}"
                      + (", NOT viable — no lastmod signal)" if pct < 50 and
                         s.get("watch_documents") else ")"))
            if s["kind"] == "sitemap" and len(results) < 100:
                verdict, _ = fetcher._robots(urlparse(s["url"]).netloc)
                if hasattr(verdict, "site_maps"):
                    sm = verdict.site_maps()
                    if sm:
                        print("    robots.txt declares sitemaps: "
                              + ", ".join(sm[:5]))
            if results and (not matched or getattr(args, "paths", False)):
                if not matched:
                    print("    NOTE: source yields URLs but none match include "
                          "patterns — tune include/exclude.")
                print("    Path structure (count, prefix):")
                for prefix, count in _path_summary(results):
                    print(f"      {count:6d}  {prefix}")
            if not results:
                failures += 1
        except Exception as e:
            failures += 1
            print(f"[{s['id']}] ({tag}) FAILED: {type(e).__name__}: {e}")
            if s["kind"] == "sitemap":
                try:
                    verdict, _n = fetcher._robots(urlparse(s["url"]).netloc)
                    if hasattr(verdict, "site_maps") and verdict.site_maps():
                        print("    robots.txt declares sitemaps: "
                              + ", ".join(verdict.site_maps()[:5]))
                except Exception:
                    pass
    print(f"\n{len(sources)} sources probed, {failures} yielded nothing or failed.")


def _run(baseline):
    defaults, sources = load_registry()
    conn = db()
    fetcher = Fetcher(defaults, conn=conn)
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    new_items = []
    for s in sources:
        try:
            results, note = collect(fetcher, s)
        except Exception as e:
            conn.execute("INSERT INTO runs VALUES (?,?,0,?,0,0,0)",
                         (now, s["id"], f"{type(e).__name__}: {e}"))
            print(f"[{s['id']}] FAILED: {e}", file=sys.stderr)
            continue
        if results is None:  # 304 — nothing changed
            conn.execute("INSERT INTO runs VALUES (?,?,1,?,0,0,0)",
                         (now, s["id"], note))
            continue
        matched = apply_filters(s, results)
        fresh = []
        for tup in matched:
            cur = conn.execute(
                "INSERT OR IGNORE INTO seen VALUES (?,?,?)",
                (s["id"], tup[0], now))
            if cur.rowcount:
                fresh.append(tup)
        attachments = []
        if s.get("watch_documents") and s["kind"] == "sitemap":
            attachments = watch_documents(conn, fetcher, s, matched, now, baseline)
        if not baseline:
            for tup in fresh:
                conn.execute(
                    "INSERT OR IGNORE INTO items "
                    "(url, source_id, agency, first_seen, title) VALUES (?,?,?,?,?)",
                    (tup[0], s["id"], s.get("agency", "?"), now, tup[1]))
                new_items.append({"url": tup[0], "title": tup[1],
                                  "agency": s.get("agency", "?"),
                                  "source": s["id"], "parent": None})
            for furl, ftitle, parent in attachments:
                conn.execute(
                    "INSERT OR IGNORE INTO items "
                    "(url, source_id, agency, first_seen, title, doc_type, "
                    "parent_url, doc_date, extracted) "
                    "VALUES (?,?,?,?,?,'attachment',?,?,1)",
                    (furl, s["id"], s.get("agency", "?"), now, ftitle, parent,
                     _derive_date(furl, None)))
                new_items.append({"url": furl, "title": ftitle,
                                  "agency": s.get("agency", "?"),
                                  "source": s["id"], "parent": parent})
        if attachments:
            note += f"; {len(attachments)} attachment(s) on changed pages"
        conn.execute("INSERT INTO runs VALUES (?,?,1,?,?,?,?)",
                     (now, s["id"], note, len(results), len(matched),
                      len(fresh) + len(attachments)))
        print(f"[{s['id']}] collected {len(results)}, matched {len(matched)}, "
              f"new {len(fresh)}"
              + (f", attachments {len(attachments)}" if attachments else "")
              + (f"  [{note}]" if not results else ""))
    conn.commit()
    if not baseline:
        # auto-enrich the day's new items: titles where missing, plus meta
        # description and AGLS published date — digests and the search page
        # arrive readable with no manual titles/enrich step. Document files
        # (PDFs) are skipped; they carry no page metadata.
        docpat = re.compile(DOC_PATTERN, re.I)
        cap = int(os.environ.get("GOVDOCS_ENRICH_CAP", "150"))
        targets = [it for it in new_items if not docpat.search(it["url"])][:cap]
        if targets:
            print(f"\nEnriching {len(targets)} new items "
                  f"(titles, summaries, dates)...")
        for it in targets:
            try:
                r, _n = fetcher.get(it["url"])
                if r is None:
                    continue
                soup = BeautifulSoup(r.text, "html.parser")
                desc, created = _page_meta(soup)
                if not created:
                    d2 = _derive_date(it["url"], None)
                    if d2 and len(d2) == 10:
                        created = d2
                if (not it["title"]
                        or it["title"].strip().lower() in JUNK_ANCHORS):
                    title = None
                    og = soup.find("meta", property="og:title")
                    if og and og.get("content"):
                        title = og["content"].strip()
                    elif soup.title and soup.title.string:
                        title = soup.title.string.strip()
                    if title:
                        title = title.split(" | ")[0].strip()
                    if title and title.lower().startswith("open point"):
                        title = None
                    if title and len(title) > 3:
                        it["title"] = title
                conn.execute(
                    "UPDATE items SET title=COALESCE(?, title), summary=?, "
                    "doc_date=COALESCE(doc_date, ?) WHERE url=?",
                    (it["title"], desc or "", created, it["url"]))
            except requests.HTTPError as e:
                code = e.response.status_code if e.response is not None else 0
                if code in (401, 403, 404, 410):
                    conn.execute("UPDATE items SET summary='' WHERE url=?",
                                 (it["url"],))
            except Exception as e:
                print(f"enrich failed for {it['url']}: {e}", file=sys.stderr)
        conn.commit()

    # chip the backlog: backfill imports arrive title-less AND summary-less,
    # so each run enriches the newest still-bare rows — title (from the page
    # we fetch), summary, refined date — then translates the whole chip in one
    # batched call. At the default 150/run the historical backlog self-heals
    # over a couple of months, newest-first, at trivial daily cost and load.
    # Tunable via GOVDOCS_ENRICH_BACKLOG; 0 disables.
    if not baseline:
        backlog_cap = int(os.environ.get("GOVDOCS_ENRICH_BACKLOG", "150"))
        if backlog_cap > 0:
            rows = conn.execute(
                "SELECT url FROM items WHERE summary IS NULL "
                "AND parent_url IS NULL "
                "ORDER BY COALESCE(doc_date, first_seen) DESC LIMIT ?",
                (backlog_cap,)).fetchall()
            if rows:
                print(f"\nChipping the backlog: {len(rows)} newest bare rows "
                      f"(title + summary + translate; "
                      f"GOVDOCS_ENRICH_BACKLOG={backlog_cap})...")
                done = 0
                for (url,) in rows:
                    try:
                        r, _n = fetcher.get(url)
                        if r is None:
                            continue
                        soup = BeautifulSoup(r.text, "html.parser")
                        desc, created = _page_meta(soup)
                        title = _title_from_soup(soup)
                        if not created:
                            d2 = _derive_date(url, None)
                            if d2 and len(d2) == 10:
                                created = d2
                        # only set title where we don't already have one, so a
                        # daily-run title is never overwritten by a page shell
                        conn.execute(
                            "UPDATE items SET summary=?, "
                            "title=COALESCE(NULLIF(title,''), ?), "
                            "doc_date=COALESCE(doc_date, ?) WHERE url=?",
                            (desc or "", title or None, created, url))
                        done += 1
                    except requests.HTTPError as e:
                        code = (e.response.status_code
                                if e.response is not None else 0)
                        if code in (401, 403, 404, 410):
                            conn.execute(
                                "UPDATE items SET summary='' WHERE url=?",
                                (url,))
                    except Exception:
                        pass
                conn.commit()
                print(f"  backlog: {done} pages enriched.")
                # translate whatever the chip just gave a title to
                if os.environ.get("ANTHROPIC_API_KEY"):
                    translate_items(backlog_cap, verbose=False)
    return new_items


def cmd_init(args):
    _run(baseline=True)
    print("\nBaseline recorded (URLs and lastmods). Future `run` invocations "
          "report new URLs and new attachments on changed pages.")


def _render_digest(new_items, date):
    lines = [f"# New documents — {date}", ""]
    if not new_items:
        lines.append("Nothing new across all sources.")
        return "\n".join(lines)
    high = [it for it in new_items if it.get("relevance") == "high"]
    if high:
        lines.append("## High interest")
        for it in high:
            label = it["title"] or it["url"]
            topic = f" ({it['topic']})" if it.get("topic") else ""
            lines.append(f"- [{label}]({it['url']}) — {it['agency']}{topic}")
        lines.append("")
        new_items = [it for it in new_items if it.get("relevance") != "high"]
        lines.append("## Everything else")
        lines.append("")
    by_agency = {}
    for it in new_items:
        by_agency.setdefault(it["agency"], []).append(it)
    for agency in sorted(by_agency):
        lines.append(f"## {agency}")
        pages = [it for it in by_agency[agency] if not it["parent"]]
        atts = [it for it in by_agency[agency] if it["parent"]]
        for it in pages:
            label = it["title"] or it["url"]
            lines.append(f"- [{label}]({it['url']}) `{it['source']}`")
        by_parent = {}
        for it in atts:
            by_parent.setdefault(it["parent"], []).append(it)
        for parent, group in by_parent.items():
            if len(group) > COLLAPSE_THRESHOLD:
                lines.append(f"- {len(group)} documents surfaced on first scan "
                             f"of changed page: {parent} `{group[0]['source']}`")
            else:
                for it in group:
                    label = it["title"] or it["url"].rsplit("/", 1)[-1]
                    lines.append(f"- [{label}]({it['url']}) — new attachment "
                                 f"on {parent} `{it['source']}`")
        lines.append("")
    return "\n".join(lines)


def post_slack(items, date):
    """Post a condensed digest to Slack if SLACK_WEBHOOK_URL is set."""
    hook = os.environ.get("SLACK_WEBHOOK_URL")
    if not hook or not items:
        return
    high = [i for i in items if i.get("relevance") == "high"]
    head = f"govdocs {date}: {len(items)} new documents"
    if high:
        head += f", {len(high)} high interest"
    lines = [head]
    show = high or items
    for i in show[:15]:
        label = (i["title"] or i["url"]).replace("<", "").replace(">", "")
        lines.append(f"\u2022 <{i['url']}|{label}> \u2014 {i['agency']}")
    if len(show) > 15:
        lines.append(f"(+{len(show)-15} more in the digest)")
    try:
        requests.post(hook, json={"text": "\n".join(lines)}, timeout=15)
        print("Posted to Slack.")
    except Exception as e:
        print(f"Slack post failed: {e}", file=sys.stderr)


def _items_since(conn, ts):
    rows = conn.execute(
        "SELECT url, COALESCE(title_en, title), agency, source_id, "
        "parent_url, relevance, topic FROM items WHERE first_seen >= ? "
        "ORDER BY relevance='high' DESC, agency", (ts,)).fetchall()
    return [{"url": u, "title": t, "agency": a, "source": s, "parent": p,
             "relevance": r, "topic": tp}
            for u, t, a, s, p, r, tp in rows]


def cmd_morning(args):
    """The whole routine: run -> extract -> translate (if key set) ->
    digest -> publish -> Slack (if webhook set)."""
    start = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    _run(baseline=False)
    conn = db()
    n_new = conn.execute("SELECT COUNT(*) FROM items WHERE first_seen >= ?",
                         (start,)).fetchone()[0]
    if n_new and os.environ.get("ANTHROPIC_API_KEY"):
        print(f"\nExtracting metadata for up to {args.limit} new items...")
        extract_items(args.limit)
        print("\nTranslating new items into English...")
        translate_items(args.limit, verbose=False)
    elif n_new:
        print("\n(Put ANTHROPIC_API_KEY in ~/.govdocs_de.env for German "
              "titles, English translations and relevance scoring.)")
    items = _items_since(conn, start)
    date = dt.date.today().isoformat()
    digest = _render_digest(items, date)
    os.makedirs(DIGEST_DIR, exist_ok=True)
    with open(os.path.join(DIGEST_DIR, f"{date}.md"), "w") as f:
        f.write(digest + "\n")
    print("\n" + digest)
    class _P: out = os.path.join(ROOT, "site")
    cmd_publish(_P())
    post_slack(items, date)


def cmd_run(args):
    new_items = _run(baseline=False)
    date = dt.date.today().isoformat()
    digest = _render_digest(new_items, date)
    os.makedirs(DIGEST_DIR, exist_ok=True)
    path = os.path.join(DIGEST_DIR, f"{date}.md")
    with open(path, "w") as f:
        f.write(digest + "\n")
    print("\n" + digest)
    print(f"\nDigest written to {path}")


def cmd_miss(args):
    for url in args.url:
        _miss_one(url, args.note)


def _miss_one(url, note_arg):
    defaults, sources = load_registry()
    conn = db()
    fetcher = Fetcher(defaults, conn=None)
    row = conn.execute("SELECT source_id, first_seen FROM seen WHERE url=?",
                       (url,)).fetchone()
    item = conn.execute("SELECT title, first_seen FROM items WHERE url=?",
                        (url,)).fetchone()
    if item:
        print(f"STATUS: in the search index (title={item[0]!r}, "
              f"date={item[1][:10] or 'undated'}) — if you couldn't find it, "
              f"it's a search/labeling problem, not coverage.")
    elif row:
        print(f"STATUS: captured by [{row[0]}] on {row[1][:10]} but NOT in "
              f"the search index — typically an undateable backfill exclusion.")
    else:
        print("STATUS: never captured by any source. Live diagnosis follows.")
    host = urlparse(url).netloc
    candidates = [s for s in sources if urlparse(s["url"]).netloc == host]
    if not candidates:
        diagnosis = f"no source covers host {host} — add one to registry.yaml"
    else:
        parts = []
        for s in candidates:
            try:
                results, _ = collect(fetcher, s)
                results = results or []
            except Exception as e:
                parts.append(f"{s['id']}: source itself failing ({e})")
                continue
            raw_urls = {tup[0] for tup in results}
            if url in raw_urls:
                if apply_filters(s, [(url, None, None)]):
                    parts.append(f"{s['id']}: URL passes filters now — likely "
                                 "published after last run, or lastmod/sitemap lag")
                else:
                    parts.append(f"{s['id']}: collected but FILTERED OUT — "
                                 "adjust include/exclude")
            else:
                parts.append(f"{s['id']}: not in source output — source gap "
                             "(different section/surface; consider a listing source)")
        diagnosis = "; ".join(parts)
        if re.search(DOC_PATTERN, url, re.I):
            diagnosis += (" | missed URL is a document file: if it sits on an "
                          "existing page, check watch_documents is on for this "
                          "source and whether the parent page's lastmod updated")
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    conn.execute("INSERT INTO misses VALUES (?,?,?,?)",
                 (url, now, note_arg or "", diagnosis))
    conn.commit()
    print(f"Logged. Diagnosis: {diagnosis}")


EXTRACT_PROMPT = """You are extracting metadata from a German federal government web page.
The page text is in German. Keep the title EXACTLY as published, in German —
translation into English is a separate step. Return ONLY a JSON object, no
prose, no markdown fences, with keys:
  title      (string: the document/release title, in the original German)
  doc_date   (string: publication date, ISO YYYY-MM-DD, or null if not stated)
  doc_type   (string: one of: media release, report, publication, consultation,
              speech, transcript, inquiry, legislation, other){relevance_keys}
Page URL: {url}
Page text (truncated):
{text}
"""

RELEVANCE_KEYS = """
  relevance  (string: high/medium/low — relevance of this document to ANY of
              the interest topics below; "low" if none apply)
  topic      (string: the single best-matching interest topic, or null)
Interest topics: {topics}"""


def extract_items(limit):
    """Fetch pages for unextracted items; pull metadata (and, if topics.yaml
    defines interest topics, a relevance score) via the Claude API.
    Returns number extracted; 0 with a message if no API key."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("extract skipped: ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 0
    import anthropic
    client = anthropic.Anthropic()
    model = os.environ.get("GOVDOCS_MODEL", "claude-haiku-4-5")
    topics = load_topics()
    rel = RELEVANCE_KEYS.format(topics="; ".join(topics)) if topics else ""
    defaults, _ = load_registry()
    conn = db()
    fetcher = Fetcher(defaults, conn=None)
    rows = conn.execute(
        "SELECT url FROM items WHERE extracted=0 "
        "ORDER BY first_seen DESC LIMIT ?", (limit,)).fetchall()
    done = 0
    for (url,) in rows:
        try:
            r, _ = fetcher.get(url)
            if r is None:
                continue
            text = BeautifulSoup(r.text, "html.parser").get_text(
                " ", strip=True)[:8000]
            msg = client.messages.create(
                model=model, max_tokens=300,
                messages=[{"role": "user",
                           "content": EXTRACT_PROMPT.format(
                               url=url, text=text, relevance_keys=rel)}])
            raw = msg.content[0].text.strip()
            raw = re.sub(r"^```(json)?|```$", "", raw, flags=re.M).strip()
            meta = json.loads(raw)
            conn.execute(
                "UPDATE items SET title=?, doc_date=?, doc_type=?, "
                "relevance=?, topic=?, extracted=1 WHERE url=?",
                (meta.get("title"), meta.get("doc_date"), meta.get("doc_type"),
                 meta.get("relevance"), meta.get("topic"), url))
            conn.commit()
            done += 1
            print(f"extracted: {url} -> {meta.get('title')}")
        except Exception as e:
            print(f"extract failed for {url}: {e}", file=sys.stderr)
    return done


def cmd_extract(args):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY not set (expected in ~/.govdocs_de.env).")
    extract_items(args.limit)


# ---------------------------------------------------------------- translation

TR_TAG = "haiku-v1"  # stamped on rows this engine translated; a future
                     # engine bumps the tag and can selectively redo old rows

TRANSLATE_PROMPT = """You are translating German federal government document \
metadata into English for a policy-monitoring index.
For each numbered item, translate TITLE (and SUMMARY when present) into English.
Rules:
- Where a document has an established official English title, use it;
  otherwise translate faithfully and idiomatically.
- Keep agency names and legal citations recognisable; never invent expansions.
- If a value is already in English, return it unchanged.
- Return ONLY a JSON array, no prose, no markdown fences, in the form:
  [{{"i": 1, "title_en": "...", "summary_en": "..."}}, ...]
  (summary_en: null when the item has no SUMMARY line.)

Items:
{items}"""


def _translate_cfg():
    """Settings from registry.yaml's optional top-level `translate:` block,
    with safe defaults. daily_token_cap is the money guard: once the day's
    calls have consumed this many tokens (input + output), translation stops
    until tomorrow — so no invocation, however large its --limit, can
    overspend."""
    cfg = {"enabled": True, "model": "claude-haiku-4-5", "batch_size": 15,
           "daily_token_cap": 250000, "summary_clip": 600}
    try:
        with open(REGISTRY_PATH) as f:
            reg = yaml.safe_load(f) or {}
        cfg.update(reg.get("translate") or {})
    except FileNotFoundError:
        pass
    return cfg


def _spend_today(conn):
    row = conn.execute(
        "SELECT tokens_in, tokens_out, calls FROM translate_spend "
        "WHERE day=?", (dt.date.today().isoformat(),)).fetchone()
    return row if row else (0, 0, 0)


def _record_spend(conn, tin, tout):
    conn.execute(
        "INSERT INTO translate_spend VALUES (?,?,?,1) ON CONFLICT(day) DO "
        "UPDATE SET tokens_in=tokens_in+?, tokens_out=tokens_out+?, "
        "calls=calls+1",
        (dt.date.today().isoformat(), tin, tout, tin, tout))


def translate_items(limit, verbose=True):
    """Translate untranslated titled rows into English via the Claude API,
    newest first, one API call per batch. Rows are stamped tr_src only on
    success, so anything skipped or failed is retried on a future run.
    Returns the number of rows translated."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("translate skipped: ANTHROPIC_API_KEY not set (expected in "
              "~/.govdocs_de.env)", file=sys.stderr)
        return 0
    cfg = _translate_cfg()
    if not cfg.get("enabled", True):
        print("translate is disabled (translate.enabled: false in "
              "registry.yaml).")
        return 0
    import anthropic
    client = anthropic.Anthropic()
    model = os.environ.get("GOVDOCS_MODEL", cfg["model"])
    conn = db()
    rows = conn.execute(
        "SELECT url, title, summary FROM items WHERE tr_src IS NULL "
        "AND title IS NOT NULL AND title != '' "
        "ORDER BY first_seen DESC LIMIT ?", (limit,)).fetchall()
    if not rows:
        print("Nothing to translate: no untranslated titled rows.")
        return 0
    cap = int(cfg["daily_token_cap"])
    tin0, tout0, _c = _spend_today(conn)
    print(f"Translating {len(rows)} rows via {model} "
          f"({tin0 + tout0:,} of {cap:,} daily tokens already used)...")
    clip = int(cfg.get("summary_clip", 600))
    size = max(1, int(cfg["batch_size"]))
    done = 0
    for start in range(0, len(rows), size):
        tin, tout, _c = _spend_today(conn)
        if tin + tout >= cap:
            print(f"Daily token cap reached ({tin + tout:,} of {cap:,}) — "
                  f"stopping here. Untranslated rows carry over to future "
                  f"runs; raise translate.daily_token_cap in registry.yaml "
                  f"to spend more per day.")
            break
        batch = rows[start:start + size]
        lines = []
        for n, (_u, title, summary) in enumerate(batch, 1):
            lines.append(f"{n}. TITLE: {' '.join(title.split())[:300]}")
            if summary:
                lines.append(f"   SUMMARY: {' '.join(summary.split())[:clip]}")
        try:
            msg = client.messages.create(
                model=model,
                max_tokens=min(8000, 350 * len(batch) + 100),
                messages=[{"role": "user", "content": TRANSLATE_PROMPT.format(
                    items="\n".join(lines))}])
        except Exception as e:
            print(f"translate: API call failed ({type(e).__name__}: {e}) — "
                  f"stopping this run.", file=sys.stderr)
            break
        usage = getattr(msg, "usage", None)
        if usage:
            _record_spend(conn, usage.input_tokens, usage.output_tokens)
            conn.commit()
        raw = msg.content[0].text.strip()
        raw = re.sub(r"^```(json)?|```$", "", raw, flags=re.M).strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            note = (" (response hit max_tokens — lower translate.batch_size)"
                    if msg.stop_reason == "max_tokens" else "")
            print(f"translate: batch response was not valid JSON{note} — "
                  f"batch skipped, its rows will retry on a future run.",
                  file=sys.stderr)
            continue
        for entry in parsed if isinstance(parsed, list) else []:
            try:
                url, title, summary = batch[int(entry.get("i")) - 1]
            except (TypeError, ValueError, IndexError):
                continue
            t_en = (entry.get("title_en") or "").strip() or None
            s_en = (entry.get("summary_en") or "").strip() or None
            if not t_en:
                continue
            conn.execute(
                "UPDATE items SET title_en=?, summary_en=?, tr_src=? "
                "WHERE url=?",
                (t_en, s_en if summary else None, TR_TAG, url))
            done += 1
            if verbose:
                print(f"  {title[:76]}")
                print(f"    -> {t_en[:76]}")
        conn.commit()
    tin, tout, calls = _spend_today(conn)
    print(f"\nTranslated {done} of {len(rows)} rows. Today so far: "
          f"{tin:,} tokens in / {tout:,} out over {calls} call(s). "
          f"Dollar figure: console.anthropic.com -> Usage.")
    return done


def cmd_translate(args):
    translate_items(args.limit)


def cmd_repair_titles(args):
    """One-off cleanup: null out titles that are pure site boilerplate
    ("Offizielle Internetseite...", "Startseite", a ministry banner), which
    earlier enrich runs stored before the boilerplate filter existed. A nulled
    row falls back to its URL-slug label and stays eligible for a better title
    on a future fetch, instead of carrying a useless banner into search and
    translation. Only touches untranslated rows (tr_src IS NULL) so it never
    disturbs a title that has already been translated and shown."""
    conn = db()
    rows = conn.execute(
        "SELECT url, title FROM items "
        "WHERE title IS NOT NULL AND title != '' AND tr_src IS NULL").fetchall()
    hits = [u for u, t in rows if _BOILERPLATE_TITLE_RE.match(t or "")]
    if not hits:
        print("No boilerplate titles to clear.")
        return
    conn.executemany("UPDATE items SET title=NULL WHERE url=?",
                     [(u,) for u in hits])
    conn.commit()
    print(f"Cleared {len(hits)} boilerplate titles (rows fall back to their "
          f"URL-slug label and will retry on a future enrich).")


DATE_URL_FULL = re.compile(r"/((?:19|20)\d{2})[-/](\d{1,2})[-/](\d{1,2})(?:/|$)")
# financial-year token: boundary allows "-to-2033-34" tails so the FIRST
# FY in a slug wins (plan START year, which approximates publication)
DATE_URL_FY = re.compile(r"((?:19|20)\d{2})-\d{2}(?:[/-]|$)")
MONTHS_TEXT = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"])}
# German month slugs — URLs mostly transliterate ä -> ae, but both appear
MONTHS_TEXT.update({m: i + 1 for i, m in enumerate(
    ["januar", "februar", "maerz", "april", "mai", "juni", "juli",
     "august", "september", "oktober", "november", "dezember"])})
MONTHS_TEXT["märz"] = 3
DATE_URL_TEXT = re.compile(
    r"(\d{1,2})-(" + "|".join(MONTHS_TEXT) + r")-((?:19|20)\d{2})", re.I)
DATE_URL_YEAR = re.compile(r"/((?:19|20)\d{2})(?:/|$)")
# German GSB (Government Site Builder) conventions, discovered on BSI/BMI/RKI:
#   (1) filename begins YYMMDD_ or YYMMDD- — e.g. "230929_erster-DACS.html"
#       = 2023-09-29. The date is the publication date by construction.
GSB_FILE_YYMMDD = re.compile(r"/(\d{2})(\d{2})(\d{2})[_-][^/]*$")
#   (2) a path segment fuses a label to the year — "Presse2023", "Jahr2021".
#       Year-level only (no month), a weaker signal than (1).
GSB_FUSED_YEAR = re.compile(r"/[A-Za-z]+((?:19|20)\d{2})(?:/|$)")
TYPE_HINTS = [("pressemitteilung", "media release"), ("/pressemeldung", "media release"),
              ("/presse", "media release"), ("/aktuelles", "news"),
              ("/meldung", "news"), ("/nachrichten", "news"),
              ("publikation", "publication"), ("/bericht", "report"),
              ("/studie", "report"), ("/reden", "speech"), ("/rede-", "speech"),
              ("gesetzentwurf", "legislation"), ("gesetzgebung", "legislation"),
              ("verordnung", "legislation"), ("konsultation", "consultation"),
              ("anhoerung", "consultation"),
              # English fallbacks — some agencies run bilingual estates
              ("media-release", "media release"), ("/media/", "media release"),
              ("consultation", "consultation"), ("publication", "publication"),
              ("/report", "report"), ("/news", "news")]


def _plausible(datestr):
    """Publication dates cannot be in the future; slugs carry coverage-period
    years (plans 'to 2033-34', regulatory periods) that must not be used."""
    try:
        return int(datestr[:4]) <= dt.date.today().year
    except (ValueError, TypeError):
        return False


def _derive_date(url, lastmod):
    # A full date in the URL is a publication date by construction — it
    # outranks lastmod, which is a modification date (site replatforms set
    # lastmod to the migration date for the entire back catalogue). Every
    # signal is clamped to plausible (non-future) years; implausible signals
    # fall through to the next.
    m = DATE_URL_FULL.search(url)
    if m:
        y, mo, d = m.groups()
        if 1 <= int(mo) <= 12 and 1 <= int(d) <= 31:
            cand = f"{y}-{int(mo):02d}-{int(d):02d}"
            if _plausible(cand):
                return cand
    m = DATE_URL_TEXT.search(urlparse(url).path)
    if m:
        day, mon, yr = int(m.group(1)), MONTHS_TEXT[m.group(2).lower()], m.group(3)
        if 1 <= day <= 31:
            cand = f"{yr}-{mon:02d}-{day:02d}"
            if _plausible(cand):
                return cand  # written-out date in the slug ("24-february-2026")
    # German GSB filename date prefix (YYMMDD_) — a full publication date,
    # so it ranks with DATE_URL_FULL above the year-only signals below.
    m = GSB_FILE_YYMMDD.search(urlparse(url).path)
    if m:
        yy, mo, d = m.groups()
        # 2-digit year: 00-69 -> 2000s, 70-99 -> 1900s (gov docs are modern)
        y = (2000 if int(yy) <= 69 else 1900) + int(yy)
        if 1 <= int(mo) <= 12 and 1 <= int(d) <= 31:
            cand = f"{y}-{int(mo):02d}-{int(d):02d}"
            if _plausible(cand):
                return cand
    m = DATE_URL_FY.search(urlparse(url).path)
    if m and _plausible(m.group(1)):
        return m.group(1)  # financial-year slug: the FY start year
    m = DATE_URL_YEAR.search(url)
    if m and _plausible(m.group(1)):
        return m.group(1)  # year segment: set at publication, beats lastmod
    m = GSB_FUSED_YEAR.search(urlparse(url).path)
    if m and _plausible(m.group(1)):
        return m.group(1)  # fused label+year ("Presse2023") — year-level
    if lastmod and _plausible(lastmod[:10]):
        return lastmod[:10]
    return None


def _stamp_lastmods(pairs):
    """Given [(url, lastmod), ...] for one source, return the set of lastmod
    DATES that are migration/regeneration stamps — a single date covering a
    large share of the catalogue is a stamp, not information — and must not
    be used for dating."""
    from collections import Counter
    dates = [lm[:10] for _u, lm in pairs if lm]
    if len(dates) < 25:
        return set()
    c = Counter(dates)
    junk = {val for val, n in c.items() if n >= 25 and n / len(dates) >= 0.25}
    # regeneration signature: a large catalogue whose lastmods bunch into the
    # last two weeks is being restamped by its CMS, not edited — treat every
    # recent date as a stamp so dating falls back to URL signals (or the row
    # is honestly undateable)
    if len(dates) >= 500:
        cutoff = (dt.date.today() - dt.timedelta(days=14)).isoformat()
        recent = [d for d in dates if d >= cutoff]
        if len(recent) / len(dates) >= 0.5:
            junk |= set(recent)
    return junk


def _guess_type(url):
    low = url.lower()
    for hint, label in TYPE_HINTS:
        if hint in low:
            return label
    return None


def cmd_backfill(args):
    """Import the recent, dateable slice of what's already on the sites into
    items, so the search page starts populated. Dates come from sitemap
    lastmod, then date-shaped URL segments, then feed publish dates; undated
    URLs are skipped. Re-fetches every sitemap/rss source (a few minutes)."""
    defaults, sources = load_registry()
    conn = db()
    if args.reset:
        n = conn.execute(
            "DELETE FROM items WHERE length(first_seen) <= 10").rowcount
        conn.commit()
        print(f"Cleared {n} previously backfilled rows "
              f"(daily-run items are untouched).")
    fetcher = Fetcher(defaults, conn=None)  # no conditional GET: need full data
    since = args.since
    total, skipped_undated, below_since = 0, 0, 0
    for s in sources:
        if s["kind"] in ("listing", "crawl"):
            if not getattr(args, "listings", False):
                continue
            try:
                results, _ = collect(fetcher, s)
                results = results or []
            except Exception as e:
                print(f"[{s['id']}] FAILED: {e}", file=sys.stderr)
                continue
            added = 0
            for tup in apply_filters(s, results):
                cur = conn.execute(
                    "INSERT OR IGNORE INTO items "
                    "(url, source_id, agency, first_seen, title, doc_type, "
                    "extracted) VALUES (?,?,?,'',?,?,1)",
                    (tup[0], s["id"], s.get("agency", "?"), tup[1],
                     _guess_type(tup[0])))
                added += cur.rowcount
            total += added
            print(f"[{s['id']}] imported {added} current listing items (undated)")
            continue
        if s["kind"] not in ("sitemap", "rss"):
            continue
        try:
            results, _ = collect(fetcher, s)
            results = results or []
        except Exception as e:
            print(f"[{s['id']}] FAILED: {e}", file=sys.stderr)
            continue
        matched = apply_filters(s, results)
        stamps = _stamp_lastmods([(t[0], t[2]) for t in matched])
        if stamps:
            print(f"[{s['id']}] lastmod stamp(s) {sorted(stamps)} cover most "
                  f"of the catalogue — ignored for dating")
        added = 0
        for tup in matched:
            lm = tup[2]
            if lm and lm[:10] in stamps:
                lm = None
            date = _derive_date(tup[0], lm)
            if not date:
                if s.get("import_undated"):
                    cur = conn.execute(
                        "INSERT OR IGNORE INTO items "
                        "(url, source_id, agency, first_seen, title, doc_type, "
                        "extracted) VALUES (?,?,?,'',?,?,1)",
                        (tup[0], s["id"], s.get("agency", "?"), tup[1],
                         _guess_type(tup[0])))
                    added += cur.rowcount
                else:
                    skipped_undated += 1
                continue
            padded = (date + "-12-31")[:10]  # year-only sorts as end of year
            if padded < since:
                below_since += 1
                continue
            cur = conn.execute(
                "INSERT OR IGNORE INTO items "
                "(url, source_id, agency, first_seen, title, doc_type, extracted) "
                "VALUES (?,?,?,?,?,?,1)",
                (tup[0], s["id"], s.get("agency", "?"), date, tup[1],
                 _guess_type(tup[0])))
            added += cur.rowcount
        total += added
        print(f"[{s['id']}] backfilled {added}")
    conn.commit()
    print(f"\nBackfilled {total} documents dated {since} or later "
          f"({below_since} older documents excluded by --since, "
          f"{skipped_undated} undated URLs skipped). Run `publish` to "
          f"regenerate the search page.")


def cmd_filecheck(args):
    """HEAD-check tracked document files for silent revisions (same URL, new
    content). Compares ETag / Content-Length / Last-Modified against the last
    check. First sight of a file records state without reporting."""
    defaults, _ = load_registry()
    conn = db()
    fetcher = Fetcher(defaults, conn=None)
    cutoff = (dt.date.today() - dt.timedelta(days=args.days)).isoformat()
    pat = re.compile(DOC_PATTERN, re.I)
    rows = conn.execute(
        "SELECT url FROM items WHERE first_seen >= ? ORDER BY first_seen DESC",
        (cutoff,)).fetchall()
    files = [u for (u,) in rows if pat.search(u)][:args.limit]
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    changed, checked = [], 0
    for url in files:
        allowed, _n = fetcher._robots_ok(url)
        if not allowed:
            continue
        try:
            fetcher._throttle(urlparse(url).netloc)
            r = fetcher.session.head(url, timeout=fetcher.timeout,
                                     allow_redirects=True)
            r.raise_for_status()
        except Exception as e:
            print(f"filecheck failed for {url}: {e}", file=sys.stderr)
            continue
        checked += 1
        state = (r.headers.get("ETag"), r.headers.get("Content-Length"),
                 r.headers.get("Last-Modified"))
        prev = conn.execute(
            "SELECT etag, content_length, last_modified FROM filestate "
            "WHERE url=?", (url,)).fetchone()
        if prev and any(a and b and a != b for a, b in zip(prev, state)):
            detail = f"was {prev} now {state}"
            changed.append((url, detail))
            conn.execute("INSERT INTO filechanges VALUES (?,?,?)",
                         (url, now, detail))
        conn.execute("INSERT OR REPLACE INTO filestate VALUES (?,?,?,?,?)",
                     (url, state[0], state[1], state[2], now))
    conn.commit()
    print(f"\nChecked {checked} files from the last {args.days} days.")
    if changed:
        print(f"{len(changed)} REVISED IN PLACE (same URL, different content):")
        for url, detail in changed:
            print(f"  {url}\n    {detail}")
    else:
        print("No silent revisions detected.")


# Site-boilerplate <title> values that carry no document information — a page
# that only returns one of these gets NO title stored (its URL slug is a more
# useful label than the ministry's generic banner, and a null title keeps the
# row eligible for a better fetch later instead of freezing the banner in).
_BOILERPLATE_TITLE_RE = re.compile(
    r"^(offizielle internetseite|startseite|home|homepage|"
    r"bundesministerium f\u00fcr|bundesumweltministerium|"
    r"bundesfinanzministerium)\b", re.I)


def _title_from_soup(soup):
    """Best title from an already-parsed page (og:title, then <title>), with
    the German site/section suffix stripped. Returns "" if none usable (no
    title, too short, or pure site boilerplate). Lets a caller that already
    fetched the page avoid a second request."""
    title = None
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        title = og["content"].strip()
    elif soup.title and soup.title.string:
        title = soup.title.string.strip()
    if title:
        title = title.split(" | ")[0].strip()
        title = re.sub(
            r"\s*[-\u2013]\s*(BM\w+|Bundes\w+|Auswärtiges Amt)\b.*$",
            "", title).strip() or title
    if title and title.lower().startswith("open point"):
        title = None
    if title and _BOILERPLATE_TITLE_RE.match(title):
        title = None  # generic ministry banner, not a document title
    return title if (title and len(title) > 3) else ""


def _fetch_page_title(fetcher, url):
    """Best title from the page itself (og:title, then <title>).
    Returns None if the fetch failed, "" if fetched but no usable title
    (so callers can mark the URL as attempted and not retry forever)."""
    r, _n = fetcher.get(url)
    if r is None:
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    title = None
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        title = og["content"].strip()
    elif soup.title and soup.title.string:
        title = soup.title.string.strip()
    if title:
        title = title.split(" | ")[0].strip()
    if title and title.lower().startswith("open point"):
        title = None  # consultation-platform shell, not the document
    if title and len(title) > 3:
        return title
    return ""


def _junk_slug(url):
    """True when the URL's last segment is mostly digits (c2026-797150,
    335696) — i.e. the slug-derived label is unreadable."""
    seg = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
    seg = re.sub(r"\.\w{2,5}$", "", seg)
    alnum = [c for c in seg if c.isalnum()]
    if not alnum:
        return False
    return sum(c.isdigit() for c in alnum) / len(alnum) > 0.5


def cmd_titles(args):
    """Fill missing titles by reading each page's own <title> tag. No API
    key needed. By default targets only items whose URL slug is unreadable
    (mostly digits); --all fills every untitled item."""
    defaults, _ = load_registry()
    conn = db()
    fetcher = Fetcher(defaults, conn=None)
    # self-heal: null out platform boilerplate stored by earlier runs
    # (e.g. Treasury's consultation shell titles itself "Open Point - ...")
    conn.execute("UPDATE items SET title=NULL WHERE title LIKE 'Open Point%'")
    conn.execute("UPDATE items SET title=NULL WHERE lower(trim(title)) IN ("
                 + ",".join("?" * len(JUNK_ANCHORS)) + ")",
                 tuple(sorted(JUNK_ANCHORS)))
    conn.commit()
    rows = conn.execute(
        "SELECT url FROM items WHERE title IS NULL "
        "ORDER BY first_seen DESC").fetchall()
    targets = [u for (u,) in rows if args.all or _junk_slug(u)][:args.limit]
    if not targets:
        print("Nothing to do: no untitled items match.")
        return
    print(f"Fetching {len(targets)} pages for titles "
          f"(~{len(targets)*2//60 + 1} min at polite rate)...")
    done = 0
    for url in targets:
        try:
            title = _fetch_page_title(fetcher, url)
            if title is None:
                continue  # fetch failed; retry on a future run
            # empty string = attempted, nothing usable — stored so the URL
            # isn't refetched every run (the page falls back to its slug)
            conn.execute("UPDATE items SET title=? WHERE url=?", (title, url))
            conn.commit()
            if title:
                done += 1
                print(f"  {url} -> {title}")
        except Exception as e:
            print(f"  failed: {url}: {e}", file=sys.stderr)
    print(f"\nTitled {done} of {len(targets)}. Run `publish` to refresh the page.")


def cmd_changes(args):
    """List existing pages modified in place (lastmod bumps logged by the
    attachment watch). New pages and new attachments live in items; this is
    the third event class: a page was touched, whatever the reason."""
    conn = db()
    cutoff = (dt.date.today() - dt.timedelta(days=args.days)).isoformat()
    q = ("SELECT detected, source_id, url, old_lastmod, new_lastmod "
         "FROM pagechanges WHERE detected >= ? ")
    params = [cutoff]
    if args.source:
        q += "AND source_id = ? "
        params.append(args.source)
    q += "ORDER BY detected DESC"
    rows = conn.execute(q, params).fetchall()
    if not rows:
        print(f"No page modifications logged in the last {args.days} days"
              + (f" for {args.source}" if args.source else "") + ".")
        return
    for detected, sid, url, old, new in rows:
        print(f"{detected[:10]}  [{sid}]  {url}")
        print(f"    lastmod {old} -> {new}")
    print(f"\n{len(rows)} page modification(s).")


def cmd_repairdates(args):
    """Re-derive dates for backfilled rows (date-only first_seen) using the
    current dating logic and stored lastmods — no network. Rows that no
    longer yield a plausible date are removed (they should never have been
    imported)."""
    conn = db()
    from collections import defaultdict
    by_source = defaultdict(list)
    for sid, url, lm in conn.execute(
            "SELECT source_id, url, lastmod FROM lastmod"):
        by_source[sid].append((url, lm))
    lastmods, stamps_by_source = {}, {}
    for sid, pairs in by_source.items():
        stamps_by_source[sid] = _stamp_lastmods(pairs)
        for url, lm in pairs:
            lastmods[url] = (sid, lm)
    # every backfilled row: full dates (10 chars), year-only (4), and
    # undated listing imports ('') — daily-run rows (full timestamps) excluded
    rows = conn.execute(
        "SELECT url, first_seen FROM items WHERE length(first_seen) <= 10"
    ).fetchall()
    fixed, dropped = 0, 0
    for url, old in rows:
        sid, lm = lastmods.get(url, (None, None))
        if lm and lm[:10] in stamps_by_source.get(sid, ()):
            lm = None
        new = _derive_date(url, lm)
        if new is None:
            if old == "":
                continue  # deliberately-undated listing import — keep
            conn.execute("DELETE FROM items WHERE url=?", (url,))
            dropped += 1
        elif new != old:
            conn.execute("UPDATE items SET first_seen=? WHERE url=?", (new, url))
            fixed += 1
    run_rows = conn.execute(
        "SELECT url, parent_url FROM items WHERE length(first_seen) > 10 "
        "AND (doc_date IS NULL OR doc_date = '')").fetchall()
    redated = 0
    for url, parent in run_rows:
        d2 = _derive_date(url, None)
        # page rows: only a full URL date beats an exact first-seen timestamp;
        # attachment rows: even a year beats the capture date (old PDFs
        # surface when their parent page changes)
        if d2 and (len(d2) == 10 or parent):
            conn.execute("UPDATE items SET doc_date=? WHERE url=?", (d2, url))
            redated += 1
    conn.commit()
    print(f"Checked {len(rows)} backfilled rows: {fixed} re-dated, "
          f"{dropped} removed (no plausible date). "
          f"Run rows: {redated} publication dates recovered from URLs. "
          f"Run `publish` to refresh.")


def cmd_audit(args):
    """Coverage check against a truth-file: one URL per line (# = comment).
    Reports, per URL: INDEXED (searchable), CAPTURED (seen but not in the
    index — usually an undateable-backfill exclusion), or MISSING (never
    collected — run `miss <url>` on these for a live diagnosis)."""
    conn = db()
    urls = []
    for line in open(args.file):
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    counts = {"INDEXED": 0, "CAPTURED": 0, "MISSING": 0}
    for url in urls:
        item = conn.execute(
            "SELECT title, first_seen FROM items WHERE url=?", (url,)).fetchone()
        seen = conn.execute(
            "SELECT source_id FROM seen WHERE url=? LIMIT 1", (url,)).fetchone()
        if item:
            status = "INDEXED"
            extra = f"({(item[0] or 'untitled')[:50]}, {item[1][:10] or 'undated'})"
        elif seen:
            status, extra = "CAPTURED", f"(by {seen[0]}, not in index)"
        else:
            status, extra = "MISSING", ""
        counts[status] += 1
        print(f"  {status:8s} {url} {extra}")
    n = len(urls)
    print(f"\n{n} URLs: {counts['INDEXED']} indexed "
          f"({100*counts['INDEXED']//max(n,1)}%), {counts['CAPTURED']} captured-"
          f"only, {counts['MISSING']} missing. Run `miss <url>` on MISSING "
          f"lines for live diagnosis.")


def cmd_health(args):
    """Vitals from the runs log: what's failing now, what's gone silently
    quiet, and how long since each source last produced a new item."""
    conn = db()
    _d, sources = load_registry()
    enabled = {s["id"] for s in sources}
    now = dt.datetime.now(dt.timezone.utc)
    failing, silent, never_ran = [], [], []
    droughts = []
    for sid in sorted(enabled):
        runs = conn.execute(
            "SELECT ts, ok, collected, new, note FROM runs WHERE source_id=? "
            "ORDER BY ts DESC LIMIT 5", (sid,)).fetchall()
        if not runs:
            never_ran.append(sid)
            continue
        last = runs[0]
        if not last[1]:
            failing.append((sid, last[4][:70]))
        elif last[2] == 0 and len(runs) >= 2 and all(r[2] == 0 for r in runs[:3]):
            ever = conn.execute(
                "SELECT MAX(collected) FROM runs WHERE source_id=?",
                (sid,)).fetchone()[0]
            if ever:
                silent.append((sid, f"last 3 runs collected 0 "
                                    f"(historically up to {ever})"))
        last_new = conn.execute(
            "SELECT MAX(ts) FROM runs WHERE source_id=? AND new > 0",
            (sid,)).fetchone()[0]
        if last_new:
            days = (now - dt.datetime.fromisoformat(last_new)).days
            droughts.append((days, sid))
    if failing:
        print("FAILING (last run errored):")
        for sid, note in failing:
            print(f"  {sid}: {note}")
    if silent:
        print("SILENT (collecting zero where they used to collect plenty):")
        for sid, note in silent:
            print(f"  {sid}: {note}")
    if never_ran:
        print(f"NEVER RUN: {', '.join(never_ran)}")
    if not (failing or silent or never_ran):
        print("No failing or silent sources.")
    droughts.sort(reverse=True)
    print("\nLongest since last new item (top 10):")
    for days, sid in droughts[:10]:
        print(f"  {days:4d} days  {sid}")


DATE_ISH = re.compile(r"^((?:19|20)\d{2}-\d{2}-\d{2})")


def _clip_summary(text, cap=1200):
    """Whitespace-normalize and clip at a sentence boundary, never mid-word."""
    text = " ".join(text.split())
    if len(text) <= cap:
        return text
    cut = text[:cap]
    for stop in (". ", "? ", "! "):
        idx = cut.rfind(stop)
        if idx > cap * 0.4:
            return cut[:idx + 1]
    return cut[:cut.rfind(" ")] + "\u2026"


def _page_meta(soup):
    """Description + published date from standard page metadata: meta
    description / og:description, and AGLS DCTERMS fields Commonwealth
    sites carry."""
    desc = None
    for sel in (("meta", {"name": "description"}),
                ("meta", {"property": "og:description"}),
                ("meta", {"name": "dcterms.description"}),
                ("meta", {"name": "DCTERMS.description"})):
        tag = soup.find(*sel)
        if tag and tag.get("content", "").strip():
            desc = _clip_summary(tag["content"])
            break
    created = None
    for name in ("DCTERMS.created", "dcterms.created", "DCTERMS.issued",
                 "dcterms.issued", "DCTERMS.date", "dcterms.date", "created"):
        tag = soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            m = DATE_ISH.match(tag["content"].strip())
            if m and _plausible(m.group(1)):
                created = m.group(1)
                break
    if not created:
        tag = soup.find("meta", attrs={"property": "article:published_time"})
        if tag and tag.get("content"):
            m = DATE_ISH.match(tag["content"].strip())
            if m and _plausible(m.group(1)):
                created = m.group(1)
    return desc, created


def cmd_enrich(args):
    """Fetch each item's page and pull its meta description (searchable +
    displayed) and AGLS published date (fixes ~ approximations). No API.
    Skips document files (PDFs carry no page metadata). Prints a per-page
    report and a tally — run with --limit 25 to evaluate on a sample."""
    defaults, _ = load_registry()
    conn = db()
    fetcher = Fetcher(defaults, conn=None)
    docpat = re.compile(DOC_PATTERN, re.I)
    if getattr(args, "redo", False):
        n = conn.execute(
            "UPDATE items SET summary=NULL WHERE summary IS NOT NULL").rowcount
        conn.commit()
        print(f"--redo: cleared {n} previously captured summaries.")
    rows = conn.execute(
        "SELECT url FROM items WHERE summary IS NULL "
        "ORDER BY first_seen DESC").fetchall()
    targets = [u for (u,) in rows if not docpat.search(u)][:args.limit]
    if not targets:
        print("Nothing to enrich.")
        return
    got_desc = got_date = 0
    # Circuit breaker: after this many consecutive failures from one host
    # (503 WAF, SSL handshake drop, timeouts), skip the rest of that host's
    # rows for this run instead of retrying each one — stops a gated or
    # flaky host (BMF/Myra, BMI/SSL) from burning an unattended run for hours.
    DEAD_HOST_THRESHOLD = 15
    host_fails = {}          # host -> consecutive failure count
    dead_hosts = set()       # hosts given up on for this run
    skipped_dead = 0
    for url in targets:
        host = urlparse(url).netloc
        if host in dead_hosts:
            skipped_dead += 1
            continue
        try:
            r, _n = fetcher.get(url)
            host_fails[host] = 0   # a success resets the host's counter
            if r is None:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            desc, created = _page_meta(soup)
            title = _title_from_soup(soup)
            if not created:
                d2 = _derive_date(url, None)
                if d2 and len(d2) == 10:
                    created = d2
            conn.execute(
                "UPDATE items SET summary=?, "
                "title=COALESCE(NULLIF(title,''), ?) WHERE url=?",
                (desc or "", title or None, url))
            if created:
                conn.execute(
                    "UPDATE items SET doc_date=? WHERE url=? "
                    "AND (doc_date IS NULL OR doc_date='')", (created, url))
            conn.commit()
            got_desc += bool(desc)
            got_date += bool(created)
            print(f"  {'D' if desc else '-'}{'T' if created else '-'}"
                  f"{'N' if title else '-'}  {url}")
            if desc:
                print(f"        {desc[:150]}"
                      + (" [console preview truncated; stored in full]"
                         if len(desc) > 150 else ""))
        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else 0
            if code in (401, 403, 404, 410):
                # page gone or refuses this client — mark attempted so future
                # batches stop re-fetching it (permanent, per-URL)
                conn.execute("UPDATE items SET summary='' WHERE url=?", (url,))
                conn.commit()
                print(f"  --  ({code}, won't retry)  {url}")
            else:
                # 503 etc. — transient/WAF, count toward the host breaker
                host_fails[host] = host_fails.get(host, 0) + 1
                if host_fails[host] >= DEAD_HOST_THRESHOLD:
                    dead_hosts.add(host)
                    print(f"  !! {host}: {DEAD_HOST_THRESHOLD} consecutive "
                          f"failures — skipping its remaining rows this run",
                          file=sys.stderr)
                print(f"  failed: {url}: {e}", file=sys.stderr)
        except Exception as e:
            # SSL EOF, timeouts, connection drops — also count toward breaker
            host_fails[host] = host_fails.get(host, 0) + 1
            if host_fails[host] >= DEAD_HOST_THRESHOLD:
                dead_hosts.add(host)
                print(f"  !! {host}: {DEAD_HOST_THRESHOLD} consecutive "
                      f"failures — skipping its remaining rows this run",
                      file=sys.stderr)
            print(f"  failed: {url}: {e}", file=sys.stderr)
    tail = (f"  Skipped {skipped_dead} rows on dead hosts: "
            f"{', '.join(sorted(dead_hosts))}." if dead_hosts else "")
    print(f"\n{len(targets)} pages: {got_desc} had descriptions, "
          f"{got_date} had publication dates in metadata. "
          f"(D = description found, T = date found.){tail} Run `publish` to "
          f"see them on the page.")


def _load_topics():
    path = os.path.join(ROOT, "topics.yaml")
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return data.get("topics") or {}


def _triage(items, topics):
    """Rules-based triage: (topic_hits, quiet_items, counts).
    topic_hits: {topic: [items]} where any stem matches title+summary.
    quiet_items: items from agencies publishing <=2 today, not already hit.
    counts: {agency: n} for the footer."""
    from collections import Counter
    counts = Counter(it.get("agency", "?") for it in items)
    hits, hit_urls = {}, set()
    for topic, stems in topics.items():
        stems = [s.lower() for s in stems]
        matched = []
        for it in items:
            hay = " ".join(filter(None, (
                it.get("title"), it.get("summary"),
                it.get("title_en"), it.get("summary_en")))).lower()
            if any(s in hay for s in stems):
                matched.append(it)
                hit_urls.add(it["url"])
        if matched:
            hits[topic] = matched
    quiet = [it for it in items
             if counts[it.get("agency", "?")] <= 3
             and it["url"] not in hit_urls]
    return hits, quiet, counts


def _slack_post(webhook, text):
    body = json.dumps({"text": text}).encode()
    req = urllib.request.Request(
        webhook, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status


def _slack_line(it):
    t = (it.get("title_en") or it.get("title")
         or it["url"].rstrip("/").split("/")[-1])[:120]
    return f"\u2022 <{it['url']}|{t}> \u2014 {it.get('agency', '?')}"


def cmd_slack(args):
    """Post the day's triaged digest to Slack. Reads the webhook from the
    SLACK_WEBHOOK environment variable (set it in morning.sh). --test posts
    a hello instead."""
    webhook = os.environ.get("SLACK_WEBHOOK", "").strip()
    if not webhook:
        print("SLACK_WEBHOOK is not set — export it (see morning.sh) "
              "before running slack.", file=sys.stderr)
        sys.exit(1)
    if args.test:
        status = _slack_post(webhook,
            "govdocs test post \u2014 the webhook works. "
            "Daily digests will arrive here.")
        print(f"Test message posted (HTTP {status}).")
        return
    conn = db()
    since = (dt.datetime.now(dt.timezone.utc)
             - dt.timedelta(hours=args.hours)).isoformat(timespec="seconds")
    rows = conn.execute(
        "SELECT url, title, agency, summary, title_en, summary_en "
        "FROM items WHERE length(first_seen) > 10 AND first_seen >= ? "
        "ORDER BY first_seen DESC", (since,)).fetchall()
    items = [{"url": u, "title": t, "agency": a, "summary": s,
              "title_en": te, "summary_en": se}
             for u, t, a, s, te, se in rows]
    if not items:
        _slack_post(webhook, f"*German gov documents monitor:* no new items "
                             f"in the last {args.hours}h. (Pipeline alive.)")
        print("Posted: no new items.")
        return
    hits, quiet, counts = _triage(items, _load_topics())
    lines = [f"*German gov documents monitor \u2014 "
             f"{len(items)} new items*"]
    shown = 0
    for topic, matched in hits.items():
        lines.append(f"\n*{topic}* ({len(matched)})")
        for it in matched[:4]:
            lines.append(_slack_line(it))
            shown += 1
        if len(matched) > 4:
            lines.append(f"  \u2026and {len(matched) - 4} more")
        if shown >= 12:
            break
    if quiet and shown < 15:
        lines.append(f"\n*Quiet publishers* "
                     f"({len(quiet)} items from low-volume agencies)")
        for it in quiet[:15 - shown]:
            lines.append(_slack_line(it))
    top = ", ".join(f"{a} {n}" for a, n in counts.most_common(6))
    site = os.environ.get("GOVDOCS_SITE_URL", "").strip()
    tail = f" \u2014 <{site}|open the index>" if site else ""
    lines.append(f"\n_{top}_{tail}")
    status = _slack_post(webhook, "\n".join(lines))
    print(f"Posted {len(items)}-item digest to Slack (HTTP {status}).")


def cmd_publish(args):
    from publish_template import SEARCH_PAGE
    conn = db()
    rows = conn.execute(
        "SELECT url, title, agency, substr(first_seen,1,10) AS date, "
        "doc_type, parent_url, source_id, relevance, topic, doc_date, "
        "length(first_seen), summary, title_en, summary_en "
        "FROM items").fetchall()
    data = []
    for u, t, a, d, ty, p, s, r, tp, dd, fslen, summ, te, se in rows:
        # best available date: extracted publication date > stored date
        date = dd[:10] if dd and re.match(r"(19|20)\d{2}", str(dd)) else d
        # approximate = backfilled AND the stored date is not what the URL
        # alone yields (i.e. it came from lastmod, the weakest signal) — or an
        # attachment with no date signal of its own (shown at capture date)
        approx = bool((fslen == 10 and not dd
                       and _derive_date(u, None) != d)
                      or (p and not dd))
        data.append({"url": u, "title": t, "agency": a, "date": date,
                     "type": ty, "parent": p, "source": s, "relevance": r,
                     "topic": tp, "approx": approx, "summary": summ or None,
                     "title_en": te, "summary_en": se or None,
                     "indexed": (d or "")[:10]})
    # year-only dates sort at the START of their year: precise dates from the
    # same year lead the index, vague ones trail (range-filtering on the page
    # still treats them as spanning the whole year)
    data.sort(key=lambda x: (x["date"] + "-01-01")[:10], reverse=True)
    out = args.out
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "docs.json"), "w") as f:
        json.dump(data, f, ensure_ascii=False)
    with open(os.path.join(out, "index.html"), "w") as f:
        f.write(SEARCH_PAGE)
    with open(os.path.join(out, "coverage.html"), "w") as f:
        from publish_template import render_coverage
        f.write(render_coverage())
    print(f"Published {len(data)} documents to {out}/ "
          f"(index.html + docs.json).")
    print("Upload both files to a folder on your web host; after each run, "
          "re-publish and re-upload docs.json only. Preview locally with: "
          f'python3 -m http.server --directory "{out}" 8000')


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("probe", help="check every source, no state written")
    pr.add_argument("--only", nargs="*", help="restrict to these source ids")
    pr.add_argument("--paths", action="store_true",
                    help="print path-structure summary for every source")
    pr.set_defaults(func=cmd_probe)
    sub.add_parser("init", help="baseline: mark current URLs as seen").set_defaults(
        func=cmd_init)
    sub.add_parser("run", help="daily diff + digest").set_defaults(func=cmd_run)
    m = sub.add_parser("miss", help="log documents the system failed to "
                                    "surface (one or more URLs)")
    m.add_argument("url", nargs="+")
    m.add_argument("--note", default="")
    m.set_defaults(func=cmd_miss)
    e = sub.add_parser("extract", help="LLM metadata extraction for new items")
    e.add_argument("--limit", type=int, default=50)
    e.set_defaults(func=cmd_extract)
    rt = sub.add_parser("repair-titles",
                        help="null out site-boilerplate titles stored by "
                             "earlier enrich runs (one-off cleanup)")
    rt.set_defaults(func=cmd_repair_titles)
    tr = sub.add_parser("translate",
                        help="translate titles + summaries into English "
                             "(newest untranslated rows first)")
    tr.add_argument("--limit", type=int, default=100,
                    help="max rows this run — the daily token cap in "
                         "registry.yaml is the spend guard (default 100)")
    tr.set_defaults(func=cmd_translate)
    pub = sub.add_parser("publish",
                         help="export items to a static searchable web page")
    pub.add_argument("--out", default=os.path.join(ROOT, "site"))
    pub.set_defaults(func=cmd_publish)
    bf = sub.add_parser("backfill",
                        help="import the recent dateable slice of existing "
                             "site content into items")
    bf.add_argument("--since", default="2022-01-01",
                    help="earliest date to import (YYYY-MM-DD, default "
                         "2022-01-01)")
    bf.add_argument("--reset", action="store_true",
                    help="clear previously backfilled rows first")
    bf.add_argument("--listings", action="store_true",
                    help="also import the CURRENT contents of listing sources "
                         "as undated, searchable entries")
    bf.set_defaults(func=cmd_backfill)
    mo = sub.add_parser("morning",
                        help="run + extract + digest + publish + Slack")
    mo.add_argument("--limit", type=int, default=120,
                    help="max items to extract metadata for")
    mo.set_defaults(func=cmd_morning)
    fc = sub.add_parser("filecheck",
                        help="detect files silently revised at the same URL")
    fc.add_argument("--days", type=int, default=90,
                    help="check files first seen within this many days")
    fc.add_argument("--limit", type=int, default=300)
    fc.set_defaults(func=cmd_filecheck)
    ch = sub.add_parser("changes", help="list pages modified in place "
                        "(lastmod bumps logged by the attachment watch)")
    ch.add_argument("--days", type=int, default=30)
    ch.add_argument("--source", help="restrict to one source id")
    ch.set_defaults(func=cmd_changes)
    ti = sub.add_parser("titles", help="fill unreadable titles from each "
                        "page's own <title> tag (no API key needed)")
    ti.add_argument("--limit", type=int, default=300)
    ti.add_argument("--all", action="store_true",
                    help="fill every untitled item, not just digit-slug ones")
    ti.set_defaults(func=cmd_titles)
    sub.add_parser("repair-dates",
                   help="re-derive backfilled dates with current logic "
                        "(no network)").set_defaults(func=cmd_repairdates)
    en = sub.add_parser("enrich", help="pull meta descriptions + AGLS dates "
                                       "from item pages (no API)")
    en.add_argument("--limit", type=int, default=50)
    en.add_argument("--redo", action="store_true",
                    help="clear and recapture all summaries (after logic "
                         "improvements)")
    en.set_defaults(func=cmd_enrich)
    au = sub.add_parser("audit", help="check a truth-file of URLs against "
                                      "the index (no network)")
    au.add_argument("--file", default=os.path.join(ROOT, "audit-urls.txt"))
    au.set_defaults(func=cmd_audit)
    sub.add_parser("health", help="source vitals: failing, silent, and "
                                  "drought report").set_defaults(
        func=cmd_health)
    sl = sub.add_parser("slack", help="post the triaged daily digest to "
                                      "Slack (needs SLACK_WEBHOOK)")
    sl.add_argument("--hours", type=int, default=26,
                    help="look-back window for 'new' items (default 26)")
    sl.add_argument("--test", action="store_true",
                    help="post a hello to verify the webhook")
    sl.set_defaults(func=cmd_slack)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
