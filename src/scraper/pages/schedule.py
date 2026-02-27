"""SchedulePage - extracts daily class schedule from SparkSource.

Navigates to /ffdates/week/booking (weekly schedule view) and extracts
today's booked classes from the booking grid.

DOM structure (confirmed from recon 2026-02-23):
  table#week
    tr.day-header -> th per day ("Mon 23rd Feb.", "Tue 24th Feb.", ...)
    tr -> td per day, each containing a table.booking
      table.booking
        tr -> th.booking-header per room (SFS1*, SFS2*, ..., ATL1)
        tr -> td.timecol (time) + td.booking-cell-* per room
          td.booking-cell-reserved -> actual booked class

Each reserved cell has data attributes:
  data-activity_start, data-activity_end, data-occupied, data-asid, data-crid
  title="activity name", CSS class "online-activity" for virtual classes
  Content: <a>CODE</a> [count]

Agenda filter (select[name="set_agenda"]):
  POSTs to /ffdates/set_agenda to switch school/centre view.
  Key values: 17=SFS Lausanne, 18=ESA Lausanne, 12=SFS Geneva, etc.
"""

import re
from datetime import date, datetime, timedelta, timezone

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from src.scraper.errors import TransientError
from src.scraper.logging import get_logger
from src.scraper.models import ScheduleEntry

log = get_logger(__name__)

# Agenda IDs for the set_agenda dropdown (confirmed from recon 2026-02-25)
AGENDA_IDS: dict[str, str] = {
    # Method classes
    "sfs_lausanne": "17",
    "esa_lausanne": "18",
    "sfs_geneva": "12",
    "esa_geneva": "13",
    "sfs_fribourg": "20",
    "esa_fribourg": "21",
    "sfs_montreux": "33",
    "esa_montreux": "34",
    # Private / VIP — Lausanne (split by language)
    "private_english_lausanne": "57",
    "private_french_lausanne": "100",
    "private_german_lausanne": "101",
}

DEFAULT_AGENDA = "sfs_lausanne"


