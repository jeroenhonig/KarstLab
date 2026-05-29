from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from karstlab.business.hydrology import HydrologyAnalyzer


class FakeWhiteboxAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Path, Path, dict[str, object]]] = []

    def breach_depressions_least_cost(
        self,
        dem_path: Path,
        output_path: Path,
        *,
        callback: Callable[[str], None] | None = None,
    ) -> Path:
        if callback is not None:
            callback("breach")
        return self._write("breach_depressions_least_cost", dem_path, output_path)

    def d8_pointer(
        self,
        dem_path: Path,
        output_path: Path,
        *,
        callback: Callable[[str], None] | None = None,
    ) -> Path:
        if callback is not None:
            callback("pointer")
        return self._write("d8_pointer", dem_path, output_path)

    def flow_accumulation(
        self,
        pointer_path: Path,
        output_path: Path,
        *,
        callback: Callable[[str], None] | None = None,
    ) -> Path:
        if callback is not None:
            callback("accumulation")
        return self._write("flow_accumulation", pointer_path, output_path)

    def extract_streams(
        self,
        flow_accumulation_path: Path,
        output_path: Path,
        *,
        threshold: float,
        zero_background: bool,
        callback: Callable[[str], None] | None = None,
    ) -> Path:
        if callback is not None:
            callback("streams")
        return self._write(
            "extract_streams",
            flow_accumulation_path,
            output_path,
            {"threshold": threshold, "zero_background": zero_background},
        )

    def _write(
        self,
        name: str,
        input_path: Path,
        output_path: Path,
        options: dict[str, object] | None = None,
    ) -> Path:
        self.calls.append((name, input_path, output_path, options or {}))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(name, encoding="utf-8")
        return output_path


def test_hydrology_run_creates_expected_pipeline_outputs(tmp_path) -> None:  # type: ignore[no-untyped-def]
    whitebox = FakeWhiteboxAdapter()
    analyzer = HydrologyAnalyzer(whitebox=whitebox)
    dem = tmp_path / "input" / "dem.tif"

    outputs = analyzer.run(dem, tmp_path / "output" / "rasters", stream_threshold=100.0)

    assert outputs.filled_dem == tmp_path / "output" / "rasters" / "dem_filled.tif"
    assert outputs.d8_pointer == tmp_path / "output" / "rasters" / "d8_pointer.tif"
    assert outputs.flow_accumulation == tmp_path / "output" / "rasters" / "flow_accum.tif"
    assert outputs.streams == tmp_path / "output" / "rasters" / "streams.tif"
    assert [call[0] for call in whitebox.calls] == [
        "breach_depressions_least_cost",
        "d8_pointer",
        "flow_accumulation",
        "extract_streams",
    ]
    assert whitebox.calls[-1][3] == {"threshold": 100.0, "zero_background": True}


def test_hydrology_run_forwards_progress_callback(tmp_path) -> None:  # type: ignore[no-untyped-def]
    whitebox = FakeWhiteboxAdapter()
    analyzer = HydrologyAnalyzer(whitebox=whitebox)
    messages: list[str] = []

    analyzer.run(
        tmp_path / "input" / "dem.tif",
        tmp_path / "output" / "rasters",
        stream_threshold=100.0,
        callback=messages.append,
    )

    assert messages == ["breach", "pointer", "accumulation", "streams"]
