"""Adapter around the WhiteboxTools Python wrapper."""

from __future__ import annotations

import os
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Protocol

# WhiteboxTools downloads its binary via HTTPS on first use. On macOS the
# bundled Python often lacks system root certificates, causing SSL failures.
# Point urllib at certifi's bundle when available so the download succeeds.
try:
    import certifi as _certifi

    os.environ.setdefault("SSL_CERT_FILE", _certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", _certifi.where())
except ModuleNotFoundError:
    pass

from whitebox.whitebox_tools import WhiteboxTools


class WhiteboxToolsLike(Protocol):
    exe_path: str
    work_dir: str

    def version(self) -> str: ...

    def breach_depressions_least_cost(
        self,
        dem: str,
        output: str,
        dist: int,
        max_cost: float | None = None,
        min_dist: bool = True,
        flat_increment: float | None = None,
        fill: bool = True,
        callback: Callable[[str], None] | None = None,
    ) -> int | None: ...

    def fill_depressions(
        self,
        dem: str,
        output: str,
        fix_flats: bool = True,
        flat_increment: float | None = None,
        max_depth: float | None = None,
        callback: Callable[[str], None] | None = None,
    ) -> int | None: ...

    def d8_pointer(
        self,
        dem: str,
        output: str,
        esri_pntr: bool = False,
        callback: Callable[[str], None] | None = None,
    ) -> int | None: ...

    def d8_flow_accumulation(
        self,
        i: str,
        output: str,
        out_type: str = "cells",
        log: bool = False,
        clip: bool = False,
        pntr: bool = False,
        esri_pntr: bool = False,
        callback: Callable[[str], None] | None = None,
    ) -> int | None: ...

    def extract_streams(
        self,
        flow_accum: str,
        output: str,
        threshold: float,
        zero_background: bool = False,
        callback: Callable[[str], None] | None = None,
    ) -> int | None: ...


class WhiteboxRunError(RuntimeError):
    """Raised when a WhiteboxTools command fails."""


_WORK_DIR_LOCK = Lock()


@dataclass(frozen=True)
class WhiteboxAdapter:
    """Thin, testable wrapper for WhiteboxTools hydrology commands."""

    tools: WhiteboxToolsLike

    @classmethod
    def create(
        cls,
        *,
        executable_path: Path | None = None,
        work_dir: Path | None = None,
    ) -> WhiteboxAdapter:
        tools = WhiteboxTools()
        if executable_path is not None:
            tools.exe_path = str(executable_path)
        if work_dir is not None:
            tools.work_dir = str(work_dir)
        # Use every available core for the multi-threaded WhiteboxTools commands
        # (flow accumulation, breaching, etc.). -1 means "all cores"; set it
        # explicitly so the analysis is not left on a conservative default.
        set_max_procs = getattr(tools, "set_max_procs", None)
        if callable(set_max_procs):
            set_max_procs(-1)
        return cls(tools=tools)

    @property
    def executable_path(self) -> Path:
        return Path(self.tools.exe_path)

    @property
    def work_dir(self) -> Path:
        return Path(self.tools.work_dir) if self.tools.work_dir else Path.cwd()

    def version(self) -> str:
        return self.tools.version().splitlines()[0]

    def breach_depressions_least_cost(
        self,
        dem_path: Path,
        output_path: Path,
        *,
        search_distance: int = 100,
        max_cost: float | None = None,
        min_dist: bool = True,
        flat_increment: float | None = None,
        fill: bool = True,
        callback: Callable[[str], None] | None = None,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result = self.tools.breach_depressions_least_cost(
            str(dem_path),
            str(output_path),
            search_distance,
            max_cost=max_cost,
            min_dist=min_dist,
            flat_increment=flat_increment,
            fill=fill,
            callback=callback,
        )
        return self._checked_output("breach_depressions_least_cost", result, output_path)

    def fill_depressions(
        self,
        dem_path: Path,
        output_path: Path,
        *,
        fix_flats: bool = True,
        flat_increment: float | None = None,
        max_depth: float | None = None,
        callback: Callable[[str], None] | None = None,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with self._temporary_work_dir(output_path.parent):
            result = self.tools.fill_depressions(
                str(dem_path),
                output_path.name,
                fix_flats=fix_flats,
                flat_increment=flat_increment,
                max_depth=max_depth,
                callback=callback,
            )
        # Some Whitebox versions ignore --output and write the output using the
        # input DEM stem as the filename (e.g. "dem.tif" instead of the requested
        # name). Detect and rename so _checked_output finds the expected path.
        if result in (0, None) and not output_path.exists():
            stem_candidate = output_path.parent / (Path(str(dem_path)).stem + ".tif")
            if stem_candidate.exists() and stem_candidate != output_path:
                stem_candidate.rename(output_path)
        return self._checked_output("fill_depressions", result, output_path)

    def d8_pointer(
        self,
        dem_path: Path,
        output_path: Path,
        *,
        esri_pointer: bool = False,
        callback: Callable[[str], None] | None = None,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result = self.tools.d8_pointer(
            str(dem_path),
            str(output_path),
            esri_pntr=esri_pointer,
            callback=callback,
        )
        return self._checked_output("d8_pointer", result, output_path)

    def flow_accumulation(
        self,
        pointer_path: Path,
        output_path: Path,
        *,
        out_type: str = "cells",
        log: bool = False,
        clip: bool = False,
        esri_pointer: bool = False,
        callback: Callable[[str], None] | None = None,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result = self.tools.d8_flow_accumulation(
            str(pointer_path),
            str(output_path),
            out_type=out_type,
            log=log,
            clip=clip,
            pntr=True,
            esri_pntr=esri_pointer,
            callback=callback,
        )
        return self._checked_output("d8_flow_accumulation", result, output_path)

    def extract_streams(
        self,
        flow_accumulation_path: Path,
        output_path: Path,
        *,
        threshold: float,
        zero_background: bool = False,
        callback: Callable[[str], None] | None = None,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result = self.tools.extract_streams(
            str(flow_accumulation_path),
            str(output_path),
            threshold,
            zero_background=zero_background,
            callback=callback,
        )
        return self._checked_output("extract_streams", result, output_path)

    def _checked_output(self, tool_name: str, result: int | None, output_path: Path) -> Path:
        if result not in (0, None):
            raise WhiteboxRunError(f"{tool_name} failed with exit code {result}")
        if not output_path.exists():
            raise WhiteboxRunError(f"{tool_name} did not create expected output: {output_path}")
        return output_path

    @contextmanager
    def _temporary_work_dir(self, work_dir: Path):  # type: ignore[no-untyped-def]
        with _WORK_DIR_LOCK:
            original_work_dir = self.tools.work_dir
            self.tools.work_dir = str(work_dir)
            try:
                yield
            finally:
                self.tools.work_dir = original_work_dir
