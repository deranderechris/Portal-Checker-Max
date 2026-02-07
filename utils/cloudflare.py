def detect_cloudflare(html: str, headers: dict) -> bool:
    h = html.lower()
    if "cf-browser-verification" in h or "cloudflare" in h:
        return True
    server = headers.get("server", "").lower()
    if "cloudflare" in server:
        return True
    return False
