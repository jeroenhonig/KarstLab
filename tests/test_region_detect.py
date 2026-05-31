from __future__ import annotations

from pathlib import Path

from rasterio.transform import from_origin

from karstlab.data.land_profiles import detect_land_profile
from karstlab.data.raster_io import save_geotiff
from tests.fixtures.synthetic_dem import synthetic_dem_array

_ASC = """ncols 2
nrows 2
xllcorner 700000
yllcorner 6600000
cellsize 1
NODATA_value -9999
250 250
250 250
"""


def _tif(path: Path, crs: str, origin: tuple[float, float]) -> Path:
    return save_geotiff(
        path,
        synthetic_dem_array(),
        crs=crs,
        transform=from_origin(origin[0], origin[1], 1.0, 1.0),
        nodata=-9999.0,
    )


def test_detect_france_from_national_crs(tmp_path: Path) -> None:
    tile = _tif(tmp_path / "fr.tif", "EPSG:2154", (700000.0, 6600000.0))
    assert detect_land_profile([tile]) == "fr"


def test_detect_belgium_from_national_crs(tmp_path: Path) -> None:
    tile = _tif(tmp_path / "be.tif", "EPSG:31370", (150000.0, 130000.0))
    assert detect_land_profile([tile]) == "be"


def test_detect_netherlands_from_national_crs(tmp_path: Path) -> None:
    tile = _tif(tmp_path / "nl.tif", "EPSG:28992", (150000.0, 450000.0))
    assert detect_land_profile([tile]) == "nl"


def test_detect_from_filename_hint_when_crs_absent(tmp_path: Path) -> None:
    # ESRI ASC has no embedded CRS; the LAMB93 filename token implies EPSG:2154.
    asc = tmp_path / "RGEALTI_1M_ASC_LAMB93-IGN69_0948_6678.asc"
    asc.write_text(_ASC, encoding="utf-8")
    assert detect_land_profile([asc]) == "fr"


def test_detect_shared_utm_crs_falls_back_to_bbox(tmp_path: Path) -> None:
    # UTM31 is shared; location (Belgium) must resolve via the bbox match.
    tile = _tif(tmp_path / "utm.tif", "EPSG:32631", (640000.0, 5635000.0))
    assert detect_land_profile([tile]) == "be"


def test_detect_returns_none_for_empty_and_unknown(tmp_path: Path) -> None:
    assert detect_land_profile([]) is None
    nameless = tmp_path / "tile.asc"
    nameless.write_text(_ASC, encoding="utf-8")
    # No embedded CRS and no filename hint → cannot determine region.
    assert detect_land_profile([nameless]) is None
