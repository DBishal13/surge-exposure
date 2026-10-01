"""Regression tests for capped building samples (paper §5.3, review B4).

A first-N LIMIT returns rows in scan order. When that order is spatially
clustered, as it is over Overture's partitioned GeoParquet, the capped
sample covers only part of the area. sample="random" must not.
"""

import duckdb
import pytest

from surge_exposure.data.overture import limit_clause


def test_limit_clause_variants():
    assert limit_clause(None) == ""
    assert limit_clause(0, sample="random") == ""
    assert limit_clause(500) == "LIMIT 500"
    assert limit_clause(500, sample="random", seed=7) == "ORDER BY hash(id || '7') LIMIT 500"
    with pytest.raises(ValueError):
        limit_clause(500, sample="stratified")


def _clustered_table(con: duckdb.DuckDBPyConnection, n: int = 2000) -> None:
    # Buildings spread evenly across x in [0, 1), but inserted in x order, so
    # "the first rows" all come from the west edge of the cell.
    con.execute(
        f"CREATE TABLE b AS SELECT 'bldg-' || i::VARCHAR AS id, i / {n}::DOUBLE AS x FROM range({n}) t(i)"
    )


def _sample_xs(con, sample: str, seed: int = 42, limit: int = 200) -> list[float]:
    sql = f"SELECT x FROM b {limit_clause(limit, sample, seed)}"
    return [r[0] for r in con.execute(sql).fetchall()]


def test_first_n_is_spatially_biased_but_random_sample_is_not():
    con = duckdb.connect()
    _clustered_table(con)

    first = _sample_xs(con, "first")
    random = _sample_xs(con, "random")

    # first-N: every sampled building comes from the westmost 10% of the cell
    assert max(first) < 0.1
    # random: the sample spans the cell and its mean sits near the middle
    assert min(random) < 0.1 and max(random) > 0.9
    assert 0.4 < sum(random) / len(random) < 0.6


def test_random_sample_is_deterministic_per_seed():
    con = duckdb.connect()
    _clustered_table(con)
    assert _sample_xs(con, "random", seed=42) == _sample_xs(con, "random", seed=42)
    assert _sample_xs(con, "random", seed=42) != _sample_xs(con, "random", seed=43)
