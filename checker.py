import json
import os
import time
from urllib.parse import urlparse

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

DEFAULT_TIMEOUT = 10
REQUEST_RETRIES = 3
REQUEST_BACKOFF = 1.5
CHANNEL_CHECK_MAX_BYTES = 512 * 1024

def save_html(mode: str, portal_name: str, content: str):
    ensure_output_dirs()
    safe_name = f"{portal_name}_{mode}".replace(":", "_").replace("/", "_").replace("\\", "_")
    filename = safe_name + ".txt"
    path = os.path.join("ausgabe", mode, filename)

    if not content or content.strip() == "":
        content = "EMPTY: Portal lieferte keinen Inhalt"

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def save_combined(portal_name: str, sections: dict[str, str]):
    ensure_output_dirs()
    lines = ["Portal Report"]
    for title, body in sections.items():
        lines.append("")
        lines.append(f"[{title}]")
        lines.append(body)
    content = "\n".join(lines)
    path = os.path.join("ausgabe", "combined", f"{portal_name}_full.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _base_url(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"http://{url}")
    base = f"{parsed.scheme}://{parsed.netloc}"
    return base.rstrip("/")


def _host_from_url(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"http://{url}")
    return parsed.netloc


def safe_get(url: str,
             headers: dict | None = None,
             proxies: dict | None = None,
             timeout: int = DEFAULT_TIMEOUT,
             stream: bool = False,
             cookies: dict | None = None) -> tuple[requests.Response | None, str]:
    last_err = ""
    for attempt in range(REQUEST_RETRIES):
        try:
            r = requests.get(
                url,
                headers=headers,
                proxies=proxies,
                timeout=timeout,
                allow_redirects=True,
                stream=stream,
                cookies=cookies,
            )
            return r, ""
        except Exception as e:
            last_err = str(e)
            time.sleep(REQUEST_BACKOFF * (attempt + 1))
    return None, last_err


def build_proxy_dict(proxy_cfg: dict | None) -> dict | None:
    if not proxy_cfg:
        return None
    server = proxy_cfg.get("server", "")
    user = proxy_cfg.get("username")
    pwd = proxy_cfg.get("password")
    if user and pwd and "://" in server:
        parsed = urlparse(server)
        if parsed.hostname and parsed.port:
            netloc = f"{user}:{pwd}@{parsed.hostname}:{parsed.port}"
            server = f"{parsed.scheme}://{netloc}"
    return {"http": server, "https": server}


def load_credentials(path: str = "eingabe/credentials.txt") -> list[dict]:
    ensure_input_dir()
    if not os.path.exists(path):
        return []
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) == 4:
                kind, url, user, password = parts
                if kind.lower() == "xtream":
                    entries.append({"kind": "xtream", "url": url, "user": user, "password": password})
            elif len(parts) == 3:
                kind = parts[0].lower()
                if kind == "stalker":
                    _, url, mac = parts
                    entries.append({"kind": "stalker", "url": url, "mac": mac})
                elif kind == "xtream":
                    _, url, user = parts
                    entries.append({"kind": "xtream", "url": url, "user": user, "password": ""})
                else:
                    url, user, password = parts
                    entries.append({"kind": "xtream", "url": url, "user": user, "password": password})
            elif len(parts) == 2:
                url, mac = parts
                entries.append({"kind": "stalker", "url": url, "mac": mac})
    return entries


def _match_credentials(creds: list[dict], url: str, kind: str | None = None) -> list[dict]:
    host = _host_from_url(url)
    matches = []
    for c in creds:
        if kind and c.get("kind") != kind:
            continue
        if _host_from_url(c.get("url", "")) == host:
            matches.append(c)
    return matches


def _peek_stream_text(url: str, headers: dict, proxies: dict | None) -> tuple[str, str]:
    r, err = safe_get(url, headers=headers, proxies=proxies, timeout=DEFAULT_TIMEOUT, stream=True)
    if not r:
        return "", err
    chunks = []
    total = 0
    try:
        for chunk in r.iter_content(chunk_size=8192):
            if not chunk:
                continue
            chunks.append(chunk)
            total += len(chunk)
            if total >= CHANNEL_CHECK_MAX_BYTES:
                break
    finally:
        r.close()
    try:
        return b"".join(chunks).decode("utf-8", errors="ignore"), ""
    except Exception as e:
        return "", str(e)


def probe_xtream(base_url: str, creds: list[dict], proxies: dict | None) -> dict:
    info = {"detected": False, "channels_ok": None, "details": []}
    headers = build_headers(BROWSER_USER_AGENTS[0])

    endpoints = [
        f"{base_url}/player_api.php",
        f"{base_url}/get.php",
        f"{base_url}/xmltv.php",
    ]

    for ep in endpoints:
        r, err = safe_get(ep, headers=headers, proxies=proxies, timeout=DEFAULT_TIMEOUT)
        if not r:
            info["details"].append(f"XTREAM endpoint {ep} error: {err}")
            continue
        text = r.text or ""
        status = r.status_code
        lower = text.lower()
        if status in (200, 401, 403) and (
            "user_info" in lower or
            "server_info" in lower or
            "xtream" in lower or
            "#extm3u" in lower or
            "<tv" in lower
        ):
            info["detected"] = True
        info["details"].append(f"XTREAM endpoint {ep} status: {status}")

    cred_list = _match_credentials(creds, base_url, kind="xtream")
    if cred_list:
        c = cred_list[0]
        auth_url = f"{base_url}/player_api.php?username={c['user']}&password={c['password']}"
        r, err = safe_get(auth_url, headers=headers, proxies=proxies, timeout=DEFAULT_TIMEOUT)
        if r and r.text:
            try:
                payload = json.loads(r.text)
                if isinstance(payload, dict) and payload.get("user_info"):
                    info["detected"] = True
                    auth = payload.get("user_info", {}).get("auth")
                    info["details"].append(f"XTREAM auth: {auth}")
            except Exception:
                info["details"].append("XTREAM auth: invalid JSON")
        else:
            info["details"].append(f"XTREAM auth error: {err}")

        channels_url = (
            f"{base_url}/player_api.php?username={c['user']}&password={c['password']}&action=get_live_streams"
        )
        text, err = _peek_stream_text(channels_url, headers, proxies)
        if text:
            if "\"stream_id\"" in text or "\"name\"" in text:
                info["channels_ok"] = True
            else:
                info["channels_ok"] = False
        else:
            info["details"].append(f"XTREAM channel check error: {err}")

    else:
        info["details"].append("XTREAM creds: none")

    return info


