"""
Diagnostic script — tests the real BaillConnect API locally.
Usage: python scripts/test_api.py

Reads credentials from .env file (copy .env.example -> .env and fill in).

Login flow discovered:
  GET  /espaces              -> role-selection page
  GET  /client/connexion     -> login form with CSRF token
  POST /client/connexion     -> 302 redirect on success
  GET  /api-client/regulations/{id}  -> regulation state (JSON)
"""
import asyncio
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

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

EMAIL         = os.environ.get("BAILLCONNECT_EMAIL", "")
PASSWORD      = os.environ.get("BAILLCONNECT_PASSWORD", "")
REGULATION_ID = int(os.environ.get("BAILLCONNECT_REGULATION_ID", "0"))

BASE_URL     = "https://www.baillconnect.com"
LOGIN_URL    = f"{BASE_URL}/client/connexion"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}


def ok(msg):   print(f"  [OK] {msg}")
def err(msg):  print(f"  [ERR] {msg}")
def info(msg): print(f"  -> {msg}")


async def step_get_login_form(session: aiohttp.ClientSession) -> tuple[str | None, str, dict]:
    """GET /client/connexion, extract CSRF token and hidden form fields.
    Returns (csrf, form_action, hidden_fields).
    """
    print(f"\n[1] GET {LOGIN_URL} — fetching login form")
    async with session.get(LOGIN_URL, headers=BROWSER_HEADERS, allow_redirects=True) as r:
        info(f"Status: {r.status}  URL: {r.url}")
        if r.status != 200:
            err(f"Unexpected status {r.status}")
            return None, LOGIN_URL, {}
        html = await r.text()

    soup = BeautifulSoup(html, "html.parser")

    # CSRF from meta tag
    meta = soup.find("meta", attrs={"name": "csrf-token"})
    csrf = str(meta["content"]) if meta and meta.get("content") else None
    if csrf:
        ok(f"CSRF from meta tag (len={len(csrf)}): {csrf[:20]}...")

    # Find the login form
    form = soup.find("form")
    form_action = LOGIN_URL
    hidden_fields: dict = {}

    if form:
        raw_action = form.get("action", "")
        if raw_action.startswith("http"):
            form_action = raw_action
        elif raw_action.startswith("/"):
            form_action = f"{BASE_URL}{raw_action}"
        else:
            form_action = LOGIN_URL
        ok(f"Form found — action: {form_action}  method: {form.get('method', 'GET').upper()}")
        for inp in form.find_all("input"):
            name = inp.get("name", "")
            typ  = inp.get("type", "")
            val  = inp.get("value", "")
            info(f"  input: name={name}  type={typ}  value={val[:40]}")
            if typ == "hidden" and name:
                hidden_fields[name] = val
                if not csrf and ("token" in name.lower() or "csrf" in name.lower()):
                    csrf = val
                    ok(f"CSRF from hidden input '{name}': {csrf[:20]}...")
    else:
        err("No <form> found on login page")
        # Dump page text for diagnosis
        info(f"Page text: {soup.get_text(' ', strip=True)[:400]}")

    return csrf, form_action, hidden_fields


async def step_login(
    session: aiohttp.ClientSession,
    csrf: str,
    form_action: str,
    hidden_fields: dict,
) -> bool:
    print(f"\n[2] POST {form_action} — submitting credentials")
    payload = {
        **hidden_fields,
        "_token": csrf,
        "email": EMAIL,
        "password": PASSWORD,
    }
    parsed = urlparse(form_action)
    post_headers = {
        **BROWSER_HEADERS,
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": LOGIN_URL,
        "Origin": f"{parsed.scheme}://{parsed.netloc}",
    }

    async with session.post(form_action, data=payload, headers=post_headers, allow_redirects=False) as r:
        info(f"Status: {r.status}")
        location = r.headers.get("Location", "-")
        info(f"Location: {location}")
        cookie_header = r.headers.get("Set-Cookie", "-")
        info(f"Set-Cookie: {cookie_header[:80]}")

        if r.status in (301, 302, 303, 307, 308):
            ok(f"Redirect -> {location}")
            # Extract regulation ID from redirect URL if present
            m = re.search(r'/regulations/(\d+)', location)
            if m:
                reg_id = int(m.group(1))
                ok(f"Regulation ID discovered from redirect: {reg_id}")
                # Update global if not already set
                global REGULATION_ID
                if not REGULATION_ID:
                    REGULATION_ID = reg_id
            # Follow the redirect chain to reach the authenticated page
            await _follow_redirects(session, location, referer=form_action)
            return True

        elif r.status == 200:
            html = await r.text()
            soup = BeautifulSoup(html, "html.parser")
            # Look for error messages
            for sel in (".alert", ".error", ".invalid-feedback", '[class*="error"]', '[class*="alert"]'):
                for el in soup.select(sel)[:3]:
                    msg = el.get_text(strip=True)[:120]
                    if msg:
                        err(f"Form error: {msg}")
            err("Login returned 200 — credentials rejected or CSRF mismatch")
            return False

        else:
            body = (await r.text())[:300]
            err(f"Unexpected status {r.status}: {body}")
            return False


