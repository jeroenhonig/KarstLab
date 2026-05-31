"""Scientific DEM validation before terrain analysis."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import numpy as np
import rasterio
from rasterio.errors import RasterioIOError


class ValidationSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class DemValidationIssue:
    check_id: str
    severity: ValidationSeverity
    message: str
    remediation: str


@dataclass(frozen=True)
class DemValidationResult:
    path: Path
    issues: tuple[DemValidationIssue, ...]

    @property
    def errors(self) -> tuple[DemValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == ValidationSeverity.ERROR)

    @property
    def warnings(self) -> tuple[DemValidationIssue, ...]:
        return tuple(
            issue for issue in self.issues if issue.severity == ValidationSeverity.WARNING
        )

    @property
    def is_valid(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class DEMValidator:
    min_resolution_m: float = 0.1
    max_resolution_m: float = 50.0
    max_nodata_fraction: float = 0.25
    required_disk_multiplier: float = 4.0

    def validate(self, path: Path) -> DemValidationResult:
        issues: list[DemValidationIssue] = []

        if not path.exists():
            return DemValidationResult(
                path=path,
                issues=(
                    _error(
                        "format",
                        f"DEM file does not exist: {path}",
                        "Choose an existing GeoTIFF DEM file.",
                    ),
                ),
            )

        try:
            with rasterio.open(path) as dataset:
                issues.extend(self._validate_dataset(path, dataset))
        except (RasterioIOError, ValueError) as exc:
            issues.append(
                _error(
                    "format",
                    f"DEM file cannot be opened as a raster: {exc}",
                    "Use a valid GeoTIFF, VRT, or raster format supported by GDAL.",
                )
            )

        issues.extend(self._validate_filename(path))
        issues.extend(self._validate_disk_space(path))
        return DemValidationResult(path=path, issues=tuple(issues))

    def _validate_dataset(
        self,
        path: Path,
        dataset: rasterio.io.DatasetReader,
    ) -> list[DemValidationIssue]:
        issues: list[DemValidationIssue] = []

        if dataset.count < 1:
            issues.append(
                _error("band_count", "DEM contains no raster bands.", "Use a single-band DEM.")
            )
            return issues
        if dataset.count > 1:
            issues.append(
                _warning(
                    "band_count",
                    f"DEM contains {dataset.count} bands; KarstLab will use band 1.",
                    "Prefer a single-band bare-earth elevation raster.",
                )
            )

        if dataset.crs is None:
            issues.append(
                _error(
                    "crs",
                    "DEM is missing CRS metadata.",
                    "Assign the correct projected CRS before analysis.",
                )
            )
        elif not dataset.crs.is_projected:
            issues.append(
                _error(
                    "crs",
                    f"DEM CRS is not projected: {dataset.crs}.",
                    "Reproject the DEM to a metric projected CRS before analysis.",
                )
            )
        else:
            linear_units = dataset.crs.linear_units or ""
            if linear_units.lower() not in {"metre", "meter", "metres", "meters"}:
                issues.append(
                    _warning(
                        "vertical_unit",
                        f"CRS horizontal unit is {linear_units!r}; metric units are expected.",
                        "Use a metre-based projected CRS for reliable area and depth thresholds.",
                    )
                )
            if not _has_vertical_metadata(dataset):
                issues.append(
                    _warning(
                        "vertical_datum",
                        "Vertical datum is not specified in raster metadata.",
                        "Confirm the DEM elevations use metres and a suitable vertical datum.",
                    )
                )

        dtype = dataset.dtypes[0]
        if not np.issubdtype(np.dtype(dtype), np.number):
            issues.append(
                _error(
                    "data_type",
                    f"DEM band has non-numeric dtype: {dtype}.",
                    "Use a numeric elevation raster.",
                )
            )
        elif np.dtype(dtype).itemsize < 2:
            issues.append(
                _warning(
                    "data_type",
                    f"DEM band dtype {dtype} has low precision for elevation analysis.",
                    "Use Int16, Float32, or Float64 elevation data.",
                )
            )

        xres, yres = dataset.res
        if xres <= 0 or yres <= 0:
            issues.append(
                _error(
                    "resolution",
                    f"DEM has invalid resolution: {dataset.res}.",
                    "Use a raster with positive pixel size.",
                )
            )
        elif min(xres, yres) < self.min_resolution_m or max(xres, yres) > self.max_resolution_m:
            issues.append(
                _warning(
                    "resolution",
                    f"DEM resolution {dataset.res} is outside the expected lidar range.",
                    f"Use DEMs between {self.min_resolution_m:g}m and {self.max_resolution_m:g}m.",
                )
            )

        if dataset.nodata is None:
            issues.append(
                _error(
                    "nodata",
                    "DEM is missing a NoData value.",
                    "Set a NoData value before running WhiteboxTools hydrology.",
                )
            )
            return issues

        array = dataset.read(1)
        nodata_mask = np.isnan(array) if np.isnan(dataset.nodata) else array == dataset.nodata
        nodata_fraction = float(np.count_nonzero(nodata_mask)) / float(array.size)
        if nodata_fraction > self.max_nodata_fraction:
            issues.append(
                _warning(
                    "nodata_coverage",
                    f"NoData covers {nodata_fraction:.1%} of the DEM.",
                    "Check tile coverage and fill missing regions if needed.",
                )
            )

        if _touches_edge(nodata_mask):
            issues.append(
                _warning(
                    "edge_artifacts",
                    "NoData touches one or more DEM edges.",
                    "Inspect tile edges; edge artifacts can affect depression detection.",
                )
            )

        return issues

    def _validate_filename(self, path: Path) -> list[DemValidationIssue]:
        lower_name = path.name.lower()
        issues: list[DemValidationIssue] = []
        if any(token in lower_name for token in ("dsm", "mns", "surface")):
            issues.append(
                _warning(
                    "dsm_detection",
                    "Filename suggests this may be a DSM/surface model rather than a DEM/MNT.",
                    "Use a bare-earth DEM/MNT for karst depression analysis.",
                )
            )
        if any(token in lower_name for token in ("filled", "breached", "hydro")):
            issues.append(
                _warning(
                    "hydro_preconditioning",
                    "Filename suggests this DEM may already be hydrologically preconditioned.",
                    "Use the original DEM if you want KarstLab to detect natural depressions.",
                )
            )
        return issues

    def _validate_disk_space(self, path: Path) -> list[DemValidationIssue]:
        free_bytes = shutil.disk_usage(path.parent).free
        required_bytes = int(path.stat().st_size * self.required_disk_multiplier)
        if free_bytes < required_bytes:
            return [
                _error(
                    "disk_space",
                    "Available disk space is too low for expected pipeline outputs.",
                    "Free disk space or choose a project directory on a larger volume.",
                )
            ]
        return []


def _has_vertical_metadata(dataset: rasterio.io.DatasetReader) -> bool:
    tags = {key.lower(): str(value).lower() for key, value in dataset.tags().items()}
    return any("vertical" in key or "vertical" in value for key, value in tags.items())


def _touches_edge(mask: np.ndarray) -> bool:
    return bool(
        np.any(mask[0, :])
        or np.any(mask[-1, :])
        or np.any(mask[:, 0])
        or np.any(mask[:, -1])
    )


def _error(check_id: str, message: str, remediation: str) -> DemValidationIssue:
    return DemValidationIssue(
        check_id=check_id,
        severity=ValidationSeverity.ERROR,
        message=message,
        remediation=remediation,
    )


def _warning(check_id: str, message: str, remediation: str) -> DemValidationIssue:
    return DemValidationIssue(
        check_id=check_id,
        severity=ValidationSeverity.WARNING,
        message=message,
        remediation=remediation,
    )
