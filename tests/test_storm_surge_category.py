import pytest

from surge_exposure.data.storm_surge import select_category_member

NAMES = [
    "US_SLOSH_MOM_Inundation_v4_20260617/",
    *[f"US_SLOSH_MOM_Inundation_v4_20260617/us_Category{c}_MOM_Inundation_HIGH.{ext}"
      for c in range(1, 6) for ext in ("tif", "tif.ovr", "tif.xml", "tfw")],
]


@pytest.mark.parametrize("category", [1, 2, 3, 4, 5])
def test_select_category_member_picks_the_requested_tif(category):
    assert select_category_member(NAMES, category).endswith(f"us_Category{category}_MOM_Inundation_HIGH.tif")


def test_select_category_member_rejects_missing_category():
    with pytest.raises(RuntimeError):
        select_category_member(NAMES, 6)
