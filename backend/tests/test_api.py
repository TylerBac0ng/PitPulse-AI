"""API request validation, session loading and fallback behaviour."""


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_seasons_offline_lists_demo_only(client):
    seasons = client.get("/api/seasons").json()["seasons"]
    assert [s["season"] for s in seasons] == ["demo"]


def test_demo_events_and_drivers(client):
    events = client.get("/api/seasons/demo/events").json()["events"]
    assert {e["round"] for e in events} == {1, 2}
    drivers = client.get("/api/seasons/demo/events/1/drivers").json()["drivers"]
    assert "MOR" in {d["code"] for d in drivers}


def test_load_demo_overview_payload(demo):
    assert demo["session"]["is_demo"] is True
    assert demo["fallback"] is None
    assert demo["selected"] == {"driver_a": "MOR", "driver_b": "COS"}
    mor = demo["summaries"]["MOR"]
    assert mor["pit_laps"] == [17, 39]
    assert mor["best_lap"]["time_s"] > 80
    assert len(demo["lap_series"]) == demo["session"]["total_laps"]
    assert demo["comparison"]["common_clean_laps"] > 30


def test_driver_codes_are_normalised(client):
    r = client.post("/api/analysis/load", json={"season": "demo", "round": 1, "driver_a": " mor ", "driver_b": "cos"})
    assert r.status_code == 200
    assert r.json()["selected"]["driver_a"] == "MOR"


def test_validation_error_is_readable(client):
    r = client.post("/api/analysis/load", json={"season": "demo", "round": 0, "driver_a": "MOR"})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "invalid_request"
    assert err["field"] == "round"
    assert err["next_action"]


def test_missing_driver_a_rejected(client):
    r = client.post("/api/analysis/load", json={"season": "demo", "round": 1})
    assert r.status_code == 422
    assert r.json()["error"]["field"] == "driver_a"


def test_unknown_driver(client):
    r = client.post("/api/analysis/load", json={"season": "demo", "round": 1, "driver_a": "XYZ"})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "invalid_selection" and err["field"] == "driver_a"
    assert err["still_available"] and err["next_action"]


def test_same_driver_twice_rejected(client):
    r = client.post("/api/analysis/load", json={"season": "demo", "round": 1, "driver_a": "MOR", "driver_b": "MOR"})
    assert r.status_code == 422
    assert r.json()["error"]["field"] == "driver_b"


def test_unavailable_session(client):
    r = client.post("/api/analysis/load", json={"season": "demo", "round": 1, "session": "Q", "driver_a": "MOR"})
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["code"] == "session_unavailable"
    assert "Race" in err["next_action"]


def test_unknown_demo_event(client):
    r = client.post("/api/analysis/load", json={"season": "demo", "round": 9, "driver_a": "MOR"})
    assert r.status_code == 404


def test_invalid_season(client):
    r = client.post("/api/analysis/load", json={"season": "abcd", "round": 1, "driver_a": "VER"})
    assert r.status_code == 422
    assert r.json()["error"]["field"] == "season"


def test_real_season_falls_back_to_labelled_demo_data(client):
    """When historical sources are unavailable, the demo session is served and clearly flagged."""
    r = client.post("/api/analysis/load", json={"season": "2023", "round": 1, "driver_a": "VER", "driver_b": "ALO"})
    assert r.status_code == 200
    body = r.json()
    assert body["session"]["is_demo"] is True
    assert body["fallback"]["requested"].startswith("2023 round 1")
    assert body["fallback"]["reason"]
    # requested drivers are not in the demo session, so demo defaults are used
    assert body["selected"]["driver_a"] == "MOR"


def test_analysis_not_loaded(client):
    r = client.get("/api/analysis/2023-5-R/overview?driver_a=VER")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "analysis_not_loaded"


def test_overview_switch_drivers(client, demo):
    r = client.get("/api/analysis/demo-1-R/overview?driver_a=SAT")
    assert r.status_code == 200
    body = r.json()
    assert body["selected"] == {"driver_a": "SAT", "driver_b": None}
    assert body["comparison"] is None


def test_non_string_driver_is_a_validation_error(client):
    r = client.post("/api/analysis/load", json={"season": "demo", "round": 1, "driver_a": 123})
    assert r.status_code == 422
    assert r.json()["error"]["field"] == "driver_a"
