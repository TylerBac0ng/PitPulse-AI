"""FastF1 adapter — the ONLY module that imports fastf1.

Two retrieval paths, tried in order by the repository:

1. ``load_full_session``: FastF1 live-timing backend (lap/sector times, compounds,
   stints, car telemetry). Since 2026 the F1 live-timing archive requires an F1 account,
   so this path is only attempted when F1_USERNAME / F1_PASSWORD are configured or
   the archive is reachable without authentication.
2. ``load_timing_session``: FastF1's Ergast interface (Jolpica mirror). Real historical
   results, lap times, running positions and pit stops — but no tyre compounds,
   sector times or telemetry. The UI shows those as unavailable.

Both paths return the normalized ``SessionData`` model.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import date
from typing import Optional

from app.config import settings
from app.data.models import (
    Availability,
    DriverInfo,
    EventInfo,
    Lap,
    LapTelemetry,
    PitStop,
    SessionData,
)
from app.errors import DataSourceError, SessionUnavailableError, TelemetryUnavailableError

log = logging.getLogger("pitpulse.fastf1")

_fastf1 = None
_ergast = None
_live_ok: Optional[bool] = None
_live_checked_at = 0.0
_full_sessions: dict[str, object] = {}  # session key -> loaded fastf1 Session (for telemetry)


def _ff1():
    global _fastf1
    if _fastf1 is None:
        import fastf1  # local import keeps app start-up fast and isolates the dependency

        settings.fastf1_cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            fastf1.Cache.enable_cache(str(settings.fastf1_cache_dir))
        except Exception as exc:  # pragma: no cover - cache is an optimisation only
            log.warning("FastF1 cache unavailable: %s", exc)
        fastf1.set_log_level("ERROR")
        _fastf1 = fastf1
    return _fastf1


def _erg():
    global _ergast
    if _ergast is None:
        _ff1()
        from fastf1.ergast import Ergast

        _ergast = Ergast(result_type="raw", auto_cast=False, limit=100)
    return _ergast


# --------------------------------------------------------------------------- helpers

def parse_laptime(value: Optional[str]) -> Optional[float]:
    """'1:39.019' -> 99.019; '59.8' -> 59.8; invalid -> None."""
    if not value:
        return None
    try:
        parts = str(value).split(":")
        secs = 0.0
        for p in parts:
            secs = secs * 60 + float(p)
        return round(secs, 3)
    except ValueError:
        return None


def _td(value) -> Optional[float]:
    """pandas Timedelta / NaT -> seconds or None."""
    try:
        if value is None or value != value:  # NaN / NaT
            return None
        return round(value.total_seconds(), 3)
    except Exception:
        return None


def _int(value) -> Optional[int]:
    try:
        if value is None or value != value:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _code_from_ergast(driver: dict) -> str:
    code = driver.get("code")
    if code:
        return code
    return (driver.get("familyName") or driver.get("driverId", "UNK"))[:3].upper()


def live_timing_available() -> bool:
    """Probe the F1 live-timing archive (cached for 10 minutes)."""
    global _live_ok, _live_checked_at
    if os.getenv("F1_USERNAME") and os.getenv("F1_PASSWORD"):
        return True
    if settings.disable_fastf1_live:
        return False
    if _live_ok is not None and time.time() - _live_checked_at < 600:
        return _live_ok
    import requests

    try:
        r = requests.get("https://livetiming.formula1.com/static/2023/Index.json", timeout=5)
        _live_ok = r.status_code == 200
    except Exception:
        _live_ok = False
    _live_checked_at = time.time()
    return _live_ok


# --------------------------------------------------------------------------- events

def list_events(season: int) -> list[EventInfo]:
    try:
        sched = _erg().get_race_schedule(season)
    except Exception as exc:
        raise DataSourceError(
            f"Could not retrieve the {season} race calendar from the historical data service.",
            still_available="The seeded demo sessions are still available offline.",
            next_action="Choose the 'Demo' season, or check your internet connection and retry.",
        ) from exc
    today = date.today().isoformat()
    events = []
    for race in sched:
        race_date = race.get("date")
        if race_date and race_date > today:
            continue  # only completed (historical) events
        sessions = ["R", "Q"]
        events.append(
            EventInfo(
                season=str(season),
                round=int(race["round"]),
                name=race["raceName"],
                country=race.get("Circuit", {}).get("Location", {}).get("country"),
                circuit=race.get("Circuit", {}).get("circuitName"),
                date=race_date,
                sessions=sessions,
                source="ergast",
            )
        )
    return events


def list_drivers(season: int, rnd: int) -> list[DriverInfo]:
    try:
        res = _erg().get_race_results(season, rnd)
    except Exception as exc:
        raise DataSourceError(
            "Could not retrieve the driver list for this event.",
            still_available="The seeded demo sessions are still available offline.",
            next_action="Retry in a moment or choose the 'Demo' season.",
        ) from exc
    if not len(res) or not res[0].get("Results"):
        raise SessionUnavailableError(
            "No race results were published for this event.",
            still_available="Other events in this season may have data.",
            next_action="Pick a different event.",
        )
    return [_driver_from_result(r) for r in res[0]["Results"]]


def _driver_from_result(r: dict) -> DriverInfo:
    d = r["Driver"]
    millis = (r.get("Time") or {}).get("millis")
    return DriverInfo(
        code=_code_from_ergast(d),
        number=r.get("number") or d.get("permanentNumber"),
        name=f"{d.get('givenName', '')} {d.get('familyName', '')}".strip(),
        team=r.get("Constructor", {}).get("name"),
        grid=_int(r.get("grid")),
        position=_int(r.get("position")),
        status=r.get("status"),
        points=float(r["points"]) if r.get("points") else None,
        total_time_s=round(int(millis) / 1000, 3) if millis else None,
    )


# --------------------------------------------------------------------------- timing path

def _all_pages(first) -> list:
    pages = [first]
    cur = first
    guard = 0
    while not cur.is_complete and guard < 40:
        try:
            cur = cur.get_next_result_page()
        except ValueError:  # FastF1 signals the final page this way ("No more data after this response")
            break
        pages.append(cur)
        guard += 1
    return pages


def load_timing_session(season: int, rnd: int, session: str) -> SessionData:
    if session != "R":
        raise SessionUnavailableError(
            "Lap-by-lap qualifying data is not available from the historical timing service.",
            still_available="The Race session for this event is available.",
            next_action="Switch the Session selector to 'Race' and load again.",
            field="session",
        )
    erg = _erg()
    try:
        results = erg.get_race_results(season, rnd)
        if not len(results) or not results[0].get("Results"):
            raise SessionUnavailableError(
                "No race results were published for this event.",
                still_available="Other events in this season may have data.",
                next_action="Pick a different event.",
            )
        race = results[0]
        id_to_code = {r["Driver"]["driverId"]: _code_from_ergast(r["Driver"]) for r in race["Results"]}
        drivers = [_driver_from_result(r) for r in race["Results"]]

        lap_rows: dict[tuple[str, int], Lap] = {}
        for page in _all_pages(erg.get_lap_times(season, rnd)):
            for rp in page:
                for lap in rp.get("Laps", []):
                    n = int(lap["number"])
                    for t in lap.get("Timings", []):
                        code = id_to_code.get(t["driverId"], t["driverId"][:3].upper())
                        lap_rows[(code, n)] = Lap(
                            driver=code,
                            lap=n,
                            time_s=parse_laptime(t.get("time")),
                            position=_int(t.get("position")),
                        )
        pits: list[PitStop] = []
        for page in _all_pages(erg.get_pit_stops(season, rnd)):
            for rp in page:
                for p in rp.get("PitStops", []):
                    dur = parse_laptime(p.get("duration"))
                    pits.append(
                        PitStop(
                            driver=id_to_code.get(p["driverId"], p["driverId"][:3].upper()),
                            lap=int(p["lap"]),
                            stop=int(p["stop"]),
                            duration_s=dur if dur is not None and dur < 120 else None,
                        )
                    )
    except SessionUnavailableError:
        raise
    except Exception as exc:
        raise DataSourceError(
            "The historical timing service did not respond.",
            still_available="The seeded demo sessions are still available offline.",
            next_action="Retry in a moment, or choose the 'Demo' season to continue.",
        ) from exc

    if not lap_rows:
        raise SessionUnavailableError(
            "Lap timing has not been published for this event.",
            still_available="Race results exist, but there is nothing to chart.",
            next_action="Pick an earlier event or the 'Demo' season.",
        )

    # derive stints and pit flags from pit stops (stint n+1 starts the lap after stop n)
    by_driver_pits: dict[str, list[int]] = {}
    for p in pits:
        by_driver_pits.setdefault(p.driver, []).append(p.lap)
    for code, plist in by_driver_pits.items():
        plist.sort()
    for (code, n), lap in lap_rows.items():
        plist = by_driver_pits.get(code, [])
        stint = 1 + sum(1 for pl in plist if pl < n)
        lap.stint = stint
        lap.pit_in = n in plist
        lap.pit_out = (n - 1) in plist
        start = max([0] + [pl for pl in plist if pl < n])
        lap.tyre_life = n - start  # age within this stint (laps since the stint started)
    total_laps = max(n for _, n in lap_rows)
    event_name = race["raceName"]
    return SessionData(
        key=f"{season}-{rnd}-R",
        season=str(season),
        round=rnd,
        event_name=event_name,
        session="R",
        session_name="Race",
        circuit=race.get("Circuit", {}).get("circuitName"),
        date=race.get("date"),
        total_laps=total_laps,
        source="ergast",
        source_label="Historical timing · FastF1 Ergast interface (Jolpica)",
        is_demo=False,
        availability=Availability(lap_times=True, sectors=False, compounds=False, telemetry=False, positions=True),
        notes=[
            "Real historical results, lap times, positions and pit stops.",
            "Car telemetry, sector times and tyre compounds require the FastF1 live-timing archive, "
            "which needs F1 account credentials (F1_USERNAME / F1_PASSWORD). They are shown as unavailable.",
        ],
        drivers=drivers,
        laps=sorted(lap_rows.values(), key=lambda l: (l.driver, l.lap)),
        pit_stops=sorted(pits, key=lambda p: (p.driver, p.stop)),
    )


# --------------------------------------------------------------------------- full FastF1 path

def load_full_session(season: int, rnd: int, session: str) -> SessionData:
    """Full FastF1 load (requires live-timing archive access)."""
    ff1 = _ff1()
    try:
        s = ff1.get_session(season, rnd, session)
        s.load(laps=True, telemetry=True, weather=False, messages=False)
        laps_df = s.laps
    except Exception as exc:
        raise DataSourceError(
            "FastF1 could not load this session.",
            still_available="Historical timing or the demo dataset may still be used.",
            next_action="Retry, or continue with the available data source.",
        ) from exc
    if laps_df is None or laps_df.empty:
        raise DataSourceError("FastF1 returned no lap data for this session.")

    drivers: list[DriverInfo] = []
    for _, r in s.results.iterrows():
        color = r.get("TeamColor")
        drivers.append(
            DriverInfo(
                code=r["Abbreviation"],
                number=str(r.get("DriverNumber") or ""),
                name=r.get("FullName") or r["Abbreviation"],
                team=r.get("TeamName"),
                team_color=f"#{color}" if isinstance(color, str) and color else None,
                grid=_int(r.get("GridPosition")),
                position=_int(r.get("Position")),
                status=r.get("Status"),
                points=float(r["Points"]) if r.get("Points") == r.get("Points") else None,
                total_time_s=None,
            )
        )
    laps: list[Lap] = []
    pits: list[PitStop] = []
    for _, r in laps_df.iterrows():
        compound = r.get("Compound")
        compound = compound if compound in ("SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET") else None
        track_status = str(r.get("TrackStatus") or "1")
        lap = Lap(
            driver=r["Driver"],
            lap=int(r["LapNumber"]),
            time_s=_td(r.get("LapTime")),
            s1_s=_td(r.get("Sector1Time")),
            s2_s=_td(r.get("Sector2Time")),
            s3_s=_td(r.get("Sector3Time")),
            compound=compound,
            stint=_int(r.get("Stint")),
            tyre_life=_int(r.get("TyreLife")),
            pit_in=_td(r.get("PitInTime")) is not None,
            pit_out=_td(r.get("PitOutTime")) is not None and int(r["LapNumber"]) > 1,
            position=_int(r.get("Position")),
            track_clear=set(track_status) <= {"1"},
        )
        laps.append(lap)
        if lap.pit_in and session == "R":
            n_prev = sum(1 for p in pits if p.driver == lap.driver)
            pits.append(PitStop(driver=lap.driver, lap=lap.lap, stop=n_prev + 1))
    # race total time from cumulative lap times of classified finishers
    for d in drivers:
        if d.status == "Finished" or (d.status or "").startswith("+"):
            ts = [l.time_s for l in laps if l.driver == d.code]
            if ts and all(t is not None for t in ts):
                d.total_time_s = round(sum(ts), 3)
    key = f"{season}-{rnd}-{session}"
    _full_sessions[key] = s
    return SessionData(
        key=key,
        season=str(season),
        round=rnd,
        event_name=s.event["EventName"],
        session=session,
        session_name=s.name,
        circuit=s.event.get("Location"),
        date=str(s.event.get("EventDate", ""))[:10],
        total_laps=int(laps_df["LapNumber"].max()),
        source="fastf1",
        source_label="FastF1 · official F1 timing archive",
        availability=Availability(lap_times=True, sectors=True, compounds=True, telemetry=True, positions=session == "R"),
        notes=["Real historical timing and car telemetry loaded through FastF1."],
        drivers=drivers,
        laps=laps,
        pit_stops=pits,
    )


def get_lap_telemetry(session_key: str, driver: str, lap: int) -> LapTelemetry:
    s = _full_sessions.get(session_key)
    if s is None:
        raise TelemetryUnavailableError(
            "Telemetry for this session is no longer in memory.",
            still_available="Lap times and stints are still available.",
            next_action="Reload the session from the selection screen.",
        )
    try:
        lap_row = s.laps.pick_drivers(driver).pick_laps(lap).iloc[0]
        car = lap_row.get_car_data().add_distance()
    except Exception as exc:
        raise TelemetryUnavailableError(
            f"FastF1 has no car telemetry for {driver} lap {lap}.",
            still_available="Lap and sector times are still available.",
            next_action="Choose a different lap.",
        ) from exc
    if car is None or car.empty:
        raise TelemetryUnavailableError(f"FastF1 has no car telemetry for {driver} lap {lap}.")

    def col(name, scale=1.0):
        if name not in car:
            return None
        return [float(x) * scale if x == x else 0.0 for x in car[name].tolist()]

    t0 = car["Time"].iloc[0]
    return LapTelemetry(
        driver=driver,
        lap=lap,
        distance=[float(x) for x in car["Distance"].tolist()],
        speed=col("Speed"),
        throttle=col("Throttle"),
        brake=[100.0 if bool(b) else 0.0 for b in car["Brake"].tolist()] if "Brake" in car else None,
        rpm=col("RPM"),
        gear=col("nGear"),
        time=[(t - t0).total_seconds() for t in car["Time"].tolist()],
    )
