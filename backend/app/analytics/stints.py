"""Tyre / stint analytics.

Degradation is estimated with a deliberately simple, explainable method:

* Only clean laps are used (no lap 1, in/out laps, flagged laps or slow outliers).
* Each lap time is fuel-corrected by adding back an assumed fuel-burn gain of
  FUEL_S_PER_LAP seconds for every lap completed (cars get faster as fuel burns off).
* A straight line is fitted to fuel-corrected lap time vs tyre age within the stint.
  The slope (seconds lost per lap of tyre age) is the degradation rate.

This is a trend estimate from lap times only; it does not model tyre physics,
temperatures, traffic or driver management.
"""
from __future__ import annotations

from collections import Counter
from typing import Optional

from app.analytics.laps import clean_laps
from app.data.models import Lap, SessionData

FUEL_S_PER_LAP = 0.035
MIN_LAPS_FOR_FIT = 4
TREND_THRESHOLDS = (0.03, 0.08)  # s/lap: below = Stable, between = Moderate, above = Degrading


def linear_fit(xs: list[float], ys: list[float]) -> Optional[tuple[float, float]]:
    """Least-squares (intercept, slope); None if under-determined."""
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return my - slope * mx, slope


def fuel_corrected(lap: Lap) -> float:
    return lap.time_s + FUEL_S_PER_LAP * (lap.lap - 1)


def trend_label(slope: Optional[float]) -> str:
    if slope is None:
        return "Insufficient data"
    if slope < TREND_THRESHOLDS[0]:
        return "Stable"
    if slope < TREND_THRESHOLDS[1]:
        return "Moderate"
    return "Degrading"


def build_stints(session: SessionData, code: str) -> list[dict]:
    laps = session.laps_for(code)
    clean_ids = {l.lap for l in clean_laps(laps)}
    groups: dict[int, list[Lap]] = {}
    for l in laps:
        groups.setdefault(l.stint or 1, []).append(l)
    stints = []
    for idx in sorted(groups):
        g = sorted(groups[idx], key=lambda l: l.lap)
        compounds = [l.compound for l in g if l.compound and l.compound != "UNKNOWN"]
        compound = Counter(compounds).most_common(1)[0][0] if compounds else None
        clean = [l for l in g if l.lap in clean_ids]
        ages = [float(l.tyre_life if l.tyre_life is not None else (l.lap - g[0].lap + 1)) for l in clean]
        fit = linear_fit(ages, [fuel_corrected(l) for l in clean]) if len(clean) >= MIN_LAPS_FOR_FIT else None
        slope = round(fit[1], 4) if fit else None
        avg = round(sum(l.time_s for l in clean) / len(clean), 3) if clean else None
        early = [l.time_s for l in clean[:3]]
        late = [l.time_s for l in clean[-3:]]
        late_drop = round(sum(late) / len(late) - sum(early) / len(early), 3) if len(clean) >= 6 else None
        points = []
        if clean:
            base = fuel_corrected(clean[0])
            for l, age in zip(clean, ages):
                points.append({"age": int(age), "lap": l.lap, "delta_s": round(fuel_corrected(l) - base, 3), "time_s": l.time_s})
        ended_in_pit = g[-1].pit_in
        stints.append(
            {
                "stint": idx,
                "compound": compound,
                "compound_known": compound is not None,
                "start_lap": g[0].lap,
                "end_lap": g[-1].lap,
                "length": len(g),
                "start_tyre_age": g[0].tyre_life,
                "ended_with_pit": ended_in_pit,
                "pit_lap": g[-1].lap if ended_in_pit else None,
                "clean_laps": len(clean),
                "avg_pace_s": avg,
                "best_s": round(min(l.time_s for l in clean), 3) if clean else None,
                "deg_s_per_lap": slope,
                "late_stint_drop_s": late_drop,
                "trend": trend_label(slope),
                "points": points,
            }
        )
    return stints


def stint_insight(code: str, stints: list[dict]) -> str:
    fitted = [s for s in stints if s["deg_s_per_lap"] is not None]
    if not fitted:
        return (
            f"Not enough clean laps to estimate degradation for {code}. "
            "Stint lengths and pit laps are still shown."
        )
    worst = max(fitted, key=lambda s: s["deg_s_per_lap"])
    comp = worst["compound"].title() if worst["compound"] else "compound unknown"
    msg = (
        f"Stint {worst['stint']} ({comp}, laps {worst['start_lap']}–{worst['end_lap']}) shows the steepest trend at "
        f"+{worst['deg_s_per_lap']:.3f}s per lap of tyre age (fuel-corrected)."
    )
    if worst["trend"] == "Degrading" and worst["ended_with_pit"]:
        earlier = max(worst["start_lap"] + 2, worst["end_lap"] - 3)
        msg += f" Testing an earlier stop around lap {earlier}–{worst['end_lap'] - 1} in the Strategy Lab is a reasonable what-if."
    elif worst["trend"] != "Degrading":
        msg += " No stint shows strong degradation, so pit timing changes are likely to have a small effect."
    return msg
