from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.microsoft import EdgeChromiumDriverManager
from webdriver_manager.firefox import GeckoDriverManager

from utils.cloudflare import detect_cloudflare

# Browser-Auswahl (D = Nutzer kann wählen)
BROWSER_CHOICE = "ask"   # "chrome", "edge", "firefox", "ask"


def _choose_browser() -> str:
    global BROWSER_CHOICE

    if BROWSER_CHOICE != "ask":
        return BROWSER_CHOICE

    print("""
Browser wählen:
1) Chrome
2) Edge
3) Firefox
""")
    choice = input("> ").strip()

    if choice == "1":
        BROWSER_CHOICE = "chrome"
    elif choice == "2":
        BROWSER_CHOICE = "edge"
    elif choice == "3":
        BROWSER_CHOICE = "firefox"
    else:
        BROWSER_CHOICE = "chrome"

    return BROWSER_CHOICE


def _build_driver(browser: str, headless: bool):
    if browser == "chrome":
        options = ChromeOptions()
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        service = ChromeService(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)

    if browser == "edge":
        options = EdgeOptions()
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        service = EdgeService(EdgeChromiumDriverManager().install())
        return webdriver.Edge(service=service, options=options)

    # Firefox
    options = FirefoxOptions()
    if headless:
        options.add_argument("-headless")
    service = FirefoxService(GeckoDriverManager().install())
    return webdriver.Firefox(service=service, options=options)


def browser_check(url: str,
                  proxy: dict | None = None,
                  cookies: list | None = None,
                  headless: bool = True) -> dict:

    result = {
        "status": "",
        "final_url": "",
        "html": "",
        "cloudflare": False,
        "redirects": 0,
        "headers": {},
        "error": "",
    }

    try:
        browser_name = _choose_browser()
        driver = _build_driver(browser_name, headless=headless)

        driver.get(url)

        result["final_url"] = driver.current_url
        html = driver.page_source
        result["html"] = html

        result["cloudflare"] = detect_cloudflare(html, {})

        if result["final_url"].rstrip("/") != url.rstrip("/"):
            result["redirects"] = 1

        if cookies is not None:
            cookies.extend(driver.get_cookies())

        driver.quit()

    except Exception as e:
        result["error"] = str(e)

    return result
