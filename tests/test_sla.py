from datetime import datetime, time

import pytest

from sla import calculate_working_minutes, load_work_schedule, parse_schedule_time


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("11", time(11, 0)),
        (11, time(11, 0)),
        ("11:00", time(11, 0)),
        ("11:30", time(11, 30)),
    ],
)
def test_parse_schedule_time_supports_hour_and_hour_minute(value, expected):
    assert parse_schedule_time(value) == expected


def test_environment_schedule_takes_priority_over_secrets(monkeypatch):
    monkeypatch.setenv("WORK_START", "12:30")

    schedule = load_work_schedule(
        {
            "WORK_START": "10:00",
            "WORK_END": "19",
            "LUNCH_START": "14",
            "LUNCH_END": "15:00",
        }
    )

    assert schedule == (time(12, 30), time(19), time(14), time(15))


def test_time_before_workday_is_excluded():
    assert working_minutes("2026-09-22 09:00", "2026-09-22 11:10") == 10


def test_lunch_break_is_excluded():
    assert working_minutes("2026-09-22 13:30", "2026-09-22 15:30") == 60


def test_deal_created_at_0959_and_taken_at_1120_has_20_working_minutes():
    assert working_minutes("2026-09-22 09:59", "2026-09-22 11:20") == 20


def test_time_after_workday_is_excluded():
    assert working_minutes("2026-09-22 18:50", "2026-09-22 20:00") == 10


def working_minutes(start, end):
    return calculate_working_minutes(
        datetime.strptime(start, "%Y-%m-%d %H:%M"),
        datetime.strptime(end, "%Y-%m-%d %H:%M"),
        time(11),
        time(19),
        time(14),
        time(15),
    )
