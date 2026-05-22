from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import QObject, QEvent, QSettings, QTimer, Qt
from PySide6.QtWidgets import QHeaderView, QTableWidget


def _event_type(name: str):
    enum_type = getattr(QEvent, "Type", None)
    if enum_type is not None and hasattr(enum_type, name):
        return getattr(enum_type, name)
    return getattr(QEvent, name)


_RESIZE_EVENT = _event_type("Resize")
_SHOW_EVENT = _event_type("Show")


_SHORT_COLUMN_WORDS = {
    "번호", "순서", "사용", "선택", "상태", "구분", "권한", "성별", "왕복", "사용여부",
}
_WIDE_COLUMN_WORDS = {
    "이름", "영문", "영문이름", "사업자", "근무 사업장", "근무사업장", "담당 근무사업장",
    "주소", "메모", "비고", "기타", "내용", "담당 사업자", "계약정보",
}
_MEDIUM_COLUMN_WORDS = {
    "연락처", "전화", "차량번호", "사업자번호", "대표자", "관리자", "운전자", "주 운전자",
    "차량", "차량명", "날짜", "일자", "주유일시", "입력방식", "표시위치",
}


def _as_list(values: Iterable[int] | None, count: int, fallback: list[int]) -> list[int]:
    if values is None:
        return fallback[:]
    result: list[int] = []
    try:
        for value in values:
            result.append(int(value))
    except Exception:
        return fallback[:]
    return result if len(result) == count else fallback[:]


