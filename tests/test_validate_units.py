import numpy as np
import pandas as pd

from scripts.validate_units import aggregate, block_bootstrap_ci, is_sfha, morans_i, to_2020


def test_is_sfha_zones():
    zones = pd.Series(["AE", "VE", "A", "x", "X500", None, "AO", "D"])
    assert is_sfha(zones).tolist() == [True, True, True, False, False, False, True, False]


def test_to_2020_keeps_valid_codes_and_crosswalks_old_ones():
    valid = {"120710001001", "120710001002"}
    crosswalk = {"120719999991": "120710001002"}
    codes = pd.Series(["120710001001", "120719999991", "120710000000", None])
    out = to_2020(codes, crosswalk, valid).tolist()
    assert out[:2] == ["120710001001", "120710001002"]
    assert pd.isna(out[2]) and pd.isna(out[3])


def test_aggregate_rates_and_take_up():
    buildings = pd.DataFrame({
        "u": ["a"] * 4 + ["b"] * 2,
        "surge_ft": [0, 2, 4, 6, 0, 0],
        "lon": [0.0] * 6, "lat": [0.0] * 6,
    })
    claims = pd.DataFrame({
        "u": ["a", "a", "b"],
        "ian": [True] * 3,
        "ratedFloodZone": ["AE", "X", "X"],
        "damage_ratio": [0.5, np.nan, 0.1],
        "payout": [1000.0, 0.0, 200.0],
    })
    policies = pd.DataFrame({"u": ["a", "a", "b"], "ratedFloodZone": ["AE", "X", "X"], "policyCount": [3, 1, 2]})
    df = aggregate(buildings, claims, policies, "u").set_index("u")

    assert df.loc["a", "mean_surge_ft"] == 3.0
    assert df.loc["a", "share_surge_exposed"] == 0.75
    assert df.loc["a", "claim_rate"] == 2 / 4
    assert df.loc["a", "claim_rate_sfha"] == 1 / 3
    assert df.loc["a", "claim_rate_non_sfha"] == 1 / 1
    assert df.loc["a", "mean_damage_ratio"] == 0.5  # NaN damage ratio is skipped, not zero
    assert df.loc["b", "take_up"] == 2 / 2


def test_morans_i_detects_clustering():
    rng = np.random.default_rng(0)
    lon, lat = np.meshgrid(np.arange(20), np.arange(20))
    lon, lat = lon.ravel() * 0.01, lat.ravel() * 0.01
    clustered = lon + rng.normal(0, 0.001, lon.size)  # smooth west-east gradient
    noise = rng.normal(size=lon.size)
    assert morans_i(clustered, lon, lat)["I"] > 0.8
    assert morans_i(clustered, lon, lat)["p_perm"] < 0.01
    assert abs(morans_i(noise, lon, lat)["I"]) < 0.15


def test_block_bootstrap_ci_brackets_true_correlation_and_is_deterministic():
    rng = np.random.default_rng(1)
    x = rng.normal(size=300)
    y = 0.6 * x + rng.normal(scale=0.8, size=300)
    blocks = np.repeat(np.arange(30), 10)
    lo, hi = block_bootstrap_ci(x, y, blocks, "pearson", reps=400)
    r = np.corrcoef(x, y)[0, 1]
    assert lo < r < hi
    assert (lo, hi) == tuple(block_bootstrap_ci(x, y, blocks, "pearson", reps=400))
