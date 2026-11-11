"""PitPulse AI — basic pit-strategy simulator (Assignment 2 MVP model).

Model (deterministic; identical inputs always give identical outputs)
--------------------------------------------------------------------
Every lap of a strategy plan is modelled as::

    lap_time = base[compound] + deg[compound] * tyre_age + curve[compound] * tyre_age²
               + wear_penalty(compound, tyre_age)
               - FUEL_S_PER_LAP * (lap - 1)
               + pit_loss            (only on the lap the car pits)

* ``base`` / ``deg`` come from a straight-line fit of the selected driver's own
  fuel-corrected clean laps on each compound (see analytics/stints.py).
* ``curve`` (accelerating wear) is only used when the data clearly supports it: a
  quadratic fit is accepted if there are at least QUAD_MIN_LAPS laps, the curvature is
  positive and it cuts the squared error by at least QUAD_MIN_IMPROVEMENT versus the line.
  Otherwise curve = 0 and the model is purely linear.
* Compounds the driver did not use borrow the field-median pace offset and degradation
  for that compound from other drivers in the same session; if that is not possible
  documented default assumptions are used (DEFAULT_OFFSET / DEFAULT_DEG).
* ``pit_loss`` is the driver's median measured pit loss: (in-lap + out-lap) minus two
  representative laps. Falls back to DEFAULT_PIT_LOSS_S.
* ``wear_penalty`` adds 0.04 s × (laps beyond recommended tyre life)² to represent a
  tyre "cliff"; the recommended life is the larger of a compound default and the
  longest stint seen on that compound in the session.

The actual strategy and the alternative are both run through the SAME model; the
reported gain/loss is the difference of the two modelled totals, and the alternative
race time is the driver's real race time plus that difference.

Not modelled: traffic, overtaking/track position, safety cars, tyre warm-up,
used tyre sets, weather or reliability. Results are estimates, not predictions.
"""
from __future__ import annotations

from statistics import median
from typing import Optional

import numpy as np
from pydantic import BaseModel, Field

from app.analytics.laps import clean_laps
from app.analytics.stints import FUEL_S_PER_LAP, build_stints, linear_fit
from app.data.models import DRY_COMPOUNDS, SessionData
from app.errors import StrategyValidationError

MODEL_VERSION = "pitpulse-strategy-mvp-1.0"
DEFAULT_PIT_LOSS_S = 22.0
DEFAULT_OFFSET = {"SOFT": -0.55, "MEDIUM": 0.0, "HARD": 0.45, "UNKNOWN": 0.0}
DEFAULT_DEG = {"SOFT": 0.085, "MEDIUM": 0.05, "HARD": 0.03, "UNKNOWN": 0.05}
DEFAULT_LIFE = {"SOFT": 20, "MEDIUM": 30, "HARD": 40, "UNKNOWN": 32}
WEAR_PENALTY_COEF = 0.04
MIN_STINT_LAPS = 3
DEG_BOUNDS = (0.0, 0.25)
CURVE_MAX = 0.02  # s per lap² — caps accelerating wear
QUAD_MIN_LAPS = 8
QUAD_MIN_IMPROVEMENT = 0.15
STRATEGY_TYPES = ("baseline", "undercut", "overcut")


class StrategyRequest(BaseModel):
    driver: str
    pit_laps: list[int] = Field(..., description="Laps on which the car pits (in-lap), ascending")
    compounds: Optional[list[str]] = Field(
        None, description="Compound for each stint (len = pits + 1). Defaults to the actual compounds."
    )
    strategy_type: str = "baseline"


# ----------------------------------------------------------------------------- model

class CompoundModel(BaseModel):
    compound: str
    base_s: float
    deg_s_per_lap: float
    curve_s_per_lap2: float = 0.0
    life_laps: int
    source: str  # "driver", "field", "default"


class DriverModel(BaseModel):
    driver: str
    total_laps: int
    compounds_known: bool
    pit_loss_s: float
    pit_loss_source: str
    compounds: dict[str, CompoundModel]
    actual_pit_laps: list[int]
    actual_compounds: list[str]
    assumptions: list[str]