class SchedulePage:
    """Weekly schedule page at /ffdates/week/booking.

    Extracts booked class entries for a given date from the weekly booking grid.
    Supports agenda filtering to select a specific school/centre.
    """

    URL_PATH = "/ffdates/week/booking"

    # Selectors confirmed from recon (2026-02-23)
    SCHEDULE_TABLE = "table#week"
    RESERVED_CELL = "td.booking-cell-reserved"
    BOOKING_TABLE = "table.booking"
    BOOKING_HEADER = "th.booking-header span"
    TIMECOL = "td.timecol"
    AGENDA_SELECT = "select[name='set_agenda']"

    def __init__(self, page: Page) -> None:
        self.page = page

    async def navigate(self, base_url: str, *, agenda: str = DEFAULT_AGENDA) -> None:
        """Navigate to the weekly schedule page and select an agenda.

        Args:
            base_url: SparkSource base URL (e.g., https://slc.sparksource.fr).
            agenda: Agenda key from AGENDA_IDS (e.g., "sfs_lausanne").

        Raises:
            TransientError: If the page fails to load within timeout.
            ValueError: If the agenda key is not recognized.
        """
        agenda_id = AGENDA_IDS.get(agenda)
        if agenda_id is None:
            raise ValueError(
                f"Unknown agenda {agenda!r}. Valid: {list(AGENDA_IDS.keys())}"
            )

        url = f"{base_url}{self.URL_PATH}"
        try:
            await self.page.goto(url, wait_until="networkidle", timeout=30000)
            await self.page.locator(self.SCHEDULE_TABLE).wait_for(
                state="visible", timeout=15000
            )
        except PlaywrightTimeoutError:
            raise TransientError("Schedule page failed to load")

        # Select the correct agenda if not already active
        await self._select_agenda(agenda_id)

        log.info("schedule_page_navigated", url=url, agenda=agenda)

    async def _select_agenda(self, agenda_id: str) -> None:
        """Select an agenda in the dropdown if it's not already active.

        Reads the current selection, and if different, changes it and
        submits the form to reload the schedule for the chosen school/centre.
        """
        select = self.page.locator(self.AGENDA_SELECT)
        current = await select.input_value()

        if current == agenda_id:
            log.debug("agenda_already_selected", agenda_id=agenda_id)
            return

        # Change selection and submit the form
        await select.select_option(agenda_id)
        await self.page.locator(
            "form:has(select[name='set_agenda']) input[type='submit']"
        ).click()
        await self.page.wait_for_load_state("networkidle", timeout=30000)
        await self.page.locator(self.SCHEDULE_TABLE).wait_for(
            state="visible", timeout=15000
        )
        log.info("agenda_changed", agenda_id=agenda_id)

    async def navigate_to_week(self, base_url: str, target_date: date) -> None:
        """Navigate to the week containing the given date.

        Uses URL-based navigation: /ffdates/week/booking/YYYY/MM/DD/
        SparkSource shows the full Mon-Sat week that contains the given date,
        so any date within the target week works (not just Monday).

        Args:
            base_url: SparkSource base URL.
            target_date: Any date within the target week.
        """
        date_path = target_date.strftime("%Y/%m/%d")
        url = f"{base_url}{self.URL_PATH}/{date_path}/"
        try:
            await self.page.goto(url, wait_until="networkidle", timeout=30000)
            await self.page.locator(self.SCHEDULE_TABLE).wait_for(
                state="visible", timeout=15000
            )
        except PlaywrightTimeoutError:
            raise TransientError(f"Failed to navigate to week {date_path}")

        log.info("navigated_to_week", target_date=date_path, url=url)

    async def next_week(self, base_url: str) -> None:
        """Navigate to the next week from the currently displayed week.

        Reads the current week's dates from the DOM, computes next Monday,
        and navigates to that week via URL.

        Args:
            base_url: SparkSource base URL.
        """
        displayed = await self.get_displayed_week_dates()
        if not displayed:
            raise TransientError("Cannot determine current week — no date headers found")

        # Parse the last displayed date and add days to get next Monday
        last_date = date.fromisoformat(displayed[-1])
        # Next Monday = last_date + (7 - last_date.weekday()) days
        next_monday = last_date + timedelta(days=(7 - last_date.weekday()))
        await self.navigate_to_week(base_url, next_monday)

    async def get_displayed_week_dates(self) -> list[str]:
        """Read the currently displayed week's dates from the DOM.

        Parses the date headers (tr.day-header th) to extract YYYY-MM-DD dates.
        The th text format is like "Mon 23rd Feb." — we parse the date from
        the reserved cells' data-activity_start attributes instead for reliability.

        Returns:
            List of YYYY-MM-DD strings for the displayed week (Mon-Sat).
        """
        # Get unique dates from all reserved cells on the page
        cells = self.page.locator("td[data-activity_start]")
        count = await cells.count()

        dates: set[str] = set()
        for i in range(count):
            start = await cells.nth(i).get_attribute("data-activity_start") or ""
            if start and len(start) >= 10:
                dates.add(start[:10])  # Extract YYYY-MM-DD

        if dates:
            return sorted(dates)

        # Fallback: parse from header text (less reliable but works on empty weeks)
        # Headers like "Mon 23rd Feb.", "Tue 24th Feb."
        headers = self.page.locator("tr.day-header th")
        header_count = await headers.count()
        _log_dates: list[str] = []
        for i in range(header_count):
            text = (await headers.nth(i).text_content() or "").strip()
            if text:
                _log_dates.append(text)

        log.debug("displayed_week_headers", headers=_log_dates)
        # We can't reliably parse "Mon 23rd Feb." without the year,
        # so return empty and let the caller handle it
        return []

    async def _build_crid_to_room_map(self) -> dict[str, str]:
        """Build a mapping from crid (classroom resource ID) to room name.

        Reads the first table.booking header row to match column positions
        (crid values from first data row) to room names from th.booking-header.

        Returns:
            Dict mapping crid string to room name (e.g., {"48": "SFS1*"}).
        """
        first_table = self.page.locator(self.BOOKING_TABLE).first

        # Get room names from headers
        headers = first_table.locator(self.BOOKING_HEADER)
        header_count = await headers.count()
        room_names: list[str] = []
        for i in range(header_count):
            name = (await headers.nth(i).text_content() or "").strip()
            room_names.append(name)

        # Get crids from first data row (row after header)
        first_data_row = first_table.locator(f"tr:has({self.TIMECOL})").first
        data_cells = first_data_row.locator("td[data-crid]")
        cell_count = await data_cells.count()

        crid_to_room: dict[str, str] = {}
        for i in range(min(cell_count, len(room_names))):
            crid = await data_cells.nth(i).get_attribute("data-crid")
            if crid:
                crid_to_room[crid] = room_names[i]

        log.debug("crid_room_map", mapping=crid_to_room)
        return crid_to_room

    async def _fetch_teacher_names(self, asids: set[str]) -> dict[str, str]:
        """Fetch teacher names from activity session attendee pages.

        For each activity_id, fetches /ffdates/list_attendees/{asid}/ and
        extracts the teacher name from the metadata table. Uses the browser's
        native fetch() to share session cookies.

        Args:
            asids: Set of activity_id strings to look up.

        Returns:
            Dict mapping activity_id to teacher name
            (e.g., {"0879034": "Sofiane CHAOUCHE"}).
        """
        if not asids:
            return {}

        teacher_map: dict[str, str] = {}
        for asid in asids:
            try:
                html = await self.page.evaluate(
                    """async (path) => {
                        const r = await fetch(path);
                        return await r.text();
                    }""",
                    f"/ffdates/list_attendees/{asid}/",
                )
                # Teacher name is in: <span ...>Teacher</span></td><td>NAME</td>
                match = re.search(
                    r"Teacher</span>\s*</td>\s*<td[^>]*>([^<]+)</td>",
                    html,
                )
                if match:
                    teacher_map[asid] = match.group(1).strip()
            except Exception:
                log.debug("teacher_fetch_failed", asid=asid)
                continue

        log.debug("teacher_map", count=len(teacher_map))
        return teacher_map

    async def extract_today(self) -> list[ScheduleEntry]:
        """Extract today's booked class entries.

        Finds all td.booking-cell-reserved cells with today's date in
        data-activity_start and converts them to ScheduleEntry models.

        Returns:
            List of ScheduleEntry for today, sorted by start time.
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return await self.extract_date(today)

    async def extract_date(self, date_str: str) -> list[ScheduleEntry]:
        """Extract booked class entries for a specific date.

        Args:
            date_str: Date in YYYY-MM-DD format.

        Returns:
            List of ScheduleEntry for the given date, sorted by start time.
        """
        # Build room mapping
        crid_to_room = await self._build_crid_to_room_map()

        # Select all reserved cells for this date using attribute prefix selector
        selector = f'td.booking-cell-reserved[data-activity_start^="{date_str}"]'
        cells = self.page.locator(selector)
        total = await cells.count()

        if total == 0:
            log.info("schedule_empty", date=date_str)
            return []

        entries: list[ScheduleEntry] = []
        for i in range(total):
            cell = cells.nth(i)

            # Extract data attributes
            start = await cell.get_attribute("data-activity_start") or ""
            end = await cell.get_attribute("data-activity_end") or ""
            occupied = await cell.get_attribute("data-occupied") or "0"
            asid = await cell.get_attribute("data-asid") or ""
            title = await cell.get_attribute("title") or ""
            cell_id = await cell.get_attribute("id") or ""
            cell_class = await cell.get_attribute("class") or ""

            # Parse time range from start/end ("2026-02-23 09:00:00" -> "09:00")
            start_time = _parse_time(start)
            end_time = _parse_time(end)
            class_time = f"{start_time}-{end_time}" if start_time and end_time else ""

            if not class_time:
                continue

            # Extract activity code from link text
            link = cell.locator("a")
            link_count = await link.count()
            activity_code = ""
            if link_count > 0:
                activity_code = (await link.first.text_content() or "").strip()

            # Parse students booked
            try:
                students = int(occupied)
            except ValueError:
                students = 0

            # Determine room from crid (middle part of cell ID: date_crid_slot)
            crid = ""
            parts = cell_id.split("_")
            if len(parts) >= 2:
                crid = parts[1]
            room = crid_to_room.get(crid)

            # Check if online
            is_online = "online-activity" in cell_class

            entry = ScheduleEntry(
                class_time=class_time,
                activity_name=title,
                activity_code=activity_code,
                room=room,
                students_booked=students,
                is_online=is_online,
                activity_id=asid or None,
            )
            entries.append(entry)

        # Sort by start time
        entries.sort(key=lambda e: e.class_time)

        # Fetch teacher names from attendee pages and inject
        asids = {e.activity_id for e in entries if e.activity_id}
        if asids:
            teacher_map = await self._fetch_teacher_names(asids)
            for entry in entries:
                if entry.activity_id and entry.activity_id in teacher_map:
                    entry.teacher_name = teacher_map[entry.activity_id]

        log.info(
            "schedule_extracted",
            date=date_str,
            entries=len(entries),
        )
        return entries


def _parse_time(datetime_str: str) -> str:
    """Extract HH:MM from 'YYYY-MM-DD HH:MM:SS' string."""
    match = re.search(r"(\d{2}:\d{2})", datetime_str)
    return match.group(1) if match else ""
