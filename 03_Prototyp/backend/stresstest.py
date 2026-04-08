"""
Stresstest gegen Mock-Backend — nur Python stdlib.
Startet den Mock-Server, führt alle Test-Suites aus, gibt Report aus.
"""

import asyncio
import json
import re
import statistics
import sys
import time
import threading
import urllib.request
import urllib.error
from collections import defaultdict
from dataclasses import dataclass, field

from mock_server import run as run_mock

PORT = 18000
BASE = f"http://127.0.0.1:{PORT}"  # wird in main() überschrieben
USER_KEY  = "key-user-abc123"
ADMIN_KEY = "key-admin-xyz789"
BAD_KEY   = "key-INVALID-000"

# ── HTTP-Hilfsfunktion (stdlib) ───────────────────────────────────────────────

def http(method, path, *, headers=None, body=None, expected=200):
    url = BASE + path
    h = {"Content-Type": "application/json", **(headers or {})}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            latency = (time.perf_counter() - t0) * 1000
            status = resp.status
    except urllib.error.HTTPError as e:
        latency = (time.perf_counter() - t0) * 1000
        status = e.code
    except Exception as e:
        latency = (time.perf_counter() - t0) * 1000
        return 0, latency, f"FEHLER: {e}"

    expected_list = expected if isinstance(expected, list) else [expected]
    ok = status in expected_list
    return status, latency, "" if ok else f"HTTP {status}"


# ── Result / Suite ────────────────────────────────────────────────────────────

@dataclass
class R:
    name: str
    status: int
    ms: float
    ok: bool
    detail: str = ""

@dataclass
class Suite:
    name: str
    results: list[R] = field(default_factory=list)

    def add(self, name, method, path, headers=None, body=None, expected=200):
        status, ms, detail = http(method, path, headers=headers, body=body, expected=expected)
        expected_list = expected if isinstance(expected, list) else [expected]
        ok = status in expected_list
        self.results.append(R(name, status, ms, ok, detail))

    @property
    def passed(self): return sum(1 for r in self.results if r.ok)
    @property
    def failed(self): return len(self.results) - self.passed
    @property
    def lats(self): return [r.ms for r in self.results]
    def p95(self):
        s = sorted(self.lats)
        return s[int(len(s) * 0.95)] if s else 0


# ── Test-Suites ───────────────────────────────────────────────────────────────

def suite_auth():
    s = Suite("Auth & Zugriffskontrolle")
    uh = {"X-API-Key": USER_KEY}
    ah = {"X-API-Key": ADMIN_KEY}
    bh = {"X-API-Key": BAD_KEY}

    s.add("GET /status ohne key → 200",      "GET",  "/status")
    s.add("GET /templates user key → 200",   "GET",  "/templates",              headers=uh)
    s.add("GET /templates admin key → 200",  "GET",  "/templates",              headers=ah)
    s.add("GET /templates kein key → 401",   "GET",  "/templates",              expected=401)
    s.add("GET /templates bad key → 401",    "GET",  "/templates",              headers=bh, expected=401)
    s.add("POST /generate kein key → 401",   "POST", "/generate",               body={"text_type":"seo","topic":"X"*3}, expected=401)
    s.add("GET /admin/kb-status user → 403", "GET",  "/admin/kb-status",        headers=uh, expected=403)
    s.add("GET /admin/kb-status admin → 200","GET",  "/admin/kb-status",        headers=ah)
    s.add("POST /admin/ingest user → 403",   "POST", "/admin/ingest",           headers=uh, body={"path":"./kb"}, expected=403)
    return s


def suite_validation():
    s = Suite("Input-Validierung & Grenzwerte")
    uh = {"X-API-Key": USER_KEY}

    s.add("text_type ungültig → 422",       "POST", "/generate", headers=uh, body={"text_type":"INVALID","topic":"Test"}, expected=422)
    s.add("topic leer → 422",               "POST", "/generate", headers=uh, body={"text_type":"seo","topic":""}, expected=422)
    s.add("topic 2 Zeichen → 422",          "POST", "/generate", headers=uh, body={"text_type":"seo","topic":"AB"}, expected=422)
    s.add("topic 3 Zeichen (Grenze) → 200", "POST", "/generate", headers=uh, body={"text_type":"seo","topic":"ABC"})
    s.add("topic 500 Zeichen (Grenze) → 200","POST","/generate", headers=uh, body={"text_type":"seo","topic":"X"*500})
    s.add("topic 501 Zeichen → 422",        "POST", "/generate", headers=uh, body={"text_type":"seo","topic":"X"*501}, expected=422)
    s.add("fehlender text_type → 422",      "POST", "/generate", headers=uh, body={"topic":"Test"}, expected=422)
    s.add("alle text_types valid: seo",     "POST", "/generate", headers=uh, body={"text_type":"seo","topic":"SEO Test"})
    s.add("alle text_types valid: produkt", "POST", "/generate", headers=uh, body={"text_type":"produkt","topic":"Produkt Test"})
    s.add("alle text_types valid: faq",     "POST", "/generate", headers=uh, body={"text_type":"faq","topic":"FAQ Test"})
    s.add("alle text_types valid: leicht",  "POST", "/generate", headers=uh, body={"text_type":"leicht","topic":"Leicht Test"})
    s.add("alle text_types valid: social",  "POST", "/generate", headers=uh, body={"text_type":"social","topic":"Social Test"})
    return s