def _fit_compound(session: SessionData, code: str, compound: Optional[str]) -> Optional[tuple[float, float, int, float]]:
    """Return (base, deg, n_laps, curve) from a driver's clean laps on a compound (None = all laps)."""
    laps = clean_laps(session.laps_for(code))
    if compound:
        laps = [l for l in laps if l.compound == compound]
    if len(laps) < 4:
        return None
    xs = [float(l.tyre_life or 1) for l in laps]
    ys = [l.time_s + FUEL_S_PER_LAP * (l.lap - 1) for l in laps]
    fit = linear_fit(xs, ys)
    if fit is None:
        return None
    base, deg = fit
    deg = min(max(deg, DEG_BOUNDS[0]), DEG_BOUNDS[1])
    # re-anchor intercept with the clipped slope so the model passes through the data mean
    base = sum(ys) / len(ys) - deg * (sum(xs) / len(xs))
    curve = 0.0
    if len(laps) >= QUAD_MIN_LAPS and len(set(xs)) >= 4:
        c2, c1, c0 = np.polyfit(xs, ys, 2)
        sse_lin = sum((y - (base + deg * x)) ** 2 for x, y in zip(xs, ys))
        sse_quad = sum((y - (c0 + c1 * x + c2 * x * x)) ** 2 for x, y in zip(xs, ys))
        if 0 < c2 <= CURVE_MAX and sse_lin > 0 and (sse_lin - sse_quad) / sse_lin >= QUAD_MIN_IMPROVEMENT:
            base, deg, curve = float(c0), float(c1), float(c2)
    return base, deg, len(laps), curve


def _pit_loss(session: SessionData, code: str) -> tuple[float, str]:
    laps = {l.lap: l for l in session.laps_for(code)}
    clean = clean_laps(list(laps.values()))
    if not clean:
        return DEFAULT_PIT_LOSS_S, "default"
    ref = median(l.time_s for l in clean)
    losses = []
    for l in laps.values():
        if l.pit_in and l.time_s is not None:
            out = laps.get(l.lap + 1)
            if out is not None and out.time_s is not None:
                loss = l.time_s + out.time_s - 2 * ref
                if 8.0 <= loss <= 45.0:  # ignore red-flag / drive-through anomalies
                    losses.append(loss)
    if losses:
        return round(median(losses), 2), "driver"
    return DEFAULT_PIT_LOSS_S, "default"


