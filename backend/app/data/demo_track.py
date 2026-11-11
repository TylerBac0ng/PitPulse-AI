"""Deterministic telemetry synthesizer for the seeded DEMO dataset.

This is NOT real Formula 1 data. It builds a plausible speed trace for a fictional
5.3 km circuit from a simple kinematic model (braking/acceleration envelopes around
corner apexes), scales it to the lap time stored in the seed file, and derives
throttle/brake/gear/RPM from the speed trace. The same inputs always produce the
same output, so the demo is fully reproducible.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

TRACK_NAME = "Harbor Park Circuit (fictional)"
TRACK_LENGTH_M = 5550.0
SECTOR_BOUNDS_M = (1700.0, 3550.0)  # end of S1, end of S2
STEP_M = 10.0
V_MAX_KMH = 328.0
BRAKE_MS2 = 34.0
ACCEL_MS2 = 5.5

# (apex distance m, apex speed km/h, name)
CORNERS: list[tuple[float, float, str]] = [
    (380, 95, "T1"),
    (620, 145, "T2"),
    (1050, 210, "T3"),
    (1500, 120, "T4"),
    (1900, 262, "T5"),
    (2350, 84, "T6"),
    (2800, 176, "T7"),
    (3150, 232, "T8"),
    (3600, 112, "T9"),
    (3950, 156, "T10"),
    (4500, 90, "T11"),
    (4900, 202, "T12"),
]

GEAR_BANDS = [0, 85, 125, 160, 195, 232, 268, 300, 400]  # km/h thresholds for gears 1..8


@dataclass(frozen=True)
class DriverStyle:
    corner_mods: tuple[float, ...]  # km/h added to each apex speed
    top_speed_mod: float  # km/h added to V_MAX


def _grid() -> list[float]:
    n = int(TRACK_LENGTH_M / STEP_M) + 1
    return [round(i * STEP_M, 1) for i in range(n)]


def _speed_profile(style: DriverStyle, rng: random.Random) -> list[float]:
    """Speed (m/s) at each grid point using corner envelopes (with lap wrap-around)."""
    vmax = (V_MAX_KMH + style.top_speed_mod + rng.uniform(-1.5, 1.5)) / 3.6
    apexes = []
    for i, (d, v, _) in enumerate(CORNERS):
        mod = style.corner_mods[i] if i < len(style.corner_mods) else 0.0
        apexes.append((d, (v + mod + rng.uniform(-1.2, 1.2)) / 3.6))
    out = []
    for d in _grid():
        v = vmax
        for ad, av in apexes:
            for shift in (-TRACK_LENGTH_M, 0.0, TRACK_LENGTH_M):
                a = ad + shift
                if d <= a:  # braking towards apex
                    v = min(v, math.sqrt(av * av + 2 * BRAKE_MS2 * (a - d)))
                else:  # accelerating out of apex
                    v = min(v, math.sqrt(av * av + 2 * ACCEL_MS2 * (d - a)))
        out.append(v)
    return out


def _integrate_time(dist: list[float], v: list[float]) -> list[float]:
    t = [0.0]
    for i in range(1, len(dist)):
        dv = (v[i] + v[i - 1]) / 2
        t.append(t[-1] + (dist[i] - dist[i - 1]) / max(dv, 1.0))
    return t


def synth_lap(style: DriverStyle, seed: str, target_lap_time_s: float) -> dict:
    """Return telemetry arrays for one lap whose integrated time equals target_lap_time_s."""
    rng = random.Random(seed)
    dist = _grid()
    v = _speed_profile(style, rng)
    t = _integrate_time(dist, v)
    k = t[-1] / target_lap_time_s  # scale speed so the lap time matches the seed data
    v = [x * k for x in v]
    t = [x / k for x in t]

    speed = [round(x * 3.6, 1) for x in v]
    throttle, brake, gear, rpm = [], [], [], []
    for i, s in enumerate(speed):
        nxt = speed[min(i + 1, len(speed) - 1)]
        if nxt < s - 0.4:  # decelerating -> braking
            throttle.append(0.0)
            brake.append(100.0)
        elif s >= max(speed) - 2 or nxt > s + 0.2:
            # accelerating: partial throttle right after the apex, then flat out
            near_apex = any(abs(dist[i] - (cd % TRACK_LENGTH_M)) < 70 for cd, _, _ in CORNERS)
            throttle.append(round(55.0 + rng.uniform(0, 10), 1) if near_apex else 100.0)
            brake.append(0.0)
        else:  # apex / maintenance throttle
            throttle.append(round(30.0 + rng.uniform(0, 8), 1))
            brake.append(0.0)
        g = 1
        for gi in range(1, 9):
            if s >= GEAR_BANDS[gi - 1]:
                g = gi
        g = min(g, 8)
        lo, hi = GEAR_BANDS[g - 1], GEAR_BANDS[g] if g < 8 else 345
        frac = max(0.0, min(1.0, (s - lo) / max(hi - lo, 1)))
        gear.append(float(g))
        rpm.append(round(7600 + frac * 4300 + rng.uniform(-60, 60)))
    return {
        "distance": dist,
        "speed": speed,
        "throttle": throttle,
        "brake": brake,
        "gear": gear,
        "rpm": [float(x) for x in rpm],
        "time": [round(x, 4) for x in t],
    }


def sector_times(tel: dict) -> tuple[float, float, float]:
    dist, t = tel["distance"], tel["time"]

    def t_at(d: float) -> float:
        for i in range(1, len(dist)):
            if dist[i] >= d:
                f = (d - dist[i - 1]) / (dist[i] - dist[i - 1])
                return t[i - 1] + f * (t[i] - t[i - 1])
        return t[-1]

    s1 = t_at(SECTOR_BOUNDS_M[0])
    s2 = t_at(SECTOR_BOUNDS_M[1]) - s1
    s3 = t[-1] - s1 - s2
    return round(s1, 3), round(s2, 3), round(s3, 3)