def probe_stalker(base_url: str, creds: list[dict], proxies: dict | None) -> dict:
    info = {"detected": False, "channels_ok": None, "details": []}
    headers = build_headers(MAG_USER_AGENTS[0])
    headers["X-User-Agent"] = "Model: MAG254; Link: Ethernet"
    headers["Referer"] = f"{base_url}/c/"

    endpoints = [
        f"{base_url}/portal.php",
        f"{base_url}/stalker_portal/portal.php",
    ]

    for ep in endpoints:
        r, err = safe_get(ep, headers=headers, proxies=proxies, timeout=DEFAULT_TIMEOUT)
        if not r:
            info["details"].append(f"STALKER endpoint {ep} error: {err}")
            continue
        text = r.text or ""
        status = r.status_code
        lower = text.lower()
        if status in (200, 401, 403) and (
            "stalker" in lower or
            "ministra" in lower or
            "portal.php" in lower
        ):
            info["detected"] = True
        info["details"].append(f"STALKER endpoint {ep} status: {status}")

    cred_list = _match_credentials(creds, base_url, kind="stalker")
    if cred_list:
        mac = cred_list[0].get("mac", "")
        cookies = {"mac": mac, "stb_lang": "en", "timezone": "UTC"}
        handshake_url = f"{base_url}/portal.php?type=stb&action=handshake"
        r, err = safe_get(handshake_url, headers=headers, proxies=proxies, cookies=cookies)
        token = ""
        if r and r.text:
            try:
                payload = json.loads(r.text)
                token = payload.get("js", {}).get("token", "") if isinstance(payload, dict) else ""
                if token:
                    info["detected"] = True
                    info["details"].append("STALKER handshake: ok")
            except Exception:
                info["details"].append("STALKER handshake: invalid JSON")
        else:
            info["details"].append(f"STALKER handshake error: {err}")

        if token:
            auth_headers = dict(headers)
            auth_headers["Authorization"] = f"Bearer {token}"
            channels_url = f"{base_url}/portal.php?type=itv&action=get_all_channels"
            text, err = _peek_stream_text(channels_url, auth_headers, proxies)
            if text:
                if "\"id\"" in text or "\"name\"" in text:
                    info["channels_ok"] = True
                else:
                    info["channels_ok"] = False
            else:
                info["details"].append(f"STALKER channel check error: {err}")

    else:
        info["details"].append("STALKER creds: none")

    return info


def portal_info_check(url: str, proxies: dict | None) -> dict:
    creds = load_credentials()
    base_url = _base_url(url)
    xtream = probe_xtream(base_url, creds, proxies)
    stalker = probe_stalker(base_url, creds, proxies)

    summary_lines = [f"Base URL: {base_url}"]
    summary_lines.append(f"XTREAM detected: {xtream['detected']}")
    summary_lines.append(f"XTREAM channels ok: {xtream['channels_ok']}")
    summary_lines.append(f"STALKER detected: {stalker['detected']}")
    summary_lines.append(f"STALKER channels ok: {stalker['channels_ok']}")

    details = xtream["details"] + stalker["details"]
    if details:
        summary_lines.append("")
        summary_lines.extend(details)

    return {"summary": "\n".join(summary_lines)}


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

def requests_check(url: str, ua: str, proxies: dict | None = None) -> dict:
    res = {
        "status": "",
        "html": "",
        "headers": {},
        "cloudflare": False,
        "error": "",
    }
    try:
        headers = build_headers(ua)
        r, err = safe_get(url, headers=headers, proxies=proxies, timeout=DEFAULT_TIMEOUT)
        if not r:
            res["error"] = err
            return res
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
                    proxy_dict = build_proxy_dict(proxy_cfg)
                    r, err = safe_get(
                        url,
                        headers=build_headers(BROWSER_USER_AGENTS[0]),
                        proxies=proxy_dict,
                        timeout=DEFAULT_TIMEOUT,
                    )
                    if not r:
                        raise Exception(err)
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
        portal_info = portal_info_check(url, None)
        combined_sections["Portal-Info"] = portal_info["summary"]
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
                proxy_dict = build_proxy_dict(proxy_cfg)
                r, err = safe_get(
                    url,
                    headers=build_headers(BROWSER_USER_AGENTS[0]),
                    proxies=proxy_dict,
                    timeout=DEFAULT_TIMEOUT,
                )
                if not r:
                    raise Exception(err)
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

        portal_info = portal_info_check(url, None)
        combined_sections["Portal-Info"] = portal_info["summary"]
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
1) Nur Gesamt-Report (TXT)
2) Nur Detail-Reports (pro Modus, TXT)
3) Gesamt-Report + Detail-Reports (TXT)
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
