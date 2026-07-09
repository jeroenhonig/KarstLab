"""Background analysis worker for KarstLab pipeline execution."""

from __future__ import annotations

import traceback
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from karstlab.data.land_profiles import load_land_profile
from karstlab.data.project_io import canonical_output_paths, create_project, save_project
from karstlab.data.schemas import AnalysisParams, PipelineResult, ProjectFile

AnalysisRunner = Callable[[ProjectFile, Callable[[str], None] | None], PipelineResult]


class AnalysisCancelled(BaseException):
    """Raised when the GUI requests cooperative analysis cancellation.

    Subclasses ``BaseException`` (not ``Exception``) so the broad
    ``except Exception`` / ``except RuntimeError`` guards in the business
    pipeline (e.g. the WhiteboxTools fill fallback) do not swallow it — a
    cancel must propagate straight up to ``run()``.
    """


class AnalysisWorker(QObject):
    """Run analysis off the UI thread and report progress through Qt signals."""

    progress = Signal(str)
    finished = Signal(object, object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        *,
        dem_paths: list[Path],
        project_base_dir: Path,
        project_name: str,
        profile_id: str,
        analysis_params: AnalysisParams,
        marker_paths: Sequence[Path] = (),
        fault_lines_path: Path | None = None,
        caveline_path: Path | None = None,
        caveline_downstream_end: str = "first",
        runner: AnalysisRunner | None = None,
        force_recompute: bool = False,
    ) -> None:
        super().__init__()
        self._dem_paths = dem_paths
        self._project_base_dir = project_base_dir
        self._project_name = project_name
        self._profile_id = profile_id
        self._analysis_params = analysis_params
        self._marker_paths = list(marker_paths)
        self._fault_lines_path = fault_lines_path
        self._caveline_path = caveline_path
        self._caveline_downstream_end = caveline_downstream_end
        self._runner = runner
        self._force_recompute = force_recompute

    def run(self) -> None:
        from karstlab.presentation.main_window import _default_analysis_runner

        project: ProjectFile | None = None
        try:
            profile = load_land_profile(self._profile_id)
            project = create_project(
                base_dir=self._project_base_dir,
                name=self._project_name,
                land_profile=profile.id,
                crs_analysis=profile.default_crs,
                analysis_params=self._analysis_params,
                overwrite=True,
            )
            project = save_project(
                project.model_copy(
                    update={
                        "dem_paths": self._dem_paths,
                        "marker_paths": self._marker_paths,
                        "fault_lines_path": self._fault_lines_path,
                        "caveline_path": self._caveline_path,
                        "caveline_downstream_end": self._caveline_downstream_end,
                    }
                )
            )
            if self._runner is not None:
                result = self._runner(project, self._emit_progress)
            else:
                result = _default_analysis_runner(
                    project, self._emit_progress, force_recompute=self._force_recompute
                )
            project = save_project(
                project.model_copy(
                    update={
                        "last_pipeline_result": canonical_output_paths(project)[
                            "pipeline_result"
                        ]
                    }
                )
            )
        except AnalysisCancelled:
            # User-requested stop — not an error; report a clean cancellation.
            self.cancelled.emit()
            return
        except Exception as exc:  # noqa: BLE001 - surfaced as actionable GUI failure text.
            log_path = _write_failure_log(
                project=project,
                fallback_dir=self._project_base_dir,
                project_name=self._project_name,
                error=exc,
            )
            self.failed.emit(f"{exc}\n\nLog: {log_path}")
            return

        self.finished.emit(result, project)

    def _emit_progress(self, message: str) -> None:
        if QThread.currentThread().isInterruptionRequested():
            raise AnalysisCancelled("Analysis cancelled by user")
        self.progress.emit(message)


def _write_failure_log(
    *,
    project: ProjectFile | None,
    fallback_dir: Path,
    project_name: str,
    error: Exception,
) -> Path:
    logs_dir = project.logs_dir if project is not None else fallback_dir / "_logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    safe_name = "".join(char if char.isalnum() or char in "-_" else "-" for char in project_name)
    path = logs_dir / f"analysis-error-{safe_name or 'project'}-{timestamp}.log"
    path.write_text(
        "".join(traceback.format_exception(type(error), error, error.__traceback__)),
        encoding="utf-8",
    )
    return path


__all__ = ["AnalysisCancelled", "AnalysisRunner", "AnalysisWorker", "_write_failure_log"]
