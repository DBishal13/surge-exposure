import pandas as pd

from surge_exposure.data import nfip


def test_build_filter_single_county():
    assert nfip._build_filter("FL", ["12071"]) == "state eq 'FL' and (countyCode eq '12071')"


def test_build_filter_multiple_counties():
    assert (
        nfip._build_filter("FL", ["12071", "12015"])
        == "state eq 'FL' and (countyCode eq '12071' or countyCode eq '12015')"
    )


def test_snap_to_grid_rounds_to_one_decimal():
    df = pd.DataFrame({"latitude": [26.442, 26.449, 26.451], "longitude": [-81.951, -81.955, -81.960]})
    out = nfip.snap_to_grid(df)
    assert out["grid_lat"].tolist() == [26.4, 26.4, 26.5]
    assert out["grid_lon"].tolist() == [-82.0, -82.0, -82.0]


def test_get_claims_paginates_and_concatenates(monkeypatch):
    page1 = [{"state": "FL", "countyCode": "12071", "latitude": 26.4, "longitude": -82.0} for _ in range(nfip.PAGE_SIZE)]
    page2 = [{"state": "FL", "countyCode": "12071", "latitude": 26.5, "longitude": -81.9}]
    pages = [page1, page2]

    class FakeResponse:
        def __init__(self, rows):
            self._rows = rows

        def raise_for_status(self):
            pass

        def json(self):
            return {"NfipClaims": self._rows}

    def fake_get(url, params=None, timeout=None):
        return FakeResponse(pages.pop(0))

    monkeypatch.setattr(nfip.httpx, "get", fake_get)

    result = nfip.get_claims(state="FL", county_codes=["12071"])

    assert len(result) == nfip.PAGE_SIZE + 1


def test_get_claims_respects_limit(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        top = params["$top"]
        rows = [{"state": "FL", "countyCode": "12071", "latitude": 26.4, "longitude": -82.0} for _ in range(top)]

        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"NfipClaims": rows}

        return FakeResponse()

    monkeypatch.setattr(nfip.httpx, "get", fake_get)

    result = nfip.get_claims(state="FL", county_codes=["12071"], limit=150)

    assert len(result) == 150


def test_get_claims_drops_rows_missing_coordinates(monkeypatch):
    rows = [
        {"state": "FL", "countyCode": "12071", "latitude": 26.4, "longitude": -82.0},
        {"state": "FL", "countyCode": "12071", "latitude": None, "longitude": None},
    ]

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"NfipClaims": rows}

    def fake_get(url, params=None, timeout=None):
        return FakeResponse()

    monkeypatch.setattr(nfip.httpx, "get", fake_get)

    result = nfip.get_claims(state="FL", county_codes=["12071"], limit=2)

    assert len(result) == 1