def build_model(session: SessionData, code: str) -> DriverModel:
    laps = session.laps_for(code)
    stints = build_stints(session, code)
    compounds_known = session.availability.compounds and all(s["compound"] for s in stints)
    total_laps = len(laps)
    actual_pits = [s["pit_lap"] for s in stints if s["pit_lap"]]
    assumptions = [
        f"Fuel effect: lap times improve by {FUEL_S_PER_LAP:.3f}s per lap as fuel burns off.",
        "Every stint starts on new tyres (tyre age 1).",
        f"Tyre cliff: +{WEAR_PENALTY_COEF}s × (laps beyond recommended life)² per lap.",
        "Degradation is a straight line per compound, plus an accelerating-wear term only where the lap data clearly shows one.",
        "Traffic, track position, safety cars and tyre warm-up are not modelled.",
    ]

    models: dict[str, CompoundModel] = {}
    if not compounds_known:
        fit = _fit_compound(session, code, None)
        if fit:
            base, deg, n, curve = fit
            src = "driver"
        else:
            base = median(l.time_s for l in laps if l.time_s) if any(l.time_s for l in laps) else 90.0
            deg, src, curve = DEFAULT_DEG["UNKNOWN"], "default", 0.0
        longest = max((s["length"] for s in stints), default=0)
        models["UNKNOWN"] = CompoundModel(
            compound="UNKNOWN", base_s=round(base, 4), deg_s_per_lap=round(deg, 4), curve_s_per_lap2=round(curve, 5),
            life_laps=max(DEFAULT_LIFE["UNKNOWN"], longest), source=src,
        )
        assumptions.insert(0, "Tyre compounds are unavailable for this session, so one generic tyre model is fitted to all stints; compound choice is disabled.")
        actual_compounds = ["UNKNOWN"] * len(stints)
    else:
        actual_compounds = [s["compound"] for s in stints]
        own = {c: _fit_compound(session, code, c) for c in set(actual_compounds)}
        # reference compound = the one with the most clean laps for this driver
        ref_c = max((c for c in own if own[c]), key=lambda c: own[c][2], default=None)
        if ref_c is None:
            base_ref = median(l.time_s for l in clean_laps(laps)) if clean_laps(laps) else 90.0
            ref_c = actual_compounds[0]
            own[ref_c] = (base_ref - DEFAULT_OFFSET.get(ref_c, 0.0), DEFAULT_DEG.get(ref_c, 0.05), 0, 0.0)
        field_fits: dict[str, dict[str, tuple[float, float, int, float]]] = {}
        for d in session.drivers:
            if d.code == code:
                continue
            for c in DRY_COMPOUNDS:
                f = _fit_compound(session, d.code, c)
                if f:
                    field_fits.setdefault(d.code, {})[c] = f
        field_stints = [s for d in session.drivers if d.code != code for s in build_stints(session, d.code)]
        for c in DRY_COMPOUNDS:
            longest = max((s["length"] for s in stints if s["compound"] == c), default=0)
            field_longest = max((s["length"] for s in field_stints if s["compound"] == c), default=0)
            life = max(DEFAULT_LIFE[c], longest, field_longest)
            if own.get(c):
                base, deg, _, curve = own[c]
                models[c] = CompoundModel(compound=c, base_s=round(base, 4), deg_s_per_lap=round(deg, 4),
                                          curve_s_per_lap2=round(curve, 5), life_laps=life, source="driver")
                continue
            # offset of compound c vs the reference compound across drivers who ran both
            offsets = [f[c][0] - f[ref_c][0] for f in field_fits.values() if c in f and ref_c in f]
            degs = [f[c][1] for f in field_fits.values() if c in f]
            if offsets and degs:
                models[c] = CompoundModel(
                    compound=c, base_s=round(own[ref_c][0] + median(offsets), 4),
                    deg_s_per_lap=round(median(degs), 4), life_laps=life, source="field",
                )
            else:
                models[c] = CompoundModel(
                    compound=c,
                    base_s=round(own[ref_c][0] + DEFAULT_OFFSET[c] - DEFAULT_OFFSET.get(ref_c, 0.0), 4),
                    deg_s_per_lap=DEFAULT_DEG[c], life_laps=life, source="default",
                )
        for c in set(actual_compounds) - set(models):  # e.g. INTERMEDIATE / WET stints
            fit = own.get(c)
            base, deg, curve = (fit[0], fit[1], fit[3]) if fit else (own[ref_c][0], DEFAULT_DEG["UNKNOWN"], 0.0)
            longest = max((s["length"] for s in stints if s["compound"] == c), default=0)
            models[c] = CompoundModel(compound=c, base_s=round(base, 4), deg_s_per_lap=round(deg, 4), curve_s_per_lap2=round(curve, 5),
                                      life_laps=max(DEFAULT_LIFE["UNKNOWN"], longest), source="driver" if fit else "default")
        for c, m in models.items():
            if m.source == "field":
                assumptions.append(f"{c.title()} pace/degradation borrowed from other drivers in this session (driver did not run it).")
            elif m.source == "default":
                assumptions.append(f"{c.title()} pace/degradation uses PitPulse default assumptions (no session data).")

    pit_loss, pit_src = _pit_loss(session, code)
    if pit_src == "default":
        assumptions.append(f"Pit loss uses a default of {DEFAULT_PIT_LOSS_S:.0f}s (could not be measured for this driver).")
    return DriverModel(
        driver=code,
        total_laps=total_laps,
        compounds_known=compounds_known,
        pit_loss_s=pit_loss,
        pit_loss_source=pit_src,
        compounds=models,
        actual_pit_laps=actual_pits,
        actual_compounds=actual_compounds,
        assumptions=assumptions,
    )


# ----------------------------------------------------------------------------- simulation

def _plan_stints(pit_laps: list[int], compounds: list[str], total: int) -> list[dict]:
    bounds = [0] + pit_laps + [total]
    return [
        {"stint": i + 1, "compound": compounds[i], "start_lap": bounds[i] + 1, "end_lap": bounds[i + 1],
         "length": bounds[i + 1] - bounds[i]}
        for i in range(len(bounds) - 1)
    ]


def _simulate(model: DriverModel, stints: list[dict]) -> tuple[float, list[float], list[dict]]:
    lap_times: list[float] = []
    out = []
    for s in stints:
        cm = model.compounds[s["compound"]]
        t_stint = 0.0
        for age, lap in enumerate(range(s["start_lap"], s["end_lap"] + 1), start=1):
            t = cm.base_s + cm.deg_s_per_lap * age + cm.curve_s_per_lap2 * age * age - FUEL_S_PER_LAP * (lap - 1)
            if age > cm.life_laps:
                t += WEAR_PENALTY_COEF * (age - cm.life_laps) ** 2
            if lap == s["end_lap"] and lap != model.total_laps:
                t += model.pit_loss_s
            lap_times.append(t)
            t_stint += t
        out.append({**s, "modelled_time_s": round(t_stint, 3), "over_life_laps": max(0, s["length"] - cm.life_laps),
                    "life_laps": cm.life_laps})
    return sum(lap_times), lap_times, out


