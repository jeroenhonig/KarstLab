from __future__ import annotations

import numpy as np
import pytest
from rasterio.transform import from_origin

from karstlab.business.dolines import DolineDetectionParams, DolineDetector, detect_dolines
from karstlab.data.schemas import DepthConfidence
from tests.fixtures.synthetic_dem import (
    SYNTHETIC_DEM_CRS,
    SYNTHETIC_DEM_NODATA,
    SYNTHETIC_DEM_TRANSFORM,
    synthetic_dem_array,
)


def test_detect_dolines_finds_three_known_synthetic_depressions() -> None:
    original = synthetic_dem_array()
    filled = original.copy()
    filled[20:28, 20:28] += 4.0
    filled[50:62, 44:58] += 7.5
    filled[72:80, 70:86] += 2.0

    depressions = detect_dolines(
        original,
        filled,
        transform=SYNTHETIC_DEM_TRANSFORM,
        crs=SYNTHETIC_DEM_CRS,
        nodata=SYNTHETIC_DEM_NODATA,
    )

    assert len(depressions) == 3
    assert [depression.id for depression in depressions] == [
        "doline-0001",
        "doline-0002",
        "doline-0003",
    ]
    assert sorted(depression.max_depth_m for depression in depressions) == [2.0, 4.0, 7.5]
    assert sorted(depression.area_m2 for depression in depressions) == [64.0, 128.0, 168.0]
    assert all(depression.geometry["type"] == "Polygon" for depression in depressions)
    assert all(-90.0 <= depression.centroid.lat <= 90.0 for depression in depressions)
    assert all(-180.0 <= depression.centroid.lon <= 180.0 for depression in depressions)


def test_detect_dolines_applies_depth_and_area_filters() -> None:
    original = np.zeros((10, 10), dtype=np.float32)
    filled = original.copy()
    filled[1:3, 1:3] = 0.2
    filled[4:8, 4:8] = 5.0

    depressions = detect_dolines(
        original,
        filled,
        transform=from_origin(0.0, 10.0, 1.0, 1.0),
        params=DolineDetectionParams(min_depth_m=1.0, max_depth_m=10.0, min_area_m2=5.0),
    )

    assert len(depressions) == 1
    assert depressions[0].max_depth_m == 5.0
    assert depressions[0].area_m2 == 16.0


def test_detect_dolines_sets_edge_and_nodata_quality_flags() -> None:
    original = np.zeros((8, 8), dtype=np.float32)
    filled = original.copy()
    filled[0:2, 0:2] = 1.0
    original[2, 2] = SYNTHETIC_DEM_NODATA
    filled[2, 2] = SYNTHETIC_DEM_NODATA

    depressions = detect_dolines(
        original,
        filled,
        transform=from_origin(0.0, 8.0, 1.0, 1.0),
        nodata=SYNTHETIC_DEM_NODATA,
    )

    assert len(depressions) == 1
    assert depressions[0].quality_flags.edge_proximity is True
    assert depressions[0].quality_flags.nodata_adjacent is True
    assert depressions[0].quality_flags.depth_confidence == DepthConfidence.MEDIUM


def test_detect_dolines_depth_confidence_thresholds() -> None:
    original = np.zeros((8, 8), dtype=np.float32)
    filled = original.copy()
    filled[1:3, 1:3] = 0.3
    filled[5:7, 5:7] = 2.5

    depressions = DolineDetector(
        params=DolineDetectionParams(min_depth_m=0.25, min_area_m2=1.0)
    ).detect(original, filled, transform=from_origin(0.0, 8.0, 1.0, 1.0))

    assert [depression.quality_flags.depth_confidence for depression in depressions] == [
        DepthConfidence.LOW,
        DepthConfidence.HIGH,
    ]


def test_detect_dolines_rejects_mismatched_shapes() -> None:
    with pytest.raises(ValueError, match="same shape"):
        detect_dolines(
            np.zeros((5, 5), dtype=np.float32),
            np.zeros((6, 5), dtype=np.float32),
            transform=from_origin(0.0, 5.0, 1.0, 1.0),
        )


def test_detect_dolines_rejects_non_2d_arrays() -> None:
    with pytest.raises(ValueError, match="2D array"):
        detect_dolines(
            np.zeros((2, 3, 4), dtype=np.float32),
            np.zeros((2, 3, 4), dtype=np.float32),
            transform=from_origin(0.0, 5.0, 1.0, 1.0),
        )
