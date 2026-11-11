"""Telemetry comparison and tyre/stint calculations."""
import pytest

from app.analytics import stints as stint_analytics
from app.analytics.laps import clean_laps
from app.analytics.telemetry import compare_laps
from app.data import seed_adapter
from app.data.models import Lap, LapTelemetry


# ----------------------------------------------------------------------------- telemetry

def test_valid_telemetry_comparison(client, demo):
    r = client.post("/api/analysis/demo-1-R/telemetry", json={"driver_a": "MOR", "lap_a": 10, "driver_b": "COS", "lap_b": 10})
    assert r.status_code == 200
    body = r.json()
    assert body["telemetry_available"] is True
    assert set(body["available_channels"]) == {"speed", "throttle", "brake", "rpm", "gear"}
    n = len(body["distance"])
    assert all(len(body["channels"][c]["a"]) == n for c in body["available_channels"])
    m = body["metrics"]
    # the end of the running delta equals the official lap-time delta
    assert body["delta"][-1] == pytest.approx(m["lap_time_delta_s"], abs=0.002)
    # mini-sector deltas sum to the lap delta
    assert sum(x["delta_s"] for x in body["mini_sectors"]) == pytest.approx(m["lap_time_delta_s"], abs=0.01)
    assert len(m["sectors"]) == 3 and all(s["delta_s"] is not None for s in m["sectors"])
    assert body["insight"]


def test_missing_telemetry_returns_lap_only_comparison(client):
    client.post("/api/analysis/load", json={"season": "demo", "round": 2, "driver_a": "MOR", "driver_b": "COS"})
    r = client.post("/api/analysis/demo-2-R/telemetry", json={"driver_a": "MOR", "lap_a": 5, "driver_b": "COS", "lap_b": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["telemetry_available"] is False
    assert body["unavailable"]["code"] == "telemetry_unavailable"
    assert body["unavailable"]["still_available"] and body["unavailable"]["next_action"]
    assert body["metrics"]["lap_time_delta_s"] is not None


def test_invalid_driver_lap_combination(client, demo):
    r = client.post("/api/analysis/demo-1-R/telemetry", json={"driver_a": "DUA", "lap_a": 50, "driver_b": "COS", "lap_b": 10})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["field"] == "lap_a"
    assert "DUA did not complete lap 50" in err["message"]


def test_empty_comparison_selection(client, demo):
    r = client.post("/api/analysis/demo-1-R/telemetry", json={"driver_a": "MOR", "lap_a": 10})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_request"


def test_pit_lap_selection_is_flagged(client, demo):
    r = client.post("/api/analysis/demo-1-R/telemetry", json={"driver_a": "MOR", "lap_a": 17, "driver_b": "COS", "lap_b": 10})
    assert any("in-lap" in n for n in r.json()["notes"])


def test_compare_handles_missing_channel():
    dist = [0.0, 100.0, 200.0, 300.0]
    a = LapTelemetry(driver="A", lap=1, distance=dist, speed=[200, 250, 150, 220], time=[0, 1.6, 3.4, 5.0])
    b = LapTelemetry(driver="B", lap=1, distance=dist, speed=[200, 240, 160, 210], throttle=[100, 100, 0, 80], time=[0, 1.7, 3.5, 5.2])
    res = compare_laps(a, b, Lap(driver="A", lap=1, time_s=5.0), Lap(driver="B", lap=1, time_s=5.2))
    assert res["available_channels"] == ["speed"]
    assert "throttle" in res["missing_channels"]
    assert res["metrics"]["a"]["full_throttle_pct"] is None
    assert res["metrics"]["lap_time_delta_s"] == pytest.approx(-0.2)


# ----------------------------------------------------------------------------- stints

def test_clean_laps_exclude_lap1_and_pit_laps():
    s = seed_adapter.load_session(1, "R")
    clean = clean_laps(s.laps_for("MOR"))
    laps = {l.lap for l in clean}
    assert 1 not in laps and 17 not in laps and 18 not in laps  # lap 1, in-lap 17, out-lap 18


def test_stints_cover_every_lap_once():
    s = seed_adapter.load_session(1, "R")
    for d in s.drivers:
        stints = stint_analytics.build_stints(s, d.code)
        covered = [lap for st in stints for lap in range(st["start_lap"], st["end_lap"] + 1)]
        assert covered == [l.lap for l in s.laps_for(d.code)]
        assert sum(st["length"] for st in stints) == len(s.laps_for(d.code))


def test_stint_values_for_known_strategy():
    s = seed_adapter.load_session(1, "R")
    stints = stint_analytics.build_stints(s, "MOR")
    assert [(x["compound"], x["start_lap"], x["end_lap"], x["length"]) for x in stints] == [
        ("SOFT", 1, 17, 17), ("MEDIUM", 18, 39, 22), ("HARD", 40, 52, 13)]
    assert [x["pit_lap"] for x in stints] == [17, 39, None]
    # the soft stint degrades the most (seeded with a tyre cliff)
    assert stints[0]["trend"] == "Degrading"
    assert stints[0]["deg_s_per_lap"] > stints[1]["deg_s_per_lap"]
    assert stints == stint_analytics.build_stints(s, "MOR")  # consistent across calls


def test_degradation_fit_recovers_known_slope():
    laps = [Lap(driver="X", lap=n, time_s=90 + 0.1 * (n - 1) - 0.035 * (n - 1), stint=1, tyre_life=n) for n in range(1, 21)]
    from app.data.models import Availability, DriverInfo, SessionData

    s = SessionData(key="t", season="t", round=1, event_name="T", session="R", session_name="Race", total_laps=20,
                    source="demo", source_label="t", availability=Availability(), drivers=[DriverInfo(code="X", name="X")], laps=laps)
    st = stint_analytics.build_stints(s, "X")[0]
    assert st["deg_s_per_lap"] == pytest.approx(0.1, abs=1e-6)
    assert st["trend"] == "Degrading"


def test_missing_compound_is_reported_unknown():
    s = seed_adapter.load_session(2, "R")
    stints = stint_analytics.build_stints(s, "CAR")
    assert any(not x["compound_known"] for x in stints)
    unknown = [x for x in stints if not x["compound_known"]]
    assert all(x["compound"] is None for x in unknown)
    # an insight about an unknown-compound stint says so instead of naming a compound
    assert "compound unknown" in stint_analytics.stint_insight("CAR", unknown)
