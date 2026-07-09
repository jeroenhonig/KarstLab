"""Results display widget for depression analysis results."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from karstlab.data.schemas import DepressionResult, PipelineResult, ProjectFile


class ResultsTab(QWidget):
    """Display analysis results in a top 25 table and full depression list."""

    depression_selected = Signal(str, float, float)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self._summary_label = QLabel(self.tr("No analysis results"))
        layout.addWidget(self._summary_label)

        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels(
            [
                self.tr("Rank"), self.tr("ID"), self.tr("Depth m"),
                self.tr("Area m²"), self.tr("Fault m"), self.tr("Lat/Lon"),
                self.tr("Flags"),
            ]
        )
        self._table.setSortingEnabled(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.itemSelectionChanged.connect(self._on_table_selection_changed)
        layout.addWidget(self._table)

        self._list_label = QLabel(self.tr("All depressions (0 total)"))
        layout.addWidget(self._list_label)

        self._list = QListWidget()
        self._list.itemSelectionChanged.connect(self._on_list_selection_changed)
        layout.addWidget(self._list)

    def display_results(
        self,
        result: PipelineResult | Sequence[DepressionResult],
        project: ProjectFile | None = None,
    ) -> None:
        """Display analysis results.

        Args:
            result: PipelineResult or sequence of DepressionResult objects.
            project: Optional ProjectFile for context.
        """
        depressions = (
            result.depressions if isinstance(result, PipelineResult) else list(result)
        )
        top = result.top_depressions if isinstance(result, PipelineResult) else list(result)

        self._summary_label.setText(
            self.tr("{0} depressions detected; {1} ranked results")
            .format(len(depressions), len(top))
        )

        # Disable sorting while populating, else setItem reorders rows mid-fill.
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(top))
        for row, depression in enumerate(top):
            rank_str = (
                str(depression.rank) if depression.rank is not None else str(row + 1)
            )
            fault = depression.distance_to_fault_m
            fault_str = "—" if fault is None else f"{fault:.0f}"
            values = [
                rank_str,
                depression.id,
                f"{depression.max_depth_m:.2f}",
                f"{depression.area_m2:.1f}",
                fault_str,
                f"{depression.centroid.lat:.6f}, {depression.centroid.lon:.6f}",
                self._format_flags(depression),
            ]

            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                # Numeric sort for the fault-distance column (rank by proximity).
                if col == 4 and fault is not None:
                    item.setData(Qt.ItemDataRole.DisplayRole, float(round(fault)))
                self._table.setItem(row, col, item)
        self._table.setSortingEnabled(True)

        self._list_label.setText(self.tr("All depressions ({0} total)").format(len(depressions)))
        self._list.clear()
        # Every depression gets a sequential number (matching the map's "All
        # depressions" layer) so the user can locate and jump to any of them,
        # not only the top-25 ranked ones. Selecting a row flies the map there.
        for number, depression in enumerate(depressions, start=1):
            rank_note = f" · rank #{depression.rank}" if depression.rank is not None else ""
            fault_note = (
                f" · fault {depression.distance_to_fault_m:.0f} m"
                if depression.distance_to_fault_m is not None
                else ""
            )
            coord = f"{depression.centroid.lat:.6f}, {depression.centroid.lon:.6f}"
            text = (
                f"#{number} — {depression.id} ({depression.max_depth_m:.2f} m) "
                f"@ {coord}{fault_note}{rank_note}"
            )
            list_item = QListWidgetItem(text)
            list_item.setData(Qt.ItemDataRole.UserRole, depression.id)
            list_item.setData(Qt.ItemDataRole.UserRole + 1, depression.centroid.lat)
            list_item.setData(Qt.ItemDataRole.UserRole + 2, depression.centroid.lon)
            self._list.addItem(list_item)

    def clear(self) -> None:
        """Reset to empty state."""
        self._summary_label.setText(self.tr("No analysis results"))
        self._table.setRowCount(0)
        self._list_label.setText(self.tr("All depressions (0 total)"))
        self._list.clear()

    @property
    def table(self) -> QTableWidget:
        """Return the top 25 results table for backward compatibility."""
        return self._table

    def _format_flags(self, depression: DepressionResult) -> str:
        """Format quality flags as a compact string."""
        flags = []
        if depression.quality_flags.edge_proximity:
            flags.append(self.tr("⚠ edge"))
        if depression.quality_flags.nodata_adjacent:
            flags.append(self.tr("⚠ nodata"))
        if depression.quality_flags.nested:
            flags.append(self.tr("⚠ nested"))
        if depression.quality_flags.depth_confidence.value == "low":
            flags.append(self.tr("↓ conf"))
        return " ".join(flags)

    def _on_table_selection_changed(self) -> None:
        """Emit depression_selected when a table row is selected."""
        indexes = self._table.selectionModel().selectedRows()
        if not indexes:
            return
        row = indexes[0].row()
        id_item = self._table.item(row, 1)
        latlon_item = self._table.item(row, 5)  # Lat/Lon column (after Fault m)
        if id_item is None or latlon_item is None:
            return
        lat_str, lon_str = latlon_item.text().split(", ")
        self.depression_selected.emit(id_item.text(), float(lat_str), float(lon_str))

    def _on_list_selection_changed(self) -> None:
        """Emit depression_selected when a list item is selected."""
        selected = self._list.selectedItems()
        if selected:
            item = selected[0]
            depression_id = item.data(Qt.ItemDataRole.UserRole)
            lat = item.data(Qt.ItemDataRole.UserRole + 1)
            lon = item.data(Qt.ItemDataRole.UserRole + 2)
            self.depression_selected.emit(depression_id, lat, lon)


__all__ = ["ResultsTab"]
