from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from karstlab.infrastructure.whitebox_adapter import WhiteboxAdapter, WhiteboxRunError


class FakeWhiteboxTools:
    def __init__(self, *, exit_code: int | None = 0, create_output: bool = True) -> None:
        self.exe_path = "/opt/whitebox/whitebox_tools"
        self.work_dir = ""
        self.exit_code = exit_code
        self.create_output = create_output
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
        self.call_work_dirs: list[str] = []

    def version(self) -> str:
        return "WhiteboxTools v2.4.0\nDetails"

    def breach_depressions_least_cost(
        self,
        dem: str,
        output: str,
        dist: int,
        max_cost: float | None = None,
        min_dist: bool = True,
        flat_increment: float | None = None,
        fill: bool = True,
        callback: object = None,
    ) -> int | None:
        return self._record(
            "breach_depressions_least_cost",
            dem,
            output,
            dist,
            max_cost=max_cost,
            min_dist=min_dist,
            flat_increment=flat_increment,
            fill=fill,
            callback=callback,
        )

    def fill_depressions(
        self,
        dem: str,
        output: str,
        fix_flats: bool = True,
        flat_increment: float | None = None,
        max_depth: float | None = None,
        callback: object = None,
    ) -> int | None:
        return self._record(
            "fill_depressions",
            dem,
            output,
            fix_flats=fix_flats,
            flat_increment=flat_increment,
            max_depth=max_depth,
            callback=callback,
        )

    def d8_pointer(
        self,
        dem: str,
        output: str,
        esri_pntr: bool = False,
        callback: object = None,
    ) -> int | None:
        return self._record("d8_pointer", dem, output, esri_pntr=esri_pntr, callback=callback)

    def d8_flow_accumulation(
        self,
        i: str,
        output: str,
        out_type: str = "cells",
        log: bool = False,
        clip: bool = False,
        pntr: bool = False,
        esri_pntr: bool = False,
        callback: object = None,
    ) -> int | None:
        return self._record(
            "d8_flow_accumulation",
            i,
            output,
            out_type=out_type,
            log=log,
            clip=clip,
            pntr=pntr,
            esri_pntr=esri_pntr,
            callback=callback,
        )

    def extract_streams(
        self,
        flow_accum: str,
        output: str,
        threshold: float,
        zero_background: bool = False,
        callback: object = None,
    ) -> int | None:
        return self._record(
            "extract_streams",
            flow_accum,
            output,
            threshold,
            zero_background=zero_background,
            callback=callback,
        )

    def _record(self, name: str, *args: object, **kwargs: object) -> int | None:
        self.calls.append((name, args, kwargs))
        self.call_work_dirs.append(self.work_dir)
        output = Path(str(args[1]))
        if not output.is_absolute() and self.work_dir:
            output = Path(self.work_dir) / output
        if self.create_output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(name, encoding="utf-8")
        return self.exit_code


def test_adapter_reports_executable_and_version() -> None:
    adapter = WhiteboxAdapter(tools=FakeWhiteboxTools())

    assert adapter.executable_path == Path("/opt/whitebox/whitebox_tools")
    assert adapter.work_dir == Path.cwd()
    assert adapter.version() == "WhiteboxTools v2.4.0"


def test_adapter_forwards_breach_depressions_parameters(tmp_path) -> None:  # type: ignore[no-untyped-def]
    tools = FakeWhiteboxTools()
    adapter = WhiteboxAdapter(tools=tools)
    dem = tmp_path / "dem.tif"
    messages: list[str] = []

    output = adapter.breach_depressions_least_cost(
        dem,
        tmp_path / "filled.tif",
        search_distance=50,
        max_cost=12.5,
        min_dist=False,
        flat_increment=0.001,
        fill=False,
        callback=messages.append,
    )

    assert output.exists()
    assert tools.calls == [
        (
            "breach_depressions_least_cost",
            (str(dem), str(output), 50),
            {
                "max_cost": 12.5,
                "min_dist": False,
                "flat_increment": 0.001,
                "fill": False,
                "callback": messages.append,
            },
        )
    ]


