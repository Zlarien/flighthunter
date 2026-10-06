"""Tests rapides du moteur (dates, routes, bagage) — exécuter avec pytest ou -m."""
from __future__ import annotations

from datetime import date

from flighthunter.engine.baggage import baggage_ok, effective_baggage_cost
from flighthunter.engine.dates import build_date_matrix
from flighthunter.engine.routes import allowed_hubs, enabled_route_types
from flighthunter.models import Alert, Baggage, FlightOption, RouteType, Stay, Techniques


def _alert(**kw) -> Alert:
    base = dict(
        name="t",
        origins=["CDG", "BVA"],
        destination="HAH",
        depart_earliest=date(2027, 6, 15),
        depart_latest=date(2027, 6, 30),
        return_earliest=date(2027, 6, 25),
        return_latest=date(2027, 7, 30),
        stay=Stay(min_nights=10, max_nights=45, maximize=True),
        date_step_days=3,
        max_price_eur=800,
        baggage=Baggage.ANY,
        techniques=Techniques(through_fare=True, self_transfer=True, open_jaw=True),
    )
    base.update(kw)
    return Alert(**base)


def test_date_matrix_respects_stay():
    pairs = build_date_matrix(_alert())
    assert pairs, "doit produire des paires"
    for dep, ret in pairs:
        assert 10 <= (ret - dep).days <= 45
    # maximize => première paire = séjour le plus long
    assert (pairs[0][1] - pairs[0][0]).days == max((r - d).days for d, r in pairs)


def test_hub_exclusion():
    routes = {"allowed_hubs": ["NBO", "ADD", "AUH"], "excluded_hubs": ["AUH"]}
    assert "AUH" not in allowed_hubs(routes)


def test_route_types_follow_toggles():
    types = enabled_route_types(_alert())
    assert RouteType.THROUGH in types and RouteType.SELF_TRANSFER in types
    assert RouteType.HIDDEN_CITY not in types


def test_baggage_hidden_city_blocked_when_checked_required():
    opt = FlightOption(
        origin="CDG", destination="HAH", outbound_date=date(2026, 6, 15),
        route_type=RouteType.HIDDEN_CITY, price_eur=500,
    )
    assert baggage_ok(opt, Baggage.CHECKED_REQUIRED) is False
    assert baggage_ok(opt, Baggage.CABIN_ONLY) is True


def test_baggage_cost_added_when_required_and_not_included():
    opt = FlightOption(
        origin="CDG", destination="HAH", outbound_date=date(2026, 6, 15),
        price_eur=600, baggage_included=False, baggage_addon_eur=60,
    )
    assert effective_baggage_cost(opt, Baggage.CHECKED_REQUIRED) == 60
    assert effective_baggage_cost(opt, Baggage.CABIN_ONLY) == 0


def test_enum_paths_and_exclusion():
    from flighthunter.engine.network import _enum_paths

    adj = {
        "A": [{"to": "B"}, {"to": "HAH"}],
        "B": [{"to": "HAH"}],
    }
    paths = _enum_paths(adj, "A", set(), "HAH", 3, frozenset({"A"}))
    assert len(paths) == 2  # direct A->HAH et A->B->HAH
    # exclusion de B => seulement le direct
    paths_excl = _enum_paths(adj, "A", {"B"}, "HAH", 3, frozenset({"A"}))
    assert len(paths_excl) == 1
    # borne de legs : max 1 vol => seulement le direct
    paths_short = _enum_paths(adj, "A", set(), "HAH", 1, frozenset({"A"}))
    assert len(paths_short) == 1


def test_build_extreme_produces_multileg():
    import os

    from flighthunter.config import Settings
    from flighthunter.engine.network import build_extreme
    from flighthunter.models import RouteType

    settings = Settings()
    os.environ.pop("TRAVELPAYOUTS_TOKEN", None)  # test hors-ligne : prix synthétiques
    alert = settings.enabled_alerts()[0]
    opts = build_extreme(alert, settings)
    assert opts, "le moteur extrême doit produire des itinéraires"
    for o in opts:
        assert o.route_type == RouteType.MULTI_LEG
        assert o.destination == "HAH"
        assert len(o.carriers) <= alert.extreme.max_flight_legs
        assert "AUH" not in o.hubs


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK  {name}")
    print("Tous les tests passent.")
