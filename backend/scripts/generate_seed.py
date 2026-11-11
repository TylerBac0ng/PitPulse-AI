"""Generate the seeded DEMO dataset (app/data/seed/demo_sessions.json).

The demo dataset is fictional and clearly labelled as DEMO data in the UI. It exists so
that the full PitPulse AI workflow can be demonstrated reliably offline, and as a
fallback when FastF1 / historical timing sources are unavailable.

Run from the backend folder:  python scripts/generate_seed.py
Output is deterministic: running it twice produces an identical file.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.data.demo_track import (  # noqa: E402
    CORNERS,
    TRACK_LENGTH_M,
    TRACK_NAME,
    DriverStyle,
    sector_times,
    synth_lap,
)

OUT = ROOT / "app" / "data" / "seed" / "demo_sessions.json"

COMPOUND_OFFSET = {"SOFT": -0.60, "MEDIUM": 0.0, "HARD": 0.45}
COMPOUND_DEG = {"SOFT": 0.085, "MEDIUM": 0.045, "HARD": 0.026}  # s per lap of tyre age
SOFT_CLIFF_AGE = 11  # soft tyres degrade faster beyond this age
FUEL_S_PER_LAP = 0.035
IN_LAP_LOSS = 4.8
OUT_LAP_LOSS = 17.4
LAP1_LOSS = 4.2

TEAMS = {
    "Apex Racing": "#34c8ff",
    "Vortex GP": "#ff9f43",
    "Meridian Motorsport": "#4fd1a1",
    "Corsa Nova": "#c38bff",
}

# code, number, name, team, base lap time (s), grid, strategy [(compound, laps)], dnf_lap, dnf_status
DRIVERS = [
    ("MOR", "4", "Alex Morgan", "Apex Racing", 92.10, 6, [("SOFT", 17), ("MEDIUM", 22), ("HARD", 13)], None, None),
    ("COS", "16", "Luca Costa", "Vortex GP", 92.02, 5, [("MEDIUM", 22), ("HARD", 30)], None, None),
    ("SAT", "22", "Naoki Sato", "Meridian Motorsport", 91.95, 2, [("SOFT", 14), ("HARD", 22), ("MEDIUM", 16)], None, None),
    ("CAR", "55", "Jordan Carter", "Corsa Nova", 92.30, 8, [("MEDIUM", 26), ("HARD", 26)], None, None),
    ("OKA", "7", "Rémi Okafor", "Apex Racing", 91.92, 1, [("SOFT", 12), ("MEDIUM", 21), ("MEDIUM", 19)], None, None),
    ("LIN", "31", "Elin Lindqvist", "Vortex GP", 92.25, 9, [("HARD", 30), ("MEDIUM", 22)], None, None),
    ("DUA", "11", "Mateo Duarte", "Meridian Motorsport", 92.18, 4, [("MEDIUM", 20), ("HARD", 32)], 44, "Gearbox"),
    ("BRE", "27", "Tom Brennan", "Corsa Nova", 92.40, 7, [("SOFT", 16), ("HARD", 36)], None, None),
]


def driver_style(code: str, team: str) -> DriverStyle:
    rng = random.Random(f"style-{code}")
    team_top = {"Apex Racing": 1.0, "Vortex GP": 3.5, "Meridian Motorsport": -1.0, "Corsa Nova": 2.0}[team]
    mods = tuple(round(rng.uniform(-3.5, 3.5), 2) for _ in CORNERS)
    return DriverStyle(corner_mods=mods, top_speed_mod=team_top)


def model_lap_time(base: float, compound: str, age: int, lap: int, total: int, rng: random.Random) -> float:
    t = base + COMPOUND_OFFSET[compound] + COMPOUND_DEG[compound] * age
    if compound == "SOFT" and age > SOFT_CLIFF_AGE:
        t += 0.035 * (age - SOFT_CLIFF_AGE) ** 2
    t += FUEL_S_PER_LAP * (total - lap)
    t += rng.gauss(0, 0.16)
    return t


def build_session(*, rnd: int, name: str, total_laps: int, limited: bool) -> dict:
    drivers_out, laps_out, pits_out, styles = [], [], [], {}
    cumulative: dict[str, list[float]] = {}
    for code, num, full, team, base, grid, strat, dnf_lap, dnf_status in DRIVERS:
        rng = random.Random(f"laps-{rnd}-{code}")
        style = driver_style(code, team)
        styles[code] = {"corner_mods": list(style.corner_mods), "top_speed_mod": style.top_speed_mod}
        # scale strategy to this session's lap count
        scale = total_laps / sum(n for _, n in strat)
        plan, acc = [], 0
        for i, (c, n) in enumerate(strat):
            length = round(n * scale) if i < len(strat) - 1 else total_laps - acc
            plan.append((c, length))
            acc += length
        last_lap = dnf_lap if (dnf_lap and dnf_lap <= total_laps) else total_laps
        lap_no, cum = 0, []
        total = 0.0
        for stint_idx, (compound, length) in enumerate(plan, start=1):
            for age in range(1, length + 1):
                lap_no += 1
                if lap_no > last_lap:
                    break
                lt = model_lap_time(base, compound, age, lap_no, total_laps, rng)
                pit_in = age == length and stint_idx < len(plan)
                pit_out = age == 1 and stint_idx > 1
                if lap_no == 1:
                    lt += LAP1_LOSS + (grid - 1) * 0.12
                if pit_in:
                    lt += IN_LAP_LOSS
                if pit_out:
                    lt += OUT_LAP_LOSS
                lt = round(lt, 3)
                tel = synth_lap(style, f"{rnd}-{code}-{lap_no}", lt)
                s1, s2, s3 = sector_times(tel)
                total += lt
                cum.append(total)
                hide_compound = limited and code in ("CAR", "LIN") and stint_idx == 2
                laps_out.append(
                    {
                        "driver": code,
                        "lap": lap_no,
                        "time_s": lt,
                        "s1_s": s1,
                        "s2_s": s2,
                        "s3_s": round(lt - s1 - s2, 3),
                        "compound": None if hide_compound else compound,
                        "stint": stint_idx,
                        "tyre_life": age,
                        "pit_in": pit_in,
                        "pit_out": pit_out,
                        "track_clear": True,
                    }
                )
                if pit_in:
                    pits_out.append(
                        {"driver": code, "lap": lap_no, "stop": stint_idx, "duration_s": round(20.6 + rng.uniform(0, 1.8), 2)}  # pit-lane time, like Ergast
                    )
        cumulative[code] = cum
        drivers_out.append(
            {
                "code": code,
                "number": num,
                "name": full,
                "team": team,
                "team_color": TEAMS[team],
                "grid": grid,
                "status": "Finished" if last_lap == total_laps else dnf_status,
                "total_time_s": round(total, 3) if last_lap == total_laps else None,
                "_laps_done": last_lap,
                "_total": total,
            }
        )

    # running positions per lap and classification
    for lap in range(1, total_laps + 1):
        running = [(c, cumulative[c][lap - 1]) for c in cumulative if len(cumulative[c]) >= lap]
        running.sort(key=lambda x: x[1])
        pos = {c: i + 1 for i, (c, _) in enumerate(running)}
        for l in laps_out:
            if l["lap"] == lap and l["driver"] in pos:
                l["position"] = pos[l["driver"]]
    drivers_out.sort(key=lambda d: (-d["_laps_done"], d["_total"]))
    points_table = [25, 18, 15, 12, 10, 8, 6, 4]
    for i, d in enumerate(drivers_out):
        d["position"] = i + 1
        d["points"] = float(points_table[i]) if d["status"] == "Finished" else 0.0
        d.pop("_laps_done")
        d.pop("_total")

    notes = ["Fictional demo session generated by scripts/generate_seed.py — not a real Formula 1 race."]
    if limited:
        notes.append("Car telemetry was intentionally withheld for this demo session.")
        notes.append("Tyre compound values are missing for some stints (shown as Unknown).")
    return {
        "key": f"demo-{rnd}-R",
        "season": "demo",
        "round": rnd,
        "event_name": name,
        "session": "R",
        "session_name": "Race",
        "circuit": TRACK_NAME,
        "date": "2026-01-01",
        "total_laps": total_laps,
        "source": "demo",
        "source_label": "Seeded demo data (fictional)",
        "is_demo": True,
        "availability": {
            "lap_times": True,
            "sectors": True,
            "compounds": True,
            "telemetry": not limited,
            "positions": True,
        },
        "notes": notes,
        "drivers": drivers_out,
        "laps": laps_out,
        "pit_stops": pits_out,
        "_styles": styles,
    }


def main() -> None:
    data = {
        "generated_by": "scripts/generate_seed.py",
        "track": {"name": TRACK_NAME, "length_m": TRACK_LENGTH_M},
        "sessions": [
            build_session(rnd=1, name="PitPulse Demo Grand Prix", total_laps=52, limited=False),
            build_session(rnd=2, name="Demo Grand Prix — Limited Data", total_laps=30, limited=True),
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
