"""Shared Pydantic contracts for KarstLab projects, profiles, and results."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


class StrictModel(BaseModel):
    """Base model that rejects unknown fields to keep persisted contracts explicit."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Locale(StrEnum):
    EN = "en"
    NL = "nl"
    FR = "fr"


class DepthConfidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PipelineStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class GeometryType(StrEnum):
    POINT = "Point"
    LINE_STRING = "LineString"
    POLYGON = "Polygon"
    MULTI_POLYGON = "MultiPolygon"


class LayerType(StrEnum):
    TILE = "tile"
    WMTS = "wmts"
    WMS = "wms"


class PoiSourceType(StrEnum):
    GEOJSON = "geojson"
    CSV = "csv"
    WFS = "wfs"
    BRGM_CAVITES = "brgm_cavites"
    SPELEBASE = "spelebase"


class LocalizedText(StrictModel):
    en: str = Field(min_length=1)
    nl: str | None = Field(default=None, min_length=1)
    fr: str | None = Field(default=None, min_length=1)


class Coordinate(StrictModel):
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)


class BoundingBox(StrictModel):
    min_x: float
    min_y: float
    max_x: float
    max_y: float
    crs: str = Field(pattern=r"^EPSG:\d+$")

    @model_validator(mode="after")
    def validate_extent(self) -> BoundingBox:
        if self.min_x >= self.max_x:
            raise ValueError("min_x must be smaller than max_x")
        if self.min_y >= self.max_y:
            raise ValueError("min_y must be smaller than max_y")
        return self


class AnalysisParams(StrictModel):
    contour_interval_m: float = Field(default=5.0, gt=0.0)
    stream_threshold_cells: int = Field(default=1000, gt=0)
    doline_min_depth_m: float = Field(default=0.25, ge=0.0)
    doline_max_depth_m: float = Field(default=40.0, gt=0.0)
    doline_min_area_m2: float = Field(default=1.0, ge=0.0)
    doline_max_area_m2: float = Field(default=60000.0, gt=0.0)

    @model_validator(mode="after")
    def validate_ranges(self) -> AnalysisParams:
        if self.doline_min_depth_m >= self.doline_max_depth_m:
            raise ValueError("doline_min_depth_m must be smaller than doline_max_depth_m")
        if self.doline_min_area_m2 >= self.doline_max_area_m2:
            raise ValueError("doline_min_area_m2 must be smaller than doline_max_area_m2")
        return self


class DemSource(StrictModel):
    name: str = Field(min_length=1)
    url: HttpUrl
    description: LocalizedText
    resolution_m: float = Field(gt=0.0)


class LayerConfig(StrictModel):
    name: str = Field(min_length=1)
    type: LayerType
    url: HttpUrl
    layer: str | None = Field(default=None, min_length=1)
    opacity: float | None = Field(default=None, ge=0.0, le=1.0)
    attribution: str | None = None

    @model_validator(mode="after")
    def validate_layer_name(self) -> LayerConfig:
        if self.type in {LayerType.WMS, LayerType.WMTS} and self.layer is None:
            raise ValueError("WMS and WMTS layers require a layer name")
        return self


class MapLayers(StrictModel):
    base: list[LayerConfig] = Field(min_length=1)
    overlays: list[LayerConfig] = Field(default_factory=list)


class PoiSource(StrictModel):
    name: str = Field(min_length=1)
    type: PoiSourceType
    path: str | None = Field(default=None, min_length=1)
    url: HttpUrl | None = None
    layer: str | None = Field(default=None, min_length=1)
    departmental: bool = False

    @model_validator(mode="after")
    def validate_location(self) -> PoiSource:
        if self.type in {PoiSourceType.GEOJSON, PoiSourceType.CSV} and self.path is None:
            raise ValueError("Static POI sources require path")
        if self.type not in {PoiSourceType.GEOJSON, PoiSourceType.CSV} and self.url is None:
            raise ValueError("Remote POI sources require url")
        return self


