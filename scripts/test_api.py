"""
Diagnostic script — tests the real BaillConnect API locally.
Usage: python scripts/test_api.py

Reads credentials from .env file (copy .env.example → .env and fill in).
"""
import asyncio
import os
import sys
from pathlib import Path

# Allow importing the custom component without HA installed
sys.path.insert(0, str(Path(__file__).parent.parent))

import aiohttp
from bs4 import BeautifulSoup

# ── Load .env ────────────────────────────────────────────────────────────────
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

EMAIL    = os.environ.get("BAILLCONNECT_EMAIL", "")
PASSWORD = os.environ.get("BAILLCONNECT_PASSWORD", "")
REGULATION_ID = int(os.environ.get("BAILLCONNECT_REGULATION_ID", "0"))

BASE_URL  = "https://www.baillconnect.com"
LOGIN_URL = f"{BASE_URL}/login"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}


def ok(msg):  print(f"  ✓ {msg}")
def err(msg): print(f"  ✗ {msg}")
def info(msg): print(f"  → {msg}")


async def step_fetch_homepage(session: aiohttp.ClientSession) -> str | None:
    print("\n[1] GET homepage — looking for CSRF token")
    async with session.get(BASE_URL, headers=BROWSER_HEADERS, allow_redirects=True) as r:
        info(f"Status: {r.status}  URL: {r.url}")
        html = await r.text()

    soup = BeautifulSoup(html, "html.parser")
    meta = soup.find("meta", attrs={"name": "csrf-token"})
    if meta and meta.get("content"):
        token = str(meta["content"])
        ok(f"CSRF token found (len={len(token)}): {token[:20]}…")
        return token
    else:
        err("No CSRF meta tag found on homepage")
        # Show all meta tags to help debug
        for m in soup.find_all("meta"):
            info(f"  meta: {m.attrs}")
        return None


async def step_inspect_login_page(session: aiohttp.ClientSession) -> tuple[str | None, str | None]:
    """Try GET /login and inspect the form action + hidden CSRF."""
    print("\n[2] GET /login — inspecting form")
    async with session.get(LOGIN_URL, headers=BROWSER_HEADERS, allow_redirects=True) as r:
        info(f"Status: {r.status}  URL: {r.url}")
        if r.status != 200:
            err(f"/login returned {r.status} — skipping form inspection")
            return None, None
        html = await r.text()

    soup = BeautifulSoup(html, "html.parser")

    # Find login form action
    form = soup.find("form")
    action = None
    if form:
        action = form.get("action", LOGIN_URL)
        ok(f"Form found — action: {action}  method: {form.get('method', 'GET')}")
        for inp in form.find_all("input"):
            info(f"  input: name={inp.get('name')}  type={inp.get('type')}  value={inp.get('value', '')[:30]}")
    else:
        err("No <form> found on /login page")

    # CSRF from this page
    meta = soup.find("meta", attrs={"name": "csrf-token"})
    csrf = str(meta["content"]) if meta and meta.get("content") else None
    if csrf:
        ok(f"CSRF from /login page (len={len(csrf)}): {csrf[:20]}…")
    else:
        err("No CSRF token on /login page")

    return csrf, action


async def step_login(session: aiohttp.ClientSession, csrf: str, action: str) -> bool:
    print(f"\n[3] POST {action} — attempting login")
    payload = {"email": EMAIL, "password": PASSWORD, "_token": csrf}
    post_headers = {
        **BROWSER_HEADERS,
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": LOGIN_URL,
        "Origin": BASE_URL,
    }
    async with session.post(action, data=payload, headers=post_headers, allow_redirects=False) as r:
        info(f"Status: {r.status}")
        info(f"Location: {r.headers.get('Location', '-')}")
        info(f"Set-Cookie: {r.headers.get('Set-Cookie', '-')[:80]}")
        if r.status in (301, 302, 303, 307, 308):
            ok("Login redirect received — authentication likely successful")
            return True
        elif r.status == 200:
            html = await r.text()
            soup = BeautifulSoup(html, "html.parser")
            errors = soup.find_all(class_=lambda c: c and "error" in c.lower())
            for e in errors[:3]:
                err(f"Page error: {e.get_text(strip=True)[:100]}")
            err("Login returned 200 — credentials rejected or CSRF mismatch")
            return False
        else:
            body_preview = (await r.text())[:300]
            err(f"Unexpected status {r.status}")
            info(f"Body preview: {body_preview}")
            return False


async def step_fetch_regulation(session: aiohttp.ClientSession, csrf: str) -> None:
    if not REGULATION_ID:
        info("BAILLCONNECT_REGULATION_ID not set — skipping API test")
        return
    print(f"\n[4] POST /api-client/regulations/{REGULATION_ID} — fetching state")
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-CSRF-TOKEN": csrf,
    }
    url = f"{BASE_URL}/api-client/regulations/{REGULATION_ID}"
    async with session.post(url, json={}, headers=headers) as r:
        info(f"Status: {r.status}")
        if r.status == 200:
            data = await r.json()
            ok(f"State fetched — uc_mode={data.get('uc_mode')}  ui_fan={data.get('ui_fan')}  is_connected={data.get('is_connected')}")
            thermostats = data.get("thermostats", [])
            ok(f"Thermostats: {len(thermostats)}")
            for th in thermostats:
                info(f"  {th.get('key')} — {th.get('name')} — {th.get('temperature')}°C")
        else:
            body = await r.text()
            err(f"API returned {r.status}: {body[:200]}")


async def main():
    if not EMAIL or not PASSWORD:
        print("ERROR: Set BAILLCONNECT_EMAIL and BAILLCONNECT_PASSWORD in .env")
        sys.exit(1)

    print(f"Testing with account: {EMAIL}")

    jar = aiohttp.CookieJar()
    async with aiohttp.ClientSession(cookie_jar=jar) as session:

        # Step 1: CSRF from homepage
        csrf = await step_fetch_homepage(session)
        if not csrf:
            sys.exit(1)

        # Step 2: Inspect login page (may return 404 — not blocking)
        login_csrf, form_action = await step_inspect_login_page(session)
        # Prefer CSRF from login page if available
        if login_csrf:
            csrf = login_csrf
        action = form_action or LOGIN_URL

        # Step 3: Login
        logged_in = await step_login(session, csrf, action)
        if not logged_in:
            sys.exit(1)

        # Refresh CSRF after login
        async with session.get(BASE_URL, headers=BROWSER_HEADERS, allow_redirects=True) as r:
            html = await r.text()
            soup = BeautifulSoup(html, "html.parser")
            meta = soup.find("meta", attrs={"name": "csrf-token"})
            if meta and meta.get("content"):
                csrf = str(meta["content"])
                ok(f"Post-login CSRF refreshed (len={len(csrf)})")

        # Step 4: API
        await step_fetch_regulation(session, csrf)

    print("\nDone.")


if __name__ == "__main__":
    # aiodns requires SelectorEventLoop on Windows (default is ProactorEventLoop)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
