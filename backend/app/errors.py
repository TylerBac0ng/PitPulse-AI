"""Domain errors. Each carries the three things the UI must always tell the user:
what is unavailable, what they can still do, and what action to take next."""
from __future__ import annotations

from typing import Optional


class PitPulseError(Exception):
    status_code = 400
    code = "pitpulse_error"

    def __init__(
        self,
        message: str,
        *,
        still_available: Optional[str] = None,
        next_action: Optional[str] = None,
        field: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.still_available = still_available
        self.next_action = next_action
        self.field = field

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "still_available": self.still_available,
            "next_action": self.next_action,
            "field": self.field,
        }


class SessionUnavailableError(PitPulseError):
    status_code = 404
    code = "session_unavailable"


class DataSourceError(PitPulseError):
    status_code = 503
    code = "data_source_error"


class InvalidSelectionError(PitPulseError):
    status_code = 422
    code = "invalid_selection"


class TelemetryUnavailableError(PitPulseError):
    status_code = 404
    code = "telemetry_unavailable"


class StrategyValidationError(PitPulseError):
    status_code = 422
    code = "invalid_strategy"


class AnalysisNotLoadedError(PitPulseError):
    status_code = 404
    code = "analysis_not_loaded"
