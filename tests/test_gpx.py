from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import pytest

from bird_desktop.data.gpx import GpxService


@dataclass(frozen=True)
class Point:
    latitude: float
    longitude: float
    time: dt.datetime | None


def test_gpx_match_accepts_point_within_tolerance(monkeypatch: pytest.MonkeyPatch) -> None:
    target = dt.datetime(2026, 5, 23, 12, 0, 0, tzinfo=dt.timezone.utc)
    point = Point(45.5, -73.6, target + dt.timedelta(seconds=120))
    monkeypatch.setattr(GpxService, "_points", staticmethod(lambda _path: [point]))

    match = GpxService.match_many([Path("track.gpx")], "2026:05:23 12:00:00", 300)

    assert match is not None
    assert match.latitude == 45.5
    assert match.longitude == -73.6
    assert match.seconds_delta == 120


def test_gpx_match_rejects_point_outside_tolerance(monkeypatch: pytest.MonkeyPatch) -> None:
    target = dt.datetime(2026, 5, 23, 12, 0, 0, tzinfo=dt.timezone.utc)
    point = Point(45.5, -73.6, target + dt.timedelta(seconds=301))
    monkeypatch.setattr(GpxService, "_points", staticmethod(lambda _path: [point]))

    assert GpxService.match_many([Path("track.gpx")], "2026:05:23 12:00:00", 300) is None


def test_gpx_match_without_tolerance_keeps_nearest_point(monkeypatch: pytest.MonkeyPatch) -> None:
    target = dt.datetime(2026, 5, 23, 12, 0, 0, tzinfo=dt.timezone.utc)
    point = Point(45.5, -73.6, target + dt.timedelta(hours=3))
    monkeypatch.setattr(GpxService, "_points", staticmethod(lambda _path: [point]))

    match = GpxService.match_many([Path("track.gpx")], "2026:05:23 12:00:00")

    assert match is not None
    assert match.seconds_delta == 10800


def test_gpx_match_without_photo_time_uses_first_point(monkeypatch: pytest.MonkeyPatch) -> None:
    point = Point(45.5, -73.6, dt.datetime(2026, 5, 23, 12, 0, 0, tzinfo=dt.timezone.utc))
    monkeypatch.setattr(GpxService, "_points", staticmethod(lambda _path: [point]))

    match = GpxService.match_many([Path("track.gpx")], None, 1)

    assert match is not None
    assert match.seconds_delta is None
