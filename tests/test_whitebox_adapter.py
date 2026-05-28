from __future__ import annotations

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
        output = Path(str(args[1]))
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

    output = adapter.breach_depressions_least_cost(
        dem,
        tmp_path / "filled.tif",
        search_distance=50,
        max_cost=12.5,
        min_dist=False,
        flat_increment=0.001,
        fill=False,
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
                "callback": None,
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


def test_adapter_raises_on_nonzero_exit_code(tmp_path) -> None:  # type: ignore[no-untyped-def]
    adapter = WhiteboxAdapter(tools=FakeWhiteboxTools(exit_code=1))

    with pytest.raises(WhiteboxRunError, match="exit code 1"):
        adapter.d8_pointer(tmp_path / "dem.tif", tmp_path / "d8.tif")


def test_adapter_raises_when_output_is_missing(tmp_path) -> None:  # type: ignore[no-untyped-def]
    adapter = WhiteboxAdapter(tools=FakeWhiteboxTools(create_output=False))

    with pytest.raises(WhiteboxRunError, match="did not create expected output"):
        adapter.d8_pointer(tmp_path / "dem.tif", tmp_path / "d8.tif")
