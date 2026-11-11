"""Lap-level analytics: clean-lap filtering, driver summaries and two-driver comparison."""
from __future__ import annotations

from statistics import median
from typing import Optional

from app.data.models import Lap, SessionData
from app.errors import InvalidSelectionError

OUTLIER_FACTOR = 1.07  # laps slower than 107% of the driver's median are treated as non-representative


def clean_laps(laps: list[Lap]) -> list[Lap]:
    """Representative racing laps: excludes lap 1, in/out laps, flagged laps and slow outliers."""
    timed = [l for l in laps if l.time_s is not None]
    if not timed:
        return []
    med = median(l.time_s for l in timed)
    return [
        l
        for l in timed
        if l.lap > 1 and not l.pit_in and not l.pit_out and l.track_clear and l.time_s <= med * OUTLIER_FACTOR
    ]


def require_driver(session: SessionData, code: Optional[str], field: str = "driver") -> str:
    if not code:
        raise InvalidSelectionError(
            "No driver was selected.",
            still_available="Every driver in the session can be analysed.",
            next_action="Choose a driver and try again.",
            field=field,
        )
    if session.driver(code) is None:
        raise InvalidSelectionError(
            f"Driver '{code}' did not take part in {session.event_name} {session.session_name}.",
            still_available=f"{len(session.drivers)} drivers are available for this session.",
            next_action="Pick a driver from the list.",
            field=field,
        )
    if not session.laps_for(code):
        raise InvalidSelectionError(
            f"{code} has no recorded laps in this session.",
            still_available="Other drivers in this session have lap data.",
            next_action="Pick a different driver.",
            field=field,
        )
    return code


def driver_summary(session: SessionData, code: str) -> dict:
    info = session.driver(code)
    laps = session.laps_for(code)
    timed = [l for l in laps if l.time_s is not None]
    clean = clean_laps(laps)
    best = min(timed, key=lambda l: l.time_s) if timed else None
    pits = sorted({p.lap for p in session.pit_stops if p.driver == code})
    if not pits:
        pits = [l.lap for l in laps if l.pit_in]
    total = info.total_time_s if info and info.total_time_s else None
    return {
        "code": code,
        "name": info.name if info else code,
        "team": info.team if info else None,
        "team_color": info.team_color if info else None,
        "grid": info.grid if info else None,
        "position": info.position if info else None,
        "status": info.status if info else None,
        "points": info.points if info else None,
        "laps_completed": len(laps),
        "best_lap": {"lap": best.lap, "time_s": best.time_s} if best else None,
        "avg_clean_pace_s": round(sum(l.time_s for l in clean) / len(clean), 3) if clean else None,
        "median_clean_pace_s": round(median(l.time_s for l in clean), 3) if clean else None,
        "clean_lap_count": len(clean),
        "pit_count": len(pits),
        "pit_laps": pits,
        "total_time_s": total,
    }


def lap_series(session: SessionData, codes: list[str]) -> list[dict]:
    """One row per lap with each driver's lap time, position, compound and pit/clean flags."""
    clean_sets = {c: {l.lap for l in clean_laps(session.laps_for(c))} for c in codes}
    by = {c: {l.lap: l for l in session.laps_for(c)} for c in codes}
    rows = []
    for n in range(1, session.total_laps + 1):
        row: dict = {"lap": n}
        for c in codes:
            l = by[c].get(n)
            row[c] = l.time_s if l else None
            row[f"{c}_pos"] = l.position if l else None
            row[f"{c}_compound"] = l.compound if l else None
            row[f"{c}_pit"] = bool(l and l.pit_in)
            row[f"{c}_clean"] = n in clean_sets[c]
        rows.append(row)
    return rows


def gap_series(session: SessionData, a: str, b: str) -> list[dict]:
    """Cumulative race-time gap per lap: positive = Driver A behind Driver B."""
    la = {l.lap: l.time_s for l in session.laps_for(a)}
    lb = {l.lap: l.time_s for l in session.laps_for(b)}
    ca = cb = 0.0
    out = []
    for n in range(1, session.total_laps + 1):
        if la.get(n) is None or lb.get(n) is None:
            break
        ca += la[n]
        cb += lb[n]
        out.append({"lap": n, "gap_s": round(ca - cb, 3)})
    return out


def compare_drivers(session: SessionData, a: str, b: str) -> dict:
    sa, sb = driver_summary(session, a), driver_summary(session, b)

    def diff(x, y):
        return round(x - y, 3) if x is not None and y is not None else None

    gaps = gap_series(session, a, b)
    # lap-by-lap: on laps where both drivers set a clean lap, who was faster?
    ca = {l.lap: l.time_s for l in clean_laps(session.laps_for(a))}
    cb = {l.lap: l.time_s for l in clean_laps(session.laps_for(b))}
    common = sorted(set(ca) & set(cb))
    a_faster = sum(1 for n in common if ca[n] < cb[n])
    finish_gap = None
    if sa["total_time_s"] and sb["total_time_s"]:
        finish_gap = diff(sa["total_time_s"], sb["total_time_s"])
    return {
        "best_lap_delta_s": diff(
            sa["best_lap"]["time_s"] if sa["best_lap"] else None, sb["best_lap"]["time_s"] if sb["best_lap"] else None
        ),
        "avg_pace_delta_s": diff(sa["avg_clean_pace_s"], sb["avg_clean_pace_s"]),
        "finish_gap_s": finish_gap,
        "position_delta": diff(sa["position"], sb["position"]),
        "common_clean_laps": len(common),
        "laps_a_faster": a_faster,
        "laps_b_faster": len(common) - a_faster,
        "max_gap": max(gaps, key=lambda g: abs(g["gap_s"])) if gaps else None,
        "gap_series": gaps,
    }
