"""Scraper configuration loaded from environment variables.

Trimmed version of Student Follow Up config — only schedule-relevant fields.
"""

from pydantic import Field
from pydantic_settings import BaseSettings


class ScraperConfig(BaseSettings):
    """Scraper configuration loaded from environment variables.

    Settings are loaded from environment variables with sensible defaults.
    For local development, create a .env file in the project root.
    """

    # SparkSource settings (browser-only ERP — no API exists)
    sparksource_url: str = Field(
        default="https://slc.sparksource.fr",
        description="SparkSource ERP URL",
    )
    sparksource_user: str = Field(
        default="",
        description="SparkSource username for Playwright login",
    )
    sparksource_pass: str = Field(
        default="",
        description="SparkSource password for Playwright login",
    )

    # Paths
    state_dir: str = Field(
        default="data/state",
        description="Directory for Playwright session state",
    )

    # Session settings
    max_session_age_hours: int = Field(
        default=24,
        description="Maximum age of Playwright session before re-authentication",
    )

    # Logging
    log_json: bool = Field(
        default=False,
        description="Output logs in JSON format (for production)",
    )
    log_level: str = Field(
        default="INFO",
        description="Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )

    # Optional CSS selectors (override for different SparkSource layouts)
    sparksource_user_selector: str = Field(
        default=".user-profile",
        description="CSS selector for authenticated user indicator",
    )
    sparksource_username_selector: str = Field(
        default="#username",
        description="CSS selector for username input on login page",
    )
    sparksource_password_selector: str = Field(
        default="#password",
        description="CSS selector for password input on login page",
    )
    sparksource_submit_selector: str = Field(
        default="button[type=submit]",
        description="CSS selector for login submit button",
    )

    model_config = {
        "env_prefix": "",
        "case_sensitive": False,
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# Singleton pattern
_config: ScraperConfig | None = None


def get_config() -> ScraperConfig:
    """Get the scraper configuration singleton.

    Returns:
        ScraperConfig: Scraper configuration instance
    """
    global _config
    if _config is None:
        _config = ScraperConfig()
    return _config