class LandProfile(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    name: LocalizedText
    default_crs: str = Field(pattern=r"^EPSG:\d+$")
    common_crs: list[str] = Field(min_length=1)
    dem_sources: list[DemSource] = Field(default_factory=list)
    map_layers: MapLayers
    poi_sources: list[PoiSource] = Field(default_factory=list)
    analysis_defaults: AnalysisParams

    @field_validator("common_crs")
    @classmethod
    def validate_common_crs(cls, value: list[str]) -> list[str]:
        for crs in value:
            if not crs.startswith("EPSG:") or not crs[5:].isdigit():
                raise ValueError("common_crs entries must use EPSG:<code> format")
        return value

    @model_validator(mode="after")
    def validate_default_crs_in_common_crs(self) -> LandProfile:
        if self.default_crs not in self.common_crs:
            raise ValueError("default_crs must be included in common_crs")
        return self


class DepressionQualityFlags(StrictModel):
    edge_proximity: bool = False
    nodata_adjacent: bool = False
    depth_confidence: DepthConfidence = DepthConfidence.MEDIUM
    shape_regularity: float | None = Field(default=None, ge=0.0, le=1.0)
    nested: bool = False


GeoJsonGeometry = dict[str, Any]
GeoJsonFeature = dict[str, Any]


class DepressionResult(StrictModel):
    id: str = Field(min_length=1)
    rank: int | None = Field(default=None, ge=1)
    max_depth_m: float = Field(ge=0.0)
    area_m2: float = Field(gt=0.0)
    centroid: Coordinate
    geometry: GeoJsonGeometry
    quality_flags: DepressionQualityFlags = Field(default_factory=DepressionQualityFlags)

    @field_validator("geometry")
    @classmethod
    def validate_geometry(cls, value: GeoJsonGeometry) -> GeoJsonGeometry:
        geometry_type = value.get("type")
        coordinates = value.get("coordinates")
        allowed = {item.value for item in GeometryType}
        if geometry_type not in allowed:
            raise ValueError(f"geometry.type must be one of {sorted(allowed)}")
        if coordinates is None:
            raise ValueError("geometry.coordinates is required")
        return value


class PipelineStepResult(StrictModel):
    step_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    status: PipelineStatus
    started_at: datetime | None = None
    finished_at: datetime | None = None
    output_paths: list[Path] = Field(default_factory=list)
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_error_state(self) -> PipelineStepResult:
        if self.status == PipelineStatus.FAILED and not self.error_message:
            raise ValueError("failed steps require error_message")
        return self


class PipelineResult(StrictModel):
    project_id: UUID
    status: PipelineStatus
    params: AnalysisParams
    input_dem_paths: list[Path] = Field(min_length=1)
    output_dir: Path
    depressions: list[DepressionResult] = Field(default_factory=list)
    top_depressions: list[DepressionResult] = Field(default_factory=list, max_length=25)
    steps: list[PipelineStepResult] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_pipeline_state(self) -> PipelineResult:
        if self.status == PipelineStatus.FAILED and not any(
            step.status == PipelineStatus.FAILED for step in self.steps
        ):
            raise ValueError("failed pipeline requires at least one failed step")
        return self


class ProjectFile(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    project_dir: Path
    input_dir: Path
    output_dir: Path
    export_dir: Path
    cache_dir: Path
    land_profile_id: str = Field(default="generic", pattern=r"^[a-z][a-z0-9_-]*$")
    language: Locale = Locale.EN
    settings: AnalysisParams = Field(default_factory=AnalysisParams)
    dem_paths: list[Path] = Field(default_factory=list)
    marker_paths: list[Path] = Field(default_factory=list)
    last_pipeline_result: Path | None = None


class UserSettings(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    language: Locale = Locale.EN
    default_land_profile_id: str = Field(default="generic", pattern=r"^[a-z][a-z0-9_-]*$")
    recent_projects: list[Path] = Field(default_factory=list, max_length=10)
    check_for_updates: bool = True
    whitebox_tools_path: Path | None = None
    default_analysis_params: AnalysisParams = Field(default_factory=AnalysisParams)
