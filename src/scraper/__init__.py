"""SparkSource schedule scraper for the Scheduling project.

Extracted from the Student Follow Up project — contains only the schedule-relevant
scraping code (SchedulePage, session management, models).
"""

from src.scraper.models import ScheduleEntry
from src.scraper.pages.schedule import DEFAULT_AGENDA, SchedulePage
from src.scraper.utils import WHITELISTED_AJAX_PATHS

__all__ = [
    "SchedulePage",
    "DEFAULT_AGENDA",
    "ScheduleEntry",
    "WHITELISTED_AJAX_PATHS",
]