def validate(model: DriverModel, req: StrategyRequest) -> tuple[list[int], list[str]]:
    total = model.total_laps
    if req.strategy_type not in STRATEGY_TYPES:
        raise StrategyValidationError(
            f"Unknown strategy type '{req.strategy_type}'.", next_action="Choose Baseline, Undercut or Overcut.",
            field="strategy_type")
    pits = list(req.pit_laps)
    if not pits:
        raise StrategyValidationError(
            "Add at least one pit stop.", still_available="Your actual strategy is shown on the left.",
            next_action="Set Pit Stop 1 and run the simulation again.", field="pit_laps")
    if len(pits) > 3:
        raise StrategyValidationError("The Strategy Lab supports up to three pit stops.", field="pit_laps")
    for i, p in enumerate(pits, 1):
        if p < 2 or p > total - 1:
            raise StrategyValidationError(
                f"Pit Stop {i} must be between lap 2 and lap {total - 1}.",
                next_action=f"Move Pit Stop {i} inside the race distance ({total} laps).", field=f"pit{i}")
    for i in range(1, len(pits)):
        if pits[i] <= pits[i - 1]:
            raise StrategyValidationError(
                f"Pit Stop {i + 1} must occur after Pit Stop {i}.",
                next_action=f"Set Pit Stop {i + 1} to lap {pits[i - 1] + MIN_STINT_LAPS} or later.", field=f"pit{i + 1}")
        if pits[i] - pits[i - 1] < MIN_STINT_LAPS:
            raise StrategyValidationError(
                f"Stints must be at least {MIN_STINT_LAPS} laps long (Pit Stop {i} → {i + 1}).",
                next_action=f"Set Pit Stop {i + 1} to lap {pits[i - 1] + MIN_STINT_LAPS} or later.", field=f"pit{i + 1}")
    if total - pits[-1] < MIN_STINT_LAPS:
        raise StrategyValidationError(
            f"The final stint must be at least {MIN_STINT_LAPS} laps long.",
            next_action=f"Pit no later than lap {total - MIN_STINT_LAPS}.", field=f"pit{len(pits)}")

    first_actual = model.actual_pit_laps[0] if model.actual_pit_laps else None
    if req.strategy_type in ("undercut", "overcut"):
        if first_actual is None:
            raise StrategyValidationError(
                f"{model.driver} did not pit in this race, so there is no actual stop to undercut or overcut.",
                next_action="Use the Baseline strategy type.", field="strategy_type")
        if req.strategy_type == "undercut" and pits[0] >= first_actual:
            raise StrategyValidationError(
                f"An undercut means pitting earlier than the actual first stop (lap {first_actual}).",
                next_action=f"Set Pit Stop 1 to lap {first_actual - 1} or earlier.", field="pit1")
        if req.strategy_type == "overcut" and pits[0] <= first_actual:
            raise StrategyValidationError(
                f"An overcut means staying out longer than the actual first stop (lap {first_actual}).",
                next_action=f"Set Pit Stop 1 to lap {first_actual + 1} or later.", field="pit1")

    if not model.compounds_known:
        compounds = ["UNKNOWN"] * (len(pits) + 1)
    else:
        compounds = [c.upper() for c in (req.compounds or [])]
        if not compounds:
            actual = model.actual_compounds
            compounds = [actual[min(i, len(actual) - 1)] for i in range(len(pits) + 1)]
        if len(compounds) != len(pits) + 1:
            raise StrategyValidationError(
                f"Choose a tyre compound for each of the {len(pits) + 1} stints.", field="compounds")
        for c in compounds:
            if c not in model.compounds:
                raise StrategyValidationError(
                    f"'{c.title()}' is not an available compound for this session.",
                    next_action="Choose Soft, Medium or Hard.", field="compounds")
    return pits, compounds


