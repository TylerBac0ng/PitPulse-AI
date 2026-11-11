"""Strategy input validation and deterministic simulation."""
import pytest

from app.data import seed_adapter
from app.errors import StrategyValidationError
from app.strategy import simulator
from app.strategy.simulator import StrategyRequest

URL = "/api/analysis/demo-1-R/strategy/simulate"


def sim(client, **body):
    return client.post(URL, json={"driver": "MOR", **body})


def test_baseline_endpoint(client, demo):
    b = client.get("/api/analysis/demo-1-R/strategy/baseline?driver=MOR").json()
    assert b["actual_pit_laps"] == [17, 39]
    assert b["actual_compounds"] == ["SOFT", "MEDIUM", "HARD"]
    assert b["compounds_known"] is True
    assert 15 < b["pit_loss_s"] < 35


def test_unchanged_plan_has_zero_delta(client, demo):
    r = sim(client, pit_laps=[17, 39], compounds=["SOFT", "MEDIUM", "HARD"]).json()
    assert r["delta_s"] == 0
    assert r["alternative"]["estimated_race_time_s"] == pytest.approx(r["actual"]["race_time_s"])


def test_identical_inputs_give_identical_results(client, demo):
    body = {"pit_laps": [14, 36], "compounds": ["SOFT", "MEDIUM", "HARD"], "strategy_type": "undercut"}
    first, second = sim(client, **body).json(), sim(client, **body).json()
    first.pop("session"), second.pop("session")
    assert first == second


def test_result_is_labelled_estimate(client, demo):
    r = sim(client, pit_laps=[20, 39]).json()
    assert "estimate" in r["label"].lower()
    assert r["explanation"]
    assert r["breakdown"]["pit_stops_s"] + r["breakdown"]["tyre_and_pace_s"] == pytest.approx(r["delta_s"], abs=0.02)


def test_extra_stop_costs_pit_loss(client, demo):
    r = sim(client, pit_laps=[12, 26, 39], compounds=["SOFT", "SOFT", "MEDIUM", "HARD"]).json()
    assert r["breakdown"]["pit_stops_s"] == pytest.approx(r["model"]["pit_loss_s"])


@pytest.mark.parametrize(
    "body,field,fragment",
    [
        ({"pit_laps": [30, 20]}, "pit2", "Pit Stop 2 must occur after Pit Stop 1"),
        ({"pit_laps": [20, 21]}, "pit2", "at least 3 laps"),
        ({"pit_laps": [1, 30]}, "pit1", "between lap 2"),
        ({"pit_laps": [20, 52]}, "pit2", "between lap 2"),
        ({"pit_laps": [20, 50]}, "pit2", "final stint"),
        ({"pit_laps": []}, "pit_laps", "at least one pit stop"),
        ({"pit_laps": [18, 39], "strategy_type": "undercut"}, "pit1", "earlier than the actual first stop"),
        ({"pit_laps": [15, 39], "strategy_type": "overcut"}, "pit1", "longer than the actual first stop"),
        ({"pit_laps": [17, 39], "compounds": ["SOFT", "MEDIUM"]}, "compounds", "each of the 3 stints"),
        ({"pit_laps": [17, 39], "compounds": ["SOFT", "MEDIUM", "PURPLE"]}, "compounds", "not an available compound"),
    ],
)
def test_strategy_validation(client, demo, body, field, fragment):
    r = sim(client, **body)
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "invalid_strategy"
    assert err["field"] == field
    assert fragment in err["message"]


def test_unknown_strategy_type_rejected(client, demo):
    r = sim(client, pit_laps=[17, 39], strategy_type="bananas")
    assert r.status_code == 422


def test_long_stint_warning_and_single_compound_rule(client, demo):
    r = sim(client, pit_laps=[45], compounds=["SOFT", "SOFT"]).json()
    assert r["tyre_risk"] == "High"
    assert any("beyond" in w for w in r["warnings"])
    assert any("two different dry compounds" in w for w in r["warnings"])


def test_unknown_compounds_use_generic_tyre_model():
    s = seed_adapter.load_session(2, "R")
    model = simulator.build_model(s, "CAR")
    assert model.compounds_known is False
    assert list(model.compounds) == ["UNKNOWN"]
    res = simulator.simulate(s, StrategyRequest(driver="CAR", pit_laps=[12], compounds=["SOFT", "HARD"]))
    assert res["alternative"]["compounds"] == ["UNKNOWN", "UNKNOWN"]


def test_retired_driver_is_warned():
    s = seed_adapter.load_session(1, "R")
    res = simulator.simulate(s, StrategyRequest(driver="DUA", pit_laps=[18]))
    assert res["total_laps"] == 44
    assert any("did not finish" in w for w in res["warnings"])


def test_validation_is_pure_function():
    s = seed_adapter.load_session(1, "R")
    model = simulator.build_model(s, "MOR")
    with pytest.raises(StrategyValidationError):
        simulator.validate(model, StrategyRequest(driver="MOR", pit_laps=[39, 17]))
