from urllib.parse import urlparse, urlunparse

def normalize_url(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    return urlunparse((parsed.scheme, netloc, parsed.path or "/", "", "", ""))