def test_flow_accumulation_uses_pointer_input(tmp_path) -> None:  # type: ignore[no-untyped-def]
    tools = FakeWhiteboxTools()
    adapter = WhiteboxAdapter(tools=tools)
    pointer = tmp_path / "d8_pointer.tif"

    adapter.flow_accumulation(pointer, tmp_path / "flow_accum.tif", out_type="sca")

    assert tools.calls[0][0] == "d8_flow_accumulation"
    assert tools.calls[0][2]["pntr"] is True
    assert tools.calls[0][2]["out_type"] == "sca"


def test_adapter_forwards_callbacks_to_each_tool(tmp_path) -> None:  # type: ignore[no-untyped-def]
    tools = FakeWhiteboxTools()
    adapter = WhiteboxAdapter(tools=tools)
    callback_messages: list[str] = []
    callback = callback_messages.append

    adapter.fill_depressions(tmp_path / "dem.tif", tmp_path / "filled.tif", callback=callback)
    adapter.d8_pointer(tmp_path / "filled.tif", tmp_path / "d8.tif", callback=callback)
    adapter.flow_accumulation(tmp_path / "d8.tif", tmp_path / "flow.tif", callback=callback)
    adapter.extract_streams(
        tmp_path / "flow.tif",
        tmp_path / "streams.tif",
        threshold=100.0,
        callback=callback,
    )

    assert [call[2]["callback"] for call in tools.calls] == [callback, callback, callback, callback]


def test_fill_depressions_uses_output_parent_work_dir_and_restores_original(tmp_path) -> None:  # type: ignore[no-untyped-def]
    tools = FakeWhiteboxTools()
    tools.work_dir = str(tmp_path / "original-work")
    adapter = WhiteboxAdapter(tools=tools)
    output = tmp_path / "filled" / "dem.tif"

    adapter.fill_depressions(tmp_path / "dem.tif", output)

    assert tools.call_work_dirs == [str(output.parent)]
    assert tools.work_dir == str(tmp_path / "original-work")


def test_fill_depressions_recovers_when_whitebox_uses_input_stem_as_output(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Whitebox sometimes ignores --output and writes <input_stem>.tif in work_dir.

    The adapter must detect that mismatch and rename to the requested output path.
    """

    class StemNamingWhiteboxTools(FakeWhiteboxTools):
        """Simulates Whitebox deriving the output name from the input DEM stem."""

        def fill_depressions(  # type: ignore[override]
            self,
            dem: str,
            output: str,
            fix_flats: bool = True,
            flat_increment: float | None = None,
            max_depth: float | None = None,
            callback: Callable[[str], None] | None = None,
        ) -> int | None:
            self.calls.append(("fill_depressions", (dem, output), {}))
            self.call_work_dirs.append(self.work_dir)
            # Write to <work_dir>/<input_stem>.tif, ignoring the output arg
            stem_output = Path(self.work_dir) / (Path(dem).stem + ".tif")
            stem_output.parent.mkdir(parents=True, exist_ok=True)
            stem_output.write_text("fill_depressions", encoding="utf-8")
            return 0

    dem = tmp_path / "source" / "survey.tif"
    dem.parent.mkdir()
    dem.write_text("fake dem", encoding="utf-8")

    output = tmp_path / "filled" / "dem_detection_filled.tif"
    tools = StemNamingWhiteboxTools()
    tools.work_dir = str(tmp_path / "original-work")
    adapter = WhiteboxAdapter(tools=tools)

    result = adapter.fill_depressions(dem, output)

    assert result == output
    assert output.exists()
    # stem candidate must have been consumed (renamed away)
    assert not (output.parent / "survey.tif").exists()


def test_adapter_raises_on_nonzero_exit_code(tmp_path) -> None:  # type: ignore[no-untyped-def]
    adapter = WhiteboxAdapter(tools=FakeWhiteboxTools(exit_code=1))

    with pytest.raises(WhiteboxRunError, match="exit code 1"):
        adapter.d8_pointer(tmp_path / "dem.tif", tmp_path / "d8.tif")


def test_adapter_raises_when_output_is_missing(tmp_path) -> None:  # type: ignore[no-untyped-def]
    adapter = WhiteboxAdapter(tools=FakeWhiteboxTools(create_output=False))

    with pytest.raises(WhiteboxRunError, match="did not create expected output"):
        adapter.d8_pointer(tmp_path / "dem.tif", tmp_path / "d8.tif")
