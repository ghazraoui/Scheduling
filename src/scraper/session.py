"""Playwright session management for SparkSource authentication.

SessionManager handles storage state persistence, session validation, and
authentication retry logic. This eliminates repeated logins and reduces CAPTCHA risk.
"""

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

from src.scraper.errors import AuthenticationError, TransientError
from src.scraper.logging import get_logger

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Page

logger = get_logger(__name__)


class SessionManager:
    """Manages Playwright authentication state persistence and validation.

    Saves browser storage state (cookies, localStorage) to disk after successful
    authentication and restores it on subsequent runs to avoid repeated logins.
    """

    def __init__(
        self, state_dir: str = "data/state", max_session_age_hours: int = 24
    ) -> None:
        """Initialize SessionManager.

        Args:
            state_dir: Directory to store session state files.
            max_session_age_hours: Maximum age of session before considering expired.
        """
        self.state_dir = Path(state_dir)
        self.state_file = self.state_dir / "sparksource_session.json"
        self.max_session_age_hours = max_session_age_hours

        # Create state directory if it doesn't exist
        self.state_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "session_manager_initialized",
            state_file=str(self.state_file),
            max_age_hours=max_session_age_hours,
        )

    def is_session_valid(self) -> bool:
        """Check if a saved session exists and is still fresh.

        Returns:
            True if session file exists and is younger than max_session_age_hours.
        """
        if not self.state_file.exists():
            logger.debug("session_check", result="missing", reason="file_not_found")
            return False

        # Check file age
        file_mtime = datetime.fromtimestamp(self.state_file.stat().st_mtime)
        age = datetime.now() - file_mtime
        max_age = timedelta(hours=self.max_session_age_hours)

        if age > max_age:
            logger.info(
                "session_check",
                result="expired",
                age_hours=age.total_seconds() / 3600,
                max_hours=self.max_session_age_hours,
            )
            return False

        logger.debug(
            "session_check",
            result="valid",
            age_hours=age.total_seconds() / 3600,
        )
        return True

    async def save_session(self, context: "BrowserContext") -> None:
        """Save browser context storage state to disk.

        Args:
            context: Playwright BrowserContext with active session.
        """
        await context.storage_state(path=str(self.state_file))
        logger.info("session_saved", path=str(self.state_file))

    async def create_authenticated_context(
        self, browser: "Browser"
    ) -> "BrowserContext":
        """Create browser context, restoring session if valid.

        Args:
            browser: Playwright Browser instance.

        Returns:
            BrowserContext with restored session or fresh context.
        """
        if self.is_session_valid():
            context = await browser.new_context(storage_state=str(self.state_file))
            logger.info(
                "context_created", type="restored", state_file=str(self.state_file)
            )
        else:
            context = await browser.new_context()
            logger.info("context_created", type="fresh", reason="no_valid_session")

        return context

    async def check_page_authenticated(self, page: "Page") -> bool:
        """Check if the current page indicates an authenticated session.

        This is a soft check - returns False if authentication indicators are missing.

        Args:
            page: Playwright Page to check.

        Returns:
            True if page appears to be authenticated, False otherwise.
        """
        # Check if we're on login page
        if "/login" in page.url.lower() or "/signin" in page.url.lower():
            logger.debug("auth_check", result="not_authenticated", reason="login_page")
            return False

        # Look for user indicator element (configurable selector)
        user_selector = os.getenv("SPARKSOURCE_USER_SELECTOR", ".user-profile")
        try:
            user_element = await page.query_selector(user_selector)
            if user_element:
                logger.debug(
                    "auth_check", result="authenticated", indicator=user_selector
                )
                return True
            else:
                logger.debug(
                    "auth_check",
                    result="not_authenticated",
                    reason="indicator_not_found",
                    selector=user_selector,
                )
                return False
        except Exception as e:
            logger.warning(
                "auth_check_error",
                error=str(e),
                selector=user_selector,
            )
            return False

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_fixed(5),
        retry=retry_if_exception_type(TransientError),
    )
    async def authenticate(self, page: "Page", username: str, password: str) -> None:
        """Authenticate to SparkSource and verify success.

        Retries on TransientError but fails fast on AuthenticationError.

        Args:
            page: Playwright Page to authenticate.
            username: SparkSource username.
            password: SparkSource password.

        Raises:
            AuthenticationError: If authentication fails (wrong credentials).
            TransientError: If network/temporary issues prevent authentication.
        """
        # Get configuration from environment
        login_url = os.getenv(
            "SPARKSOURCE_URL", "https://sparksource.example.com/login"
        )
        username_selector = os.getenv("SPARKSOURCE_USERNAME_SELECTOR", "#username")
        password_selector = os.getenv("SPARKSOURCE_PASSWORD_SELECTOR", "#password")
        submit_selector = os.getenv(
            "SPARKSOURCE_SUBMIT_SELECTOR", "button[type=submit]"
        )

        logger.info("authentication_started", url=login_url)

        try:
            # Navigate to login page
            await page.goto(login_url, wait_until="networkidle", timeout=30000)

            # Fill credentials
            await page.fill(username_selector, username)
            await page.fill(password_selector, password)

            # Submit form
            await page.click(submit_selector)

            # Wait for navigation away from login page
            await page.wait_for_url(
                lambda url: (
                    "/login" not in url.lower() and "/signin" not in url.lower()
                ),
                timeout=30000,
            )

            # Verify authentication succeeded
            if not await self.check_page_authenticated(page):
                logger.error("authentication_failed", reason="verification_failed")
                raise AuthenticationError(
                    "Authentication verification failed - may be invalid credentials"
                )

            logger.info("authentication_succeeded")

        except TimeoutError as e:
            logger.warning("authentication_timeout", error=str(e))
            raise TransientError(f"Authentication timed out: {e}") from e
        except AuthenticationError:
            # Re-raise without retry - wrong credentials won't fix on retry
            raise
        except Exception as e:
            logger.error("authentication_error", error=str(e), type=type(e).__name__)
            # Classify unknown errors as transient for safety (will retry)
            raise TransientError(f"Authentication failed: {e}") from e

    def clear_session(self) -> None:
        """Delete saved session state file.

        Useful for forcing fresh authentication or clearing expired sessions.
        """
        if self.state_file.exists():
            self.state_file.unlink()
            logger.info("session_cleared", path=str(self.state_file))
        else:
            logger.debug("session_clear_skipped", reason="file_not_found")