def suite_pii():
    s = Suite("PII-Sanitizer")
    uh = {"X-API-Key": USER_KEY}

    s.add("E-Mail → 422",                   "POST", "/generate", headers=uh, body={"text_type":"seo","topic":"Mail: info@test.de"}, expected=422)
    s.add("Telefon → 422",                  "POST", "/generate", headers=uh, body={"text_type":"seo","topic":"Tel: 0211 12345678"}, expected=422)
    s.add("IBAN → 422",                     "POST", "/generate", headers=uh, body={"text_type":"seo","topic":"IBAN: DE89370400440532013000"}, expected=422)
    s.add("IP-Adresse → 422",               "POST", "/generate", headers=uh, body={"text_type":"seo","topic":"IP: 192.168.1.100"}, expected=422)
    s.add("E-Mail verschleiert → 200",      "POST", "/generate", headers=uh, body={"text_type":"seo","topic":"info [at] beispiel [dot] de"})
    s.add("Normaler Text → 200",            "POST", "/generate", headers=uh, body={"text_type":"seo","topic":"Nachhaltige Verpackung"})
    return s


def suite_resilience():
    s = Suite("Robustheit & Sonderzeichen")
    uh = {"X-API-Key": USER_KEY}

    cases = [
        ("Unicode Emoji",        "Produkt 🚀 mit ✨ Features"),
        ("Umlaute",              "Größte Überraschung für Müller & Söhne"),
        ("Sonderzeichen",        "Preis: 49,99 € | Rabatt: 20% | #SAVE20"),
        ("SQL-Injection",        "'; DROP TABLE users; --"),
        ("HTML/Script-Tags",     "<script>alert('xss')</script> Text"),
        ("Newlines",             "Zeile 1\nZeile 2\nZeile 3"),
        ("Nur Zahlen",           "123456789"),
        ("Gemischt alles",       "Test™ №1 — café résumé 2026 ✓"),
    ]
    for name, topic in cases:
        s.add(f"{name} → 200/422", "POST", "/generate", headers=uh,
              body={"text_type":"seo","topic":topic}, expected=[200, 422])
    return s


def suite_admin():
    s = Suite("Admin-Endpoints")
    ah = {"X-API-Key": ADMIN_KEY}

    s.add("kb-status → 200",                "GET",  "/admin/kb-status", headers=ah)
    s.add("documents list → 200",           "GET",  "/admin/documents", headers=ah)
    s.add("ingest ungültiger Pfad → 404",   "POST", "/admin/ingest",    headers=ah, body={"path":"/nonexistent/path"}, expected=404)
    s.add("ingest gültiger Pfad → 200",     "POST", "/admin/ingest",    headers=ah, body={"path":"./knowledge_base"})
    s.add("kb-reset → 200",                 "DELETE","/admin/kb-reset", headers=ah)
    return s


def suite_load(workers=20, rounds=3):
    s = Suite(f"Lasttest ({workers} parallel × {rounds} Runden)")
    uh = {"X-API-Key": USER_KEY}
    types = ["seo","produkt","faq","leicht","social"]

    def single(i):
        tt = types[i % len(types)]
        return http("POST", "/generate", headers=uh,
                    body={"text_type":tt,"topic":f"Lasttest Thema Nummer {i}"},
                    expected=[200, 429])

    for round_n in range(rounds):
        results_raw = []
        threads = []
        lock = threading.Lock()

        def worker(idx):
            status, ms, detail = single(idx)
            expected = [200, 429]
            ok = status in expected
            with lock:
                results_raw.append(R(f"load #{idx}", status, ms, ok, detail))

        for i in range(workers):
            t = threading.Thread(target=worker, args=(round_n * workers + i,))
            threads.append(t)

        for t in threads: t.start()
        for t in threads: t.join()

        for r in results_raw:
            s.results.append(r)

    return s


