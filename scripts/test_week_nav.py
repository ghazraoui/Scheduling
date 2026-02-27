"""Discover SparkSource week navigation mechanism.

Temporary test script — run with `--headed` to observe the browser.
Logs findings to stdout so we know how to implement --weeks N in the scraper.

Usage:
    python scripts/test_week_nav.py --headed
    python scripts/test_week_nav.py --headed --agenda private_english_lausanne
"""

import argparse
import asyncio
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.scraper.pages.schedule import AGENDA_IDS, DEFAULT_AGENDA, SchedulePage
from src.scraper.utils import WHITELISTED_AJAX_PATHS

BASE_URL = os.getenv("SPARKSOURCE_URL", "https://slc.sparksource.fr")
SPARKSOURCE_USER = os.getenv("SPARKSOURCE_USER", "")
SPARKSOURCE_PASS = os.getenv("SPARKSOURCE_PASS", "")
SESSION_PATH = Path("data/session/state.json")


def _log(msg: str) -> None:
    print(msg)


async def get_week_dates_from_dom(page) -> list[str]:
    """Read the date headers from tr.day-header th elements."""
    headers = page.locator("tr.day-header th")
    count = await headers.count()
    dates = []
    for i in range(count):
        text = (await headers.nth(i).text_content() or "").strip()
        if text:
            dates.append(text)
    return dates


