import os
import requests
from utils.normalize import normalize_url
from utils.user_agents import MAG_USER_AGENTS, BROWSER_USER_AGENTS
from utils.anti_bot import build_headers
from utils.cloudflare import detect_cloudflare
from browser_check import browser_check
from proxy_handler import load_proxies, choose_proxy
from session_clone import load_browser_cookies


# ============================================================
# ORDNERVERWALTUNG
# ============================================================

def ensure_output_dirs():
    base = "ausgabe"
    modes = ["requests", "browser", "proxy", "headless", "session", "pfade", "cloudflare", "combined"]
    os.makedirs(base, exist_ok=True)
    for m in modes:
        os.makedirs(os.path.join(base, m), exist_ok=True)

def ensure_input_dir():
    os.makedirs("eingabe", exist_ok=True)


# ============================================================
# REPORT-SYSTEM
# ============================================================

REPORT_MODE = "details"  # "single", "details", "both"

def save_html(mode: str, portal_name: str, content: str):
    ensure_output_dirs()
    safe_name = f"{portal_name}_{mode}".replace(":", "_").replace("/", "_").replace("\\", "_")
    filename = safe_name + ".html"
    path = os.path.join("ausgabe", mode, filename)

    if not content or content.strip() == "":
        content = "<!-- EMPTY HTML: Portal lieferte keinen Inhalt -->"

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def save_combined(portal_name: str, sections: dict[str, str]):
    ensure_output_dirs()
    html_parts = ["<html><body><h1>Portal Report</h1>"]
    for title, body in sections.items():
        html_parts.append(f"<h2>{title}</h2><pre>{body}</pre>")
    html_parts.append("</body></html>")
    content = "\n".join(html_parts)
    path = os.path.join("ausgabe", "combined", f"{portal_name}_full.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ============================================================
# BASIS-TESTS
# ============================================================

def classify_portal(result: dict) -> str:
    if result.get("error"):
        return "Fehler"
    status = result.get("status")
    if isinstance(status, int) and 200 <= status < 300:
        return "Online"
    if isinstance(status, int) and status in (401, 403):
        return "Geblockt"
    if result.get("cloudflare"):
        return "Cloudflare"
    return "Unklar"

def requests_check(url: str, ua: str) -> dict:
    res = {
        "status": "",
        "html": "",
        "headers": {},
        "cloudflare": False,
        "error": "",
    }
    try:
        headers = build_headers(ua)
        r = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        res["status"] = r.status_code
        res["html"] = r.text
        res["headers"] = dict(r.headers)
        res["cloudflare"] = detect_cloudflare(res["html"], res["headers"])
    except Exception as e:
        res["error"] = str(e)
    return res


# ============================================================
# AUTO-SCAN SCHNELL
# ============================================================

def auto_scan_schnell(urls: list[str]):
    proxies = load_proxies()
    cookies = load_browser_cookies()

    for raw in urls:
        url = normalize_url(raw)
        portal_name = url.replace("://", "_").replace("/", "_")
        print(f"\n[Schnellscan] {url}")

        combined_sections = {}
        final_class = "Unklar"

        # Reihenfolge: Requests → Browser-UA → MAG → Proxy → Selenium → Session
        modes = ["requests", "browser", "mag", "proxy", "selenium", "session"]

        for mode in modes:

            # Requests
            if mode == "requests":
                r = requests_check(url, BROWSER_USER_AGENTS[0])
                combined_sections["Requests"] = f"Status: {r['status']}\nError: {r['error']}"
                if classify_portal(r) == "Online":
                    final_class = "Online"
                    save_html("requests", portal_name, r["html"])
                    break

            # Browser-UA
            elif mode == "browser":
                r = requests_check(url, BROWSER_USER_AGENTS[1])
                combined_sections["Browser-UA"] = f"Status: {r['status']}\nError: {r['error']}"
                if classify_portal(r) == "Online":
                    final_class = "Online"
                    save_html("browser", portal_name, r["html"])
                    break

            # MAG-UA
            elif mode == "mag":
                r = requests_check(url, MAG_USER_AGENTS[0])
                combined_sections["MAG-UA"] = f"Status: {r['status']}\nError: {r['error']}"
                if classify_portal(r) == "Online":
                    final_class = "Online"
                    save_html("requests", portal_name, r["html"])
                    break

            # Proxy
            elif mode == "proxy":
                proxy_cfg = choose_proxy(proxies)
                if not proxy_cfg:
                    continue
                try:
                    r = requests.get(url, headers=build_headers(BROWSER_USER_AGENTS[0]),
                                     proxies={"http": proxy_cfg["server"], "https": proxy_cfg["server"]},
                                     timeout=10)
                    res = {
                        "status": r.status_code,
                        "html": r.text,
                        "headers": dict(r.headers),
                        "cloudflare": detect_cloudflare(r.text, r.headers),
                        "error": "",
                    }
                except Exception as e:
                    res = {"status": "", "html": "", "headers": {}, "cloudflare": False, "error": str(e)}

                combined_sections["Proxy"] = f"Status: {res['status']}\nError: {res['error']}"
                if classify_portal(res) == "Online":
                    final_class = "Online"
                    save_html("proxy", portal_name, res["html"])
                    break

            # Selenium
            elif mode == "selenium":
                res = browser_check(url, proxy=None, cookies=None, headless=True)
                combined_sections["Selenium"] = f"Final URL: {res['final_url']}\nError: {res['error']}"
                if not res["error"]:
                    final_class = "Online"
                    save_html("headless", portal_name, res["html"])
                    break

            # Session-Clone
            elif mode == "session":
                res = browser_check(url, proxy=None, cookies=cookies, headless=True)
                combined_sections["Session-Clone"] = f"Final URL: {res['final_url']}\nError: {res['error']}"
                if not res["error"]:
                    final_class = "Online"
                    save_html("session", portal_name, res["html"])
                    break

        print(f"Ergebnis: {final_class}")
        save_combined(portal_name, combined_sections)


# ============================================================
# AUTO-SCAN VOLL
# ============================================================

def auto_scan_voll(urls: list[str]):
    proxies = load_proxies()
    cookies = load_browser_cookies()

    for raw in urls:
        url = normalize_url(raw)
        portal_name = url.replace("://", "_").replace("/", "_")
        print(f"\n[Vollscan] {url}")

        combined_sections = {}

        # Requests
        r1 = requests_check(url, BROWSER_USER_AGENTS[0])
        combined_sections["Requests"] = f"Status: {r1['status']}\nError: {r1['error']}"
        save_html("requests", portal_name, r1["html"])

        # Browser-UA
        r2 = requests_check(url, BROWSER_USER_AGENTS[1])
        combined_sections["Browser-UA"] = f"Status: {r2['status']}\nError: {r2['error']}"
        save_html("browser", portal_name, r2["html"])

        # MAG-UA
        r3 = requests_check(url, MAG_USER_AGENTS[0])
        combined_sections["MAG-UA"] = f"Status: {r3['status']}\nError: {r3['error']}"
        save_html("requests", portal_name, r3["html"])

        # Proxy
        proxy_cfg = choose_proxy(proxies)
        if proxy_cfg:
            try:
                r = requests.get(url, headers=build_headers(BROWSER_USER_AGENTS[0]),
                                 proxies={"http": proxy_cfg["server"], "https": proxy_cfg["server"]},
                                 timeout=10)
                r4 = {
                    "status": r.status_code,
                    "html": r.text,
                    "headers": dict(r.headers),
                    "cloudflare": detect_cloudflare(r.text, r.headers),
                    "error": "",
                }
            except Exception as e:
                r4 = {"status": "", "html": "", "headers": {}, "cloudflare": False, "error": str(e)}
            combined_sections["Proxy"] = f"Status: {r4['status']}\nError: {r4['error']}"
            save_html("proxy", portal_name, r4["html"])

        # Selenium
        r5 = browser_check(url, proxy=None, cookies=None, headless=True)
        combined_sections["Selenium"] = f"Final URL: {r5['final_url']}\nError: {r5['error']}"
        save_html("headless", portal_name, r5["html"])

        # Session-Clone
        r6 = browser_check(url, proxy=None, cookies=cookies, headless=True)
        combined_sections["Session-Clone"] = f"Final URL: {r6['final_url']}\nError: {r6['error']}"
        save_html("session", portal_name, r6["html"])

        save_combined(portal_name, combined_sections)


# ============================================================
# URL-EINGABE
# ============================================================

def input_urls_mode() -> list[str]:
    print("\nURL-Eingabe:")
    print("1) Einzel-URL eingeben")
    print("2) Mehrere URLs (Komma getrennt)")
    print("3) Datei laden (eingabe/portale.txt)")
    choice = input("> ").strip()

    urls = []

    if choice == "1":
        u = input("Portal-URL: ").strip()
        if u:
            urls.append(u)

    elif choice == "2":
        line = input("Portale (Komma getrennt): ").strip()
        urls = [x.strip() for x in line.split(",") if x.strip()]

    elif choice == "3":
        path = "eingabe/portale.txt"
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                urls = [line.strip() for line in f if line.strip()]
        else:
            print("Datei nicht gefunden:", path)

    return urls


# ============================================================
# PROFI-MODUS
# ============================================================

def profi_modus():
    while True:
        print("""
=== MANUELLER PROFI-MODUS ===

--- Direkt-Tests ---
1) Requests
2) Browser-UA
3) MAG-UA
4) Proxy
5) Selenium-Browser
6) Session-Clone

--- Analyse-Tools ---
7) Pfad-Scan
8) Cloudflare-Analyse
9) HTML-Analyse (Body, Keywords)
10) Header-Analyse
11) Redirect-Analyse

--- Komplett ---
12) Komplettscan für EIN Portal
13) Zurück
""")

        choice = input("> ").strip()
        if choice == "13":
            break

        urls = input_urls_mode()
        if not urls:
            print("Keine URLs.")
            continue

        for url in urls:
            print(f"\n[Profi-Modus] Teste: {url}")

            # 1) Requests
            if choice == "1":
                r = requests_check(url, BROWSER_USER_AGENTS[0])
                print(r)

            # 2) Browser-UA
            elif choice == "2":
                r = requests_check(url, BROWSER_USER_AGENTS[1])
                print(r)

            # 3) MAG-UA
            elif choice == "3":
                r = requests_check(url, MAG_USER_AGENTS[0])
                print(r)

            # 4) Proxy
            elif choice == "4":
                proxies = load_proxies()
                proxy_cfg = choose_proxy(proxies)
                if not proxy_cfg:
                    print("Keine Proxys gefunden.")
                    continue
                try:
                    r = requests.get(url, headers=build_headers(BROWSER_USER_AGENTS[0]),
                                     proxies={"http": proxy_cfg["server"], "https": proxy_cfg["server"]},
                                     timeout=10)
                    print("Status:", r.status_code)
                    print("Cloudflare:", detect_cloudflare(r.text, r.headers))
                except Exception as e:
                    print("Proxy-Fehler:", e)

            # 5) Selenium-Browser
            elif choice == "5":
                res = browser_check(url, proxy=None, cookies=None, headless=False)
                print(res)

            # 6) Session-Clone
            elif choice == "6":
                cookies = load_browser_cookies()
                res = browser_check(url, proxy=None, cookies=cookies, headless=True)
                print(res)

            # 7) Pfad-Scan
            elif choice == "7":
                pfade = [
                    "/c/",
                    "/stalker_portal/c/",
                    "/stalker_portal/",
                    "/portal.php",
                    "/player_api.php",
                    "/xmltv.php",
                    "/get.php",
                ]
                for p in pfade:
                    test_url = url.rstrip("/") + p
                    r = requests_check(test_url, BROWSER_USER_AGENTS[0])
                    print(test_url, "→", r["status"])

            # 8) Cloudflare-Analyse
            elif choice == "8":
                r = requests_check(url, BROWSER_USER_AGENTS[0])
                print("Cloudflare erkannt:", detect_cloudflare(r["html"], r["headers"]))

            # 9) HTML-Analyse
            elif choice == "9":
                r = requests_check(url, BROWSER_USER_AGENTS[0])
                html = r["html"]
                print("Body-Länge:", len(html))
                if "<title>" in html.lower():
                    start = html.lower().find("<title>") + 7
                    end = html.lower().find("</title>")
                    print("Titel:", html[start:end])
                keywords = ["iptv", "portal", "stalker", "mag", "login", "playlist"]
                for k in keywords:
                    if k in html.lower():
                        print("Keyword gefunden:", k)

            # 10) Header-Analyse
            elif choice == "10":
                r = requests_check(url, BROWSER_USER_AGENTS[0])
                for k, v in r["headers"].items():
                    print(f"{k}: {v}")

            # 11) Redirect-Analyse
            elif choice == "11":
                r = requests_check(url, BROWSER_USER_AGENTS[0])
                print("Status:", r["status"])
                print("Hinweis: Requests folgt Redirects automatisch.")

            # 12) Komplettscan
            elif choice == "12":
                auto_scan_voll([url])

            else:
                print("Ungültige Auswahl.")


# ============================================================
# REPORT-EINSTELLUNGEN
# ============================================================

def report_einstellungen():
    global REPORT_MODE
    print("""
=== REPORT-EINSTELLUNGEN ===
1) Nur Gesamt-Report (HTML)
2) Nur Detail-Reports (pro Modus)
3) Gesamt-Report + Detail-Reports
4) Zurück
""")
    choice = input("> ").strip()
    if choice == "1":
        REPORT_MODE = "single"
    elif choice == "2":
        REPORT_MODE = "details"
    elif choice == "3":
        REPORT_MODE = "both"


# ============================================================
# BATCH-SCAN
# ============================================================

def batch_scan():
    path = "eingabe/portale.txt"
    if not os.path.exists(path):
        print("Datei nicht gefunden:", path)
        return

    with open(path, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    if not urls:
        print("Keine URLs in Datei.")
        return

    mode = input("Batch-Modus: 1) Schnellscan  2) Vollscan > ").strip()
    if mode == "1":
        auto_scan_schnell(urls)
    else:
        auto_scan_voll(urls)


# ============================================================
# HAUPTMENÜ
# ============================================================

def main_menu():
    ensure_output_dirs()
    ensure_input_dir()

    while True:
        print("""
=== IPTV Portal Checker PRO MAX ===

--- Automatik ---
1) Schnellscan
2) Vollscan

--- Manuell ---
3) Profi-Modus

--- Dateien ---
4) Batch-Scan

--- Einstellungen ---
5) Report-Einstellungen

--- System ---
6) Beenden
""")
        choice = input("> ").strip()

        if choice == "1":
            urls = input_urls_mode()
            if urls:
                auto_scan_schnell(urls)

        elif choice == "2":
            urls = input_urls_mode()
            if urls:
                auto_scan_voll(urls)

        elif choice == "3":
            profi_modus()

        elif choice == "4":
            batch_scan()

        elif choice == "5":
            report_einstellungen()

        elif choice == "6":
            break

        else:
            print("Ungültige Auswahl.")


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main_menu()
