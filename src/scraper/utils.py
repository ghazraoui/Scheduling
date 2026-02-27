"""Shared scraping utilities for resource blocking and read-only guardrails."""

from playwright.async_api import Page, Route

from src.scraper.logging import get_logger

log = get_logger(__name__)

BLOCKED_RESOURCE_TYPES: frozenset[str] = frozenset(
    {"image", "stylesheet", "font", "media", "other"}
)

# HTTP methods that modify server state — block these in read-only mode.
_BLOCKED_METHODS: frozenset[str] = frozenset({"POST", "PUT", "DELETE", "PATCH"})

# AJAX endpoints that are safe to POST even in read-only mode (read-only search calls).
WHITELISTED_AJAX_PATHS: frozenset[str] = frozenset(
    {
        "/student/student_search_ajax",
        "/ffdates/set_agenda",
    }
)


async def configure_page_for_scraping(page: Page, *, read_only: bool = False) -> None:
    """Set up a Playwright page for efficient scraping.

    Blocks unnecessary resource types (images, stylesheets, fonts, media)
    to reduce bandwidth and improve scraping speed (~10x faster).

    Args:
        page: Playwright Page instance.
        read_only: If True, also block POST/PUT/DELETE/PATCH requests
                   to prevent accidental data modification.
    """

    async def _block_resources(route: Route) -> None:
        request = route.request

        # Block mutating HTTP methods in read-only mode
        if read_only and request.method in _BLOCKED_METHODS:
            # Allow whitelisted AJAX endpoints (read-only POSTs like search)
            if any(path in request.url for path in WHITELISTED_AJAX_PATHS):
                await route.continue_()
                return
            log.warning(
                "blocked_mutating_request",
                method=request.method,
                url=request.url,
            )
            await route.abort("blockedbyclient")
            return

        if request.resource_type in BLOCKED_RESOURCE_TYPES:
            await route.abort()
        else:
            await route.continue_()

    await page.route("**/*", _block_resources)
    page.set_default_timeout(30000)
    page.set_default_navigation_timeout(30000)
