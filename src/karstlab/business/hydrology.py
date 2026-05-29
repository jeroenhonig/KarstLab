"""Hydrology analysis orchestration backed by WhiteboxTools."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class HydrologyBackend(Protocol):
    def breach_depressions_least_cost(
        self,
        dem_path: Path,
        output_path: Path,
        *,
        callback: Callable[[str], None] | None = None,
    ) -> Path: ...

    def fill_depressions(
        self,
        dem_path: Path,
        output_path: Path,
        *,
        callback: Callable[[str], None] | None = None,
    ) -> Path: ...

    def d8_pointer(
        self,
        dem_path: Path,
        output_path: Path,
        *,
        callback: Callable[[str], None] | None = None,
    ) -> Path: ...

    def flow_accumulation(
        self,
        pointer_path: Path,
        output_path: Path,
        *,
        callback: Callable[[str], None] | None = None,
    ) -> Path: ...

    def extract_streams(
        self,
        flow_accumulation_path: Path,
        output_path: Path,
        *,
        threshold: float,
        zero_background: bool,
        callback: Callable[[str], None] | None = None,
    ) -> Path: ...


@dataclass(frozen=True)
class HydrologyOutputs:
    filled_dem: Path
    d8_pointer: Path
    flow_accumulation: Path
    streams: Path


@dataclass(frozen=True)
class HydrologyAnalyzer:
    whitebox: HydrologyBackend

    def fill_dem(
        self,
        dem_path: Path,
        output_path: Path,
        *,
        callback: Callable[[str], None] | None = None,
    ) -> Path:
        return self.whitebox.breach_depressions_least_cost(
            dem_path,
            output_path,
            callback=callback,
        )

    def d8_pointer(
        self,
        dem_path: Path,
        output_path: Path,
        *,
        callback: Callable[[str], None] | None = None,
    ) -> Path:
        return self.whitebox.d8_pointer(dem_path, output_path, callback=callback)

    def flow_accumulation(
        self,
        pointer_path: Path,
        output_path: Path,
        *,
        callback: Callable[[str], None] | None = None,
    ) -> Path:
        return self.whitebox.flow_accumulation(pointer_path, output_path, callback=callback)

    def extract_streams(
        self,
        flow_accumulation_path: Path,
        output_path: Path,
        *,
        threshold: float,
        callback: Callable[[str], None] | None = None,
    ) -> Path:
        return self.whitebox.extract_streams(
            flow_accumulation_path,
            output_path,
            threshold=threshold,
            zero_background=True,
            callback=callback,
        )

    def run(
        self,
        dem_path: Path,
        output_dir: Path,
        *,
        stream_threshold: float,
        callback: Callable[[str], None] | None = None,
    ) -> HydrologyOutputs:
        output_dir.mkdir(parents=True, exist_ok=True)
        filled_dem = self.fill_dem(dem_path, output_dir / "dem_filled.tif", callback=callback)
        pointer = self.d8_pointer(filled_dem, output_dir / "d8_pointer.tif", callback=callback)
        accumulation = self.flow_accumulation(
            pointer,
            output_dir / "flow_accum.tif",
            callback=callback,
        )
        streams = self.extract_streams(
            accumulation,
            output_dir / "streams.tif",
            threshold=stream_threshold,
            callback=callback,
        )
        return HydrologyOutputs(
            filled_dem=filled_dem,
            d8_pointer=pointer,
            flow_accumulation=accumulation,
            streams=streams,
        )
