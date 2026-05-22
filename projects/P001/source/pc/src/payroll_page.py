from __future__ import annotations

from calendar import monthrange
from pathlib import Path
import json
import re
import os
import subprocess
import sys

from PySide6.QtCore import QDate, Qt, Signal, QTimer, QPersistentModelIndex, QRect, QEvent, QObject, QPoint
from PySide6.QtGui import QColor, QBrush, QFont, QDoubleValidator, QPainter, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractItemDelegate,
    QApplication,
    QComboBox,
    QColorDialog,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextBrowser,
    QMenu,
    QSplitter,
    QStyledItemDelegate,
    QStyle,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QToolTip,
)

from PySide6.QtPrintSupport import QPrintDialog, QPrinter

from .state import AppState
from .widgets import Panel, PAGE_OUTER_MARGINS, PAGE_OUTER_SPACING, PAGE_INNER_MARGINS, PAGE_INNER_SPACING, StatCard
from .attendance_page import build_korean_holiday_map, HOLIDAY_SHORT_NAMES
from .payroll_slip_export import (
    build_payroll_slip_payload,
    build_payroll_slip_png_bytes,
    export_payroll_slip_image,
)


CATEGORY_ROWS = [("base", "기본"), ("over", "연장"), ("night", "심야")]
HOLIDAY_COLUMN_BG = "#FFE8EE"
HEADER_BG = "#F1F5F9"
GRID_COLOR = "#D6DEE8"

DEFAULT_PAYROLL_QUICK_CELL_COLORS = [
    "#FFF59D",
    "#FFCDD2",
    "#C8E6C9",
    "#BBDEFB",
    "#E1BEE7",
    "#E5E7EB",
]


def _month_dates(year: int, month: int) -> list[str]:
    last = monthrange(year, month)[1]
    return [f"{year:04d}-{month:02d}-{d:02d}" for d in range(1, last + 1)]




class _ResizeRefreshFilter(QObject):
    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self._callback = callback

    def eventFilter(self, watched, event):
        if event.type() in {QEvent.Resize, QEvent.Show}:
            QTimer.singleShot(0, self._callback)
        return super().eventFilter(watched, event)


class _ZoomPanPreviewController(QObject):
    def __init__(self, scroll_area: QScrollArea, state_box: dict, render_callback, parent=None):
        super().__init__(parent)
        self.scroll_area = scroll_area
        self.state_box = state_box
        self.render_callback = render_callback
        self._dragging = False
        self._drag_start = QPoint()
        self._h_start = 0
        self._v_start = 0

    def eventFilter(self, watched, event):
        event_type = event.type()

        if event_type == QEvent.Wheel:
            delta = event.angleDelta().y()
            if delta:
                current = float(self.state_box.get("zoom", 1.0) or 1.0)
                step = 0.10 if delta > 0 else -0.10
                new_zoom = max(0.80, min(2.00, round(current + step, 2)))
                if new_zoom != current:
                    hbar = self.scroll_area.horizontalScrollBar()
                    vbar = self.scroll_area.verticalScrollBar()
                    h_ratio = hbar.value() / max(1, hbar.maximum())
                    v_ratio = vbar.value() / max(1, vbar.maximum())
                    self.state_box["zoom"] = new_zoom
                    self.render_callback()
                    QTimer.singleShot(0, lambda: (
                        hbar.setValue(int(hbar.maximum() * h_ratio)),
                        vbar.setValue(int(vbar.maximum() * v_ratio)),
                    ))
            return True

        if event_type == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_start = event.position().toPoint()
            self._h_start = self.scroll_area.horizontalScrollBar().value()
            self._v_start = self.scroll_area.verticalScrollBar().value()
            watched.setCursor(Qt.ClosedHandCursor)
            return True

        if event_type == QEvent.MouseMove and self._dragging:
            pos = event.position().toPoint()
            diff = pos - self._drag_start
            self.scroll_area.horizontalScrollBar().setValue(self._h_start - diff.x())
            self.scroll_area.verticalScrollBar().setValue(self._v_start - diff.y())
            return True

        if event_type == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            self._dragging = False
            watched.setCursor(Qt.OpenHandCursor)
            return True

        if event_type == QEvent.MouseButtonDblClick:
            self.state_box["zoom"] = 1.0
            self.render_callback()
            return True

        return super().eventFilter(watched, event)


