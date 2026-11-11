"""Seeded demo dataset adapter (offline, deterministic, clearly labelled DEMO)."""
from __future__ import annotations

import json
from functools import lru_cache

from app.config import settings
from app.data.demo_track import DriverStyle, synth_lap
from app.data.models import DriverInfo, EventInfo, LapTelemetry, SessionData
from app.errors import SessionUnavailableError, TelemetryUnavailableError

DEMO_SEASON = "demo"


@lru_cache(maxsize=1)
def _raw() -> dict:
    return json.loads(settings.seed_file.read_text(encoding="utf-8"))


def _raw_session(rnd: int) -> dict:
    for s in _raw()["sessions"]:
        if s["round"] == rnd:
            return s
    raise SessionUnavailableError(
        f"Demo event #{rnd} does not exist.",
        still_available="The PitPulse Demo Grand Prix is always available.",
        next_action="Choose an event from the Event list.",
        field="event",
    )


def list_events() -> list[EventInfo]:
    return [
        EventInfo(
            season=DEMO_SEASON,
            round=s["round"],
            name=s["event_name"],
            circuit=s["circuit"],
            date=None,
            sessions=["R", "Q"],
            source="demo",
        )
        for s in _raw()["sessions"]
    ]


def list_drivers(rnd: int) -> list[DriverInfo]:
    return [DriverInfo(**d) for d in _raw_session(rnd)["drivers"]]


def load_session(rnd: int, session: str) -> SessionData:
    raw = _raw_session(rnd)
    if session != "R":
        raise SessionUnavailableError(
            "The demo dataset only includes the Race session.",
            still_available="The Race session for this demo event is fully available.",
            next_action="Switch the Session selector to 'Race' and load again.",
            field="session",
        )
    data = {k: v for k, v in raw.items() if not k.startswith("_")}
    return SessionData(**data)


def get_lap_telemetry(rnd: int, driver: str, lap: int) -> LapTelemetry:
    raw = _raw_session(rnd)
    if not raw["availability"]["telemetry"]:
        raise TelemetryUnavailableError(
            "Car telemetry is not available for this session.",
            still_available="Lap times, sector times, stints and the Strategy Lab still work.",
            next_action="Use the lap and sector comparison below, or load the PitPulse Demo Grand Prix for full telemetry.",
        )
    style_raw = raw["_styles"].get(driver)
    lap_row = next((l for l in raw["laps"] if l["driver"] == driver and l["lap"] == lap), None)
    if style_raw is None or lap_row is None or lap_row["time_s"] is None:
        raise TelemetryUnavailableError(
            f"No telemetry for {driver} on lap {lap}.",
            still_available="Other laps for this driver can be compared.",
            next_action="Pick a lap the driver completed.",
        )
    style = DriverStyle(corner_mods=tuple(style_raw["corner_mods"]), top_speed_mod=style_raw["top_speed_mod"])
    tel = synth_lap(style, f"{rnd}-{driver}-{lap}", lap_row["time_s"])
    return LapTelemetry(driver=driver, lap=lap, **tel)