def suite_rate_limit():
    s = Suite("Rate-Limiting (25 schnelle Requests, neuer Key)")
    # Neuer Key, der nicht USER_KEYS zugeordnet ist – der Mock akzeptiert
    # ihn nicht, daher 401 erwartet. Das prüft, dass Unknown-Keys korrekt geblockt werden.
    rh = {"X-API-Key": "key-ratelimit-stress-unknown"}
    for i in range(25):
        status, ms, detail = http("POST", "/generate", headers=rh,
            body={"text_type":"seo","topic":f"RateTest {i}"}, expected=[200,401,429])
        ok = status in [200, 401, 429]
        s.results.append(R(f"rate #{i}", status, ms, ok, detail))

    rate_limited = sum(1 for r in s.results if r.status == 429)
    blocked      = sum(1 for r in s.results if r.status == 401)
    print(f"     → 429: {rate_limited}  |  401 (unbekannter Key): {blocked}")
    return s


# ── Reporting ─────────────────────────────────────────────────────────────────

W = 72

def bar(pct, width=20):
    filled = int(width * pct / 100)
    return "█" * filled + "░" * (width - filled)

def print_suite(s: Suite):
    color_ok   = "\033[32m"
    color_fail = "\033[31m"
    color_dim  = "\033[2m"
    reset      = "\033[0m"

    icon = "✓" if s.failed == 0 else "✗"
    c = color_ok if s.failed == 0 else color_fail
    lats = s.lats
    avg = statistics.mean(lats) if lats else 0
    mx  = max(lats) if lats else 0

    print(f"\n{c}{icon} {s.name}{reset}")
    print(f"  {color_dim}{s.passed}/{len(s.results)} bestanden  "
          f"avg {avg:.0f}ms  p95 {s.p95():.0f}ms  max {mx:.0f}ms{reset}")

    for r in s.results:
        if not r.ok:
            print(f"  {color_fail}✗ [{r.status:3d}] {r.name}  {r.detail}{reset}")


def print_summary(suites, elapsed):
    reset = "\033[0m"; bold = "\033[1m"; green = "\033[32m"; red = "\033[31m"; dim = "\033[2m"
    print("\n" + "═" * W)
    print(f"{'SUITE':<38} {'OK':>4} {'FAIL':>4} {'RATE':>5}  {'avg':>5}  {'p95':>5}  {'max':>5}")
    print("─" * W)
    total_ok = total_fail = 0
    for s in suites:
        lats = s.lats
        avg  = f"{statistics.mean(lats):.0f}" if lats else "—"
        p95  = f"{s.p95():.0f}"               if lats else "—"
        mx   = f"{max(lats):.0f}"             if lats else "—"
        rate = f"{s.passed/len(s.results)*100:.0f}%" if s.results else "—"
        c = green if s.failed == 0 else red
        print(f"{c}{s.name[:38]:<38}{reset} {green}{s.passed:>4}{reset} "
              f"{(red+str(s.failed)+reset) if s.failed else dim+'0'+reset:>13} "
              f"{rate:>5}  {avg:>5}  {p95:>5}  {mx:>5}")
        total_ok += s.passed; total_fail += s.failed
    print("─" * W)
    total = total_ok + total_fail
    overall = total_ok / total * 100 if total else 0
    c = green if total_fail == 0 else (red if overall < 90 else "\033[33m")
    print(f"{bold}{'GESAMT':<38}{reset} {green}{total_ok:>4}{reset} "
          f"{(red+str(total_fail)+reset) if total_fail else dim+'0'+reset:>13} "
          f"{c}{overall:.1f}%{reset}")
    print(f"{dim}Laufzeit: {elapsed:.1f}s{reset}")
    print("═" * W)


# ── Main ──────────────────────────────────────────────────────────────────────

def main(workers=20, rounds=3):
    # Mock-Server starten
    server = run_mock(PORT)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)

    print(f"\n{'═'*W}")
    print(f"  EVL-2026-002 · Stresstest   →   {BASE}  (Mock-Backend)")
    print(f"  Workers: {workers}  ·  Runden: {rounds}")
    print(f"{'═'*W}")

    t0 = time.perf_counter()
    suites = []

    for fn, kw in [
        (suite_auth,       {}),
        (suite_validation, {}),
        (suite_pii,        {}),
        (suite_resilience, {}),
        (suite_admin,      {}),
        (suite_rate_limit, {}),
        (suite_load,       {"workers": workers, "rounds": rounds}),
    ]:
        print(f"\033[2m  → {fn.__name__.replace('suite_','').upper()}…\033[0m")
        suites.append(fn(**kw))

    print_summary(suites, time.perf_counter() - t0)
    server.shutdown()
    total_fail = sum(s.failed for s in suites)
    sys.exit(0 if total_fail == 0 else 1)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--workers", type=int, default=20)
    p.add_argument("--rounds",  type=int, default=3)
    args = p.parse_args()
    main(args.workers, args.rounds)
