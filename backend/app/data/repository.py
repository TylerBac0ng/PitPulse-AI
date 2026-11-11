"""Session repository: chooses a data source, applies fallback, and caches processed sessions.

Source order for a real season:  FastF1 full  ->  FastF1 Ergast timing  ->  seeded demo (fallback).
Processed sessions are cached in memory and as JSON files under cache/processed/, so a
session is only fetched and normalized once.
"""
from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from datetime import date
from typing import Optional

from pydantic import BaseModel

from app.config import settings
from app.data import fastf1_adapter, seed_adapter
from app.data.models import DriverInfo, EventInfo, LapTelemetry, SessionData
from app.errors import (
    AnalysisNotLoadedError,
    DataSourceError,
    InvalidSelectionError,
    PitPulseError,
    TelemetryUnavailableError,
)

log = logging.getLogger("pitpulse.repository")

FALLBACK_DEMO_ROUND = 1
SESSION_NAMES = {"R": "Race", "Q": "Qualifying"}


class Fallback(BaseModel):
    requested: str
    reason: str


class LoadResult(BaseModel):
    session: SessionData
    fallback: Optional[Fallback] = None
    cached: bool = False


class SessionRepository:
    def __init__(self, max_memory: int = 8) -> None:
        self._mem: "OrderedDict[str, SessionData]" = OrderedDict()
        self._max = max_memory
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ catalog
    def seasons(self) -> list[dict]:
        out = [{"season": "demo", "label": "Demo (offline)", "source": "demo"}]
        if not settings.offline:
            last = date.today().year
            for y in range(last, settings.first_season - 1, -1):
                out.append({"season": str(y), "label": str(y), "source": "historical"})
        return out

    def events(self, season: str) -> list[EventInfo]:
        if season == "demo":
            return seed_adapter.list_events()
        year = self._year(season)
        self._require_online()
        return fastf1_adapter.list_events(year)

    def drivers(self, season: str, rnd: int) -> list[DriverInfo]:
        if season == "demo":
            return seed_adapter.list_drivers(rnd)
        year = self._year(season)
        cached = self._get_cached(f"{season}-{rnd}-R")
        if cached:
            return cached.drivers
        self._require_online()
        return fastf1_adapter.list_drivers(year, rnd)

    # ------------------------------------------------------------------ sessions
    def load(self, season: str, rnd: int, session: str) -> LoadResult:
        if session not in SESSION_NAMES:
            raise InvalidSelectionError(
                f"Unknown session '{session}'.",
                still_available="Race sessions are supported for every event.",
                next_action="Choose Race or Qualifying.",
                field="session",
            )
        key = f"{season}-{rnd}-{session}"
        cached = self._get_cached(key)
        if cached:
            return LoadResult(session=cached, cached=True)

        if season == "demo":
            data = seed_adapter.load_session(rnd, session)
            self._put(data, persist=False)
            return LoadResult(session=data)

        year = self._year(season)
        reasons: list[str] = []
        if not settings.offline:
            if fastf1_adapter.live_timing_available():
                try:
                    data = fastf1_adapter.load_full_session(year, rnd, session)
                    self._put(data)
                    return LoadResult(session=data)
                except DataSourceError as exc:
                    reasons.append(exc.message)
                    log.warning("FastF1 full load failed for %s: %s", key, exc.__cause__ or exc)
            try:
                data = fastf1_adapter.load_timing_session(year, rnd, session)
                self._put(data)
                return LoadResult(session=data)
            except DataSourceError as exc:
                reasons.append(exc.message)
                log.warning("Historical timing load failed for %s: %s", key, exc.__cause__ or exc)
        else:
            reasons.append("Network data sources are disabled (offline mode).")

        # Fallback: the seeded demo session, visibly labelled as such.
        demo = seed_adapter.load_session(FALLBACK_DEMO_ROUND, "R")
        self._put(demo, persist=False)
        return LoadResult(
            session=demo,
            fallback=Fallback(
                requested=f"{season} round {rnd} · {SESSION_NAMES[session]}",
                reason=" ".join(reasons) or "Historical data could not be retrieved.",
            ),
        )

    def get(self, key: str) -> SessionData:
        data = self._get_cached(key)
        if data is None:
            raise AnalysisNotLoadedError(
                "This session has not been loaded yet (or the server was restarted).",
                still_available="All analysis screens work once a session is loaded.",
                next_action="Go back to session selection and click Load Analysis.",
            )
        return data

    def lap_telemetry(self, data: SessionData, driver: str, lap: int) -> LapTelemetry:
        if data.source == "demo":
            return seed_adapter.get_lap_telemetry(data.round, driver, lap)
        if data.source == "ergast" or not data.availability.telemetry:
            raise TelemetryUnavailableError(
                "Car telemetry is not available for this session.",
                still_available="Lap-time comparison, running positions, stints and the Strategy Lab still work.",
                next_action="Compare lap times below, or load the PitPulse Demo Grand Prix to explore the full telemetry view.",
            )
        try:
            return fastf1_adapter.get_lap_telemetry(data.key, driver, lap)
        except TelemetryUnavailableError:
            # session object may have been evicted (e.g. after restart): reload once via FastF1 cache
            fastf1_adapter.load_full_session(int(data.season), data.round, data.session)
            return fastf1_adapter.get_lap_telemetry(data.key, driver, lap)

    # ------------------------------------------------------------------ cache
    def _get_cached(self, key: str) -> Optional[SessionData]:
        with self._lock:
            if key in self._mem:
                self._mem.move_to_end(key)
                return self._mem[key]
        if key.startswith("demo-"):
            try:
                season, rnd, session = key.split("-")
                data = seed_adapter.load_session(int(rnd), session)
            except (PitPulseError, ValueError):
                return None
            self._put(data, persist=False)
            return data
        path = settings.processed_cache_dir / f"{key}.json"
        if path.exists():
            try:
                data = SessionData.model_validate_json(path.read_text(encoding="utf-8"))
            except Exception:
                log.warning("Discarding unreadable cache file %s", path)
                return None
            self._put(data, persist=False)
            return data
        return None

    def _put(self, data: SessionData, persist: bool = True) -> None:
        with self._lock:
            self._mem[data.key] = data
            self._mem.move_to_end(data.key)
            while len(self._mem) > self._max:
                self._mem.popitem(last=False)
        if persist:
            try:
                settings.processed_cache_dir.mkdir(parents=True, exist_ok=True)
                (settings.processed_cache_dir / f"{data.key}.json").write_text(data.model_dump_json(), encoding="utf-8")
            except OSError as exc:  # cache is best-effort
                log.warning("Could not write processed cache: %s", exc)

    def clear_memory(self) -> None:
        with self._lock:
            self._mem.clear()

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _year(season: str) -> int:
        try:
            year = int(season)
        except ValueError:
            raise InvalidSelectionError(
                f"'{season}' is not a valid season.",
                still_available="Seasons 2018 onwards and the Demo season are supported.",
                next_action="Pick a season from the list.",
                field="season",
            )
        if year < settings.first_season or year > date.today().year:
            raise InvalidSelectionError(
                f"Season {year} is outside the supported range.",
                still_available=f"Seasons {settings.first_season}–{date.today().year} and the Demo season are supported.",
                next_action="Pick a season from the list.",
                field="season",
            )
        return year

    @staticmethod
    def _require_online() -> None:
        if settings.offline:
            raise DataSourceError(
                "Historical data sources are disabled (offline mode).",
                still_available="The Demo season works fully offline.",
                next_action="Choose the 'Demo' season.",
            )


repository = SessionRepository()
