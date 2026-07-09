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
    COMPLETED = "completed"
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


class PoiType(StrEnum):
    CAVE = "cave"
    PERTE = "perte"
    RESURGENCE = "resurgence"
    UNKNOWN = "unknown"


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


class VectorLayerConfig(StrictModel):
    """A queryable vector overlay fetched from an OGC WFS (or compatible) service.

    Additive to the existing tile/WMS ``LayerConfig`` registry. Defaults match
    the observed French services (WFS 2.0, GeoJSON, Lambert-93 native). ``bake``
    controls whether the layer is fetched and embedded into the analysis map
    (small fixed analysis-context sets only) versus fetched on demand.
    """

    name: str = Field(min_length=1)
    url: HttpUrl
    typename: str = Field(min_length=1)
    service: Literal["wfs"] = "wfs"
    version: str = "2.0.0"
    output_format: str = "application/json"
    srs: str = Field(default="EPSG:2154", pattern=r"^EPSG:\d+$")
    bbox_filter: bool = True
    max_features: int = Field(default=5000, gt=0)
    cql_filter: str | None = None
    geometry_name: str = "geom"
    style: dict[str, Any] | None = None
    queryable: bool = True
    bake: bool = False
    attribution: str | None = None


class MapLayers(StrictModel):
    base: list[LayerConfig] = Field(min_length=1)
    overlays: list[LayerConfig] = Field(default_factory=list)
    vector_overlays: list[VectorLayerConfig] = Field(default_factory=list)


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
    # Approximate WGS84 extent [min_lon, min_lat, max_lon, max_lat] used to
    # auto-detect the region from DEM tile location. None = no geographic match.
    bbox_wgs84: tuple[float, float, float, float] | None = None
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


class DepressionResult(StrictModel):
    id: str = Field(min_length=1)
    rank: int | None = Field(default=None, ge=1)
    max_depth_m: float = Field(ge=0.0)
    area_m2: float = Field(gt=0.0)
    centroid: Coordinate
    geometry: GeoJsonGeometry
    quality_flags: DepressionQualityFlags = Field(default_factory=DepressionQualityFlags)
    # Distance from the depression centroid to the nearest mapped geological fault
    # (BDCharm50 structural lines), in metres; ``None`` when no fault layer is set.
    distance_to_fault_m: float | None = Field(default=None, ge=0.0)
    nearest_fault_type: str | None = None
    # Orientation of the nearest fault (folded bearing 0-180°) and its relation to
    # the cave line ("parallel"/"oblique"/"transverse") — a parallel fault is the
    # one a conduit most likely follows.
    nearest_fault_bearing_deg: float | None = Field(default=None, ge=0.0, le=180.0)
    fault_orientation: str | None = None

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
    warnings: list[str] = Field(default_factory=list)
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
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    land_profile: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    analysis_params: AnalysisParams
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
    schema_version: Literal["1.0.0"] = "1.0.0"
    pipeline_version: Literal["1.0.0"] = "1.0.0"
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    created: datetime = Field(default_factory=lambda: datetime.now(UTC))
    modified: datetime = Field(default_factory=lambda: datetime.now(UTC))
    project_dir: Path
    input_dir: Path
    output_dir: Path
    export_dir: Path
    map_dir: Path
    cache_dir: Path
    logs_dir: Path
    land_profile: str = Field(default="generic", pattern=r"^[a-z][a-z0-9_-]*$")
    crs_analysis: str = Field(pattern=r"^EPSG:\d+$")
    crs_display: str = Field(default="EPSG:4326", pattern=r"^EPSG:\d+$")
    language: Locale = Locale.EN
    analysis_params: AnalysisParams = Field(default_factory=AnalysisParams)
    dem_paths: list[Path] = Field(default_factory=list)
    marker_paths: list[Path] = Field(default_factory=list)
    # Optional local BDCharm50 fault dataset (shapefile, directory, or .zip) used
    # for the per-doline distance-to-nearest-fault analysis.
    fault_lines_path: Path | None = None
    # Optional known cave-survey line (GPX/KML). When set, the pipeline runs the
    # conduit-projection stage (doline alignment → corridor likelihood) to predict
    # where the cave continues from the survey's downstream end.
    caveline_path: Path | None = None
    # Which end of the survey line is the downstream terminus the corridor projects
    # FROM: "first" = survey start, "last" = survey end. Flips the projection sense.
    caveline_downstream_end: Literal["first", "last"] = "first"
    # Optional target points (e.g. a neighbouring cave entrance) that pull the
    # predicted conduit heading; used only when caveline_path is set.
    conduit_target_points: list[Coordinate] = Field(default_factory=list)
    last_pipeline_result: Path | None = None


class UserSettings(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    language: Locale = Locale.EN
    land_profile: str = Field(default="generic", pattern=r"^[a-z][a-z0-9_-]*$")
    recent_projects: list[Path] = Field(default_factory=list, max_length=10)
    update_check: bool = True
    whitebox_path: Path | None = None
    crs_override: str | None = Field(default=None, pattern=r"^EPSG:\d+$")
    large_dem_threshold_mb: int = Field(default=500, gt=0)
    last_project_dir: Path | None = None
    analysis_params: AnalysisParams = Field(default_factory=AnalysisParams)
    # Per-file colour overrides for imported markers, keyed by file name. Keeps
    # an imported KML/GPX at a stable, user-chosen colour across analyses.
    marker_colors: dict[str, str] = Field(default_factory=dict)
