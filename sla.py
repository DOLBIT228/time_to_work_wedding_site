"""Working-schedule configuration and SLA calculations."""

from __future__ import annotations

import os
from datetime import datetime, time, timedelta
from typing import Mapping, Any


DEFAULT_SCHEDULE = {
    "WORK_START": "11:00",
    "WORK_END": "19:00",
    "LUNCH_START": "14:00",
    "LUNCH_END": "15:00",
}


def parse_schedule_time(value: str | int) -> time:
    """Parse schedule time in ``HH`` or ``HH:MM`` format."""
    if isinstance(value, bool):
        raise ValueError("Schedule time must use HH or HH:MM format")

    raw_value = str(value).strip()
    for time_format in ("%H", "%H:%M"):
        try:
            return datetime.strptime(raw_value, time_format).time()
        except ValueError:
            continue

    raise ValueError(
        f"Invalid schedule time {value!r}; expected HH or HH:MM format"
    )


def load_work_schedule(
    secrets: Mapping[str, Any] | None = None,
) -> tuple[time, time, time, time]:
    """Load the work schedule, preferring environment variables to secrets."""
    if secrets is None:
        secrets = {}

    def get_value(name: str) -> Any:
        environment_value = os.environ.get(name)
        if environment_value is not None:
            return environment_value
        return secrets.get(name, DEFAULT_SCHEDULE[name])

    schedule = tuple(
        parse_schedule_time(get_value(name))
        for name in ("WORK_START", "WORK_END", "LUNCH_START", "LUNCH_END")
    )
    work_start, work_end, lunch_start, lunch_end = schedule

    if work_start >= work_end:
        raise ValueError("WORK_START must be earlier than WORK_END")
    if lunch_start >= lunch_end:
        raise ValueError("LUNCH_START must be earlier than LUNCH_END")

    return schedule


def calculate_working_minutes(
    start_dt: datetime,
    end_dt: datetime,
    work_start: time,
    work_end: time,
    lunch_start: time,
    lunch_end: time,
) -> int:
    """Return elapsed minutes inside work hours, excluding the lunch break."""
    if start_dt >= end_dt:
        return 0

    # Bitrix may return timezone-aware datetimes. The configured schedule denotes
    # local wall-clock time, matching the previous dashboard behaviour.
    start_dt = start_dt.replace(tzinfo=None)
    end_dt = end_dt.replace(tzinfo=None)
    total_minutes = 0.0
    current_day = start_dt.date()

    while current_day <= end_dt.date():
        day_start = datetime.combine(current_day, work_start)
        day_end = datetime.combine(current_day, work_end)
        actual_start = max(start_dt, day_start)
        actual_end = min(end_dt, day_end)

        if actual_start < actual_end:
            total_minutes += (actual_end - actual_start).total_seconds() / 60

            break_start = datetime.combine(current_day, lunch_start)
            break_end = datetime.combine(current_day, lunch_end)
            overlap_start = max(actual_start, break_start)
            overlap_end = min(actual_end, break_end)
            if overlap_start < overlap_end:
                total_minutes -= (
                    overlap_end - overlap_start
                ).total_seconds() / 60

        current_day += timedelta(days=1)

    return round(total_minutes)
