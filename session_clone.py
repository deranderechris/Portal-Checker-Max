import json
import os

def load_browser_cookies(path: str = "cookies.json") -> list:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
