"""Hydrology analysis orchestration backed by WhiteboxTools."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from karstlab.infrastructure.whitebox_adapter import WhiteboxAdapter


@dataclass(frozen=True)
class HydrologyOutputs:
    filled_dem: Path
    d8_pointer: Path
    flow_accumulation: Path
    streams: Path


@dataclass(frozen=True)
class HydrologyAnalyzer:
    whitebox: WhiteboxAdapter

    def fill_dem(self, dem_path: Path, output_path: Path) -> Path:
        return self.whitebox.breach_depressions_least_cost(dem_path, output_path)

    def d8_pointer(self, dem_path: Path, output_path: Path) -> Path:
        return self.whitebox.d8_pointer(dem_path, output_path)

    def flow_accumulation(self, pointer_path: Path, output_path: Path) -> Path:
        return self.whitebox.flow_accumulation(pointer_path, output_path)

    def extract_streams(
        self,
        flow_accumulation_path: Path,
        output_path: Path,
        *,
        threshold: float,
    ) -> Path:
        return self.whitebox.extract_streams(
            flow_accumulation_path,
            output_path,
            threshold=threshold,
            zero_background=True,
        )

    def run(
        self,
        dem_path: Path,
        output_dir: Path,
        *,
        stream_threshold: float,
    ) -> HydrologyOutputs:
        output_dir.mkdir(parents=True, exist_ok=True)
        filled_dem = self.fill_dem(dem_path, output_dir / "dem_filled.tif")
        pointer = self.d8_pointer(filled_dem, output_dir / "d8_pointer.tif")
        accumulation = self.flow_accumulation(pointer, output_dir / "flow_accum.tif")
        streams = self.extract_streams(
            accumulation,
            output_dir / "streams.tif",
            threshold=stream_threshold,
        )
        return HydrologyOutputs(
            filled_dem=filled_dem,
            d8_pointer=pointer,
            flow_accumulation=accumulation,
            streams=streams,
        )
