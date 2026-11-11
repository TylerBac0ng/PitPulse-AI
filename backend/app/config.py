"""Runtime configuration (environment variables, see .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    cache_dir: Path = field(default_factory=lambda: Path(os.getenv("PITPULSE_CACHE_DIR", BACKEND_DIR / "cache")))
    seed_file: Path = BACKEND_DIR / "app" / "data" / "seed" / "demo_sessions.json"
    # Disable all network data sources (demo data only) — useful for offline demos and tests.
    offline: bool = field(default_factory=lambda: _flag("PITPULSE_OFFLINE"))
    # Skip the FastF1 live-timing probe (it needs F1 account credentials since 2026).
    disable_fastf1_live: bool = field(default_factory=lambda: _flag("PITPULSE_DISABLE_FASTF1_LIVE"))
    cors_origins: list[str] = field(
        default_factory=lambda: os.getenv(
            "PITPULSE_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
    )
    first_season: int = 2018

    @property
    def fastf1_cache_dir(self) -> Path:
        return self.cache_dir / "fastf1"

    @property
    def processed_cache_dir(self) -> Path:
        return self.cache_dir / "processed"


settings = Settings()
