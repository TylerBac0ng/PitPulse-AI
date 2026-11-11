"""Normalized domain models shared by every data adapter.

Every adapter (FastF1, FastF1/Ergast timing, seeded demo) converts its raw data into
these models. The analytics and strategy layers only ever see these types, which keeps
FastF1-specific logic isolated inside the Data Access Layer.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

SourceKind = Literal["fastf1", "ergast", "demo"]
Compound = Literal["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET", "UNKNOWN"]

DRY_COMPOUNDS = ("SOFT", "MEDIUM", "HARD")


class EventInfo(BaseModel):
    season: str
    round: int
    name: str
    country: Optional[str] = None
    circuit: Optional[str] = None
    date: Optional[str] = None
    sessions: list[str] = Field(default_factory=lambda: ["R"])
    source: SourceKind


class DriverInfo(BaseModel):
    code: str
    number: Optional[str] = None
    name: str
    team: Optional[str] = None
    team_color: Optional[str] = None
    grid: Optional[int] = None
    position: Optional[int] = None
    status: Optional[str] = None
    points: Optional[float] = None
    total_time_s: Optional[float] = None


class Lap(BaseModel):
    driver: str
    lap: int
    time_s: Optional[float] = None
    s1_s: Optional[float] = None
    s2_s: Optional[float] = None
    s3_s: Optional[float] = None
    compound: Optional[Compound] = None
    stint: Optional[int] = None
    tyre_life: Optional[int] = None
    pit_in: bool = False
    pit_out: bool = False
    position: Optional[int] = None
    track_clear: bool = True  # False when a SC/VSC/flag affected the lap (if known)


class PitStop(BaseModel):
    driver: str
    lap: int
    stop: int
    duration_s: Optional[float] = None  # stationary/pit-lane time if the source provides it


class Availability(BaseModel):
    lap_times: bool = True
    sectors: bool = False
    compounds: bool = False
    telemetry: bool = False
    positions: bool = False


class SessionData(BaseModel):
    key: str
    season: str
    round: int
    event_name: str
    session: str  # "R" or "Q"
    session_name: str
    circuit: Optional[str] = None
    date: Optional[str] = None
    total_laps: int
    source: SourceKind
    source_label: str
    is_demo: bool = False
    availability: Availability
    notes: list[str] = Field(default_factory=list)
    drivers: list[DriverInfo]
    laps: list[Lap]
    pit_stops: list[PitStop] = Field(default_factory=list)

    def driver(self, code: str) -> Optional[DriverInfo]:
        return next((d for d in self.drivers if d.code == code), None)

    def laps_for(self, code: str) -> list[Lap]:
        return sorted((l for l in self.laps if l.driver == code), key=lambda l: l.lap)


class LapTelemetry(BaseModel):
    """Car telemetry for one lap, sampled along distance (metres)."""

    driver: str
    lap: int
    distance: list[float]
    speed: Optional[list[float]] = None
    throttle: Optional[list[float]] = None
    brake: Optional[list[float]] = None
    rpm: Optional[list[float]] = None
    gear: Optional[list[float]] = None
    time: Optional[list[float]] = None  # seconds since lap start, same length as distance
