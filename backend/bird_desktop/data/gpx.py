from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import gpxpy


@dataclass(frozen=True)
class GpxMatch:
    latitude: float
    longitude: float
    timestamp: str | None
    seconds_delta: float | None


class GpxService:
    @staticmethod
    def parse_photo_datetime(value: str | None) -> dt.datetime | None:
        if not value:
            return None

        normalized = value.strip().replace(":", "-", 2)
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                length = 19 if "%S" in fmt else 10
                parsed = dt.datetime.strptime(normalized[:length], fmt)
                return parsed.replace(tzinfo=dt.timezone.utc)
            except ValueError:
                continue

        return None


    @staticmethod
    def day_of_year(value: str | None) -> float:
        parsed = GpxService.parse_photo_datetime(value)
        if parsed is None:
            return float("nan")

        return float(parsed.timetuple().tm_yday)


    @staticmethod
    def match_many(paths: list[str | Path], photo_datetime: str | None, max_seconds_delta: float | None = None) -> GpxMatch | None:
        target = GpxService.parse_photo_datetime(photo_datetime)
        points = []
        for path in paths:
            points.extend(GpxService._points(path))

        if not points:
            return None

        if target is None:
            point = points[0]
            return GpxMatch(float(point.latitude), float(point.longitude), point.time.isoformat() if point.time else None, None)

        point = min(points, key=lambda item: GpxService._delta_seconds(item, target))
        seconds_delta = GpxService._delta_seconds(point, target)
        if seconds_delta == float("inf"):
            return None

        if max_seconds_delta is not None and seconds_delta > max_seconds_delta:
            return None

        return GpxMatch(float(point.latitude), float(point.longitude), point.time.isoformat() if point.time else None, seconds_delta if seconds_delta != float("inf") else None)


    @staticmethod
    def _points(path: str | Path):
        points = []
        with Path(path).open("r", encoding="utf-8") as handle:
            gpx = gpxpy.parse(handle)

        for track in gpx.tracks:
            for segment in track.segments:
                points.extend(segment.points)

        for route in gpx.routes:
            points.extend(route.points)

        return points


    @staticmethod
    def _delta_seconds(point, target: dt.datetime) -> float:
        if point.time is None:
            return float("inf")

        point_time = point.time if point.time.tzinfo else point.time.replace(tzinfo=dt.timezone.utc)
        return abs((point_time - target).total_seconds())
