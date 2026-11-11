"""PitPulse AI — FastAPI application entry point.

Run:  uvicorn app.main:app --reload --port 8010
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import settings
from app.errors import PitPulseError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("pitpulse")

app = FastAPI(
    title="PitPulse AI API",
    version="0.2.0",
    description="Historical F1 race strategy & telemetry analytics (CS 4800 Assignment 2 MVP).",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins if o.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.exception_handler(PitPulseError)
async def pitpulse_error_handler(_: Request, exc: PitPulseError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.to_dict()})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    first = exc.errors()[0] if exc.errors() else {}
    loc = [str(x) for x in first.get("loc", []) if x not in ("body", "query", "path")]
    field = loc[0] if loc else None
    msg = first.get("msg", "Invalid request.")
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "invalid_request",
                "message": f"Invalid value for '{field}': {msg}" if field else msg,
                "still_available": None,
                "next_action": "Check the highlighted input and try again.",
                "field": field,
                "details": [
                    {"field": ".".join(str(x) for x in e.get("loc", [])), "message": e.get("msg")} for e in exc.errors()
                ],
            }
        },
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(_: Request, exc: Exception) -> JSONResponse:
    log.exception("Unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "Something went wrong while preparing this analysis.",
                "still_available": "Previously loaded screens are unaffected.",
                "next_action": "Try again, or reload the session from the selection screen.",
                "field": None,
            }
        },
    )


app.include_router(router)