async def main():
    parser = argparse.ArgumentParser(description="Discover SparkSource week navigation")
    parser.add_argument("--headed", action="store_true", help="Visible browser")
    parser.add_argument("--agenda", default=DEFAULT_AGENDA, help="Agenda key")
    args = parser.parse_args()

    _log(f"=== SparkSource Week Navigation Discovery ===")
    _log(f"Agenda: {args.agenda}")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not args.headed)

        context_kwargs = {}
        if SESSION_PATH.exists():
            _log(f"Loading session from {SESSION_PATH}")
            context_kwargs["storage_state"] = str(SESSION_PATH)

        context = await browser.new_context(**context_kwargs)
        page = await context.new_page()

        # --- Authenticate ---
        await page.goto(f"{BASE_URL}/login/show_login/true", wait_until="networkidle")
        if "launchpad" in page.url or "dashboard" in page.url.lower():
            _log("Logged in via saved session")
        else:
            if not SPARKSOURCE_USER or not SPARKSOURCE_PASS:
                _log("ERROR: No session and no credentials in .env")
                await browser.close()
                sys.exit(1)
            _log("Logging in...")
            await page.fill("#username", SPARKSOURCE_USER)
            await page.fill("#password", SPARKSOURCE_PASS)
            await page.click("button[type='submit']")
            await page.wait_for_load_state("networkidle", timeout=30000)
            SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
            await context.storage_state(path=str(SESSION_PATH))
            _log(f"Logged in — {page.url}")

        # --- Read-only guardrails ---
        _BLOCKED_METHODS = frozenset({"PUT", "DELETE", "PATCH"})

        async def _block_mutations(route):
            req = route.request
            if req.method in _BLOCKED_METHODS:
                _log(f"  [BLOCKED] {req.method} {req.url}")
                await route.abort("blockedbyclient")
            elif req.method == "POST" and not any(
                p in req.url for p in WHITELISTED_AJAX_PATHS
            ):
                _log(f"  [BLOCKED] POST {req.url}")
                await route.abort("blockedbyclient")
            else:
                await route.continue_()

        await page.route("**/*", _block_mutations)

        # --- Navigate to schedule page ---
        schedule_page = SchedulePage(page)
        await schedule_page.navigate(BASE_URL, agenda=args.agenda)

        _log(f"\nCurrent URL: {page.url}")

        # --- Log current week's date headers ---
        _log("\n--- STEP 1: Current week date headers ---")
        current_dates = await get_week_dates_from_dom(page)
        for d in current_dates:
            _log(f"  {d}")

        # --- Test 1: Check for navigation buttons/links ---
        _log("\n--- STEP 2: Looking for navigation elements ---")

        nav_selectors = [
            ("a.next", "a.next link"),
            ("a[rel='next']", "a[rel=next] link"),
            (".week-nav", ".week-nav container"),
            ("a.arrow-right", "a.arrow-right"),
            ("button.next", "button.next"),
            (".fc-next-button", "fullcalendar next"),
            ("a[href*='next']", "a with 'next' in href"),
            ("a.fa-chevron-right", "chevron right"),
            ("a.fa-arrow-right", "arrow right"),
            ("i.fa-chevron-right", "icon chevron right"),
            ("a:has(i.fa-chevron-right)", "link with chevron icon"),
            ("[class*='next']", "any element with 'next' in class"),
            ("[class*='forward']", "any element with 'forward' in class"),
            ("a[href*='/ffdates/']", "any links to /ffdates/"),
        ]

        for selector, desc in nav_selectors:
            try:
                count = await page.locator(selector).count()
                if count > 0:
                    _log(f"  FOUND: {desc} ({selector}) — {count} element(s)")
                    for i in range(min(count, 5)):
                        el = page.locator(selector).nth(i)
                        href = await el.get_attribute("href") or "(no href)"
                        text = (await el.text_content() or "").strip()[:50]
                        _log(f"    [{i}] href={href}  text={text!r}")
            except Exception as e:
                pass  # Selector not found

        # --- Test 2: Try URL-based navigation ---
        _log("\n--- STEP 3: Trying URL-based navigation ---")

        today = date.today()
        # Compute next Monday
        next_monday = today + timedelta(days=(7 - today.weekday()))
        next_monday_str = next_monday.strftime("%Y-%m-%d")

        # Try different URL patterns
        url_patterns = [
            f"{BASE_URL}/ffdates/week/booking/{next_monday_str}",
            f"{BASE_URL}/ffdates/week/booking?date={next_monday_str}",
            f"{BASE_URL}/ffdates/week/booking?start={next_monday_str}",
            f"{BASE_URL}/ffdates/week/booking/{next_monday.strftime('%d-%m-%Y')}",
        ]

        for url in url_patterns:
            _log(f"\n  Trying: {url}")
            try:
                resp = await page.goto(url, wait_until="networkidle", timeout=15000)
                status = resp.status if resp else "no response"
                _log(f"  Status: {status}")
                _log(f"  Final URL: {page.url}")

                # Check if week changed
                try:
                    await page.locator("table#week").wait_for(state="visible", timeout=5000)
                    new_dates = await get_week_dates_from_dom(page)
                    _log(f"  Date headers: {new_dates}")
                    if new_dates != current_dates:
                        _log(f"  >>> WEEK CHANGED! This URL pattern works. <<<")
                    else:
                        _log(f"  (same week — pattern may not work)")
                except Exception:
                    _log(f"  (schedule table not found)")
            except Exception as e:
                _log(f"  Error: {e}")

            # Navigate back to current week
            await schedule_page.navigate(BASE_URL, agenda=args.agenda)

        # --- Test 3: Check for form-based navigation ---
        _log("\n--- STEP 4: Looking for date/week forms ---")
        forms = page.locator("form")
        form_count = await forms.count()
        _log(f"  Found {form_count} forms on page")
        for i in range(form_count):
            form = forms.nth(i)
            action = await form.get_attribute("action") or "(no action)"
            method = await form.get_attribute("method") or "(no method)"
            inner = (await form.inner_html() or "")[:200]
            _log(f"  Form [{i}]: action={action} method={method}")
            if "date" in inner.lower() or "week" in inner.lower():
                _log(f"    >>> Contains date/week elements <<<")
                _log(f"    HTML: {inner[:200]}")

        # --- Summary ---
        _log("\n--- SUMMARY ---")
        _log("Check the output above to determine which navigation method works.")
        _log("The scraper will use whichever approach succeeded.")

        if args.headed:
            _log("\nBrowser is open for manual inspection. Press Ctrl+C to close.")
            try:
                await asyncio.sleep(300)  # Keep open 5 minutes
            except (KeyboardInterrupt, asyncio.CancelledError):
                pass

        await browser.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
