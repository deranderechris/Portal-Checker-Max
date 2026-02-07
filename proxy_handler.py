import os
import random

def load_proxies(path: str = "proxies.txt") -> list[str]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def choose_proxy(proxies: list[str]) -> dict | None:
    if not proxies:
        return None
    p = random.choice(proxies)
    if "@" in p:
        creds, host = p.split("@", 1)
        user, pwd = creds.split(":", 1)
        ip, port = host.split(":", 1)
        return {
            "server": f"http://{ip}:{port}",
            "username": user,
            "password": pwd,
        }
    else:
        ip, port = p.split(":", 1)
        return {"server": f"http://{ip}:{port}"}
