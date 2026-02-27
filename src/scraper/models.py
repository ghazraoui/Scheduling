"""Pydantic models for schedule data.

All data structures use Pydantic v2 for validation, serialization, and type safety.
"""

from pydantic import BaseModel


class ScheduleEntry(BaseModel):
    """A single class entry from the daily schedule.

    Represents one booked time slot on the SparkSource schedule page at
    /ffdates/week/booking. Fields derived from td.booking-cell-reserved
    data attributes and content.
    """

    class_time: str  # "09:00-10:00" from data-activity_start/end
    activity_name: str  # Full name from title attr, e.g. "Echange 13", "A2"
    activity_code: str  # Short code from link text, e.g. "E13", "A2", "SCL"
    room: str | None = None  # Room name from crid->header mapping, e.g. "SFS7*"
    students_booked: int = 0  # From data-occupied attribute
    is_online: bool = False  # True if cell has "online-activity" CSS class
    activity_id: str | None = None  # data-asid for linking to attendee list
    teacher_name: str | None = None  # From teacher summary table mapping
