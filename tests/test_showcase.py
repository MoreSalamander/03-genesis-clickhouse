"""The showcase queries — each must exercise its named engine feature and
replay offline from recorded fixtures, so the deep-dive capabilities are
provable with no credentials and no cluster.
"""
import os

os.environ.setdefault("GENESIS_MOCK", "1")

from fastapi.testclient import TestClient

from app.main import app
from app.showcase import SHOWCASE

FEATURE_MARKERS = {
    "cash_curves": "OVER w",
    "collapsing_window": "windowFunnel(",
    "revenue_quantiles": "quantiles(0.1",
    "franchise_fatigue_curves": "avgForEach(",
    "shock_attribution": "ASOF JOIN",
    "superlatives": "argMax(",
    "era_attribution_dict": "dictGetString(",
}


def test_every_showcase_query_carries_its_feature():
    for key, marker in FEATURE_MARKERS.items():
        assert marker in SHOWCASE[key]["sql"], f"{key} no longer exercises {marker}"
        assert SHOWCASE[key]["feature"], key
        assert SHOWCASE[key]["story"], key


def test_showcase_endpoint_replays_offline():
    client = TestClient(app)
    items = client.get("/api/showcase").json()
    assert len(items) == len(SHOWCASE)
    by_key = {i["key"]: i for i in items}
    for key in SHOWCASE:
        item = by_key[key]
        assert item["error"] is None, f"{key}: {item['error']}"
        assert item["row_count"] > 0, f"{key} returned no rows from fixtures"
        assert item["columns"], key


def test_collapsing_window_tells_the_story():
    """The 45-day home window exists ONLY in the PVOD era — the century's most
    famous structural break, recovered by windowFunnel from recorded data."""
    client = TestClient(app)
    items = {i["key"]: i for i in client.get("/api/showcase").json()}
    rows = items["collapsing_window"]["rows"]
    cols = items["collapsing_window"]["columns"]
    era_i, y_i, d45_i = cols.index("era"), cols.index("home_within_year"), cols.index("home_within_45_days")
    by_era = {r[era_i]: (r[y_i], r[d45_i]) for r in rows}
    assert by_era["golden_age"][0] == 0.0, "no home window existed in the golden age"
    assert by_era["home_video"][0] >= 0.9, "the video era put nearly everything in homes within a year"
    assert by_era["streaming_wars_covid"][1] >= 0.5, "the 45-day window is a COVID-era invention"
    assert all(v[1] == 0.0 for e, v in by_era.items() if e != "streaming_wars_covid"), \
        "a 45-day home window before 2020 would be an anachronism"
