"""Telemetry comparison for two laps.

Both laps are resampled onto a shared distance grid so the channels can be overlaid.
The running time delta (Driver A elapsed time minus Driver B elapsed time at the same
distance) shows where one driver gains or loses time; the lap is then split into equal
mini-sectors to rank the biggest gains and losses.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from app.data.models import Lap, LapTelemetry

CHANNELS = ("speed", "throttle", "brake", "rpm", "gear")
MAX_POINTS = 500
MINI_SECTORS = 20


def _resample(tel: LapTelemetry, grid: np.ndarray, name: str) -> Optional[np.ndarray]:
    values = getattr(tel, name)
    if not values or len(values) != len(tel.distance):
        return None
    d = np.asarray(tel.distance, dtype=float)
    v = np.asarray(values, dtype=float)
    if name == "gear":  # step channel: nearest previous sample
        idx = np.clip(np.searchsorted(d, grid, side="right") - 1, 0, len(v) - 1)
        return v[idx]
    return np.interp(grid, d, v)


def _elapsed(tel: LapTelemetry, grid: np.ndarray) -> Optional[np.ndarray]:
    if tel.time and len(tel.time) == len(tel.distance):
        return np.interp(grid, np.asarray(tel.distance), np.asarray(tel.time))
    if tel.speed:  # integrate distance / speed
        d = np.asarray(tel.distance)
        v = np.maximum(np.asarray(tel.speed) / 3.6, 1.0)
        dt = np.diff(d) / ((v[1:] + v[:-1]) / 2)
        t = np.concatenate([[0.0], np.cumsum(dt)])
        return np.interp(grid, d, t)
    return None


def _brake_zones(brake: Optional[np.ndarray]) -> Optional[int]:
    if brake is None:
        return None
    on = brake > 50
    return int(np.sum(on[1:] & ~on[:-1]) + (1 if on[0] else 0))


def _r(x, nd=3):
    return None if x is None else round(float(x), nd)


def compare_laps(tel_a: LapTelemetry, tel_b: LapTelemetry, lap_a: Lap, lap_b: Lap) -> dict:
    length = min(max(tel_a.distance), max(tel_b.distance))
    n = int(min(MAX_POINTS, max(50, length // 10)))
    grid = np.linspace(0.0, length, n)

    channels: dict[str, dict] = {}
    available: list[str] = []
    for name in CHANNELS:
        a = _resample(tel_a, grid, name)
        b = _resample(tel_b, grid, name)
        if a is not None and b is not None:
            channels[name] = {"a": [_r(x, 1) for x in a], "b": [_r(x, 1) for x in b]}
            available.append(name)

    ta, tb = _elapsed(tel_a, grid), _elapsed(tel_b, grid)
    delta = None
    mini: list[dict] = []
    if ta is not None and tb is not None:
        delta = ta - tb  # + = A behind at this distance
        # align end-of-lap delta with the official lap-time delta when both are known
        if lap_a.time_s and lap_b.time_s and ta[-1] > 0 and tb[-1] > 0:
            ta = ta * (lap_a.time_s / ta[-1])
            tb = tb * (lap_b.time_s / tb[-1])
            delta = ta - tb
        edges = np.linspace(0, n - 1, MINI_SECTORS + 1).astype(int)
        for i in range(MINI_SECTORS):
            s, e = edges[i], edges[i + 1]
            seg = float(delta[e] - delta[s])
            entry = {
                "index": i + 1,
                "start_m": _r(grid[s], 0),
                "end_m": _r(grid[e], 0),
                "delta_s": _r(seg),
            }
            if "speed" in channels:
                sa = np.asarray(channels["speed"]["a"][s : e + 1], dtype=float)
                sb = np.asarray(channels["speed"]["b"][s : e + 1], dtype=float)
                entry["min_speed_a"] = _r(sa.min(), 1)
                entry["min_speed_b"] = _r(sb.min(), 1)
            mini.append(entry)

    def stats(tel: LapTelemetry, key: str) -> dict:
        sp = _resample(tel, grid, "speed")
        th = _resample(tel, grid, "throttle")
        br = _resample(tel, grid, "brake")
        return {
            "top_speed": _r(sp.max(), 1) if sp is not None else None,
            "min_speed": _r(sp.min(), 1) if sp is not None else None,
            "avg_speed": _r(sp.mean(), 1) if sp is not None else None,
            "full_throttle_pct": _r(100 * np.mean(th >= 98), 1) if th is not None else None,
            "brake_zones": _brake_zones(br),
        }

    st_a, st_b = stats(tel_a, "a"), stats(tel_b, "b")

    def d(x, y, nd=3):
        return _r(x - y, nd) if x is not None and y is not None else None

    sectors = []
    for i, (xa, xb) in enumerate(((lap_a.s1_s, lap_b.s1_s), (lap_a.s2_s, lap_b.s2_s), (lap_a.s3_s, lap_b.s3_s)), 1):
        sectors.append({"sector": i, "a_s": xa, "b_s": xb, "delta_s": d(xa, xb)})

    losses = sorted([m for m in mini if m["delta_s"] is not None], key=lambda m: m["delta_s"], reverse=True)
    return {
        "distance": [_r(x, 0) for x in grid],
        "channels": channels,
        "available_channels": available,
        "missing_channels": [c for c in CHANNELS if c not in available],
        "delta": [_r(x) for x in delta] if delta is not None else None,
        "mini_sectors": mini,
        "biggest_losses_a": [m for m in losses[:3] if m["delta_s"] > 0.005],
        "biggest_gains_a": [m for m in reversed(losses[-3:]) if m["delta_s"] < -0.005],
        "metrics": {
            "lap_time_a": lap_a.time_s,
            "lap_time_b": lap_b.time_s,
            "lap_time_delta_s": d(lap_a.time_s, lap_b.time_s),
            "sectors": sectors,
            "a": st_a,
            "b": st_b,
            "top_speed_delta": d(st_a["top_speed"], st_b["top_speed"], 1),
            "min_speed_delta": d(st_a["min_speed"], st_b["min_speed"], 1),
        },
    }


def lap_only_comparison(lap_a: Lap, lap_b: Lap) -> dict:
    """Comparison values that need no telemetry (used when telemetry is unavailable)."""

    def d(x, y):
        return round(x - y, 3) if x is not None and y is not None else None

    return {
        "lap_time_a": lap_a.time_s,
        "lap_time_b": lap_b.time_s,
        "lap_time_delta_s": d(lap_a.time_s, lap_b.time_s),
        "sectors": [
            {"sector": i, "a_s": xa, "b_s": xb, "delta_s": d(xa, xb)}
            for i, (xa, xb) in enumerate(
                ((lap_a.s1_s, lap_b.s1_s), (lap_a.s2_s, lap_b.s2_s), (lap_a.s3_s, lap_b.s3_s)), 1
            )
        ],
    }


def telemetry_insight(result: dict, a: str, b: str) -> str:
    m = result["metrics"]
    parts = []
    if m.get("lap_time_delta_s") is not None:
        dd = m["lap_time_delta_s"]
        who, other = (a, b) if dd < 0 else (b, a)
        parts.append(f"{who} is {abs(dd):.3f}s faster than {other} over the lap.")
    secs = [s for s in m["sectors"] if s["delta_s"] is not None]
    if secs:
        worst = max(secs, key=lambda s: abs(s["delta_s"]))
        who = b if worst["delta_s"] > 0 else a
        parts.append(f"The biggest sector difference is Sector {worst['sector']} ({abs(worst['delta_s']):.3f}s to {who}).")
    if result.get("biggest_losses_a"):
        l0 = result["biggest_losses_a"][0]
        txt = f"{a} loses most between {int(l0['start_m'])}–{int(l0['end_m'])} m ({l0['delta_s']:+.3f}s)"
        if l0.get("min_speed_a") is not None:
            txt += f", with a minimum speed of {l0['min_speed_a']:.0f} vs {l0['min_speed_b']:.0f} km/h"
        parts.append(txt + ".")
    if result.get("biggest_gains_a"):
        g0 = result["biggest_gains_a"][0]
        parts.append(f"{a} gains most between {int(g0['start_m'])}–{int(g0['end_m'])} m ({g0['delta_s']:+.3f}s).")
    return " ".join(parts) or "Not enough data to describe the difference between these laps."