class PayrollCalendarHeaderView(QHeaderView):
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self._section_meta: dict[int, dict] = {}
        self.setDefaultAlignment(Qt.AlignCenter)
        self.setSectionsClickable(False)
        self.setHighlightSections(False)
        self.setStretchLastSection(False)
        self.setMouseTracking(True)

    def clear_section_meta(self):
        self._section_meta.clear()
        self.viewport().update()

    def set_section_meta(self, section: int, meta: dict):
        self._section_meta[int(section)] = dict(meta)

    def viewportEvent(self, event):
        if event.type() == QEvent.ToolTip:
            section = self.logicalIndexAt(event.pos())
            tooltip = str(self._section_meta.get(section, {}).get("tooltip", "")).strip()
            if tooltip:
                QToolTip.showText(event.globalPos(), tooltip, self)
                return True
            QToolTip.hideText()
        return super().viewportEvent(event)

    def paintSection(self, painter, rect, logical_index):
        painter.save()
        meta = self._section_meta.get(logical_index, {})
        background = QColor(meta.get("background", HEADER_BG))
        main_background = QColor(meta.get("main_background", background.name()))
        note_background = QColor(meta.get("note_background", background.name()))
        border = QColor(meta.get("border", GRID_COLOR))
        main_text = str(meta.get("main_text", ""))
        note_text = str(meta.get("note_text", ""))
        split = bool(meta.get("split", False) or note_text)

        painter.fillRect(rect, background)
        painter.setPen(border)
        painter.drawRect(rect.adjusted(0, 0, -1, -1))

        if split:
            split_y = rect.y() + rect.height() // 2
            main_bg_rect = QRect(rect.x() + 1, rect.y() + 1, max(0, rect.width() - 2), max(0, rect.height() // 2 - 1))
            note_bg_rect = QRect(rect.x() + 1, split_y, max(0, rect.width() - 2), max(0, rect.height() - rect.height() // 2 - 1))
            painter.fillRect(main_bg_rect, main_background)
            painter.fillRect(note_bg_rect, note_background)
            main_rect = QRect(rect.x() + 2, rect.y() + 2, max(0, rect.width() - 4), max(0, rect.height() // 2 - 4))
            note_rect = QRect(rect.x() + 2, split_y + 1, max(0, rect.width() - 4), max(0, rect.height() - rect.height() // 2 - 3))
        else:
            painter.fillRect(rect.adjusted(1, 1, -1, -1), main_background)
            main_rect = rect.adjusted(2, 2, -2, -2)
            note_rect = QRect()

        main_font = QFont("Malgun Gothic")
        main_font.setPointSize(int(meta.get("main_font_size", 9)))
        main_font.setBold(bool(meta.get("main_bold", True)))
        painter.setFont(main_font)
        painter.setPen(QColor(meta.get("main_color", "#111827")))
        painter.drawText(main_rect, Qt.AlignCenter | Qt.TextWordWrap, main_text)

        if note_text:
            note_font = QFont("Malgun Gothic")
            note_font.setPointSize(int(meta.get("note_font_size", 7)))
            note_font.setBold(bool(meta.get("note_bold", False)))
            painter.setFont(note_font)
            painter.setPen(QColor(meta.get("note_color", "#DC2626")))
            painter.drawText(note_rect, Qt.AlignCenter | Qt.TextWordWrap, note_text)

        painter.restore()


class PayrollCellEditor(QLineEdit):
    navigateRequested = Signal(int)

    def keyPressEvent(self, event):
        nav_keys = {
            Qt.Key_Return,
            Qt.Key_Enter,
            Qt.Key_Tab,
            Qt.Key_Backtab,
            Qt.Key_Left,
            Qt.Key_Right,
            Qt.Key_Up,
            Qt.Key_Down,
        }
        if event.key() in nav_keys:
            self.navigateRequested.emit(int(event.key()))
            return
        super().keyPressEvent(event)


class PayrollInputTable(QTableWidget):
    def __init__(self, page: "PayrollPage", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._page = page
        self._editable_col_start = 0
        self._editable_col_end = 0
        self.batchEditRequested = None

    def paintEvent(self, event):
        # 공휴일 배경은 각 실제 표 셀의 배경색으로만 표시한다.
        # 여기서 열 전체를 칠하면 데이터 행 아래의 빈 여백까지 색이 내려가므로 제거한다.
        super().paintEvent(event)

    def set_editable_day_range(self, start_column: int, end_column: int):
        self._editable_col_start = int(start_column)
        self._editable_col_end = int(end_column)

    def is_day_input_cell(self, row: int, column: int) -> bool:
        if row < 0 or column < 0:
            return False
        if column < self._editable_col_start or column >= self._editable_col_end:
            return False
        item = self.item(row, column)
        return bool(item and (item.flags() & Qt.ItemIsEditable))

    def _edit_cell_later(self, row: int, column: int):
        QTimer.singleShot(0, lambda r=int(row), c=int(column): self._edit_cell_if_valid(r, c))

    def _edit_cell_if_valid(self, row: int, column: int):
        if not self.is_day_input_cell(row, column):
            return
        item = self.item(row, column)
        if item is None:
            return
        self.editItem(item)

    def _select_and_maybe_edit(self, row: int, column: int, start_edit: bool = False):
        if not self.is_day_input_cell(row, column):
            return False
        self.setCurrentCell(row, column)
        if start_edit:
            self._edit_cell_later(row, column)
        return True

    def move_to_input_cell(self, row: int, column: int, start_edit: bool = False):
        if self.rowCount() <= 0 or not (self._editable_col_start <= column < self._editable_col_end):
            return
        target_row = min(max(int(row), 0), self.rowCount() - 1)
        while target_row >= 0:
            if self._select_and_maybe_edit(target_row, column, start_edit):
                return
            if target_row >= self.rowCount() - 1:
                break
            target_row += 1

    def move_vertical(self, row: int, column: int, step: int, start_edit: bool = False):
        target_row = row + step
        while 0 <= target_row < self.rowCount():
            if self._select_and_maybe_edit(target_row, column, start_edit):
                return True
            target_row += step
        return self._select_and_maybe_edit(row, column, start_edit)

    def move_horizontal(self, row: int, column: int, step: int, start_edit: bool = False):
        target_col = column + step
        while self._editable_col_start <= target_col < self._editable_col_end:
            if self._select_and_maybe_edit(row, target_col, start_edit):
                return True
            target_col += step
        return self._select_and_maybe_edit(row, column, start_edit)

    def _paste_into_day_cells(self):
        text = QApplication.clipboard().text()
        if not text or not callable(self.batchEditRequested):
            return False
        current = self.currentIndex()
        start_row = current.row()
        start_col = current.column()
        indexes = self.selectedIndexes()
        if indexes:
            start_row = min(index.row() for index in indexes)
            start_col = min(index.column() for index in indexes)
        if not self.is_day_input_cell(start_row, start_col):
            return False
        rows = [line.split("\t") for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n") if line != ""]
        if not rows:
            return False
        self.batchEditRequested(start_row, start_col, rows)
        return True

    def _clear_selected_day_cells(self):
        if not callable(self.batchEditRequested):
            return False
        indexes = [index for index in self.selectedIndexes() if self.is_day_input_cell(index.row(), index.column())]
        if not indexes:
            row = self.currentRow()
            col = self.currentColumn()
            if self.is_day_input_cell(row, col):
                indexes = [self.model().index(row, col)]
        if not indexes:
            return False
        updates = [[""] for _ in indexes]
        top_row = min(index.row() for index in indexes)
        left_col = min(index.column() for index in indexes)
        mapping = {(index.row(), index.column()): [""] for index in indexes}
        self.batchEditRequested(top_row, left_col, updates, mapping=mapping)
        return True

    def keyPressEvent(self, event):
        if (event.modifiers() & Qt.ControlModifier) and event.key() == Qt.Key_V:
            if self._paste_into_day_cells():
                return
        if event.key() == Qt.Key_Delete and self.state() != QAbstractItemView.EditingState:
            if self._clear_selected_day_cells():
                return
        if self.state() != QAbstractItemView.EditingState:
            row = self.currentRow()
            column = self.currentColumn()
            if event.key() in (Qt.Key_Return, Qt.Key_Enter) and self.is_day_input_cell(row, column):
                item = self.item(row, column)
                if item is not None:
                    self.editItem(item)
                    return
            if event.key() == Qt.Key_Tab and self.is_day_input_cell(row, column):
                self.move_horizontal(row, column, 1, start_edit=True)
                return
            if event.key() == Qt.Key_Backtab and self.is_day_input_cell(row, column):
                self.move_horizontal(row, column, -1, start_edit=True)
                return
            if event.key() == Qt.Key_Left and self.is_day_input_cell(row, column):
                self.move_horizontal(row, column, -1, start_edit=True)
                return
            if event.key() == Qt.Key_Right and self.is_day_input_cell(row, column):
                self.move_horizontal(row, column, 1, start_edit=True)
                return
            if event.key() == Qt.Key_Up and self.is_day_input_cell(row, column):
                self.move_vertical(row, column, -1, start_edit=True)
                return
            if event.key() == Qt.Key_Down and self.is_day_input_cell(row, column):
                self.move_vertical(row, column, 1, start_edit=True)
                return
        super().keyPressEvent(event)


class LargeNumericCellDelegate(QStyledItemDelegate):
    def __init__(self, table: PayrollInputTable):
        super().__init__(table)
        self.table = table
        self._active_editors: set[int] = set()

    def paint(self, painter, option, index):
        page = getattr(self.table, "_page", None)
        column = index.column()
        if page is not None and self.table._editable_col_start <= column < self.table._editable_col_end:
            option_copy = QStyleOptionViewItem(option)
            self.initStyleOption(option_copy, index)

            bg_data = index.data(Qt.BackgroundRole)
            bg_color = None
            if isinstance(bg_data, QBrush):
                bg_color = bg_data.color()
            elif isinstance(bg_data, QColor):
                bg_color = bg_data

            date = page._column_date(column)
            is_holiday = bool(date and page._is_holiday_date(date))
            if bg_color is not None or is_holiday:
                if bg_color is None:
                    bg_color = QColor(HOLIDAY_COLUMN_BG)
                painter.save()
                painter.fillRect(option_copy.rect.adjusted(1, 0, -1, 0), bg_color)

                text = str(index.data(Qt.DisplayRole) or "")
                align = index.data(Qt.TextAlignmentRole) or Qt.AlignCenter
                font_data = index.data(Qt.FontRole)
                if isinstance(font_data, QFont):
                    painter.setFont(font_data)
                else:
                    font = painter.font()
                    font.setPointSize(max(font.pointSize(), 9))
                    painter.setFont(font)

                fg_data = index.data(Qt.ForegroundRole)
                if isinstance(fg_data, QBrush):
                    painter.setPen(fg_data.color())
                elif isinstance(fg_data, QColor):
                    painter.setPen(fg_data)
                else:
                    painter.setPen(QColor("#0F172A"))
                painter.drawText(option_copy.rect.adjusted(2, 0, -2, 0), align | Qt.AlignVCenter, text)

                if option_copy.state & QStyle.State_Selected:
                    painter.setPen(QColor("#2563EB"))
                    painter.drawRect(option_copy.rect.adjusted(1, 1, -2, -2))
                painter.restore()
                return
        super().paint(painter, option, index)

    def createEditor(self, parent, option, index):
        editor = PayrollCellEditor(parent)
        editor.setAlignment(Qt.AlignCenter)
        editor.setValidator(QDoubleValidator(0.0, 9999999.0, 2, editor))
        font = editor.font()
        font.setPointSize(max(font.pointSize(), 14))
        font.setBold(True)
        editor.setFont(font)
        editor.setStyleSheet(
            "QLineEdit { background: #DBEAFE; color: #0F172A; border: 0px; padding: 0 6px; selection-background-color: #BFDBFE; selection-color: #0F172A; }"
        )
        editor.destroyed.connect(lambda *_args, ed_id=id(editor): self._active_editors.discard(ed_id))
        persistent_index = QPersistentModelIndex(index)
        editor.navigateRequested.connect(lambda key, ed=editor, idx=persistent_index: self._commit_editor_and_move(ed, idx, key))
        return editor

    def _commit_editor_and_move(self, editor: QLineEdit, index: QPersistentModelIndex, key: int):
        if not index.isValid() or self.table.rowCount() <= 0:
            return
        editor_id = id(editor)
        if editor_id in self._active_editors:
            return
        if editor.parent() is not self.table.viewport():
            return
        self._active_editors.add(editor_id)
        self.commitData.emit(editor)
        self.closeEditor.emit(editor, QAbstractItemDelegate.NoHint)

        if key in (Qt.Key_Return, Qt.Key_Enter):
            QTimer.singleShot(0, lambda r=index.row(), c=index.column(): self.table.move_vertical(r, c, 1, start_edit=True))
        elif key == Qt.Key_Tab:
            QTimer.singleShot(0, lambda r=index.row(), c=index.column(): self.table.move_horizontal(r, c, 1, start_edit=True))
        elif key == Qt.Key_Backtab:
            QTimer.singleShot(0, lambda r=index.row(), c=index.column(): self.table.move_horizontal(r, c, -1, start_edit=True))
        elif key == Qt.Key_Left:
            QTimer.singleShot(0, lambda r=index.row(), c=index.column(): self.table.move_horizontal(r, c, -1, start_edit=True))
        elif key == Qt.Key_Right:
            QTimer.singleShot(0, lambda r=index.row(), c=index.column(): self.table.move_horizontal(r, c, 1, start_edit=True))
        elif key == Qt.Key_Up:
            QTimer.singleShot(0, lambda r=index.row(), c=index.column(): self.table.move_vertical(r, c, -1, start_edit=True))
        elif key == Qt.Key_Down:
            QTimer.singleShot(0, lambda r=index.row(), c=index.column(): self.table.move_vertical(r, c, 1, start_edit=True))

    def setEditorData(self, editor, index):
        if isinstance(editor, QLineEdit):
            editor.setText(str(index.data() or ""))
            QTimer.singleShot(0, editor.selectAll)
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        if isinstance(editor, QLineEdit):
            model.setData(index, editor.text())
        else:
            super().setModelData(editor, model, index)

    def destroyEditor(self, editor, index):
        self._active_editors.discard(id(editor))
        super().destroyEditor(editor, index)


class PayrollPage(QWidget):
    request_settings = Signal()

    def __init__(self, state: AppState):
        super().__init__()
        # 급여관리는 엑셀형 표와 우측 상세 패널이 각각 자체 스크롤을 사용한다.
        # 바깥 PageScrollArea의 세로 스크롤까지 켜지면 우측에 스크롤이 2개처럼 보이므로
        # MainWindow에서 이 페이지의 외부 세로 스크롤만 끄도록 표시한다.
        self.setObjectName("PayrollPage")
        self.setProperty("disableOuterVerticalScroll", True)
        self.setProperty("fixedViewportPage", True)
        self.setMinimumWidth(0)
        self.setMaximumWidth(16777215)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.state = state
        today = QDate.currentDate()
        self.range_end_month = QDate(today.year(), today.month(), 1)
        self.range_start_month = QDate(today.year(), today.month(), 1)
        self.active_display_month = QDate(today.year(), today.month(), 1)
        self.month_buttons: list[QPushButton] = []
        self._row_meta: list[dict] = []
        self._loading_table = False
        self._loading_detail_fields = False
        self._last_selected_employee_id: int | None = None
        self._body_initialized = False
        self._splitter_initialized = False
        self._selected_cell_meta: dict | None = None
        self._detail_field_edits: dict[str, QLineEdit] = {}
        self._pending_focus_cell: tuple[int, int, bool] | None = None
        self._last_color_targets: list[tuple[int, str, int, int, int]] = []
        self._payroll_quick_colors = self._load_local_payroll_quick_colors()
        self._quick_color_buttons: list[QPushButton] = []
        self._last_generated_slip_payload: dict | None = None
        self._slip_preview_ready = False
        self._suppress_payroll_refresh = False

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(*PAGE_OUTER_MARGINS)
        main_layout.setSpacing(PAGE_OUTER_SPACING)

        # 상단 고정 배너는 MainWindow에서 표시합니다.
        payroll_frame = QFrame()
        payroll_frame.setObjectName("ScrollPageOuterFrame")
        payroll_frame.setMinimumWidth(0)
        payroll_frame.setMaximumWidth(16777215)
        payroll_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        payroll_content_layout = QVBoxLayout(payroll_frame)
        payroll_content_layout.setContentsMargins(0, 0, 0, 0)
        payroll_content_layout.setSpacing(PAGE_INNER_SPACING)

        self.filter_panel = Panel("급여 관리", "월 기준 조회 · 근태 불러오기 · 수동 입력")
        self.filter_panel.setProperty("panelRole", "toolbar")
        self.filter_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self._set_panel_density(self.filter_panel, header_margins=(6, 6, 6, 6), body_margins=(6, 6, 6, 6), body_spacing=6)
        self.filter_panel.body_layout.addLayout(self._create_filters())
        payroll_content_layout.addWidget(self.filter_panel)

        self.summary_row = self._create_summary_row()
        self.summary_row.hide()

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(6)
        self.splitter.setMinimumWidth(0)
        self.splitter.setMaximumWidth(16777215)
        self.splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.splitter.addWidget(self._create_table_panel())
        self.splitter.addWidget(self._create_detail_panel())
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        # 전체 급여관리 폭을 강제로 키우지 않는다.
        # 오른쪽 상세 패널은 6px 핸들 옆 고정폭, 넓은 날짜 칸은 급여표 내부 가로 스크롤로 처리한다.
        self.splitter.setSizes([780, 300])
        payroll_content_layout.addWidget(self.splitter, 1)
        main_layout.addWidget(payroll_frame, 1)

        self.state.employees_changed.connect(self.refresh)
        self.state.payroll_changed.connect(self._on_payroll_changed)
        self.state.settings_changed.connect(self._on_settings_changed)
        if hasattr(self.state, "holidays_changed"):
            self.state.holidays_changed.connect(lambda *_args: self.refresh(False))
        self.refresh()

    def _set_panel_density(self, panel: Panel, *, header_margins=(6, 6, 6, 6), body_margins=(6, 6, 6, 6), body_spacing=6):
        if panel.root.count() >= 1:
            header = panel.root.itemAt(0).widget()
            if header is not None and header.layout() is not None:
                header.layout().setContentsMargins(*header_margins)
                header.layout().setSpacing(6)
        panel.body_layout.setContentsMargins(*body_margins)
        panel.body_layout.setSpacing(body_spacing)

    def _create_hero(self):
        hero = QFrame()
        hero.setObjectName("HeroCard")
        hero.setFixedHeight(78)
        row = QHBoxLayout(hero)
        row.setContentsMargins(6, 6, 6, 6)
        row.setSpacing(6)
        left = QVBoxLayout()
        left.setSpacing(6)
        badge = QLabel("PAYROLL MANAGEMENT")
        badge.setObjectName("HeroBadge")
        title = QLabel("급여 관리")
        title.setObjectName("HeroTitle")
        desc = QLabel("근태관리 값은 불러오기 초안으로만 사용하고, 급여표에서 날짜별 숫자를 직접 수정합니다.")
        desc.setObjectName("HeroDesc")
        desc.setWordWrap(True)
        left.addWidget(badge)
        left.addWidget(title)
        left.addWidget(desc)
        left.addStretch()
        row.addLayout(left, 1)
        return hero

    def _month_range_years(self) -> list[int]:
        current_year = QDate.currentDate().year()
        years = set(range(current_year - 5, current_year + 6))
        for date in [self.range_start_month, self.range_end_month, self.active_display_month]:
            if date and date.isValid():
                years.add(date.year())
        return sorted(years)

    def _set_combo_value(self, combo: QComboBox, value: int, label: str | None = None):
        index = combo.findData(value)
        if index < 0:
            combo.addItem(label or str(value), value)
            index = combo.findData(value)
        combo.setCurrentIndex(index)

    def _make_year_combo(self, year: int) -> QComboBox:
        combo = QComboBox()
        for value in self._month_range_years():
            combo.addItem(str(value), value)
        combo.setMinimumWidth(86)
        self._set_combo_value(combo, year, str(year))
        return combo

    def _make_month_combo(self, month: int) -> QComboBox:
        combo = QComboBox()
        for value in range(1, 13):
            combo.addItem(f"{value}월", value)
        combo.setMinimumWidth(72)
        self._set_combo_value(combo, month, f"{month}월")
        return combo

    def _sync_month_range_inputs(self):
        self._set_combo_value(self.start_year_combo, self.range_start_month.year(), str(self.range_start_month.year()))
        self._set_combo_value(self.start_month_combo, self.range_start_month.month(), f"{self.range_start_month.month()}월")
        self._set_combo_value(self.end_year_combo, self.range_end_month.year(), str(self.range_end_month.year()))
        self._set_combo_value(self.end_month_combo, self.range_end_month.month(), f"{self.range_end_month.month()}월")

    def _create_filters(self):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        def filter_label(text: str):
            label = QLabel(text)
            label.setObjectName("FilterLabel")
            label.setMinimumHeight(30)
            return label

        self.start_year_combo = self._make_year_combo(self.range_start_month.year())
        self.start_month_combo = self._make_month_combo(self.range_start_month.month())

        self.end_year_combo = self._make_year_combo(self.range_end_month.year())
        self.end_month_combo = self._make_month_combo(self.range_end_month.month())

        self.biz_combo = QComboBox()
        self.site_combo = QComboBox()

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("이름 / 사업자 / 근무 사업장 검색")
        self.search_edit.returnPressed.connect(self._apply_query_filters)

        self.query_btn = QPushButton("조회")
        self.query_btn.setObjectName("PrimaryButton")
        self.query_btn.clicked.connect(self._apply_query_filters)

        self.settings_btn = QPushButton("급여 설정")
        self.settings_btn.setObjectName("GhostButton")
        self.settings_btn.clicked.connect(self.request_settings.emit)

        self.month_close_btn = QPushButton("월 마감")
        self.month_close_btn.setObjectName("WarnButton")
        self.month_close_btn.clicked.connect(self._close_current_month)

        self.month_reopen_btn = QPushButton("마감 취소")
        self.month_reopen_btn.setObjectName("GhostButton")
        self.month_reopen_btn.clicked.connect(self._reopen_current_month)

        for widget in [
            self.start_year_combo,
            self.start_month_combo,
            self.end_year_combo,
            self.end_month_combo,
            self.biz_combo,
            self.site_combo,
            self.search_edit,
            self.query_btn,
            self.settings_btn,
            self.month_close_btn,
            self.month_reopen_btn,
        ]:
            widget.setMinimumHeight(30)

        self.query_btn.setMinimumWidth(56)
        self.settings_btn.setMinimumWidth(86)
        self.month_close_btn.setMinimumWidth(76)
        self.month_reopen_btn.setMinimumWidth(82)

        row.addWidget(filter_label("기간"))
        row.addWidget(filter_label("연도"))
        row.addWidget(self.start_year_combo)
        row.addWidget(filter_label("월"))
        row.addWidget(self.start_month_combo)
        row.addWidget(filter_label("~"))
        row.addWidget(filter_label("연도"))
        row.addWidget(self.end_year_combo)
        row.addWidget(filter_label("월"))
        row.addWidget(self.end_month_combo)
        row.addWidget(filter_label("사업자"))
        row.addWidget(self.biz_combo, 1)
        row.addWidget(filter_label("근무 사업장"))
        row.addWidget(self.site_combo, 1)
        row.addWidget(self.search_edit, 2)
        row.addWidget(self.query_btn)
        row.addWidget(self.settings_btn)
        row.addWidget(self.month_close_btn)
        row.addWidget(self.month_reopen_btn)

        self.biz_combo.currentIndexChanged.connect(self._on_biz_changed)
        self.site_combo.currentIndexChanged.connect(lambda: self.refresh(False))
        return row

    def _create_month_button_strip(self):
        frame = QFrame()
        frame.setObjectName("DetailSummaryCard")
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        frame.setMinimumHeight(38)
        frame.setMaximumHeight(42)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        title = QLabel("표시 월")
        title.setObjectName("DetailKey")
        layout.addWidget(title)

        self.month_button_wrap = QWidget()
        self.month_button_layout = QHBoxLayout(self.month_button_wrap)
        self.month_button_layout.setContentsMargins(0, 0, 0, 0)
        self.month_button_layout.setSpacing(6)
        layout.addWidget(self.month_button_wrap, 1)

        self._refresh_display_month_buttons(self.range_start_month, self.range_end_month)
        return frame

    def _create_summary_row(self):
        frame = QFrame()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.total_hours_card = StatCard("총 입력시간", "0H", "현재 표시 월 합계", "#1D4ED8", "attendance")
        self.avg_hours_card = StatCard("평균 총시간", "0H", "직원 1인 평균", "#10B981", "coin")
        self.headcount_card = StatCard("대상 인원", "0명", "현재 조회 대상", "#6366F1", "user")
        for card in [self.total_hours_card, self.avg_hours_card, self.headcount_card]:
            card.setFixedHeight(100)
            layout.addWidget(card)
        return frame

    def _create_table_panel(self):
        self.table_panel = Panel("월간 급여표", "조회 기준 월을 확인하세요")
        self.table_panel.setProperty("panelRole", "board")
        self.table_panel.setMinimumWidth(0)
        self.table_panel.setMaximumWidth(16777215)
        self.table_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._set_panel_density(self.table_panel, header_margins=(6, 6, 6, 6), body_margins=(6, 6, 6, 6), body_spacing=6)

        self._day_col_offset = 2
        self._summary_col_offset = self._day_col_offset + 31
        total_cols = self._day_col_offset + 31 + 2
        headers = ["이름", "구분"] + [str(d) for d in range(1, 32)] + ["소계", "총"]

        self.payroll_table = PayrollInputTable(self, 0, total_cols)
        self.payroll_table.setHorizontalHeaderLabels(headers)
        self.payroll_table.verticalHeader().setVisible(False)
        self.payroll_table.verticalHeader().setDefaultSectionSize(30)
        self.payroll_table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.payroll_table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.payroll_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.payroll_table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed | QAbstractItemView.AnyKeyPressed)
        self.payroll_table.setShowGrid(True)
        self.payroll_table.setAlternatingRowColors(False)
        self.payroll_table.setWordWrap(False)
        self.payroll_table.setItemDelegate(LargeNumericCellDelegate(self.payroll_table))

        self.payroll_header = PayrollCalendarHeaderView(Qt.Horizontal, self.payroll_table)
        self.payroll_table.setHorizontalHeader(self.payroll_header)
        hdr = self.payroll_table.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(QHeaderView.Fixed)

        self.payroll_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.payroll_table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.payroll_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.payroll_table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.payroll_table.setMinimumWidth(0)
        self.payroll_table.setMaximumWidth(16777215)
        self.payroll_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.payroll_table.setStyleSheet(
            "QTableWidget { font-size: 10px; gridline-color: #D6DEE8; selection-background-color: #DBEAFE; selection-color: #0F172A; outline: 0; }"
            "QTableWidget::item { border: 0px; padding: 0px; }"
            "QTableWidget::item:selected { background: #DBEAFE; color: #0F172A; border: 0px; }"
            "QTableWidget::item:selected:active { background: #DBEAFE; color: #0F172A; border: 0px; }"
            "QTableWidget::item:selected:!active { background: #DBEAFE; color: #0F172A; border: 0px; }"
            "QTableWidget::item:focus { outline: 0; border: 0px; }"
            "QHeaderView::section { padding: 6px 6px; font-size: 9px; font-weight: 800; background: #F1F5F9; }"
        )
        self.payroll_table.set_editable_day_range(self._day_col_offset, self._summary_col_offset)
        self.payroll_table.batchEditRequested = self._apply_batch_from_clipboard
        self.payroll_table.currentCellChanged.connect(self._on_current_cell_changed)
        self.payroll_table.itemSelectionChanged.connect(self._on_table_selection_changed)
        self.payroll_table.cellChanged.connect(self._handle_cell_changed)
        self.payroll_table.cellDoubleClicked.connect(self._handle_table_double_click)
        self.payroll_table.cellClicked.connect(self._on_table_cell_clicked)
        self.month_strip = self._create_month_button_strip()
        self.cell_color_toolbar = self._create_cell_color_toolbar()
        self.table_panel.header.layout().addWidget(self.cell_color_toolbar, 0, Qt.AlignRight | Qt.AlignTop)
        self.table_panel.body_layout.addWidget(self.month_strip, 0)
        self.table_panel.body_layout.addWidget(self.payroll_table, 1)
        self.table_panel.body_layout.setStretch(0, 0)
        self.table_panel.body_layout.setStretch(1, 1)
        self.table_panel.body_layout.setAlignment(self.month_strip, Qt.AlignTop)
        return self.table_panel

    def _create_cell_color_toolbar(self):
        wrap = QWidget()
        wrap.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        row = QHBoxLayout(wrap)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        self._quick_color_buttons = []
        for index, color_hex in enumerate(self._payroll_quick_colors):
            button = QPushButton("")
            button.setObjectName("PayrollColorChip")
            button.setFixedSize(18, 18)
            button.setToolTip(f"기본 색상 {index + 1} 적용")
            button.clicked.connect(lambda _checked=False, c=color_hex: self._apply_selected_cell_color(c))
            self._quick_color_buttons.append(button)
            row.addWidget(button)

        toolbar_button_style = (
            "QPushButton { background:#FFFFFF; border:1px solid #CBD5E1; border-radius:8px; "
            "padding: 6px 6px; font-size:11px; font-weight:800; color:#0F172A; }"
            "QPushButton:hover { border:1px solid #2563EB; background:#F8FAFC; }"
        )

        custom_btn = QPushButton("선택")
        custom_btn.setObjectName("GhostButton")
        custom_btn.setMinimumHeight(26)
        custom_btn.setMaximumHeight(28)
        custom_btn.setMinimumWidth(48)
        custom_btn.setStyleSheet(toolbar_button_style)
        custom_btn.clicked.connect(self._choose_and_apply_cell_color)
        row.addWidget(custom_btn)

        clear_btn = QPushButton("제거")
        clear_btn.setObjectName("GhostButton")
        clear_btn.setMinimumHeight(26)
        clear_btn.setMaximumHeight(28)
        clear_btn.setMinimumWidth(48)
        clear_btn.setStyleSheet(toolbar_button_style)
        clear_btn.clicked.connect(lambda: self._apply_selected_cell_color(None))
        row.addWidget(clear_btn)

        setup_btn = QPushButton("설정")
        setup_btn.setObjectName("GhostButton")
        setup_btn.setMinimumHeight(26)
        setup_btn.setMaximumHeight(28)
        setup_btn.setMinimumWidth(48)
        setup_btn.setStyleSheet(toolbar_button_style)
        setup_btn.setToolTip("이 PC에서 사용할 기본 색상 6개를 변경합니다.")
        setup_btn.clicked.connect(self._open_quick_color_settings)
        row.addWidget(setup_btn)

        self._refresh_quick_color_buttons()
        return wrap

    def _local_ui_settings_path(self) -> Path:
        data_root = Path(str(getattr(self.state, "data_root_path", "") or Path.cwd()))
        config_dir = data_root / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "local_ui_settings.json"

    def _load_local_payroll_quick_colors(self) -> list[str]:
        colors = list(DEFAULT_PAYROLL_QUICK_CELL_COLORS)
        try:
            path = self._local_ui_settings_path()
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                saved = data.get("payroll_quick_colors", [])
                if isinstance(saved, list):
                    for index, value in enumerate(saved[:6]):
                        color_text = str(value or "").strip().upper()
                        if re.match(r"^#[0-9A-F]{6}$", color_text):
                            colors[index] = color_text
        except Exception:
            pass
        return colors[:6]

    def _save_local_payroll_quick_colors(self):
        try:
            path = self._local_ui_settings_path()
            data = {}
            if path.exists():
                try:
                    loaded = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        data = loaded
                except Exception:
                    data = {}
            data["payroll_quick_colors"] = list(self._payroll_quick_colors[:6])
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            return

    def _refresh_quick_color_buttons(self):
        for index, button in enumerate(getattr(self, "_quick_color_buttons", [])):
            color_hex = self._payroll_quick_colors[index] if index < len(self._payroll_quick_colors) else "#E5E7EB"
            button.clicked.disconnect()
            button.clicked.connect(lambda _checked=False, c=color_hex: self._apply_selected_cell_color(c))
            button.setStyleSheet(
                f"QPushButton#PayrollColorChip {{ background: {color_hex}; border: 1px solid #94A3B8; border-radius: 4px; padding: 0px; }}"
                f"QPushButton#PayrollColorChip:hover {{ border: 2px solid #2563EB; }}"
            )
            button.setToolTip(f"기본 색상 {index + 1} 적용")

    def _open_quick_color_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("급여표 기본색 설정")
        dialog.setFixedSize(390, 142)

        root = QVBoxLayout(dialog)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        guide = QLabel("기본 색상은 이 PC에만 저장됩니다.")
        guide.setObjectName("DetailMeta")
        guide.setWordWrap(False)
        root.addWidget(guide)

        chip_row = QHBoxLayout()
        chip_row.setContentsMargins(0, 0, 0, 0)
        chip_row.setSpacing(6)
        preview_buttons: list[QPushButton] = []

        def update_preview_button(btn: QPushButton, color_text: str):
            btn.setStyleSheet(
                f"QPushButton {{ background: {color_text}; border: 1px solid #94A3B8; border-radius: 5px; "
                f"min-width: 24px; max-width: 24px; min-height: 22px; max-height: 22px; padding: 0px; color: transparent; }}"
                f"QPushButton:hover {{ border: 2px solid #2563EB; }}"
            )

        def choose_color(index: int):
            current = QColor(self._payroll_quick_colors[index])
            color = QColorDialog.getColor(current, dialog, f"기본 색상 {index + 1} 변경")
            if not color.isValid():
                return
            self._payroll_quick_colors[index] = color.name().upper()
            update_preview_button(preview_buttons[index], self._payroll_quick_colors[index])
            self._save_local_payroll_quick_colors()
            self._refresh_quick_color_buttons()

        for index, color_hex in enumerate(self._payroll_quick_colors):
            btn = QPushButton("")
            btn.setFixedSize(24, 22)
            btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            btn.setToolTip(f"기본 색상 {index + 1} 변경")
            update_preview_button(btn, color_hex)
            btn.clicked.connect(lambda _checked=False, i=index: choose_color(i))
            preview_buttons.append(btn)
            chip_row.addWidget(btn)

        chip_row.addStretch(1)
        root.addLayout(chip_row)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(6)

        small_button_style = (
            "QPushButton { background:#FFFFFF; border:1px solid #CBD5E1; border-radius:8px; "
            "padding: 6px 6px; font-size:12px; font-weight:800; color:#0F172A; }"
            "QPushButton:hover { border:1px solid #2563EB; background:#F8FAFC; }"
        )
        primary_button_style = (
            "QPushButton { background:#1D4ED8; border:1px solid #1D4ED8; border-radius:8px; "
            "padding: 6px 6px; font-size:12px; font-weight:900; color:#FFFFFF; }"
            "QPushButton:hover { background:#1E40AF; }"
        )

        reset_btn = QPushButton("기본값")
        reset_btn.setFixedSize(72, 30)
        reset_btn.setStyleSheet(small_button_style)

        close_btn = QPushButton("닫기")
        close_btn.setFixedSize(72, 30)
        close_btn.setStyleSheet(primary_button_style)

        def reset_defaults():
            self._payroll_quick_colors = list(DEFAULT_PAYROLL_QUICK_CELL_COLORS)
            for index, btn in enumerate(preview_buttons):
                update_preview_button(btn, self._payroll_quick_colors[index])
            self._save_local_payroll_quick_colors()
            self._refresh_quick_color_buttons()

        reset_btn.clicked.connect(reset_defaults)
        close_btn.clicked.connect(dialog.accept)
        button_row.addWidget(reset_btn)
        button_row.addStretch(1)
        button_row.addWidget(close_btn)
        root.addLayout(button_row)

        dialog.exec()

    def _selected_payroll_color_targets(self) -> list[tuple[int, str, int, int, int]]:
        if not hasattr(self, "payroll_table"):
            return []

        targets: list[tuple[int, str, int, int, int]] = []
        seen: set[tuple[int, str, int]] = set()

        def add_cell(row: int, col: int):
            if not self.payroll_table.is_day_input_cell(row, col) or row >= len(self._row_meta):
                return
            day = col - self._day_col_offset + 1
            if day < 1 or day > 31:
                return
            meta = self._row_meta[row]
            try:
                employee_id = int(meta.get("employee_id", 0) or 0)
            except (TypeError, ValueError):
                return
            category_key = str(meta.get("category_key", "") or "")
            key = (employee_id, category_key, day)
            if employee_id <= 0 or category_key not in {"base", "over", "night"} or key in seen:
                return
            seen.add(key)
            targets.append((employee_id, category_key, day, row, col))

        selection_model = self.payroll_table.selectionModel()
        if selection_model is not None:
            for selection_range in self.payroll_table.selectedRanges():
                for row in range(selection_range.topRow(), selection_range.bottomRow() + 1):
                    for col in range(selection_range.leftColumn(), selection_range.rightColumn() + 1):
                        add_cell(row, col)
            for index in selection_model.selectedIndexes():
                add_cell(index.row(), index.column())

        current_row = self.payroll_table.currentRow()
        current_col = self.payroll_table.currentColumn()
        add_cell(current_row, current_col)

        if not targets and self._selected_cell_meta:
            try:
                row = int(self._selected_cell_meta.get("row", -1))
                col = int(self._selected_cell_meta.get("column", -1))
                add_cell(row, col)
            except Exception:
                pass

        if targets:
            self._last_color_targets = list(targets)
            return targets
        return list(self._last_color_targets)

    def _choose_and_apply_cell_color(self):
        color = QColorDialog.getColor(QColor("#FFF59D"), self, "급여표 셀 색상 선택")
        if not color.isValid():
            return
        self._apply_selected_cell_color(color.name().upper())

    def _apply_selected_cell_color(self, color_hex: str | None):
        targets = self._selected_payroll_color_targets()
        if not targets:
            QMessageBox.information(self, "셀 색상", "색상을 적용할 급여표 날짜 칸을 먼저 선택하세요.")
            return

        color_text = str(color_hex or "").strip().upper() if color_hex else None
        changes = [(employee_id, category_key, day, color_text) for employee_id, category_key, day, _row, _col in targets]

        # 상태 저장은 하되, 전체 표를 즉시 다시 그리면 선택 색상이 파란 선택 배경에 가려져
        # 적용되지 않은 것처럼 보일 수 있으므로 현재 보이는 칸을 바로 갱신한다.
        self._suppress_payroll_refresh = True
        try:
            self.state.set_payroll_cell_colors_bulk(self._month_key(), changes)
        finally:
            self._suppress_payroll_refresh = False

        display_date = self._current_display_month()
        year, month = display_date.year(), display_date.month()
        for employee_id, category_key, day, row, col in targets:
            item = self.payroll_table.item(row, col)
            if item is None:
                continue
            auto_color = self._row_band_color(category_key, year, month, day)
            self._apply_payroll_cell_background(item, color_text or auto_color)

        # 색상 적용 결과가 바로 보이도록 표를 다시 칠하고, 오른쪽 선택 셀 정보만 갱신한다.
        if targets:
            _employee_id, _category_key, _day, row, col = targets[-1]
            self._sync_selected_cell_editor(row, col)
        self.payroll_table.viewport().update()

    def _manual_cell_color_for(self, entry: dict, category_key: str, day: int) -> str | None:
        colors = (entry or {}).get("cell_colors", {}) or {}
        category_colors = colors.get(category_key, {}) if isinstance(colors, dict) else {}
        if not isinstance(category_colors, dict):
            return None
        value = category_colors.get(day, category_colors.get(str(day), ""))
        color_text = str(value or "").strip()
        if re.match(r"^#[0-9A-Fa-f]{6}$", color_text):
            return color_text.upper()
        return None

    def _day_cell_background(self, entry: dict, category_key: str, year: int, month: int, day: int) -> str:
        manual_color = self._manual_cell_color_for(entry, category_key, day)
        if manual_color:
            return manual_color
        return self._row_band_color(category_key, year, month, day)

    def _apply_payroll_cell_background(self, item: QTableWidgetItem | None, color_hex: str):
        if item is None:
            return
        color = QColor(color_hex)
        item.setData(Qt.BackgroundRole, color)
        item.setBackground(QBrush(color))

    def _create_detail_panel(self):
        scroll = QScrollArea()
        scroll.setObjectName("PayrollDetailScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        scroll.setStyleSheet(
            "QScrollArea#PayrollDetailScrollArea { background: transparent; border: none; }"
            "QScrollArea#PayrollDetailScrollArea > QWidget > QWidget { background: transparent; }"
        )

        container = QWidget()
        container.setObjectName("PayrollDetailScrollContent")
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        self.detail_panel = Panel("선택 직원 입력 상세", "", icon_name="user")
        self.detail_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.det_name = QLabel("—")
        self.det_name.setObjectName("DetailName")
        self.det_meta = QLabel("—")
        self.det_meta.setObjectName("DetailMeta")
        self.det_pay_type = QLabel("급여형태: —")
        self.det_pay_type.setObjectName("DetailMeta")
        self.det_month = QLabel("표시 월: —")
        self.det_month.setObjectName("DetailMeta")
        self.det_base = QLabel("기본 소계: —")
        self.det_base.setObjectName("DetailKey")
        self.det_over = QLabel("연장 소계: —")
        self.det_over.setObjectName("DetailKey")
        self.det_night = QLabel("심야 소계: —")
        self.det_night.setObjectName("DetailKey")
        self.det_total = QLabel("총시간: —")
        self.det_total.setObjectName("DetailName")
        self.det_total.setStyleSheet("color: #059669; font-size: 15px; font-weight: 900;")

        self.detail_import_btn = QPushButton("현재 월 불러오기")
        self.detail_import_btn.setObjectName("PrimaryButton")
        self.detail_import_btn.clicked.connect(self._import_from_attendance)

        self.detail_site_conversion_btn = QPushButton("사업장 기준 적용")
        self.detail_site_conversion_btn.setObjectName("PrimaryButton")
        self.detail_site_conversion_btn.setToolTip("설정 > 사업장별 시간 환산 기준을 현재 월 급여 입력표에 적용합니다.")
        self.detail_site_conversion_btn.clicked.connect(self._apply_site_time_conversion_to_payroll)

        for widget in [
            self.det_name, self.det_meta, self.det_pay_type, self.det_month,
            self.det_base, self.det_over, self.det_night, self.det_total,
            self.detail_import_btn, self.detail_site_conversion_btn,
        ]:
            if hasattr(widget, "setWordWrap"):
                widget.setWordWrap(True)
            self.detail_panel.body_layout.addWidget(widget)
        v.addWidget(self.detail_panel)

        self.cell_editor_panel = Panel("선택 셀 직접 수정", "", icon_name="attendance")
        self.cell_editor_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.sel_cell_label = QLabel("선택된 날짜 칸이 없습니다.")
        self.sel_cell_label.setObjectName("DetailMeta")
        self.sel_cell_label.setWordWrap(True)
        self.sel_cell_input = QLineEdit()
        self.sel_cell_input.setPlaceholderText("숫자 입력")
        self.sel_cell_input.setMinimumHeight(42)
        self.sel_cell_input.setAlignment(Qt.AlignCenter)
        self.sel_cell_input.setStyleSheet(
            "QLineEdit { font-size: 15px; font-weight: 800; background: #FFFFFF; border: 2px solid #2563EB; padding: 0px 6px; }"
        )
        self.sel_cell_input.returnPressed.connect(self._apply_current_cell_input)
        cell_btn_row = QHBoxLayout()
        self.sel_cell_apply_btn = QPushButton("적용")
        self.sel_cell_apply_btn.setObjectName("PrimaryButton")
        self.sel_cell_apply_btn.clicked.connect(self._apply_current_cell_input)
        self.sel_cell_clear_btn = QPushButton("비우기")
        self.sel_cell_clear_btn.setObjectName("GhostButton")
        self.sel_cell_clear_btn.clicked.connect(self._clear_current_cell_input)
        cell_btn_row.addWidget(self.sel_cell_apply_btn)
        cell_btn_row.addWidget(self.sel_cell_clear_btn)
        self.cell_editor_panel.body_layout.addWidget(self.sel_cell_label)
        self.cell_editor_panel.body_layout.addWidget(self.sel_cell_input)
        self.cell_editor_panel.body_layout.addLayout(cell_btn_row)
        self.cell_editor_panel.setVisible(False)
        v.addWidget(self.cell_editor_panel)

        self.guide_panel = Panel("불러오기 방식", "", icon_name="attendance")
        self.guide_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        guide_label = QLabel("현재 월 초안 불러오기")
        guide_label.setObjectName("SectionSub")
        self.guide_panel.body_layout.addWidget(guide_label)
        self.guide_panel.setVisible(False)
        v.addWidget(self.guide_panel)

        self.summary_items_panel = Panel("정산 요약", "", icon_name="payroll")
        self.summary_items_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.summary_items_grid = QGridLayout()
        self.summary_items_grid.setHorizontalSpacing(6)
        self.summary_items_grid.setVerticalSpacing(6)
        self.summary_items_panel.body_layout.addLayout(self.summary_items_grid)
        v.addWidget(self.summary_items_panel)

        self.allowance_panel = Panel("수당 항목", "", icon_name="coin")
        self.allowance_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.allowance_grid = QGridLayout()
        self.allowance_grid.setHorizontalSpacing(6)
        self.allowance_grid.setVerticalSpacing(6)
        self.allowance_panel.body_layout.addLayout(self.allowance_grid)
        v.addWidget(self.allowance_panel)

        self.deduction_panel = Panel("공제 항목", "", icon_name="settings")
        self.deduction_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.deduction_grid = QGridLayout()
        self.deduction_grid.setHorizontalSpacing(6)
        self.deduction_grid.setVerticalSpacing(6)
        self.deduction_panel.body_layout.addLayout(self.deduction_grid)
        v.addWidget(self.deduction_panel)

        self._rebuild_adjustment_sections()

        v.addStretch(1)



        scroll.setWidget(container)
        # 우측 상세 패널 폭은 고정한다.
        # 화면 전체 폭은 유지하고, 급여표 가로 이동은 표 내부 스크롤에서만 처리한다.
        scroll.setFixedWidth(300)
        return scroll

    def _current_display_month(self) -> QDate:
        if hasattr(self, "active_display_month") and self.active_display_month.isValid():
            return self.active_display_month
        return QDate.currentDate()

    def _month_sequence(self, start, end):
        cursor = QDate(start.year(), start.month(), 1)
        last = QDate(end.year(), end.month(), 1)
        items = []
        while cursor <= last:
            items.append(cursor)
            cursor = cursor.addMonths(1)
        return items

    def _refresh_display_month_buttons(self, start, end, preferred=None):
        preferred_date = preferred if preferred and preferred.isValid() else start
        if preferred_date < start or preferred_date > end:
            preferred_date = start
        self.active_display_month = QDate(preferred_date.year(), preferred_date.month(), 1)

        while self.month_button_layout.count():
            item = self.month_button_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.month_buttons.clear()

        for month in self._month_sequence(start, end):
            btn = QPushButton(f"{month.month()}월")
            btn.setObjectName("MonthChip")
            btn.setCheckable(True)
            btn.setMinimumHeight(30)
            btn.setChecked(month.year() == self.active_display_month.year() and month.month() == self.active_display_month.month())
            btn.clicked.connect(lambda checked=False, m=QDate(month.year(), month.month(), 1): self._set_display_month(m))
            self.month_button_layout.addWidget(btn)
            self.month_buttons.append(btn)
        self.month_button_layout.addStretch(1)

    def _set_display_month(self, month):
        self.active_display_month = QDate(month.year(), month.month(), 1)
        for button, candidate in zip(self.month_buttons, self._month_sequence(self.range_start_month, self.range_end_month)):
            button.setChecked(candidate.year() == month.year() and candidate.month() == month.month())
        self.refresh(False)

    def _format_amount(self, value: float) -> str:
        try:
            amount = float(value or 0)
        except (TypeError, ValueError):
            amount = 0.0
        if abs(amount - int(amount)) < 1e-9:
            return f"{int(amount):,}"
        return f"{amount:,.2f}".rstrip("0").rstrip(".")

    def _payroll_export_dir(self) -> Path:
        return Path(self.state.export_subdir_path("payroll_slips"))

    def _reset_slip_preview(self, message: str | None = None):
        self._last_generated_slip_payload = None
        self._slip_preview_ready = False

    def _build_selected_slip_payload(self) -> dict | None:
        employee_id = self._resolve_selected_employee_id()
        if not employee_id:
            return None
        try:
            return build_payroll_slip_payload(self.state, int(employee_id), self._month_key())
        except Exception as exc:
            QMessageBox.warning(self, "급여명세표", f"명세표 데이터를 만드는 중 문제가 생겼습니다.\n{exc}")

    def _generate_payroll_slip_preview(self, *, silent: bool = False) -> dict | None:
        payload = self._build_selected_slip_payload()
        if not payload:
            if not silent:
                QMessageBox.information(self, "급여명세표", "먼저 급여표에서 직원을 선택하세요.")
            self._reset_slip_preview()
            return None
        self._last_generated_slip_payload = payload
        self._slip_preview_ready = True
        return payload

    def _ensure_slip_payload(self) -> dict | None:
        if self._last_generated_slip_payload and self._slip_preview_ready:
            payload = self._last_generated_slip_payload
            if str(payload.get("month_key")) == self._month_key() and int(payload.get("employee_id", 0) or 0) == int(self._resolve_selected_employee_id() or 0):
                return payload
        return self._generate_payroll_slip_preview(silent=True)

    def _default_export_path(self, payload: dict, suffix: str) -> Path:
        folder = self._payroll_export_dir()
        return folder / f"{payload.get('default_filename', 'payroll_slip')}{suffix}"

    def _show_payroll_slip_export_menu(self):
        payload = self._ensure_slip_payload()
        if not payload:
            QMessageBox.information(self, "급여명세표", "먼저 직원을 선택하고 명세표를 생성하세요.")
            return
        self._show_payroll_slip_export_menu_for_payload(payload, None)

    def _export_payroll_slip_file(self, export_type: str, payload: dict):
        export_type = str(export_type).lower().strip()
        suffix_map = {
            "png": ".png",
            "jpg": ".jpg",
        }
        filter_map = {
            "png": "PNG 파일 (*.png)",
            "jpg": "JPG 파일 (*.jpg *.jpeg)",
        }
        suffix = suffix_map.get(export_type)
        if not suffix:
            return
        default_path = self._default_export_path(payload, suffix)
        file_path, _ = QFileDialog.getSaveFileName(self, "급여명세표 저장", str(default_path), filter_map.get(export_type, "모든 파일 (*.*)"))
        if not file_path:
            return
        target = Path(file_path)
        if not target.suffix:
            target = target.with_suffix(suffix)
        try:
            if export_type == "png":
                export_payroll_slip_image(payload, target, image_format="PNG")
            elif export_type == "jpg":
                export_payroll_slip_image(payload, target, image_format="JPEG")
            else:
                return
        except Exception as exc:
            QMessageBox.warning(self, "급여명세표", f"파일 저장 중 문제가 생겼습니다.\n{exc}")
            return
        QMessageBox.information(self, "급여명세표", f"저장 완료\n{target}")

    def _print_payroll_slip(self, payload: dict):
        try:
            png_bytes = build_payroll_slip_png_bytes(payload)
            image = QImage.fromData(png_bytes, "PNG")
            if image.isNull():
                raise RuntimeError("명세표 이미지를 불러오지 못했습니다.")

            printer = QPrinter(QPrinter.HighResolution)
            printer.setDocName(payload.get("display_title", "급여명세표"))
            if hasattr(printer, "setPageOrientation"):
                try:
                    from PySide6.QtGui import QPageLayout
                    printer.setPageOrientation(QPageLayout.Landscape)
                except Exception:
                    pass

            dialog = QPrintDialog(printer, self)
            if dialog.exec() != 1:
                return

            painter = QPainter()
            if not painter.begin(printer):
                raise RuntimeError("프린터를 시작하지 못했습니다.")
            try:
                page_rect = printer.pageRect(QPrinter.DevicePixel)
                scaled_size = image.size()
                scaled_size.scale(page_rect.size(), Qt.KeepAspectRatio)
                x = page_rect.x() + max(0, (page_rect.width() - scaled_size.width()) // 2)
                y = page_rect.y() + max(0, (page_rect.height() - scaled_size.height()) // 2)
                target_rect = QRect(int(x), int(y), int(scaled_size.width()), int(scaled_size.height()))
                painter.drawImage(target_rect, image)
            finally:
                painter.end()
        except Exception as exc:
            QMessageBox.warning(self, "급여명세표", f"프린터 출력 중 문제가 생겼습니다.\n{exc}")

    def _open_path_in_shell(self, target: Path):
        try:
            resolved = Path(target).resolve()
            if os.name == "nt":
                os.startfile(str(resolved))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(resolved)])
            else:
                subprocess.Popen(["xdg-open", str(resolved)])
        except Exception as exc:
            QMessageBox.warning(self, "폴더 열기", f"폴더를 여는 중 문제가 생겼습니다.\n{exc}")

    def _open_payroll_export_dir(self):
        folder = self._payroll_export_dir()
        folder.mkdir(parents=True, exist_ok=True)
        self._open_path_in_shell(folder)

    def _show_payroll_slip_export_menu_for_payload(self, payload: dict, anchor_widget: QWidget | None = None):
        if not payload:
            return
        menu = QMenu(self)
        actions = [
            ("PNG 저장", lambda: self._export_payroll_slip_file("png", payload)),
            ("JPG 저장", lambda: self._export_payroll_slip_file("jpg", payload)),
            ("프린터 출력", lambda: self._print_payroll_slip(payload)),
        ]
        for label, callback in actions:
            action = menu.addAction(label)
            action.triggered.connect(callback)
        button = anchor_widget if anchor_widget is not None else self
        rect = button.rect() if hasattr(button, "rect") else QRect(0, 0, 0, 0)
        menu.exec(button.mapToGlobal(rect.bottomLeft()))

    def _open_selected_payroll_popup(self, employee_id: int | None = None):
        target_employee_id = int(employee_id or self._resolve_selected_employee_id() or 0)
        if not target_employee_id:
            QMessageBox.information(self, "급여명세표", "먼저 급여표에서 직원을 선택하세요.")
            return
        try:
            payload = build_payroll_slip_payload(self.state, target_employee_id, self._month_key())
        except Exception as exc:
            QMessageBox.warning(self, "급여명세표", f"명세표 데이터를 만드는 중 문제가 생겼습니다.\n{exc}")
            return

        self._last_generated_slip_payload = payload
        self._slip_preview_ready = True

        dialog = QDialog(self)
        dialog.setWindowTitle(f"급여명세표 - {payload.get('employee_name', '')}")
        dialog.resize(980, 720)

        root = QVBoxLayout(dialog)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        top_note = QLabel("마우스 휠로 확대·축소하고, 왼쪽 버튼을 누른 채 움직이면 확대된 내용을 이동해서 볼 수 있습니다. 더블클릭하면 기본 크기로 돌아갑니다.")
        top_note.setWordWrap(True)
        top_note.setStyleSheet("color:#6B7280; font-size:12px;")
        root.addWidget(top_note)

        preview_scroll = QScrollArea()
        preview_scroll.setWidgetResizable(True)
        preview_scroll.setFrameShape(QFrame.NoFrame)
        preview_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        preview_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        preview_scroll.setStyleSheet("QScrollArea { background:#F3F4F6; border:1px solid #D1D5DB; border-radius:10px; }")
        preview_scroll.viewport().setCursor(Qt.OpenHandCursor)
        preview_host = QWidget()
        preview_layout = QVBoxLayout(preview_host)
        preview_layout.setContentsMargins(6, 6, 6, 6)
        preview_layout.setSpacing(0)
        preview_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        preview_label = QLabel()
        preview_label.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        preview_label.setStyleSheet("QLabel { background:#FFFFFF; border:1px solid #D1D5DB; border-radius:10px; padding: 6px; }")
        preview_layout.addWidget(preview_label, 0, Qt.AlignTop | Qt.AlignHCenter)
        preview_scroll.setWidget(preview_host)

        preview_nav_row = QHBoxLayout()
        preview_nav_row.setContentsMargins(0, 0, 0, 0)
        preview_nav_row.setSpacing(6)

        nav_button_style = (
            "QPushButton#PaystubNavButton {"
            "background:#F8FAFC; border:1px solid #CBD5E1; border-radius:10px;"
            "color:#1D4ED8; font-size:18px; font-weight:800; padding:0px;"
            "min-width:26px; max-width:26px; min-height:150px; max-height:150px;"
            "}"
            "QPushButton#PaystubNavButton:hover { background:#EFF6FF; border-color:#93C5FD; }"
            "QPushButton#PaystubNavButton:pressed { background:#DBEAFE; }"
            "QPushButton#PaystubNavButton:disabled { color:#94A3B8; background:#F1F5F9; border-color:#E2E8F0; }"
        )
        prev_employee_btn = QPushButton("‹")
        prev_employee_btn.setObjectName("PaystubNavButton")
        prev_employee_btn.setToolTip("이전 직원 급여명세표")
        prev_employee_btn.setFixedSize(26, 150)
        prev_employee_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        prev_employee_btn.setStyleSheet(nav_button_style)
        next_employee_btn = QPushButton("›")
        next_employee_btn.setObjectName("PaystubNavButton")
        next_employee_btn.setToolTip("다음 직원 급여명세표")
        next_employee_btn.setFixedSize(26, 150)
        next_employee_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        next_employee_btn.setStyleSheet(nav_button_style)

        preview_nav_row.addWidget(prev_employee_btn, 0, Qt.AlignVCenter)
        preview_nav_row.addWidget(preview_scroll, 1)
        preview_nav_row.addWidget(next_employee_btn, 0, Qt.AlignVCenter)
        root.addLayout(preview_nav_row, 1)

        state_box = {"payload": payload, "pixmap": None, "zoom": 1.0, "employee_id": int(target_employee_id)}

        def render_preview_pixmap():
            pixmap = state_box.get("pixmap")
            if pixmap is None or pixmap.isNull():
                return
            viewport = preview_scroll.viewport()
            max_w = max(240, viewport.width() - 32)
            max_h = max(240, viewport.height() - 32)
            base_scaled = pixmap.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            zoom = float(state_box.get("zoom", 1.0) or 1.0)
            target_w = max(160, int(base_scaled.width() * zoom))
            target_h = max(160, int(base_scaled.height() * zoom))
            scaled = pixmap.scaled(target_w, target_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            preview_label.setPixmap(scaled)
            preview_label.resize(scaled.size())
            preview_label.setMinimumSize(scaled.size())
            preview_label.setMaximumSize(scaled.size())
            margins = preview_layout.contentsMargins()
            preview_host.setMinimumSize(
                scaled.width() + margins.left() + margins.right(),
                scaled.height() + margins.top() + margins.bottom(),
            )

        def update_preview_image(current_payload: dict):
            png_bytes = build_payroll_slip_png_bytes(current_payload)
            image = QImage.fromData(png_bytes, "PNG")
            if image.isNull():
                raise RuntimeError("미리보기 이미지를 만들지 못했습니다.")
            pixmap = QPixmap.fromImage(image)
            state_box["pixmap"] = pixmap
            render_preview_pixmap()

        def refresh_preview():
            try:
                current_employee_id = int(state_box.get("employee_id") or target_employee_id)
                new_payload = build_payroll_slip_payload(self.state, current_employee_id, self._month_key())
                update_preview_image(new_payload)
            except Exception as exc:
                QMessageBox.warning(dialog, "급여명세표", f"명세표를 다시 만드는 중 문제가 생겼습니다.\n{exc}")
                return
            state_box["payload"] = new_payload
            self._last_generated_slip_payload = new_payload
            self._slip_preview_ready = True
            dialog.setWindowTitle(f"급여명세표 - {new_payload.get('employee_name', '')}")

        def _paystub_employee_order() -> list[int]:
            order: list[int] = []
            seen: set[int] = set()
            for meta in self._row_meta:
                if str(meta.get("category_key", "") or "") != "base":
                    continue
                try:
                    employee_id = int(meta.get("employee_id", 0) or 0)
                except Exception:
                    continue
                if employee_id > 0 and employee_id not in seen:
                    seen.add(employee_id)
                    order.append(employee_id)
            return order

        def _select_payroll_table_employee(employee_id: int):
            row = self._find_employee_start_row(int(employee_id))
            if row < 0 or not hasattr(self, "payroll_table"):
                return
            self.payroll_table.setCurrentCell(row, 0)
            item = self.payroll_table.item(row, 0)
            if item is not None:
                self.payroll_table.scrollToItem(item, QAbstractItemView.PositionAtCenter)
            self._last_selected_employee_id = int(employee_id)
            self._refresh_detail(int(employee_id))

        def move_paystub_employee(step: int):
            order = _paystub_employee_order()
            if len(order) <= 1:
                QMessageBox.information(dialog, "급여명세표", "이동할 다른 직원이 없습니다.")
                return
            current_employee_id = int(state_box.get("employee_id") or target_employee_id)
            try:
                current_index = order.index(current_employee_id)
            except ValueError:
                current_index = 0
            next_employee_id = int(order[(current_index + int(step)) % len(order)])
            try:
                new_payload = build_payroll_slip_payload(self.state, next_employee_id, self._month_key())
                update_preview_image(new_payload)
            except Exception as exc:
                QMessageBox.warning(dialog, "급여명세표", f"직원 명세표를 여는 중 문제가 생겼습니다.\n{exc}")
                return
            state_box["employee_id"] = next_employee_id
            state_box["payload"] = new_payload
            self._last_generated_slip_payload = new_payload
            self._slip_preview_ready = True
            dialog.setWindowTitle(f"급여명세표 - {new_payload.get('employee_name', '')}")
            _select_payroll_table_employee(next_employee_id)
            update_bank_info_label()

        def show_export_menu():
            self._show_payroll_slip_export_menu_for_payload(state_box["payload"], export_btn)

        resize_filter = _ResizeRefreshFilter(render_preview_pixmap, preview_scroll.viewport())
        preview_scroll.viewport().installEventFilter(resize_filter)
        preview_scroll._resize_refresh_filter = resize_filter

        zoom_pan_filter = _ZoomPanPreviewController(preview_scroll, state_box, render_preview_pixmap, preview_scroll.viewport())
        preview_scroll.viewport().installEventFilter(zoom_pan_filter)
        preview_scroll._zoom_pan_filter = zoom_pan_filter

        update_preview_image(payload)
        QTimer.singleShot(0, render_preview_pixmap)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(6)

        refresh_btn = QPushButton("다시 생성")
        refresh_btn.setObjectName("PrimaryButton")
        export_btn = QPushButton("출력")
        export_btn.setObjectName("GhostButton")
        export_btn.clicked.connect(show_export_menu)
        close_btn = QPushButton("닫기")
        close_btn.setObjectName("GhostButton")
        close_btn.clicked.connect(dialog.accept)

        bank_info_label = QLabel()
        bank_info_label.setObjectName("PaystubBankInfoLabel")
        bank_info_label.setAlignment(Qt.AlignCenter)
        bank_info_label.setMinimumHeight(30)
        bank_info_label.setMinimumWidth(360)
        bank_info_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        bank_info_label.setStyleSheet(
            "QLabel#PaystubBankInfoLabel {"
            "background:#F8FAFC; border:1px solid #CBD5E1; border-radius:8px;"
            "padding:4px 10px; color:#1E3A8A; font-size:12px; font-weight:600;"
            "}"
        )

        def update_bank_info_label():
            current_payload = state_box.get("payload") or payload
            current_employee_id = int(state_box.get("employee_id") or target_employee_id)
            employee = self.state.get_employee_by_id(current_employee_id) or {}
            bank_name = str(employee.get("bank_name") or employee.get("bank") or "").strip()
            account_number = str(employee.get("bank_account") or employee.get("account_number") or "").strip()
            holder = str(employee.get("name") or current_payload.get("employee_name") or "").strip()
            if bank_name and account_number:
                holder_part = f"  예금주: {holder}" if holder else ""
                bank_info_label.setText(f"입금계좌: {bank_name} {account_number}{holder_part}")
            elif bank_name:
                bank_info_label.setText(f"입금계좌: {bank_name} 계좌번호 미등록")
            elif account_number:
                holder_part = f"  예금주: {holder}" if holder else ""
                bank_info_label.setText(f"입금계좌: 은행 미등록 {account_number}{holder_part}")
            else:
                bank_info_label.setText("입금계좌: 미등록")

        def refresh_preview_with_bank_info():
            refresh_preview()
            update_bank_info_label()

        refresh_btn.clicked.connect(refresh_preview_with_bank_info)
        prev_employee_btn.clicked.connect(lambda: move_paystub_employee(-1))
        next_employee_btn.clicked.connect(lambda: move_paystub_employee(1))
        if len(_paystub_employee_order()) <= 1:
            prev_employee_btn.setEnabled(False)
            next_employee_btn.setEnabled(False)
        update_bank_info_label()

        button_row.addWidget(refresh_btn)
        button_row.addWidget(export_btn)
        button_row.addStretch(1)
        button_row.addWidget(bank_info_label, 2)
        button_row.addStretch(1)
        button_row.addWidget(close_btn)
        root.addLayout(button_row)

        dialog.exec()

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                self._clear_layout(child_layout)

    def _detail_site_context(self) -> tuple[str, str]:
        if self._last_selected_employee_id:
            emp = self.state.get_employee_by_id(int(self._last_selected_employee_id)) or {}
            return str(emp.get("affiliated_business", "") or ""), str(emp.get("work_site", "") or emp.get("company", "") or "")
        biz_name = self.biz_combo.currentText().strip() if hasattr(self, "biz_combo") else ""
        site_name = self.site_combo.currentText().strip() if hasattr(self, "site_combo") else ""
        if biz_name == "전체 사업자":
            biz_name = ""
        if site_name == "전체 근무 사업장":
            site_name = ""
        return biz_name, site_name

    def _rebuild_adjustment_sections(self):
        self._detail_field_edits = {}
        for grid in [self.summary_items_grid, self.allowance_grid, self.deduction_grid]:
            self._clear_layout(grid)

        business_name, site_name = self._detail_site_context()
        detail_rows = [
            row for row in self.state.get_payroll_detail_item_configs(site_name, business_name)
            if row.get("enabled", True) and row.get("location") in {"detail", "both"}
        ]
        grouped = {"summary": [], "allowance": [], "deduction": []}
        for row in detail_rows:
            grouped.setdefault(row.get("group", "summary"), []).append(row)

        def add_rows(grid, rows):
            for row_idx, row in enumerate(rows):
                label = QLabel(str(row.get("label", "")))
                label.setObjectName("DetailKey")
                label.setWordWrap(False)
                edit = QLineEdit()
                edit.setMinimumHeight(28)
                edit.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                edit.setProperty("payroll_key", row.get("key"))
                edit.setProperty("payroll_mode", row.get("input_mode", "manual"))
                if row.get("input_mode") == "readonly" or row.get("group") == "summary":
                    edit.setReadOnly(True)
                    edit.setStyleSheet("QLineEdit { background: #F8FAFC; color: #0F172A; font-weight: 700; }")
                else:
                    edit.setStyleSheet("QLineEdit { background: #FFFFFF; color: #0F172A; font-weight: 700; }")
                    edit.editingFinished.connect(lambda key=row.get("key"): self._save_adjustment_field(key))
                grid.addWidget(label, row_idx, 0)
                grid.addWidget(edit, row_idx, 1)
                self._detail_field_edits[str(row.get("key"))] = edit
            grid.setColumnStretch(1, 1)

        add_rows(self.summary_items_grid, grouped.get("summary", []))
        add_rows(self.allowance_grid, grouped.get("allowance", []))
        add_rows(self.deduction_grid, grouped.get("deduction", []))

    def _save_adjustment_field(self, key: str):
        if self._loading_detail_fields or not self._last_selected_employee_id:
            return
        edit = self._detail_field_edits.get(str(key))
        if not edit or edit.isReadOnly():
            return
        text = edit.text().strip().replace(",", "")
        if not text:
            value = 0.0
        else:
            try:
                value = float(text)
            except ValueError:
                payload = self.state.get_payroll_detail_payload(self._last_selected_employee_id, self._month_key())
                fallback = payload.get("adjustments", {}).get(str(key), 0)
                self._loading_detail_fields = True
                edit.setText(self._format_amount(fallback))
                self._loading_detail_fields = False
                QMessageBox.information(self, "급여 관리", "숫자만 입력할 수 있습니다.")
                return
        current = self.state.get_individual_adjustment(self._last_selected_employee_id, self._month_key())
        current[str(key)] = value
        self.state.set_individual_adjustment(self._last_selected_employee_id, self._month_key(), current)

    def _sync_selected_cell_editor(self, row: int, column: int):
        self._selected_cell_meta = None
        if row < 0 or row >= len(self._row_meta) or column < self._day_col_offset or column >= self._summary_col_offset:
            self.sel_cell_label.setText("선택된 날짜 칸이 없습니다.")
            self.sel_cell_input.clear()
            return
        meta = self._row_meta[row]
        day = column - self._day_col_offset + 1
        employee = meta.get("employee", {})
        entry = self.state.get_payroll_month_entry(int(meta["employee_id"]), self._month_key())
        value = float(entry.get(meta["category_key"], {}).get(day, 0) or 0)
        self._selected_cell_meta = {"row": row, "column": column, "day": day, **meta}
        self.sel_cell_label.setText(f"{employee.get('name', '')} · {meta.get('category_label', '')} · {day}일")
        self.sel_cell_input.setText(self._format_hours(value) if value > 0 else "")
        self.sel_cell_input.selectAll()

    def _focus_selected_cell_editor(self, row: int, column: int):
        self._update_detail_from_table_cell(row, column)
        self.sel_cell_input.setFocus()
        self.sel_cell_input.selectAll()

    def _handle_table_double_click(self, row: int, column: int):
        self._update_detail_from_table_cell(row, column)
        if column == 0:
            employee_id = self._resolve_selected_employee_id(row)
            if employee_id:
                self._open_selected_payroll_popup(int(employee_id))
            return
        self._focus_selected_cell_editor(row, column)

    def _on_table_cell_clicked(self, row: int, column: int):
        self._update_detail_from_table_cell(row, column)

    def _apply_current_cell_input(self):
        if not self._selected_cell_meta:
            return
        text = self.sel_cell_input.text().strip()
        if not text:
            value = 0.0
        else:
            try:
                value = float(text)
            except ValueError:
                QMessageBox.information(self, "급여 관리", "숫자만 입력할 수 있습니다.")
                self.sel_cell_input.setFocus()
                self.sel_cell_input.selectAll()
                return
        meta = self._selected_cell_meta
        self._set_payroll_cell_value(int(meta["employee_id"]), meta["category_key"], int(meta["day"]), value)
        self.payroll_table.setCurrentCell(int(meta["row"]), int(meta["column"]))
        self.sel_cell_input.setText(self._format_hours(value) if value > 0 else "")
        self.sel_cell_input.selectAll()

    def _clear_current_cell_input(self):
        self.sel_cell_input.clear()
        if self._selected_cell_meta:
            self._apply_current_cell_input()

    def _parse_numeric_text(self, raw_text: str) -> float | None:
        text = str(raw_text or "").strip().replace(",", "")
        if not text:
            return 0.0
        try:
            value = float(text)
        except ValueError:
            return None
        if value < 0:
            return None
        return value

    def _apply_batch_cell_updates(self, updates: list[tuple[int, str, int, float]], focus_cell: tuple[int, int] | None = None):
        if not updates:
            return
        month_key = self._month_key()
        grouped: dict[int, dict] = {}
        for employee_id, category_key, day, value in updates:
            emp_id = int(employee_id)
            entry = grouped.setdefault(emp_id, self.state.get_payroll_month_entry(emp_id, month_key))
            bucket = entry.setdefault(str(category_key), {})
            if float(value or 0) > 0:
                bucket[int(day)] = float(value)
            else:
                bucket.pop(int(day), None)
        if focus_cell is not None:
            self._pending_focus_cell = (int(focus_cell[0]), int(focus_cell[1]), False)
        self.state.set_payroll_month_entries_bulk(month_key, grouped)

    def _apply_batch_from_clipboard(self, start_row: int, start_col: int, grid_rows: list[list[str]], mapping: dict[tuple[int, int], list[str]] | None = None):
        updates: list[tuple[int, str, int, float]] = []
        last_focus = (start_row, start_col)
        invalid_found = False
        if mapping:
            iterable = sorted(mapping.items())
            for (row, col), values in iterable:
                raw_value = values[0] if values else ""
                if not self.payroll_table.is_day_input_cell(row, col) or row >= len(self._row_meta):
                    continue
                parsed = self._parse_numeric_text(raw_value)
                if parsed is None:
                    invalid_found = True
                    continue
                meta = self._row_meta[row]
                day = col - self._day_col_offset + 1
                updates.append((int(meta["employee_id"]), str(meta["category_key"]), int(day), float(parsed)))
                last_focus = (row, col)
        else:
            for row_offset, row_values in enumerate(grid_rows):
                target_row = start_row + row_offset
                if target_row >= self.payroll_table.rowCount() or target_row >= len(self._row_meta):
                    break
                for col_offset, raw_value in enumerate(row_values):
                    target_col = start_col + col_offset
                    if target_col >= self._summary_col_offset:
                        break
                    if not self.payroll_table.is_day_input_cell(target_row, target_col):
                        continue
                    parsed = self._parse_numeric_text(raw_value)
                    if parsed is None:
                        invalid_found = True
                        continue
                    meta = self._row_meta[target_row]
                    day = target_col - self._day_col_offset + 1
                    updates.append((int(meta["employee_id"]), str(meta["category_key"]), int(day), float(parsed)))
                    last_focus = (target_row, target_col)
        if updates:
            self._apply_batch_cell_updates(updates, focus_cell=last_focus)
        if invalid_found:
            QMessageBox.information(self, "급여 관리", "숫자만 입력할 수 있어 숫자가 아닌 값은 제외했습니다.")

    def _on_payroll_changed(self):
        if self._suppress_payroll_refresh:
            return
        self.refresh()

    def _set_payroll_cell_value(self, employee_id: int, category_key: str, day: int, value: float):
        self._suppress_payroll_refresh = True
        try:
            self.state.set_payroll_cell(int(employee_id), self._month_key(), category_key, int(day), float(value))
        finally:
            self._suppress_payroll_refresh = False
        self._refresh_employee_rows(int(employee_id))
        self._refresh_summary_cards_from_table()

        current_row = self.payroll_table.currentRow() if hasattr(self, "payroll_table") else -1
        current_col = self.payroll_table.currentColumn() if hasattr(self, "payroll_table") else -1
        if current_row >= 0 and current_col >= 0:
            self._update_detail_from_table_cell(current_row, current_col, sync_editor=False)
        elif self._last_selected_employee_id == int(employee_id):
            self._refresh_detail(int(employee_id))

    def _find_employee_start_row(self, employee_id: int) -> int:
        target = int(employee_id)
        for row, meta in enumerate(self._row_meta):
            if int(meta.get("employee_id", 0)) == target and str(meta.get("category_key")) == "base":
                return row
        return -1

    def _refresh_employee_rows(self, employee_id: int):
        start_row = self._find_employee_start_row(employee_id)
        if start_row < 0:
            return

        display_date = self._current_display_month()
        year, month = display_date.year(), display_date.month()
        last_day = monthrange(year, month)[1]
        entry = self.state.get_payroll_month_entry(int(employee_id), self._month_key())
        subtotal_map = {
            key: sum(float(entry.get(key, {}).get(day, 0) or 0) for day in range(1, last_day + 1))
            for key, _label in CATEGORY_ROWS
        }
        grand_total = subtotal_map["base"] + subtotal_map["over"] + subtotal_map["night"]

        bold_font = QFont()
        bold_font.setBold(True)

        self.payroll_table.blockSignals(True)
        try:
            for idx, (category_key, _category_label) in enumerate(CATEGORY_ROWS):
                row = start_row + idx
                if row >= self.payroll_table.rowCount():
                    continue
                for day in range(1, last_day + 1):
                    col = self._day_col_offset + day - 1
                    item = self.payroll_table.item(row, col)
                    if item is None:
                        continue
                    value = float(entry.get(category_key, {}).get(day, 0) or 0)
                    text = self._format_hours(value) if value > 0 else ""
                    if item.text() != text:
                        item.setText(text)
                    self._apply_payroll_cell_background(item, self._day_cell_background(entry, category_key, year, month, day))

                sub_item = self.payroll_table.item(row, self._summary_col_offset)
                if sub_item is not None:
                    sub_text = self._format_hours(subtotal_map[category_key]) if subtotal_map[category_key] > 0 else ""
                    if sub_item.text() != sub_text:
                        sub_item.setText(sub_text)
                    sub_item.setFont(bold_font if subtotal_map[category_key] > 0 else QFont())

                total_item = self.payroll_table.item(row, self._summary_col_offset + 1)
                if total_item is not None:
                    total_text = self._format_hours(grand_total) if idx == 0 and grand_total > 0 else ""
                    if total_item.text() != total_text:
                        total_item.setText(total_text)
                    if idx == 0 and grand_total > 0:
                        total_item.setFont(bold_font)
                        total_item.setForeground(QBrush(QColor("#059669")))
                    else:
                        total_item.setFont(QFont())
                        total_item.setForeground(QBrush(QColor("#0F172A")))
        finally:
            self.payroll_table.blockSignals(False)

    def _refresh_summary_cards_from_table(self):
        count = len(self._filtered_employees())
        total_hours = 0.0
        if hasattr(self, "payroll_table"):
            for row in range(0, self.payroll_table.rowCount(), len(CATEGORY_ROWS)):
                total_item = self.payroll_table.item(row, self._summary_col_offset + 1)
                raw = (total_item.text() or "").strip() if total_item is not None else ""
                try:
                    total_hours += float(raw) if raw else 0.0
                except ValueError:
                    continue
        avg_hours = total_hours / count if count else 0
        self.total_hours_card.value_lbl.setText(f"{self._format_hours(total_hours)}H")
        self.avg_hours_card.value_lbl.setText(f"{self._format_hours(avg_hours)}H")
        self.headcount_card.value_lbl.setText(f"{count}명")

    def _on_settings_changed(self):
        self._rebuild_adjustment_sections()
        self.refresh(False)

    def _apply_query_filters(self):
        start = QDate(int(self.start_year_combo.currentData()), int(self.start_month_combo.currentData()), 1)
        end = QDate(int(self.end_year_combo.currentData()), int(self.end_month_combo.currentData()), 1)
        if end < start:
            end = QDate(start.year(), start.month(), 1)
        preferred = self.active_display_month if start <= self.active_display_month <= end else start
        self.range_start_month = start
        self.range_end_month = end
        self._sync_month_range_inputs()
        self._refresh_display_month_buttons(start, end, preferred)
        self.refresh()

    def _on_biz_changed(self):
        biz_name = self.biz_combo.currentText().strip()
        if biz_name == "전체 사업자":
            biz_name = None
        self._refresh_site_combo(biz_name)
        self.refresh(False)

    def _refresh_site_combo(self, biz_name: str | None = None):
        current = self.site_combo.currentText().strip() if hasattr(self, "site_combo") else ""
        self.site_combo.blockSignals(True)
        self.site_combo.clear()
        self.site_combo.addItem("전체 근무 사업장")
        for site in self.state.work_site_records(biz_name):
            if site.get("name"):
                self.site_combo.addItem(site["name"])
        idx = self.site_combo.findText(current)
        self.site_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.site_combo.blockSignals(False)

    def _refresh_biz_combo(self):
        current = self.biz_combo.currentText().strip() if hasattr(self, "biz_combo") else ""
        self.biz_combo.blockSignals(True)
        self.biz_combo.clear()
        self.biz_combo.addItem("전체 사업자")
        for business in self.state.business_master_records():
            if business.get("name"):
                self.biz_combo.addItem(business["name"])
        idx = self.biz_combo.findText(current)
        self.biz_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.biz_combo.blockSignals(False)
        self._refresh_site_combo(None if current == "전체 사업자" else current)

    def _filtered_employees(self) -> list[dict]:
        biz_filter = self.biz_combo.currentText().strip() if hasattr(self, "biz_combo") else "전체 사업자"
        site_filter = self.site_combo.currentText().strip() if hasattr(self, "site_combo") else "전체 근무 사업장"
        search = self.search_edit.text().strip().lower()

        employees = [row for row in self.state.employees if row.get("status") != "퇴사"]
        if biz_filter and biz_filter != "전체 사업자":
            employees = [row for row in employees if row.get("affiliated_business") == biz_filter]
        if site_filter and site_filter != "전체 근무 사업장":
            employees = [row for row in employees if row.get("work_site") == site_filter]
        if search:
            filtered = []
            for row in employees:
                haystack = " ".join([
                    str(row.get("name", "")),
                    str(row.get("affiliated_business", "")),
                    str(row.get("work_site", "")),
                ]).lower()
                if search in haystack:
                    filtered.append(row)
            employees = filtered
        return employees

    def _month_key(self) -> str:
        date = self._current_display_month()
        return f"{date.year()}-{date.month():02d}"

    def _update_month_close_button_state(self):
        if not hasattr(self, "month_close_btn"):
            return
        month_key = self._month_key()
        locked = False
        lock_info = None
        if hasattr(self.state, "is_attendance_month_locked"):
            locked = bool(self.state.is_attendance_month_locked(month_key))
        if locked and hasattr(self.state, "get_attendance_month_lock"):
            lock_info = self.state.get_attendance_month_lock(month_key) or {}
        if locked:
            self.month_close_btn.setText("마감 완료")
            self.month_close_btn.setEnabled(False)
            locked_at = str((lock_info or {}).get("locked_at") or "")
            self.month_close_btn.setToolTip(f"{month_key} 마감 완료" + (f"\n마감일시: {locked_at}" if locked_at else ""))
            if hasattr(self, "month_reopen_btn"):
                self.month_reopen_btn.setVisible(True)
                self.month_reopen_btn.setEnabled(True)
                self.month_reopen_btn.setToolTip("현재 표시 월의 마감을 취소하고 모바일 근태 수정 잠금을 해제합니다.")
        else:
            self.month_close_btn.setText("월 마감")
            self.month_close_btn.setEnabled(True)
            self.month_close_btn.setToolTip("현재 표시 월을 마감하고 모바일 근태 수정을 잠급니다.")
            if hasattr(self, "month_reopen_btn"):
                self.month_reopen_btn.setVisible(False)
                self.month_reopen_btn.setEnabled(False)
                self.month_reopen_btn.setToolTip("마감된 월에서만 사용할 수 있습니다.")

    def _close_current_month(self):
        month_key = self._month_key()
        if hasattr(self.state, "is_attendance_month_locked") and self.state.is_attendance_month_locked(month_key):
            QMessageBox.information(self, "월 마감", f"{month_key}은 이미 마감된 월입니다.")
            self._update_month_close_button_state()
            return

        box = QMessageBox(self)
        box.setWindowTitle("월 마감")
        box.setText(f"{month_key} 급여/근태 자료를 마감하시겠습니까?")
        box.setInformativeText("마감 후 모바일에서 해당 월 근태 수정이 불가능합니다.\n계속 진행하시겠습니까?")
        close_btn = box.addButton("마감", QMessageBox.AcceptRole)
        box.addButton("취소", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not close_btn:
            return

        if not hasattr(self.state, "close_attendance_month"):
            QMessageBox.information(self, "월 마감", "현재 프로그램 상태에서 월 마감 저장 기능을 사용할 수 없습니다.")
            return
        result = self.state.close_attendance_month(
            month_key,
            locked_by="PC 급여관리",
            memo="급여관리 화면에서 월 마감 처리",
        )
        self._update_month_close_button_state()
        if bool((result or {}).get("server_synced")):
            QMessageBox.information(
                self,
                "월 마감",
                f"{month_key} 월 마감이 완료되었습니다.\n서버에도 반영되어 모바일에서는 해당 월 근태 수정이 잠깁니다.",
            )
        else:
            reason = str((result or {}).get("server_sync_message") or "서버 연결 상태를 확인해 주세요.")
            QMessageBox.warning(
                self,
                "월 마감",
                f"{month_key} 월 마감은 PC에 저장되었습니다.\n다만 서버 반영은 실패했습니다.\n\n사유: {reason}",
            )


    def _reopen_current_month(self):
        month_key = self._month_key()
        if not (hasattr(self.state, "is_attendance_month_locked") and self.state.is_attendance_month_locked(month_key)):
            QMessageBox.information(self, "마감 취소", f"{month_key}은 마감된 월이 아닙니다.")
            self._update_month_close_button_state()
            return

        box = QMessageBox(self)
        box.setWindowTitle("마감 취소")
        box.setText(f"{month_key} 마감을 취소하시겠습니까?")
        box.setInformativeText("마감이 취소되면 모바일에서 해당 월 근태 수정이 다시 가능해질 수 있습니다.\n계속 진행하시겠습니까?")
        reopen_btn = box.addButton("마감 취소", QMessageBox.AcceptRole)
        box.addButton("닫기", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not reopen_btn:
            return

        if not hasattr(self.state, "reopen_attendance_month"):
            QMessageBox.information(self, "마감 취소", "현재 프로그램 상태에서 마감 취소 저장 기능을 사용할 수 없습니다.")
            return
        result = self.state.reopen_attendance_month(
            month_key,
            reopened_by="PC 급여관리",
            memo="급여관리 화면에서 월 마감 취소",
        )
        self._update_month_close_button_state()
        if bool((result or {}).get("server_synced")):
            QMessageBox.information(
                self,
                "마감 취소",
                f"{month_key} 마감이 취소되었습니다.\n서버에도 반영되어 모바일 근태 수정 잠금이 해제됩니다.",
            )
        else:
            reason = str((result or {}).get("server_sync_message") or "서버 연결 상태를 확인해 주세요.")
            QMessageBox.warning(
                self,
                "마감 취소",
                f"{month_key} 마감 취소는 PC에 저장되었습니다.\n다만 서버 반영은 실패했습니다.\n\n사유: {reason}",
            )

    def _format_hours(self, value: float) -> str:
        if abs(value - int(value)) < 1e-9:
            return str(int(value))
        text = f"{value:.2f}".rstrip("0").rstrip(".")
        return text

    def _column_date(self, column: int) -> str:
        if column < self._day_col_offset or column >= self._summary_col_offset:
            return ""
        day = column - self._day_col_offset + 1
        display = self._current_display_month()
        qdate = QDate(display.year(), display.month(), day)
        return qdate.toString("yyyy-MM-dd") if qdate.isValid() else ""

    def _holiday_name(self, date: str) -> str:
        value = QDate.fromString(date, "yyyy-MM-dd")
        if not value.isValid():
            return ""
        return build_korean_holiday_map(value.year()).get(date, "")

    def _holiday_short_name(self, date: str) -> str:
        name = self._holiday_name(date)
        return HOLIDAY_SHORT_NAMES.get(name, name)

    def _is_named_holiday(self, date: str) -> bool:
        return bool(self._holiday_name(date))

    def _is_holiday_date(self, date: str) -> bool:
        value = QDate.fromString(date, "yyyy-MM-dd")
        return value.isValid() and (value.dayOfWeek() == 7 or self._is_named_holiday(date))

    def _header_number_color(self, date: str) -> str:
        value = QDate.fromString(date, "yyyy-MM-dd")
        if not value.isValid():
            return "#0F172A"
        if self._is_named_holiday(date) or value.dayOfWeek() == 7:
            return "#DC2626"
        if value.dayOfWeek() == 6:
            return "#2563EB"
        return "#0F172A"

    def _header_tooltip(self, date: str) -> str:
        value = QDate.fromString(date, "yyyy-MM-dd")
        if not value.isValid():
            return date
        weekday_map = {1: "월요일", 2: "화요일", 3: "수요일", 4: "목요일", 5: "금요일", 6: "토요일", 7: "일요일"}
        holiday_name = self._holiday_name(date)
        if holiday_name:
            return f"{date} · {weekday_map.get(value.dayOfWeek(), '')} · {holiday_name}"
        return f"{date} · {weekday_map.get(value.dayOfWeek(), '')}"

    def _row_band_color(self, category_key: str, year: int | None = None, month: int | None = None, day: int | None = None) -> str:
        if year and month and day:
            qdate = QDate(int(year), int(month), int(day))
            if qdate.isValid() and self._is_holiday_date(qdate.toString("yyyy-MM-dd")):
                return HOLIDAY_COLUMN_BG
        return "#FFFFFF"

    def _fit_payroll_table(self, last_day: int | None = None):
        if not hasattr(self, "payroll_table") or not hasattr(self, "month_strip"):
            return
        display_date = self._current_display_month()
        effective_last_day = int(last_day or monthrange(display_date.year(), display_date.month())[1])
        table = self.payroll_table
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Fixed)

        frame_width = table.frameWidth() * 2
        h_scroll_height = table.horizontalScrollBar().sizeHint().height() if table.horizontalScrollBar() else 16

        name_width = 84
        category_width = 46
        subtotal_width = 56
        total_width = 60
        visible_day_count = max(1, effective_last_day)
        body_width = self.table_panel.body.width() if hasattr(self, "table_panel") and self.table_panel.body.width() > 0 else max(table.width(), 980)
        available_width = max(820, body_width - frame_width - 6)
        fixed_width = name_width + category_width + subtotal_width + total_width
        day_width = max(38, min(48, int((available_width - fixed_width) / visible_day_count)))

        table.setColumnWidth(0, name_width)
        table.setColumnWidth(1, category_width)
        for day in range(1, 32):
            col = self._day_col_offset + day - 1
            hidden = day > effective_last_day
            table.setColumnHidden(col, hidden)
            if not hidden:
                table.setColumnWidth(col, day_width)
        table.setColumnWidth(self._summary_col_offset, subtotal_width)
        table.setColumnWidth(self._summary_col_offset + 1, total_width)

        row_height = 26
        header_height = 42
        header.setFixedHeight(header_height)
        table.verticalHeader().setDefaultSectionSize(row_height)

        if hasattr(self, "table_panel") and self.table_panel.body.height() > 0:
            month_height = max(self.month_strip.height(), self.month_strip.sizeHint().height())
            body_available = self.table_panel.body.height() - month_height - self.table_panel.body_layout.spacing() - 2
        else:
            body_available = self.height() - 300

        min_body_height = header_height + (row_height * 8) + h_scroll_height + frame_width + 6

        # 표 높이를 현재 표/패널 높이에 다시 맞추면 바깥 페이지 스크롤 영역이
        # 커지고, 그 커진 높이를 기준으로 표가 또 커지는 순환이 생길 수 있다.
        # 창 높이를 기준으로 안전한 최대값을 두고, 많은 근로자는 표 내부 스크롤로만 본다.
        window = self.window()
        window_height = window.height() if window is not None and window.height() > 0 else self.height()
        safe_max_height = max(min_body_height, min(620, max(320, window_height - 300)))
        requested_height = body_available if body_available > 0 else self.height() - 300
        body_height = max(min_body_height, min(requested_height, safe_max_height))

        table.setMinimumHeight(body_height)
        table.setMaximumHeight(body_height)

    def _make_readonly_item(self, text: str = "", align=Qt.AlignCenter, user_data=None, bg: str | None = None):
        item = QTableWidgetItem(text)
        item.setTextAlignment(align | Qt.AlignVCenter)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        if user_data is not None:
            item.setData(Qt.UserRole, user_data)
        if bg:
            color = QColor(bg)
            item.setData(Qt.BackgroundRole, color)
            item.setBackground(QBrush(color))
        return item

    def _make_editable_item(self, text: str = "", bg: str | None = None):
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignCenter)
        if bg:
            color = QColor(bg)
            item.setData(Qt.BackgroundRole, color)
            item.setBackground(QBrush(color))
        return item

    def _apply_holiday_day_cell_backgrounds(self, year: int, month: int, last_day: int):
        month_key = f"{year}-{month:02d}"
        entry_cache: dict[int, dict] = {}
        for row in range(self.payroll_table.rowCount()):
            meta = self._row_meta[row] if row < len(self._row_meta) else {}
            employee_id = int(meta.get("employee_id", 0) or 0) if meta else 0
            category_key = str(meta.get("category_key", "") or "")
            if employee_id and employee_id not in entry_cache:
                entry_cache[employee_id] = self.state.get_payroll_month_entry(employee_id, month_key)
            entry = entry_cache.get(employee_id, {})
            for day in range(1, 32):
                col = self._day_col_offset + day - 1
                item = self.payroll_table.item(row, col)
                if item is None:
                    continue
                if day > last_day:
                    color_hex = "#E2E8F0"
                elif category_key in {"base", "over", "night"}:
                    color_hex = self._day_cell_background(entry, category_key, year, month, day)
                else:
                    color_hex = HOLIDAY_COLUMN_BG if self._is_holiday_date(QDate(year, month, day).toString("yyyy-MM-dd")) else "#FFFFFF"
                self._apply_payroll_cell_background(item, color_hex)

    def refresh(self, update_combos: bool = True):
        preferred_month = self.state.get_payroll_active_month()
        if preferred_month:
            try:
                y, m = map(int, preferred_month.split("-"))
                preferred_qdate = QDate(y, m, 1)
                if preferred_qdate.isValid():
                    if preferred_qdate < self.range_start_month or preferred_qdate > self.range_end_month:
                        self.range_start_month = preferred_qdate
                        self.range_end_month = preferred_qdate
                        self._sync_month_range_inputs()
                    if preferred_qdate != self.active_display_month:
                        self._refresh_display_month_buttons(self.range_start_month, self.range_end_month, preferred_qdate)
            except Exception:
                pass

        if update_combos:
            self._refresh_biz_combo()

        display_date = self._current_display_month()
        year, month = display_date.year(), display_date.month()
        month_key = f"{year}-{month:02d}"
        last_day = monthrange(year, month)[1]
        start_month = f"{self.range_start_month.year()}-{self.range_start_month.month():02d}"
        end_month = f"{self.range_end_month.year()}-{self.range_end_month.month():02d}"
        self.table_panel.header.title_lbl.setText(f"월간 급여표 ({month_key})")
        if start_month == end_month:
            self.table_panel.header.note_lbl.setText(f"조회 기간: {start_month}")
        else:
            self.table_panel.header.note_lbl.setText(f"조회 기간: {start_month} ~ {end_month}")
        self._update_month_close_button_state()

        self.payroll_header.clear_section_meta()
        self.payroll_header.set_section_meta(0, {
            "main_text": "이름",
            "background": HEADER_BG,
            "main_background": HEADER_BG,
            "main_color": "#0F172A",
            "main_font_size": 9,
        })
        self.payroll_header.set_section_meta(1, {
            "main_text": "구분",
            "background": HEADER_BG,
            "main_background": HEADER_BG,
            "main_color": "#0F172A",
            "main_font_size": 9,
        })
        for day in range(1, 32):
            col = self._day_col_offset + day - 1
            if day <= last_day:
                date = QDate(year, month, day).toString("yyyy-MM-dd")
                self.payroll_header.set_section_meta(col, {
                    "main_text": str(day),
                    "note_text": self._holiday_short_name(date),
                    "split": True,
                    "background": HEADER_BG,
                    "main_background": HEADER_BG,
                    "note_background": HEADER_BG,
                    "main_color": self._header_number_color(date),
                    "note_color": "#DC2626",
                    "main_font_size": 9,
                    "note_font_size": 7,
                    "tooltip": self._header_tooltip(date),
                })
            else:
                self.payroll_header.set_section_meta(col, {
                    "main_text": "",
                    "background": HEADER_BG,
                    "main_background": HEADER_BG,
                })
        self.payroll_header.set_section_meta(self._summary_col_offset, {
            "main_text": "소계",
            "background": HEADER_BG,
            "main_background": HEADER_BG,
            "main_color": "#0F172A",
            "main_font_size": 9,
        })
        self.payroll_header.set_section_meta(self._summary_col_offset + 1, {
            "main_text": "총",
            "background": HEADER_BG,
            "main_background": HEADER_BG,
            "main_color": "#0F172A",
            "main_font_size": 9,
        })

        employees = self._filtered_employees()
        self._row_meta = []
        loaded_count = 0
        total_hours = 0.0

        self._loading_table = True
        self.payroll_table.blockSignals(True)
        self.payroll_table.setUpdatesEnabled(False)

        try:
            self.payroll_table.setRowCount(len(employees) * 3)

            bold_font = QFont()
            bold_font.setBold(True)

            current_row = 0
            for emp in employees:
                emp_id = int(emp["id"])
                # 직원별 월 급여 데이터는 한 번만 가져와 표 값/소계/배경색 계산에 재사용한다.
                # AppState.get_payroll_month_entry()가 deepcopy를 반환하므로 반복 호출하면 직원 수가
                # 많을 때 급여표 첫 로딩 시간이 길어진다.
                entry = self.state.get_payroll_month_entry(emp_id, month_key)
                has_loaded = any(bool(entry.get(key)) for key in ("base", "over", "night"))
                if has_loaded:
                    loaded_count += 1

                subtotal_map = {}
                for key, _label in CATEGORY_ROWS:
                    subtotal_map[key] = sum(float(entry.get(key, {}).get(day, 0) or 0) for day in range(1, last_day + 1))
                grand_total = subtotal_map["base"] + subtotal_map["over"] + subtotal_map["night"]
                total_hours += grand_total

                for idx, (category_key, category_label) in enumerate(CATEGORY_ROWS):
                    row = current_row + idx
                    self._row_meta.append({
                        "employee_id": emp_id,
                        "employee": emp,
                        "category_key": category_key,
                        "category_label": category_label,
                    })
                    self.payroll_table.setRowHeight(row, 26)

                    name_text = emp.get("name", "") if idx == 0 else ""
                    name_item = self._make_readonly_item(name_text, Qt.AlignLeft, user_data=emp_id, bg="#FFFFFF")
                    if idx == 0:
                        name_item.setFont(bold_font)
                        name_item.setToolTip(str(emp.get("name", "") or ""))
                    self.payroll_table.setItem(row, 0, name_item)

                    category_bg = self._row_band_color(category_key)
                    category_item = self._make_readonly_item(category_label, Qt.AlignCenter, bg=category_bg)
                    self.payroll_table.setItem(row, 1, category_item)

                    for day in range(1, 32):
                        col = self._day_col_offset + day - 1
                        if day <= last_day:
                            value = float(entry.get(category_key, {}).get(day, 0) or 0)
                            text = self._format_hours(value) if value > 0 else ""
                            day_bg = self._day_cell_background(entry, category_key, year, month, day)
                            day_item = self._make_editable_item(text, day_bg)
                            day_item.setData(Qt.UserRole, {"employee_id": emp_id, "category_key": category_key, "day": day})
                        else:
                            day_item = self._make_readonly_item("", Qt.AlignCenter, bg="#E2E8F0")
                        self.payroll_table.setItem(row, col, day_item)

                    subtotal_bg = self._row_band_color(category_key)
                    sub_item = self._make_readonly_item(self._format_hours(subtotal_map[category_key]) if subtotal_map[category_key] > 0 else "", Qt.AlignRight, bg=subtotal_bg)
                    if subtotal_map[category_key] > 0:
                        sub_item.setFont(bold_font)
                    self.payroll_table.setItem(row, self._summary_col_offset, sub_item)

                    total_text = self._format_hours(grand_total) if idx == 0 and grand_total > 0 else ""
                    total_item = self._make_readonly_item(total_text, Qt.AlignRight, bg="#ECFDF5" if idx == 0 else subtotal_bg)
                    if idx == 0 and grand_total > 0:
                        total_item.setFont(bold_font)
                        total_item.setForeground(QBrush(QColor("#059669")))
                    self.payroll_table.setItem(row, self._summary_col_offset + 1, total_item)

                current_row += 3

        finally:
            self.payroll_table.blockSignals(False)
            self.payroll_table.setUpdatesEnabled(True)
            self.payroll_table.viewport().update()
            self._loading_table = False

        count = len(employees)
        avg_hours = total_hours / count if count else 0
        self.total_hours_card.value_lbl.setText(f"{self._format_hours(total_hours)}H")
        self.avg_hours_card.value_lbl.setText(f"{self._format_hours(avg_hours)}H")
        self.headcount_card.value_lbl.setText(f"{count}명")
        self._fit_payroll_table(last_day)

        if self._pending_focus_cell is not None:
            focus_row, focus_col, focus_edit = self._pending_focus_cell
            self._pending_focus_cell = None
            if 0 <= focus_row < self.payroll_table.rowCount() and self.payroll_table.is_day_input_cell(focus_row, focus_col):
                self.payroll_table.setCurrentCell(focus_row, focus_col)
                if focus_edit:
                    self.payroll_table.move_to_input_cell(focus_row, focus_col, start_edit=True)

        if self._last_selected_employee_id and any(int(emp["id"]) == self._last_selected_employee_id for emp in employees):
            selected_employee_id = int(self._last_selected_employee_id)
            current_row = self.payroll_table.currentRow()
            current_col = self.payroll_table.currentColumn()
            QTimer.singleShot(0, lambda emp_id=selected_employee_id, row=current_row, col=current_col: self._finish_refresh_detail_after_table(emp_id, row, col))
        else:
            self._clear_detail()

    def _finish_refresh_detail_after_table(self, employee_id: int, row: int, col: int):
        if self._loading_table:
            QTimer.singleShot(0, lambda: self._finish_refresh_detail_after_table(employee_id, row, col))
            return
        if int(self._last_selected_employee_id or 0) != int(employee_id):
            return
        if not any(int(meta.get("employee_id") or 0) == int(employee_id) for meta in self._row_meta):
            self._clear_detail()
            return
        self._refresh_detail(employee_id)
        self._sync_selected_cell_editor(row, col)

    def _clear_detail(self):
        self.det_name.setText("—")
        self.det_meta.setText("—")
        self.det_pay_type.setText("급여형태: —")
        self.det_month.setText("표시 월: —")
        self.det_base.setText("기본 소계: —")
        self.det_over.setText("연장 소계: —")
        self.det_night.setText("심야 소계: —")
        self.det_total.setText("총시간: —")
        self.sel_cell_label.setText("선택된 날짜 칸이 없습니다.")
        self.sel_cell_input.clear()
        self._selected_cell_meta = None
        self._loading_detail_fields = True
        for edit in self._detail_field_edits.values():
            edit.clear()
        self._loading_detail_fields = False
        self._reset_slip_preview()

    def _resolve_selected_employee_id(self, row: int | None = None) -> int | None:
        if row is not None and 0 <= row < len(self._row_meta):
            try:
                return int(self._row_meta[row]["employee_id"])
            except Exception:
                return None
        current_row = self.payroll_table.currentRow() if hasattr(self, "payroll_table") else -1
        if 0 <= current_row < len(self._row_meta):
            try:
                return int(self._row_meta[current_row]["employee_id"])
            except Exception:
                return None
        if hasattr(self, "payroll_table") and self.payroll_table.selectionModel() is not None:
            indexes = self.payroll_table.selectionModel().selectedIndexes()
            if indexes:
                pick_row = min(index.row() for index in indexes)
                if 0 <= pick_row < len(self._row_meta):
                    try:
                        return int(self._row_meta[pick_row]["employee_id"])
                    except Exception:
                        return None
        return None

    def _update_detail_from_table_cell(self, row: int, column: int, *, sync_editor: bool = True):
        employee_id = self._resolve_selected_employee_id(row)
        if employee_id:
            self._last_selected_employee_id = int(employee_id)
            self._refresh_detail(self._last_selected_employee_id)
        else:
            self._clear_detail()
        if sync_editor:
            self._sync_selected_cell_editor(row, column)

    def _on_table_selection_changed(self):
        if self._loading_table:
            return
        row = self.payroll_table.currentRow() if hasattr(self, "payroll_table") else -1
        column = self.payroll_table.currentColumn() if hasattr(self, "payroll_table") else -1
        employee_id = self._resolve_selected_employee_id(row)
        if employee_id:
            self._last_selected_employee_id = int(employee_id)
            self._refresh_detail(self._last_selected_employee_id)
        elif not self.payroll_table.selectedItems():
            self._clear_detail()
        if self.payroll_table.is_day_input_cell(row, column):
            self._sync_selected_cell_editor(row, column)
        elif not self.payroll_table.selectedItems():
            self._sync_selected_cell_editor(-1, -1)

    def _refresh_detail(self, employee_id: int):
        emp = self.state.get_employee_by_id(int(employee_id))
        if not emp:
            self._clear_detail()
            return
        month_key = self._month_key()
        payload = self.state.get_payroll_detail_payload(int(employee_id), month_key)
        summary_values = payload.get("summary_values", {})

        self.det_name.setText(emp.get("name", ""))
        self.det_meta.setText(f"{emp.get('affiliated_business', '')} · {emp.get('work_site', '')}")
        effective_pay_type = str(payload.get("effective_pay_type") or emp.get("pay_type", "-") or "-")
        effective_work_type = str(payload.get("effective_work_type") or emp.get("work_type", "-") or "-")
        self.det_pay_type.setText(f"급여형태: {effective_pay_type} / 근무형태: {effective_work_type}")
        self.det_month.setText(f"표시 월: {month_key}")
        self.det_base.setText(f"기본 소계: {self._format_hours(summary_values.get('base_hours', 0))}H")
        self.det_over.setText(f"연장 소계: {self._format_hours(summary_values.get('over_hours', 0))}H")
        self.det_night.setText(f"심야 소계: {self._format_hours(summary_values.get('night_hours', 0))}H")
        self.det_total.setText(f"총시간: {self._format_hours(summary_values.get('total_hours', 0))}H")

        value_map = {row.get('key'): row.get('value', 0) for group in ('summary', 'allowance', 'deduction') for row in payload.get(group, [])}
        self._loading_detail_fields = True
        for key, edit in self._detail_field_edits.items():
            value = value_map.get(key, 0)
            edit.setText(self._format_amount(value))
        self._loading_detail_fields = False
        self._reset_slip_preview("선택 직원 또는 급여 값이 바뀌었습니다. <b>명세표 생성</b>을 다시 눌러 최신 결과를 확인하세요.")

    def _on_current_cell_changed(self, current_row: int, current_column: int, _prev_row: int, _prev_column: int):
        if self._loading_table:
            return
        if current_row < 0 or current_row >= len(self._row_meta):
            if not self.payroll_table.selectedItems():
                self._clear_detail()
            else:
                self._sync_selected_cell_editor(-1, -1)
            return
        self._update_detail_from_table_cell(current_row, current_column)

    def _handle_cell_changed(self, row: int, column: int):
        if self._loading_table:
            return
        if row < 0 or row >= len(self._row_meta):
            return
        if column < self._day_col_offset or column >= self._summary_col_offset:
            return
        item = self.payroll_table.item(row, column)
        if item is None:
            return
        meta = self._row_meta[row]
        day = column - self._day_col_offset + 1
        text = (item.text() or "").strip()
        if not text:
            value = 0.0
        else:
            try:
                value = float(text)
            except ValueError:
                self._restore_cell_value(int(meta["employee_id"]), meta["category_key"], day, row, column)
                return
        self._set_payroll_cell_value(int(meta["employee_id"]), meta["category_key"], day, value)

    def _restore_cell_value(self, employee_id: int, category_key: str, day: int, row: int, column: int):
        entry = self.state.get_payroll_month_entry(employee_id, self._month_key())
        value = float(entry.get(category_key, {}).get(day, 0) or 0)
        self.payroll_table.blockSignals(True)
        self.payroll_table.item(row, column).setText(self._format_hours(value) if value > 0 else "")
        self.payroll_table.blockSignals(False)
        QMessageBox.information(self, "급여 관리", "숫자만 입력할 수 있습니다.")

    def _day_type_candidates_for_date(self, date_key: str) -> list[str]:
        qdate = QDate.fromString(str(date_key or ""), "yyyy-MM-dd")
        if not qdate.isValid():
            return ["전체", ""]
        named_holiday = self._is_named_holiday(date_key)
        if named_holiday:
            return ["공휴일", "일요일공휴일", "주말", "전체", ""]
        if qdate.dayOfWeek() == 7:
            return ["일요일공휴일", "일요일", "공휴일", "주말", "전체", ""]
        if qdate.dayOfWeek() == 6:
            return ["토요일", "주말", "전체", ""]
        return ["평일", "전체", ""]

    def _payroll_source_hours_for_day(self, employee_id: int, month_key: str, day: int, employee: dict, entry: dict) -> tuple[float, float, float]:
        def _num(value) -> float:
            try:
                return float(value or 0)
            except (TypeError, ValueError):
                return 0.0

        base = _num(entry.get("base", {}).get(day, 0))
        over = _num(entry.get("over", {}).get(day, 0))
        night = _num(entry.get("night", {}).get(day, 0))
        if base > 0 or over > 0 or night > 0:
            return round(base, 2), round(over, 2), round(night, 2)

        date_key = f"{month_key}-{day:02d}"
        record = getattr(self.state, "monthly_records", {}).get((int(employee_id), date_key), {})
        base = _num(record.get("base", 0))
        over = _num(record.get("over", 0))
        night = _num(record.get("night", 0))
        status = str(record.get("status", "") or "").strip()
        if base <= 0 and over <= 0 and night <= 0 and status in {"출석", "지각", "조퇴", "병원"}:
            base, over, night = self.state.get_default_attendance_hours(employee, date_key, status)
        elif base <= 0 and over <= 0 and night <= 0 and status in {"", "휴무"}:
            base, over, night = self.state.get_weekly_paid_sunday_hours(int(employee_id), date_key)
        return round(float(base or 0), 2), round(float(over or 0), 2), round(float(night or 0), 2)

    def _site_conversion_rules_for_employee(self, employee: dict) -> list[dict]:
        if not hasattr(self.state, "site_time_conversion_rules"):
            return []
        site = str(employee.get("work_site") or employee.get("company") or "").strip()
        biz = str(employee.get("affiliated_business") or "").strip()
        all_rows = self.state.site_time_conversion_rules()

        def _same(a, b):
            return str(a or "").strip() == str(b or "").strip()

        rows = []
        for row in all_rows:
            row_site = str(row.get("work_site_name") or "").strip()
            row_biz = str(row.get("business_name") or "").strip()
            if not row_site:
                continue
            if _same(row_site, site) or (site and site in row_site) or (row_site and row_site in site):
                if not row_biz or not biz or _same(row_biz, biz):
                    rows.append(dict(row))
        return sorted(rows, key=lambda r: int(float(r.get("order", 0) or 0)))

    def _rule_number(self, row: dict, key: str) -> float:
        try:
            return float(row.get(key, 0) or 0)
        except (TypeError, ValueError):
            return 0.0

    def _rule_matches_day(self, row: dict, date_key: str, day: int, candidates: list[str]) -> bool:
        conversion_type = str(row.get("conversion_type") or "").strip()
        value_type = str(row.get("value_type") or "").strip()
        if conversion_type == "날짜별월간" or value_type == "날짜별":
            raw_day = str(row.get("day_number") or row.get("start_time") or "").strip()
            return raw_day == str(int(day))
        row_day_type = str(row.get("day_type") or "").strip()
        return row_day_type in candidates

    def _rule_actual_signature(self, row: dict) -> tuple[float, float, float]:
        actual_base = (
            self._rule_number(row, "base_hours")
            + self._rule_number(row, "special_hours")
            + self._rule_number(row, "holiday_special_hours")
            + self._rule_number(row, "weekly_holiday_hours")
        )
        actual_over = self._rule_number(row, "over_hours") + self._rule_number(row, "special_over_hours")
        actual_night = self._rule_number(row, "night_hours")
        return round(actual_base, 2), round(actual_over, 2), round(actual_night, 2)

    def _hours_close(self, left: tuple[float, float, float], right: tuple[float, float, float]) -> bool:
        return all(abs(float(a or 0) - float(b or 0)) < 0.01 for a, b in zip(left, right))

    def _converted_hours_from_rule(self, row: dict, raw_hours: tuple[float, float, float]) -> tuple[float, float, float]:
        value_type = str(row.get("value_type") or "").strip()
        conversion_type = str(row.get("conversion_type") or "").strip()
        work_site = str(row.get("work_site_name") or "").strip()
        base = self._rule_number(row, "base_hours")
        over = self._rule_number(row, "over_hours")
        night = self._rule_number(row, "night_hours")
        special = self._rule_number(row, "special_hours")
        special_over = self._rule_number(row, "special_over_hours")
        holiday_special = self._rule_number(row, "holiday_special_hours")
        weekly = self._rule_number(row, "weekly_holiday_hours")

        if value_type == "배율계산" or conversion_type == "항목별배율":
            raw_base, raw_over, raw_night = raw_hours
            base_multiplier = base if base > 0 else 1.0
            over_multiplier = over if over > 0 else 1.0
            night_multiplier = night if night > 0 else 1.0
            return round(raw_base * base_multiplier, 2), round(raw_over * over_multiplier, 2), round(raw_night * night_multiplier, 2)

        # 마감환산표 또는 현우 표처럼 이미 급여 환산시간으로 정리된 표는 그대로 넣는다.
        if value_type == "마감환산값" or work_site == "현우":
            return round(base + special + holiday_special + weekly, 2), round(over + special_over, 2), round(night, 2)

        # 실제시간 표는 기존 급여표가 시급 × 총 환산시간 방식인 점에 맞춰 급여 환산시간으로 바꾼다.
        converted_base = base + (special * 1.5) + (holiday_special * 1.5) + weekly
        converted_over = (over * 1.5) + (special_over * 2.0)
        converted_night = night * 0.5
        return round(converted_base, 2), round(converted_over, 2), round(converted_night, 2)

    def _conversion_rule_for_day(self, employee: dict, rules: list[dict], date_key: str, day: int, raw_hours: tuple[float, float, float]) -> tuple[dict | None, tuple[float, float, float] | None]:
        if not rules:
            return None, None
        candidates = self._day_type_candidates_for_date(date_key)

        # 1) 날짜별 월간표는 날짜가 기준이므로 가장 먼저 적용한다.
        for row in rules:
            conversion_type = str(row.get("conversion_type") or "").strip()
            value_type = str(row.get("value_type") or "").strip()
            if (conversion_type == "날짜별월간" or value_type == "날짜별") and self._rule_matches_day(row, date_key, day, candidates):
                return row, self._converted_hours_from_rule(row, raw_hours)

        # 2) 항목별 배율은 현재 급여/근태 시간에 배율을 곱한다.
        for row in rules:
            conversion_type = str(row.get("conversion_type") or "").strip()
            value_type = str(row.get("value_type") or "").strip()
            if (conversion_type == "항목별배율" or value_type == "배율계산") and (sum(raw_hours) > 0):
                return row, self._converted_hours_from_rule(row, raw_hours)

        if sum(raw_hours) <= 0:
            return None, None

        # 3) 시간대별 표는 현재 들어온 기본/연장/심야 조합과 가장 가까운 행을 찾는다.
        direct_candidates = []
        for row in rules:
            conversion_type = str(row.get("conversion_type") or "").strip()
            if conversion_type not in {"시간대별", "마감환산표"}:
                continue
            if not self._rule_matches_day(row, date_key, day, candidates):
                continue
            direct_candidates.append(row)

        for row in direct_candidates:
            # 실제시간표: 특근/특근연장도 기존 급여표의 기본/연장 칸 입력값과 비교한다.
            if self._hours_close(self._rule_actual_signature(row), raw_hours):
                return row, self._converted_hours_from_rule(row, raw_hours)

        # 4) 현우처럼 표 자체가 기본/연장/심야 환산값인 경우, 직접값으로도 비교한다.
        for row in direct_candidates:
            direct_signature = (
                round(self._rule_number(row, "base_hours") + self._rule_number(row, "special_hours") + self._rule_number(row, "holiday_special_hours") + self._rule_number(row, "weekly_holiday_hours"), 2),
                round(self._rule_number(row, "over_hours") + self._rule_number(row, "special_over_hours"), 2),
                round(self._rule_number(row, "night_hours"), 2),
            )
            if self._hours_close(direct_signature, raw_hours):
                return row, self._converted_hours_from_rule(row, raw_hours)
        return None, None

    def _apply_site_time_conversion_to_payroll(self):
        employees = self._filtered_employees()
        if not employees:
            QMessageBox.information(self, "급여 관리", "적용할 근로자가 없습니다.")
            return
        month_key = self._month_key()
        employee_ids = [int(emp["id"]) for emp in employees]
        has_existing = any(self.state.has_payroll_month_entry(emp_id, month_key) for emp_id in employee_ids)
        overwrite = True
        if has_existing:
            box = QMessageBox(self)
            box.setWindowTitle("사업장 기준 적용")
            box.setText(f"{month_key} 급여 입력표에 이미 값이 있습니다.")
            box.setInformativeText("사업장별 시간 환산 기준으로 계산한 값으로 덮어쓰거나, 빈칸만 채울 수 있습니다.")
            fill_btn = box.addButton("빈칸만 채우기", QMessageBox.AcceptRole)
            overwrite_btn = box.addButton("전체 덮어쓰기", QMessageBox.DestructiveRole)
            box.addButton("취소", QMessageBox.RejectRole)
            box.exec()
            clicked = box.clickedButton()
            if clicked is overwrite_btn:
                overwrite = True
            elif clicked is fill_btn:
                overwrite = False
            else:
                return

        display = self._current_display_month()
        year, month = display.year(), display.month()
        last_day = monthrange(year, month)[1]
        entries_by_employee: dict[int, dict] = {}
        applied_count = 0
        skipped_count = 0
        missing_rule_sites: set[str] = set()

        for emp in employees:
            employee_id = int(emp["id"])
            rules = self._site_conversion_rules_for_employee(emp)
            if not rules:
                missing_rule_sites.add(str(emp.get("work_site") or emp.get("company") or "미지정").strip() or "미지정")
                continue
            entry = self.state.get_payroll_month_entry(employee_id, month_key)
            updated = dict(entry)
            updated.setdefault("base", dict(entry.get("base", {})))
            updated.setdefault("over", dict(entry.get("over", {})))
            updated.setdefault("night", dict(entry.get("night", {})))
            changed = False

            for day in range(1, last_day + 1):
                date_key = f"{month_key}-{day:02d}"
                raw_hours = self._payroll_source_hours_for_day(employee_id, month_key, day, emp, entry)
                rule, converted = self._conversion_rule_for_day(emp, rules, date_key, day, raw_hours)
                if converted is None:
                    if sum(raw_hours) > 0:
                        skipped_count += 1
                    continue
                base, over, night = converted
                target_has_value = any(float(updated.get(key, {}).get(day, 0) or 0) > 0 for key in ("base", "over", "night"))
                if target_has_value and not overwrite:
                    continue
                for key, value in (("base", base), ("over", over), ("night", night)):
                    bucket = updated.setdefault(key, {})
                    if float(value or 0) > 0:
                        bucket[day] = round(float(value), 2)
                    else:
                        bucket.pop(day, None)
                updated["imported_from_attendance"] = True
                changed = True
                applied_count += 1

            if changed:
                entries_by_employee[employee_id] = updated

        if not entries_by_employee:
            detail = ""
            if missing_rule_sites:
                detail = "\n환산 기준이 없는 사업장: " + ", ".join(sorted(missing_rule_sites)[:8])
            QMessageBox.information(self, "사업장 기준 적용", "적용된 급여 값이 없습니다." + detail)
            return

        self.state.set_payroll_month_entries_bulk(month_key, entries_by_employee)
        self.state.set_payroll_active_month(month_key)
        notice = f"{month_key} 사업장별 시간 환산 기준을 급여 입력표에 적용했습니다.\n적용 일수: {applied_count}건"
        if skipped_count:
            notice += f"\n기준과 맞지 않아 건너뛴 기존 시간: {skipped_count}건"
        if missing_rule_sites:
            notice += "\n환산 기준이 없는 사업장: " + ", ".join(sorted(missing_rule_sites)[:8])
        QMessageBox.information(self, "사업장 기준 적용", notice)

    def _import_from_attendance(self):
        employees = self._filtered_employees()
        if not employees:
            QMessageBox.information(self, "급여 관리", "불러올 근로자가 없습니다.")
            return
        month_key = self._month_key()
        employee_ids = [int(emp["id"]) for emp in employees]
        has_existing = any(self.state.has_payroll_month_entry(emp_id, month_key) for emp_id in employee_ids)
        overwrite = False
        if has_existing:
            box = QMessageBox(self)
            box.setWindowTitle("불러오기 방식 선택")
            box.setText(f"{month_key} 급여 입력표에 이미 값이 있습니다.")
            box.setInformativeText("빈칸만 채우기 또는 전체 덮어쓰기 중 하나를 선택하세요.")
            fill_btn = box.addButton("빈칸만 채우기", QMessageBox.AcceptRole)
            overwrite_btn = box.addButton("전체 덮어쓰기", QMessageBox.DestructiveRole)
            box.addButton("취소", QMessageBox.RejectRole)
            box.exec()
            clicked = box.clickedButton()
            if clicked is overwrite_btn:
                overwrite = True
            elif clicked is fill_btn:
                overwrite = False
            else:
                return

        self.state.import_payroll_month_from_attendance(month_key, employee_ids=employee_ids, overwrite=overwrite)
        self.state.set_payroll_active_month(month_key)
        QMessageBox.information(self, "급여 관리", f"{month_key} 근태값을 급여 입력표로 불러왔습니다.")

    def _adjust_payroll_splitter_widths(self):
        if not hasattr(self, "splitter"):
            return
        # 6px 간격 기준: QSplitter 핸들을 6px로 유지하고 오른쪽 상세 패널은 300px 고정.
        # 왼쪽 급여표 영역은 남은 폭만 사용하며, 날짜 칸 전체 이동은 table 내부 가로 스크롤이 담당한다.
        total = max(0, self.splitter.width())
        right = min(300, max(240, total - 240 - 6)) if total > 0 else 300
        handle = 6
        left = max(0, total - right - handle)
        self.splitter.setSizes([left, right])

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adjust_payroll_splitter_widths()
        QTimer.singleShot(0, self._fit_payroll_table)

    def showEvent(self, event):
        super().showEvent(event)
        first_show = not getattr(self, "_show_layout_initialized", False)
        if not self._splitter_initialized:
            self._splitter_initialized = True
            self._adjust_payroll_splitter_widths()
            first_show = True
        if not self._body_initialized:
            self._body_initialized = True
            self.refresh()
            first_show = True
        if first_show:
            self._show_layout_initialized = True
            QTimer.singleShot(0, self._fit_payroll_table)