async def _follow_redirects(session: aiohttp.ClientSession, start_url: str, referer: str, max_hops: int = 8) -> str:
    """Follow redirect chain manually and log each hop."""
    url = start_url
    for hop in range(max_hops):
        if not url or url == "-":
            break
        if url.startswith("/"):
            parsed = urlparse(referer)
            url = f"{parsed.scheme}://{parsed.netloc}{url}"
        info(f"  hop {hop+1}: GET {url}")
        headers = {**BROWSER_HEADERS, "Referer": referer}
        async with session.get(url, headers=headers, allow_redirects=False) as r:
            next_loc = r.headers.get("Location", "-")
            info(f"    -> {r.status}  Location: {next_loc}")
            if r.status in (301, 302, 303, 307, 308) and next_loc != "-":
                referer = url
                url = next_loc
            else:
                ok(f"  Settled at: {url} (status={r.status})")
                return url
    return url


async def step_fetch_regulation(session: aiohttp.ClientSession, csrf: str) -> None:
    if not REGULATION_ID:
        info("BAILLCONNECT_REGULATION_ID not set — skipping API test")
        return
    print(f"\n[3] POST /api-client/regulations/{REGULATION_ID} — fetching state")
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
            raw = await r.json()
            # Response is wrapped: {"data": {...}}
            data = raw.get("data", raw)
            ok(f"State fetched -- uc_mode={data.get('uc_mode')}  ui_fan={data.get('ui_fan')}  is_connected={data.get('is_connected')}")
            thermostats = data.get("thermostats", [])
            ok(f"Thermostats: {len(thermostats)}")
            for th in thermostats:
                info(f"  {th.get('key')} -- {th.get('name')} -- {th.get('temperature')} degC")
        else:
            body = await r.text()
            err(f"API returned {r.status}: {body[:400]}")


async def main():
    if not EMAIL or not PASSWORD:
        print("ERROR: Set BAILLCONNECT_EMAIL and BAILLCONNECT_PASSWORD in .env")
        sys.exit(1)

    print(f"Testing with account: {EMAIL}")

    connector = aiohttp.TCPConnector(resolver=aiohttp.resolver.ThreadedResolver())
    jar = aiohttp.CookieJar()
    async with aiohttp.ClientSession(cookie_jar=jar, connector=connector) as session:

        # Step 1: Get login form + CSRF
        csrf, form_action, hidden_fields = await step_get_login_form(session)
        if not csrf:
            err("No CSRF token — cannot continue")
            sys.exit(1)

        # Step 2: Login
        logged_in = await step_login(session, csrf, form_action, hidden_fields)
        if not logged_in:
            sys.exit(1)

        # Refresh CSRF from baillconnect.com after login
        print(f"\n[+] Refreshing CSRF post-login...")
        async with session.get(BASE_URL, headers=BROWSER_HEADERS, allow_redirects=True) as r:
            info(f"Status: {r.status}  URL: {r.url}")
            html = await r.text()
            soup = BeautifulSoup(html, "html.parser")
            meta = soup.find("meta", attrs={"name": "csrf-token"})
            if meta and meta.get("content"):
                csrf = str(meta["content"])
                ok(f"Post-login CSRF refreshed (len={len(csrf)})")
            else:
                err("No CSRF token after login — may not be authenticated")

        # Step 3: API call
        await step_fetch_regulation(session, csrf)

    print("\nDone.")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