class ResizableTableColumns(QObject):
    """QTableWidget 컬럼 폭을 공통으로 조절/저장/복원한다.

    - 사용자가 잡은 컬럼과 바로 옆 컬럼만 서로 폭을 주고받는다.
    - 자동 맞춤은 저장된 값을 덮어쓰지 않는다.
    - 저장값이 없을 때만 헤더/셀 글자 길이를 기준으로 기본 폭을 계산한다.
    """

    def __init__(
        self,
        table: QTableWidget,
        *,
        state=None,
        key: str,
        default_widths: Iterable[int] | None = None,
        min_widths: Iterable[int] | None = None,
        sample_rows: int = 80,
    ):
        super().__init__(table)
        self.table = table
        self.state = state
        self.key = f"table_columns/{key.strip()}"
        self.sample_rows = max(1, int(sample_rows))
        self._explicit_default_widths = list(default_widths) if default_widths is not None else None
        self._explicit_min_widths = list(min_widths) if min_widths is not None else None
        self._applying = False
        self._pending = False
        self._user_has_saved = False
        self._last_viewport_width = 0
        self._install()

    def _install(self) -> None:
        table = self.table
        header = table.horizontalHeader()
        for column in range(table.columnCount()):
            header.setSectionResizeMode(column, QHeaderView.Interactive)
        header.setStretchLastSection(False)
        header.setCascadingSectionResizes(False)
        header.setMinimumSectionSize(38)
        header.setDefaultAlignment(Qt.AlignCenter)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.setWordWrap(False)

        if not bool(table.property("soft_column_resize_line_applied")):
            table.setStyleSheet(table.styleSheet() + """
                QHeaderView::section {
                    border-right: 1px solid #E5EDF5;
                }
            """)
            table.setProperty("soft_column_resize_line_applied", True)

        header.sectionResized.connect(self._on_section_resized)
        table.installEventFilter(self)
        table.viewport().installEventFilter(self)
        model = table.model()
        model.dataChanged.connect(lambda *_: self.schedule_fit())
        model.rowsInserted.connect(lambda *_: self.schedule_fit())
        model.modelReset.connect(lambda *_: self.schedule_fit())

        saved = self._read_saved_widths()
        self._user_has_saved = bool(saved)
        widths = saved or self._default_widths_from_content()
        self._apply_widths(widths, save=False, fit_to_table=True)
        self.schedule_fit(delay_ms=0)

    def eventFilter(self, watched, event):
        if event.type() in (_RESIZE_EVENT, _SHOW_EVENT):
            self.schedule_fit(delay_ms=0)
        return super().eventFilter(watched, event)

    def _header_text(self, column: int) -> str:
        item = self.table.horizontalHeaderItem(column)
        return item.text().strip() if item is not None else ""

    def _parse_widths(self, raw) -> list[int]:
        count = self.table.columnCount()
        if raw is None:
            return []
        values = raw if isinstance(raw, (list, tuple)) else str(raw).split(",")
        widths: list[int] = []
        for value in values:
            try:
                width = int(value)
            except Exception:
                return []
            if width < 32:
                return []
            widths.append(width)
        return widths if len(widths) == count else []

    def _read_saved_widths(self) -> list[int]:
        raw = None
        if self.state is not None and hasattr(self.state, "get_local_ui_setting"):
            raw = self.state.get_local_ui_setting(self.key, None)
        widths = self._parse_widths(raw)
        if widths:
            return widths

        legacy_raw = QSettings("SmartWorkforce365", "PC").value(self.key, "")
        widths = self._parse_widths(legacy_raw)
        if widths:
            self._write_saved_widths(widths)
            return widths
        return []

    def _write_saved_widths(self, widths: list[int]) -> None:
        safe = [max(32, int(width)) for width in widths]
        if self.state is not None and hasattr(self.state, "set_local_ui_setting"):
            self.state.set_local_ui_setting(self.key, safe)
        QSettings("SmartWorkforce365", "PC").setValue(self.key, ",".join(str(width) for width in safe))
        self._user_has_saved = True

    def _minimum_widths(self) -> list[int]:
        count = self.table.columnCount()
        if self._explicit_min_widths is not None and len(self._explicit_min_widths) == count:
            return [max(38, int(width)) for width in self._explicit_min_widths]
        result: list[int] = []
        for column in range(count):
            text = self._header_text(column)
            if any(word in text for word in ("번호", "순서", "사용", "선택", "왕복")):
                result.append(50)
            elif any(word in text for word in ("상태", "성별", "구분", "권한")):
                result.append(66)
            elif any(word in text for word in ("km", "금액", "기본값")):
                result.append(78)
            elif any(word in text for word in ("연락처", "전화", "날짜", "일자", "차량번호", "사업자번호")):
                result.append(88)
            elif any(word in text for word in ("이름", "사업장", "사업자", "주소", "메모", "비고", "내용", "계약정보")):
                result.append(105)
            else:
                result.append(74)
        return result

    def _priority_columns(self) -> list[int]:
        count = self.table.columnCount()
        scores: list[tuple[int, int]] = []
        for column in range(count):
            text = self._header_text(column)
            score = 10
            if any(word in text for word in _WIDE_COLUMN_WORDS):
                score += 30
            if any(word in text for word in _MEDIUM_COLUMN_WORDS):
                score += 18
            if any(word in text for word in _SHORT_COLUMN_WORDS):
                score -= 18
            if column == count - 1:
                score += 6
            scores.append((score, column))
        return [column for _, column in sorted(scores, reverse=True)]

    def _default_widths_from_content(self) -> list[int]:
        count = self.table.columnCount()
        minimums = self._minimum_widths()
        if self._explicit_default_widths is not None and len(self._explicit_default_widths) == count:
            base = [max(minimums[index], int(width)) for index, width in enumerate(self._explicit_default_widths)]
        else:
            base = minimums[:]
        metrics = self.table.fontMetrics()
        row_limit = min(self.table.rowCount(), self.sample_rows)
        for column in range(count):
            header_width = metrics.horizontalAdvance(self._header_text(column)) + 34
            desired = max(base[column], header_width)
            for row in range(row_limit):
                item = self.table.item(row, column)
                if item is None:
                    continue
                text = item.text().strip()
                if not text:
                    continue
                cell_width = metrics.horizontalAdvance(text) + 34
                desired = max(desired, min(cell_width, 260))
            text = self._header_text(column)
            if any(word in text for word in _WIDE_COLUMN_WORDS):
                desired = max(desired, 120)
            if any(word in text for word in _SHORT_COLUMN_WORDS):
                desired = min(max(desired, minimums[column]), 92)
            base[column] = max(minimums[column], desired)
        return self._fit_widths(base)

    def _available_width(self) -> int:
        width = self.table.viewport().width()
        if width <= 0:
            width = self.table.width() - 4
        return max(0, int(width) - 2)

    def _fit_widths(self, widths: list[int], locked_column: int | None = None) -> list[int]:
        count = self.table.columnCount()
        minimums = self._minimum_widths()
        widths = _as_list(widths, count, self._default_widths_from_content_unfitted())
        widths = [max(minimums[index], int(widths[index])) for index in range(count)]
        available = self._available_width()
        if available <= 0:
            return widths

        hard_floor = [min(width, 42) for width in minimums]
        min_total = sum(minimums)
        if min_total > available:
            widths = [max(hard_floor[index], min(widths[index], minimums[index])) for index in range(count)]
            overflow = sum(widths) - available
            for column in reversed(self._priority_columns()):
                if overflow <= 0:
                    break
                can_reduce = max(0, widths[column] - hard_floor[column])
                take = min(can_reduce, overflow)
                widths[column] -= take
                overflow -= take
            return widths

        total = sum(widths)
        if total < available:
            remain = available - total
            priority = [column for column in self._priority_columns() if column != locked_column]
            if locked_column is not None and 0 <= locked_column < count:
                priority.append(locked_column)
            while remain > 0 and priority:
                changed = False
                for column in priority:
                    if remain <= 0:
                        break
                    add = min(24, remain)
                    widths[column] += add
                    remain -= add
                    changed = True
                if not changed:
                    break
            return widths

        if total > available:
            overflow = total - available
            priority = [column for column in reversed(self._priority_columns()) if column != locked_column]
            if locked_column is not None and 0 <= locked_column < count:
                priority.append(locked_column)
            for column in priority:
                if overflow <= 0:
                    break
                can_reduce = max(0, widths[column] - minimums[column])
                take = min(can_reduce, overflow)
                widths[column] -= take
                overflow -= take
        return widths

    def _default_widths_from_content_unfitted(self) -> list[int]:
        count = self.table.columnCount()
        minimums = self._minimum_widths()
        if self._explicit_default_widths is not None and len(self._explicit_default_widths) == count:
            return [max(minimums[index], int(width)) for index, width in enumerate(self._explicit_default_widths)]
        return minimums[:]

    def _current_widths(self) -> list[int]:
        return [max(32, self.table.columnWidth(column)) for column in range(self.table.columnCount())]

    def _apply_widths(self, widths: list[int], *, save: bool = False, locked_column: int | None = None, fit_to_table: bool = True) -> None:
        count = self.table.columnCount()
        minimums = self._minimum_widths()
        if len(widths) != count:
            widths = self._default_widths_from_content()
        safe = [max(minimums[index], int(widths[index])) for index in range(count)]
        if fit_to_table:
            safe = self._fit_widths(safe, locked_column=locked_column)
        self._applying = True
        try:
            for column, width in enumerate(safe):
                self.table.setColumnWidth(column, int(width))
        finally:
            self._applying = False
        if save:
            self._write_saved_widths(safe)
        self._last_viewport_width = self._available_width()

    def _rebalance_adjacent(self, logical_index: int, old_size: int, new_size: int) -> list[int]:
        count = self.table.columnCount()
        minimums = self._minimum_widths()
        widths = self._current_widths()
        if not (0 <= logical_index < count):
            return self._fit_widths(widths)
        pair = logical_index + 1 if logical_index + 1 < count else logical_index - 1
        if not (0 <= pair < count):
            return self._fit_widths(widths)

        previous_total = sum(widths) - int(new_size) + int(old_size)
        widths[logical_index] = max(minimums[logical_index], int(new_size))
        diff = sum(widths) - previous_total
        if diff > 0:
            can_reduce = max(0, widths[pair] - minimums[pair])
            take = min(diff, can_reduce)
            widths[pair] -= take
            diff -= take
            if diff > 0:
                widths[logical_index] = max(minimums[logical_index], widths[logical_index] - diff)
        elif diff < 0:
            widths[pair] += abs(diff)
        return self._fit_widths(widths, locked_column=logical_index)

    def _on_section_resized(self, logical_index: int, old_size: int, new_size: int) -> None:
        if self._applying:
            return
        widths = self._rebalance_adjacent(logical_index, old_size, new_size)
        self._apply_widths(widths, save=True, locked_column=logical_index, fit_to_table=False)

    def schedule_fit(self, *, delay_ms: int = 0) -> None:
        if self._pending:
            return
        self._pending = True

        def apply_later() -> None:
            self._pending = False
            saved = self._read_saved_widths()
            if saved:
                self._apply_widths(saved, save=False, fit_to_table=True)
            else:
                self._apply_widths(self._default_widths_from_content(), save=False, fit_to_table=True)

        QTimer.singleShot(max(0, int(delay_ms)), apply_later)


def install_resizable_table_columns(
    table: QTableWidget,
    *,
    state=None,
    key: str,
    default_widths: Iterable[int] | None = None,
    min_widths: Iterable[int] | None = None,
) -> ResizableTableColumns:
    controller = ResizableTableColumns(
        table,
        state=state,
        key=key,
        default_widths=default_widths,
        min_widths=min_widths,
    )
    table._column_resize_controller = controller
    return controller


def schedule_table_column_fit(table: QTableWidget | None) -> None:
    if table is None:
        return
    controller = getattr(table, "_column_resize_controller", None)
    if controller is not None:
        controller.schedule_fit(delay_ms=0)
