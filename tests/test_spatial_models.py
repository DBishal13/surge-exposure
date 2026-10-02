import numpy as np

from scripts.spatial_models import dutilleul


def _grid(n_side=15):
    lon, lat = np.meshgrid(np.arange(n_side), np.arange(n_side))
    return lon.ravel() * 0.02 - 82.0, lat.ravel() * 0.02 + 26.5


def test_dutilleul_keeps_n_for_independent_noise():
    rng = np.random.default_rng(0)
    lon, lat = _grid()
    out = dutilleul(rng.normal(size=lon.size), rng.normal(size=lon.size), lon, lat)
    assert out["effective_n"] > 0.7 * lon.size


def test_dutilleul_shrinks_n_for_smooth_fields():
    rng = np.random.default_rng(1)
    lon, lat = _grid()
    x = lon + rng.normal(0, 0.01, lon.size)
    y = lon + lat + rng.normal(0, 0.01, lon.size)
    out = dutilleul(x, y, lon, lat)
    assert out["effective_n"] < 0.3 * lon.size
    assert out["p"] > 1e-6  # far less significant than a naive test with n=225 would claim
