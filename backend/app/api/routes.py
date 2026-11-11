"""Application layer: request validation, orchestration and response formatting.

Routes never touch FastF1 directly — they go through the repository (data access) and
call the analytics / strategy layers on the normalized SessionData.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Path, Query
from pydantic import BaseModel, Field, field_validator

from app.analytics import laps as lap_analytics
from app.analytics import stints as stint_analytics
from app.analytics import telemetry as tel_analytics
from app.data.models import SessionData
from app.data.repository import repository
from app.errors import InvalidSelectionError, TelemetryUnavailableError
from app.strategy import simulator

router = APIRouter(prefix="/api")


# ----------------------------------------------------------------------------- schemas

def _norm_code(v: Optional[str]) -> Optional[str]:
    if not isinstance(v, str):
        return v  # let field validation report the type error
    v = v.strip().upper()
    return v or None


class LoadRequest(BaseModel):
    season: str = Field(..., min_length=4, max_length=8, examples=["demo", "2023"])
    round: int = Field(..., ge=1, le=30)
    session: Literal["R", "Q"] = "R"
    driver_a: str = Field(..., min_length=2, max_length=4)
    driver_b: Optional[str] = Field(None, max_length=4)

    @field_validator("driver_a", "driver_b", mode="before")
    @classmethod
    def _codes(cls, v):
        return _norm_code(v)


class TelemetryRequest(BaseModel):
    driver_a: str = Field(..., min_length=2, max_length=4)
    lap_a: int = Field(..., ge=1, le=100)
    driver_b: str = Field(..., min_length=2, max_length=4)
    lap_b: int = Field(..., ge=1, le=100)

    @field_validator("driver_a", "driver_b", mode="before")
    @classmethod
    def _codes(cls, v):
        return _norm_code(v)


class SimulateRequest(BaseModel):
    driver: str = Field(..., min_length=2, max_length=4)
    pit_laps: list[int] = Field(..., max_length=3)
    compounds: Optional[list[str]] = None
    strategy_type: Literal["baseline", "undercut", "overcut"] = "baseline"

    @field_validator("driver", mode="before")
    @classmethod
    def _code(cls, v):
        return _norm_code(v)


# ----------------------------------------------------------------------------- helpers

def _meta(s: SessionData) -> dict:
    return {
        "key": s.key,
        "season": s.season,
        "round": s.round,
        "event_name": s.event_name,
        "session": s.session,
        "session_name": s.session_name,
        "circuit": s.circuit,
        "date": s.date,
        "total_laps": s.total_laps,
        "source": s.source,
        "source_label": s.source_label,
        "is_demo": s.is_demo,
        "availability": s.availability.model_dump(),
        "notes": s.notes,
    }


def _laps_index(s: SessionData, code: str) -> list[dict]:
    clean = {l.lap for l in lap_analytics.clean_laps(s.laps_for(code))}
    return [
        {
            "lap": l.lap,
            "time_s": l.time_s,
            "compound": l.compound,
            "stint": l.stint,
            "pit_in": l.pit_in,
            "pit_out": l.pit_out,
            "clean": l.lap in clean,
        }
        for l in s.laps_for(code)
    ]


def _overview(s: SessionData, a: str, b: Optional[str]) -> dict:
    a = lap_analytics.require_driver(s, a, "driver_a")
    if b:
        b = lap_analytics.require_driver(s, b, "driver_b")
        if b == a:
            raise InvalidSelectionError(
                "Driver A and Driver B are the same driver.",
                still_available="A single-driver analysis works without Driver B.",
                next_action="Pick a different Driver B, or clear it.",
                field="driver_b",
            )
    codes = [a] + ([b] if b else [])
    stints = {c: stint_analytics.build_stints(s, c) for c in codes}
    return {
        "session": _meta(s),
        "drivers": [d.model_dump() for d in s.drivers],
        "selected": {"driver_a": a, "driver_b": b},
        "summaries": {c: lap_analytics.driver_summary(s, c) for c in codes},
        "comparison": lap_analytics.compare_drivers(s, a, b) if b else None,
        "lap_series": lap_analytics.lap_series(s, codes),
        "stints": stints,
        "stint_insights": {c: stint_analytics.stint_insight(c, stints[c]) for c in codes},
        "laps": {c: _laps_index(s, c) for c in codes},
        "lap_counts": {d.code: len(s.laps_for(d.code)) for d in s.drivers},
        "pit_stops": {c: [p.model_dump() for p in s.pit_stops if p.driver == c] for c in codes},
    }


# ----------------------------------------------------------------------------- routes

@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/seasons")
def seasons() -> dict:
    return {"seasons": repository.seasons()}


@router.get("/seasons/{season}/events")
def events(season: str = Path(..., max_length=8)) -> dict:
    return {"season": season, "events": [e.model_dump() for e in repository.events(season)]}


@router.get("/seasons/{season}/events/{rnd}/drivers")
def drivers(season: str = Path(..., max_length=8), rnd: int = Path(..., ge=1, le=30)) -> dict:
    return {"drivers": [d.model_dump() for d in repository.drivers(season, rnd)]}


@router.post("/analysis/load")
def load_analysis(req: LoadRequest) -> dict:
    result = repository.load(req.season, req.round, req.session)
    s = result.session
    a, b = req.driver_a, req.driver_b
    if result.fallback:
        # requested drivers do not exist in the demo session: use the demo defaults
        codes = [d.code for d in s.drivers]
        a = a if a in codes else "MOR"
        b = b if (b in codes and b != a) else ("COS" if a != "COS" else "SAT")
    payload = _overview(s, a, b)
    payload["fallback"] = result.fallback.model_dump() if result.fallback else None
    payload["cached"] = result.cached
    return payload


@router.get("/analysis/{key}/overview")
def overview(key: str, driver_a: str = Query(..., min_length=2), driver_b: Optional[str] = Query(None)) -> dict:
    s = repository.get(key)
    payload = _overview(s, _norm_code(driver_a), _norm_code(driver_b))
    payload["fallback"] = None
    payload["cached"] = True
    return payload


@router.post("/analysis/{key}/telemetry")
def telemetry(key: str, req: TelemetryRequest) -> dict:
    s = repository.get(key)
    a = lap_analytics.require_driver(s, req.driver_a, "driver_a")
    b = lap_analytics.require_driver(s, req.driver_b, "driver_b")
    lap_a = next((l for l in s.laps_for(a) if l.lap == req.lap_a), None)
    lap_b = next((l for l in s.laps_for(b) if l.lap == req.lap_b), None)
    for code, lap_no, lap, fld in ((a, req.lap_a, lap_a, "lap_a"), (b, req.lap_b, lap_b, "lap_b")):
        if lap is None:
            n = len(s.laps_for(code))
            raise InvalidSelectionError(
                f"{code} did not complete lap {lap_no} (completed {n} laps).",
                still_available=f"Laps 1–{n} are available for {code}.",
                next_action="Choose a lap from the list.",
                field=fld,
            )
    notes = []
    for code, lap in ((a, lap_a), (b, lap_b)):
        if lap.pit_in or lap.pit_out or lap.lap == 1:
            kind = "lap 1" if lap.lap == 1 else ("an in-lap" if lap.pit_in else "an out-lap")
            notes.append(f"{code} lap {lap.lap} is {kind}, so it is not representative of race pace.")
    base = {
        "session": _meta(s),
        "selection": req.model_dump(),
        "notes": notes,
    }
    try:
        tel_a = repository.lap_telemetry(s, a, req.lap_a)
        tel_b = repository.lap_telemetry(s, b, req.lap_b)
    except TelemetryUnavailableError as exc:
        return {
            **base,
            "telemetry_available": False,
            "unavailable": exc.to_dict(),
            "metrics": tel_analytics.lap_only_comparison(lap_a, lap_b),
            "insight": None,
        }
    result = tel_analytics.compare_laps(tel_a, tel_b, lap_a, lap_b)
    return {
        **base,
        "telemetry_available": True,
        **result,
        "insight": tel_analytics.telemetry_insight(result, a, b),
    }


@router.get("/analysis/{key}/strategy/baseline")
def strategy_baseline(key: str, driver: str = Query(..., min_length=2)) -> dict:
    s = repository.get(key)
    code = lap_analytics.require_driver(s, _norm_code(driver))
    model = simulator.build_model(s, code)
    return {
        "driver": code,
        "total_laps": model.total_laps,
        "compounds_known": model.compounds_known,
        "available_compounds": list(model.compounds.keys()),
        "actual_pit_laps": model.actual_pit_laps,
        "actual_compounds": model.actual_compounds,
        "actual_stints": stint_analytics.build_stints(s, code),
        "race_time_s": (s.driver(code).total_time_s if s.driver(code) else None),
        "pit_loss_s": model.pit_loss_s,
        "pit_loss_source": model.pit_loss_source,
        "compound_models": {k: v.model_dump() for k, v in model.compounds.items()},
        "assumptions": model.assumptions,
        "min_stint_laps": simulator.MIN_STINT_LAPS,
    }


@router.post("/analysis/{key}/strategy/simulate")
def strategy_simulate(key: str, req: SimulateRequest) -> dict:
    s = repository.get(key)
    code = lap_analytics.require_driver(s, req.driver)
    result = simulator.simulate(
        s, simulator.StrategyRequest(driver=code, pit_laps=req.pit_laps, compounds=req.compounds, strategy_type=req.strategy_type)
    )
    result["session"] = _meta(s)
    return result
