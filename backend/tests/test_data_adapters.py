"""Data adapter normalization, seeded data and caching."""
import json

import pytest

from app.config import settings
from app.data import fastf1_adapter, seed_adapter
from app.data.models import SessionData
from app.data.repository import SessionRepository
from app.errors import SessionUnavailableError, TelemetryUnavailableError


@pytest.mark.parametrize(
    "raw,expected",
    [("1:39.019", 99.019), ("59.8", 59.8), ("1:00:01.5", 3601.5), (None, None), ("", None), ("abc", None)],
)
def test_parse_laptime(raw, expected):
    assert fastf1_adapter.parse_laptime(raw) == expected


class _Page(list):
    """Mimics fastf1.ergast ErgastRawResponse pagination."""

    def __init__(self, items, rest=()):
        super().__init__(items)
        self._rest = list(rest)
        self.is_complete = not self._rest

    def get_next_result_page(self):
        if not self._rest:
            raise ValueError("No more data after this response.")
        return _Page(self._rest[0], self._rest[1:])


class FakeErgast:
    def get_race_results(self, season, rnd):
        def res(code, did, pos, grid, millis, status="Finished"):
            return {
                "number": "1", "position": str(pos), "points": "10", "grid": str(grid), "status": status,
                "Driver": {"driverId": did, "code": code, "givenName": "A", "familyName": did.title()},
                "Constructor": {"name": "Team"},
                "Time": {"millis": str(millis)} if millis else None,
            }

        return _Page([{
            "raceName": "Test Grand Prix", "date": "2023-03-05", "Circuit": {"circuitName": "Test Circuit"},
            "Results": [res("AAA", "alpha", 1, 2, 500_000), res("BBB", "bravo", 2, 1, None, "+1 Lap")],
        }])

    def get_lap_times(self, season, rnd):
        def lap(n, a, b):
            return {"number": str(n), "Timings": [
                {"driverId": "alpha", "time": a, "position": "1"},
                {"driverId": "bravo", "time": b, "position": "2"},
            ]}

        laps = [lap(n, f"1:3{n % 10}.000", "1:40.000") for n in range(1, 11)]
        # split over two pages, including a lap number that spans both pages
        return _Page([{"Laps": laps[:6]}], [[{"Laps": laps[5:]}]])

    def get_pit_stops(self, season, rnd):
        return _Page([{"PitStops": [
            {"driverId": "alpha", "lap": "4", "stop": "1", "duration": "22.5"},
            {"driverId": "alpha", "lap": "7", "stop": "2", "duration": "31:22.1"},  # red-flag style outlier
        ]}])


def test_timing_session_normalization(monkeypatch):
    monkeypatch.setattr(fastf1_adapter, "_erg", lambda: FakeErgast())
    s = fastf1_adapter.load_timing_session(2023, 1, "R")
    assert isinstance(s, SessionData)
    assert s.source == "ergast" and not s.is_demo
    assert s.availability.telemetry is False and s.availability.compounds is False
    assert s.total_laps == 10
    alpha = s.laps_for("AAA")
    assert len(alpha) == 10  # page overlap does not duplicate laps
    assert alpha[0].time_s == 91.0
    # pit on lap 4 -> stint 2 starts lap 5; pit on lap 7 -> stint 3 starts lap 8
    assert [l.stint for l in alpha] == [1, 1, 1, 1, 2, 2, 2, 3, 3, 3]
    assert alpha[3].pit_in and alpha[4].pit_out
    assert alpha[4].tyre_life == 1
    assert s.driver("AAA").total_time_s == 500.0
    assert s.driver("BBB").total_time_s is None
    stops = [p for p in s.pit_stops if p.driver == "AAA"]
    assert stops[0].duration_s == 22.5 and stops[1].duration_s is None


def test_timing_session_rejects_qualifying(monkeypatch):
    monkeypatch.setattr(fastf1_adapter, "_erg", lambda: FakeErgast())
    with pytest.raises(SessionUnavailableError):
        fastf1_adapter.load_timing_session(2023, 1, "Q")


def test_seed_session_is_valid_and_labelled():
    s = seed_adapter.load_session(1, "R")
    assert s.is_demo and s.source == "demo"
    assert "not a real" in " ".join(s.notes).lower()
    for d in s.drivers:
        laps = s.laps_for(d.code)
        assert laps, d.code
        assert [l.lap for l in laps] == list(range(1, len(laps) + 1))
    # sector times add up to the lap time
    for l in s.laps[:50]:
        assert abs(l.s1_s + l.s2_s + l.s3_s - l.time_s) < 0.01


def test_seed_generation_is_deterministic(tmp_path, monkeypatch):
    import scripts.generate_seed as gen

    out1, out2 = tmp_path / "a.json", tmp_path / "b.json"
    monkeypatch.setattr(gen, "OUT", out1)
    gen.main()
    monkeypatch.setattr(gen, "OUT", out2)
    gen.main()
    assert out1.read_text() == out2.read_text()
    assert json.loads(out1.read_text()) == json.loads(settings.seed_file.read_text())


def test_demo_telemetry_matches_lap_time():
    tel = seed_adapter.get_lap_telemetry(1, "MOR", 10)
    lap = next(l for l in seed_adapter.load_session(1, "R").laps if l.driver == "MOR" and l.lap == 10)
    assert abs(tel.time[-1] - lap.time_s) < 0.01
    assert len(tel.distance) == len(tel.speed) == len(tel.gear)
    assert 280 < max(tel.speed) < 350


def test_limited_demo_has_no_telemetry_and_missing_compounds():
    s = seed_adapter.load_session(2, "R")
    assert s.availability.telemetry is False
    assert any(l.compound is None for l in s.laps)
    with pytest.raises(TelemetryUnavailableError) as exc:
        seed_adapter.get_lap_telemetry(2, "MOR", 5)
    assert exc.value.still_available and exc.value.next_action


def test_processed_cache_round_trip(monkeypatch):
    monkeypatch.setattr(fastf1_adapter, "_erg", lambda: FakeErgast())
    monkeypatch.setattr(fastf1_adapter, "live_timing_available", lambda: False)
    monkeypatch.setattr(settings, "offline", False)
    repo = SessionRepository()
    first = repo.load("2023", 1, "R")
    assert first.cached is False and first.session.source == "ergast"
    assert (settings.processed_cache_dir / "2023-1-R.json").exists()

    # a new repository (e.g. after restart) reads the processed cache without the network
    monkeypatch.setattr(fastf1_adapter, "_erg", lambda: (_ for _ in ()).throw(RuntimeError("network down")))
    second = SessionRepository().load("2023", 1, "R")
    assert second.cached is True
    assert second.session == first.session


def test_network_failure_falls_back_to_demo(monkeypatch):
    class Broken:
        def __getattr__(self, name):
            raise ConnectionError("offline")

    monkeypatch.setattr(fastf1_adapter, "_erg", lambda: Broken())
    monkeypatch.setattr(fastf1_adapter, "live_timing_available", lambda: False)
    monkeypatch.setattr(settings, "offline", False)
    result = SessionRepository().load("2023", 1, "R")
    assert result.session.is_demo
    assert result.fallback is not None
    assert "did not respond" in result.fallback.reason