def simulate(session: SessionData, req: StrategyRequest) -> dict:
    model = build_model(session, req.driver)
    pits, compounds = validate(model, req)
    total = model.total_laps

    actual_stints = _plan_stints(model.actual_pit_laps, model.actual_compounds, total)
    alt_stints = _plan_stints(pits, compounds, total)
    act_total, act_laps, act_out = _simulate(model, actual_stints)
    alt_total, alt_laps, alt_out = _simulate(model, alt_stints)
    delta = round(alt_total - act_total, 2)

    # cumulative delta per lap (alternative minus actual) for the comparison chart
    cum, run = [], 0.0
    for i, (a, b) in enumerate(zip(act_laps, alt_laps), start=1):
        run += b - a
        cum.append({"lap": i, "delta_s": round(run, 3)})

    pit_component = round((len(pits) - len(model.actual_pit_laps)) * model.pit_loss_s, 2)
    tyre_component = round(delta - pit_component, 2)

    info = session.driver(req.driver)
    real_total = info.total_time_s if info and info.total_time_s else None
    if real_total is None:
        timed = [l.time_s for l in session.laps_for(req.driver) if l.time_s is not None]
        real_total = round(sum(timed), 3) if len(timed) == total else None

    warnings: list[str] = []
    for s in alt_out:
        if s["over_life_laps"] > 0:
            warnings.append(
                f"Stint {s['stint']} ({s['compound'].title() if s['compound'] != 'UNKNOWN' else 'tyre'}) runs {s['length']} laps — "
                f"{s['over_life_laps']} beyond the {s['life_laps']}-lap recommended life. High tyre-wear risk."
            )
    if model.compounds_known:
        dry = {c for c in compounds if c in DRY_COMPOUNDS}
        if len(dry) < 2:
            warnings.append("F1 sporting rules require at least two different dry compounds in a dry race; this plan uses only one.")
    if info and info.status and info.status not in ("Finished",) and not info.status.startswith("+"):
        warnings.append(f"{req.driver} did not finish ({info.status}); the comparison covers the {total} laps completed.")
    risk = "High" if any("beyond" in w for w in warnings) else ("Medium" if max(s["length"] for s in alt_out) > 0.8 * max(
        model.compounds[s["compound"]].life_laps for s in alt_out) else "Low")

    return {
        "label": "Estimate — not a guaranteed race prediction",
        "model_version": MODEL_VERSION,
        "driver": req.driver,
        "strategy_type": req.strategy_type,
        "total_laps": total,
        "actual": {
            "pit_laps": model.actual_pit_laps,
            "compounds": model.actual_compounds,
            "stints": act_out,
            "modelled_time_s": round(act_total, 3),
            "race_time_s": real_total,
        },
        "alternative": {
            "pit_laps": pits,
            "compounds": compounds,
            "stints": alt_out,
            "modelled_time_s": round(alt_total, 3),
            "estimated_race_time_s": round(real_total + delta, 3) if real_total else None,
        },
        "delta_s": delta,
        "faster": delta < 0,
        "breakdown": {"pit_stops_s": pit_component, "tyre_and_pace_s": tyre_component},
        "cumulative_delta": cum,
        "tyre_risk": risk,
        "warnings": warnings,
        "explanation": _explain(model, pits, compounds, alt_out, act_out, delta, pit_component, tyre_component),
        "model": {
            "pit_loss_s": model.pit_loss_s,
            "pit_loss_source": model.pit_loss_source,
            "compounds": {k: v.model_dump() for k, v in model.compounds.items()},
            "assumptions": model.assumptions,
        },
    }


def _explain(model, pits, compounds, alt_out, act_out, delta, pit_c, tyre_c) -> str:
    parts = []
    act = model.actual_pit_laps
    if act and pits:
        shift = pits[0] - act[0]
        if shift < 0:
            parts.append(f"Pitting {abs(shift)} lap{'s' if abs(shift) != 1 else ''} earlier (lap {pits[0]} instead of {act[0]}) shortens the opening stint on older tyres")
        elif shift > 0:
            parts.append(f"Staying out {shift} lap{'s' if shift != 1 else ''} longer (lap {pits[0]} instead of {act[0]}) extends the opening stint")
        else:
            parts.append(f"Keeping the first stop on lap {pits[0]}")
    if len(pits) != len(act):
        parts.append(f"changing from {len(act)} to {len(pits)} stop{'s' if len(pits) != 1 else ''} moves pit-lane time by {pit_c:+.1f}s")
    if model.compounds_known and compounds != model.actual_compounds:
        parts.append(f"running {' → '.join(c.title() for c in compounds)} instead of {' → '.join(c.title() for c in model.actual_compounds)}")
    head = ", ".join(parts) + "." if parts else "This plan matches the actual strategy."
    head = head[0].upper() + head[1:]
    verdict = (
        f" Net estimate: {abs(delta):.1f}s {'faster' if delta < 0 else 'slower'} than the modelled actual strategy "
        f"(tyre/pace effect {tyre_c:+.1f}s, pit-stop effect {pit_c:+.1f}s)."
    )
    if abs(delta) < 0.5:
        verdict += " The difference is within the model's noise, so treat the two strategies as roughly equal."
    return head + verdict
