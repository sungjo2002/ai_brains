from __future__ import annotations

from calendar import monthrange
from datetime import date as py_date, timedelta, datetime
from functools import lru_cache
from PySide6.QtCore import QDate, QPoint, Qt, Signal, QTimer, QSize, QEvent, QRect
from PySide6.QtGui import QColor, QBrush, QFont, QPainter, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QHeaderView,
    QLineEdit,
    QMenu,
    QMessageBox,
    QApplication,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStyle,
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QTableWidget,
    QToolTip,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from korean_lunar_calendar import KoreanLunarCalendar

from .widgets import Panel, PAGE_OUTER_MARGINS, PAGE_OUTER_SPACING, PAGE_INNER_MARGINS, PAGE_INNER_SPACING
from .icons import get_qicon, STATUS_ICON_MAP
from .app_metadata import get_default_data_root
from .holiday_manager import load_cached_holiday_map


@lru_cache(maxsize=8)
def _attendance_font(point_size: int, bold: bool) -> QFont:
    font = QFont()
    font.setFamilies(["Malgun Gothic"])
    font.setPointSize(point_size)
    font.setBold(bold)
    return font


WEEKDAY_NAMES = {1: "월요일", 2: "화요일", 3: "수요일", 4: "목요일", 5: "금요일", 6: "토요일", 7: "일요일"}
FIXED_HOLIDAY_NAMES = {
    (1, 1): "신정",
    (3, 1): "삼일절",
    (5, 5): "어린이날",
    (6, 6): "현충일",
    (8, 15): "광복절",
    (10, 3): "개천절",
    (10, 9): "한글날",
    (12, 25): "성탄절",
}
HOLIDAY_SHORT_NAMES = {
    "신정": "신정",
    "삼일절": "삼일절",
    "설날 연휴": "설연휴",
    "설날": "설날",
    "어린이날": "어린이날",
    "부처님오신날": "부처님날",
    "현충일": "현충일",
    "광복절": "광복절",
    "개천절": "개천절",
    "추석 연휴": "추연휴",
    "추석": "추석",
    "한글날": "한글날",
    "성탄절": "성탄절",
    "대체공휴일": "대체휴일",
    "삼일절 대체공휴일": "삼일절",
    "어린이날 대체공휴일": "어린이날",
    "부처님오신날 대체공휴일": "부처님날",
    "광복절 대체공휴일": "광복절",
    "개천절 대체공휴일": "개천절",
    "노동절": "노동절",
    "제헌절": "제헌절",
    "전국동시지방선거": "선거일",
}


def _holiday_config_dir() -> str:
    return str(get_default_data_root() / "config")


@lru_cache(maxsize=16)
def _build_builtin_korean_holiday_map(year: int) -> dict[str, str]:
    holidays: dict[str, str] = {}

    def add_day(target: py_date, name: str):
        holidays[target.isoformat()] = name

    for (month, day), name in FIXED_HOLIDAY_NAMES.items():
        add_day(py_date(year, month, day), name)

    lunar = KoreanLunarCalendar()

    def lunar_to_solar(lunar_year: int, lunar_month: int, lunar_day: int) -> py_date:
        lunar.setLunarDate(lunar_year, lunar_month, lunar_day, False)
        return py_date.fromisoformat(lunar.SolarIsoFormat())

    seollal = lunar_to_solar(year, 1, 1)
    add_day(seollal - timedelta(days=1), "설날 연휴")
    add_day(seollal, "설날")
    add_day(seollal + timedelta(days=1), "설날 연휴")

    buddha = lunar_to_solar(year, 4, 8)
    add_day(buddha, "부처님오신날")

    chuseok = lunar_to_solar(year, 8, 15)
    add_day(chuseok - timedelta(days=1), "추석 연휴")
    add_day(chuseok, "추석")
    add_day(chuseok + timedelta(days=1), "추석 연휴")
    return holidays


@lru_cache(maxsize=16)
def build_korean_holiday_map(year: int) -> dict[str, str]:
    holidays = dict(_build_builtin_korean_holiday_map(int(year)))
    # 공공데이터포털에서 갱신된 공휴일 파일이 있으면 같은 날짜 이름을 최신 기준으로 덮어쓴다.
    # API 설정이 없거나 인터넷 갱신에 실패해도 기본 계산값으로 프로그램은 계속 동작한다.
    try:
        holidays.update(load_cached_holiday_map(_holiday_config_dir(), int(year)))
    except Exception:
        pass
    return holidays


def clear_holiday_cache():
    _build_builtin_korean_holiday_map.cache_clear()
    build_korean_holiday_map.cache_clear()


class CalendarHeaderView(QHeaderView):
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
        self._section_meta[section] = meta

    def viewportEvent(self, event):
        if event.type() == QEvent.ToolTip:
            section = self.logicalIndexAt(event.pos())
            tooltip = self._section_meta.get(section, {}).get("tooltip", "")
            if tooltip:
                QToolTip.showText(event.globalPos(), tooltip, self)
                return True
            QToolTip.hideText()
        return super().viewportEvent(event)

    def paintSection(self, painter: QPainter, rect: QRect, logical_index: int):
        painter.save()
        meta = self._section_meta.get(logical_index, {})

        background = QColor(meta.get("background", "#f8fbff"))
        main_background = QColor(meta.get("main_background", background.name()))
        note_background = meta.get("note_background")
        border = QColor(meta.get("border", "#d8e3f2"))
        main_text = str(meta.get("main_text", ""))
        note_text = str(meta.get("note_text", ""))
        split_header = bool(meta.get("split", False) or note_text or note_background)

        painter.fillRect(rect, background)
        painter.setPen(border)
        painter.drawRect(rect.adjusted(0, 0, -1, -1))

        if split_header:
            split_y = rect.y() + rect.height() // 2
            main_bg_rect = QRect(rect.x() + 1, rect.y() + 1, max(0, rect.width() - 2), max(0, rect.height() // 2 - 1))
            note_bg_rect = QRect(rect.x() + 1, split_y, max(0, rect.width() - 2), max(0, rect.height() - rect.height() // 2 - 1))
            painter.fillRect(main_bg_rect, main_background)
            painter.fillRect(note_bg_rect, QColor(note_background) if note_background else QColor(background))
            main_rect = QRect(rect.x() + 2, rect.y() + 2, max(0, rect.width() - 4), max(0, rect.height() // 2 - 4))
            note_rect = QRect(rect.x() + 2, split_y + 1, max(0, rect.width() - 4), max(0, rect.height() - rect.height() // 2 - 3))
        else:
            painter.fillRect(rect.adjusted(1, 1, -1, -1), main_background)
            main_rect = rect.adjusted(2, 2, -2, -2)
            note_rect = QRect()

        main_font = QFont("Malgun Gothic")
        main_font.setPointSize(meta.get("main_font_size", 10))
        main_font.setBold(meta.get("main_bold", True))
        painter.setFont(main_font)
        painter.setPen(QColor(meta.get("main_color", "#183153")))
        painter.drawText(main_rect, Qt.AlignCenter | Qt.TextWordWrap, main_text)

        if note_text:
            note_font = QFont("Malgun Gothic")
            note_font.setPointSize(meta.get("note_font_size", 7))
            note_font.setBold(meta.get("note_bold", False))
            painter.setFont(note_font)
            painter.setPen(QColor(meta.get("note_color", meta.get("main_color", "#183153"))))
            painter.drawText(note_rect, Qt.AlignCenter | Qt.TextWordWrap, note_text)

        painter.restore()


STATUS_OPTIONS = ["출석", "병원", "지각", "조퇴", "결근", "무단결근", "무단이탈", "휴무"]
STATUS_ACTION_ORDER = ["출석", "결근", "휴무", "병원", "지각", "조퇴", "무단결근", "무단이탈"]
STATUS_COLORS = {
    "출석": ("#EAF3FF", "#3B82F6"),      # Day shift blue (fallback)
    "병원": ("#F5F3FF", "#8B5CF6"),      # Violet
    "지각": ("#FFFBEB", "#F59E0B"),      # Amber
    "조퇴": ("#EFF6FF", "#3B82F6"),      # Blue
    "결근": ("#FEF2F2", "#EF4444"),      # Red
    "무단결근": ("#FFF1F2", "#E11D48"),    # Rose/Deep Red
    "무단이탈": ("#FFF7ED", "#F97316"),    # Orange
    "휴무": ("#F9FAFB", "#6B7280"),      # Gray
}
DAY_WORK_COLORS = ("#EAF3FF", "#3B82F6")
NIGHT_WORK_COLORS = ("#EEF2FF", "#4F46E5")
HOLIDAY_COLORS = ("#FFE8EE", "#D23A57")
SPECIAL_WORK_COLORS = ("#FFF7E8", "#F59E0B")
STATUS_ICONS = {
    "전체": "home",
    "출석": "presence",
    "병원": "hospital",
    "지각": "late",
    "조퇴": "early",
    "결근": "absence",
    "무단결근": "unauthorized_absence",
    "무단이탈": "unauthorized_absence",
    "휴무": "off",
    "해제": "empty",
}




class AttendanceCellDelegate(QStyledItemDelegate):
    def __init__(self, table: "AttendanceTableWidget"):
        super().__init__(table)
        self._table = table

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        if index.column() == 0:
            super().paint(painter, option, index)
            return

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        background_value = index.data(Qt.BackgroundRole)
        if isinstance(background_value, QBrush):
            background = background_value.color()
        elif isinstance(background_value, QColor):
            background = background_value
        else:
            background = QColor("#ffffff")

        foreground_value = index.data(Qt.ForegroundRole)
        if isinstance(foreground_value, QBrush):
            foreground = foreground_value.color()
        elif isinstance(foreground_value, QColor):
            foreground = foreground_value
        else:
            foreground = QColor("#27314d")

        painter.save()
        painter.fillRect(opt.rect, background)

        text = str(index.data(Qt.DisplayRole) or "")
        icon = index.data(Qt.DecorationRole)
        text_rect = opt.rect.adjusted(2, 1, -2, -1)

        if isinstance(icon, QIcon) and not icon.isNull():
            icon_size = opt.decorationSize if opt.decorationSize.isValid() else self._table.iconSize()
            actual = icon.actualSize(icon_size)
            icon_rect = QRect(
                opt.rect.x() + (opt.rect.width() - actual.width()) // 2,
                opt.rect.y() + (opt.rect.height() - actual.height()) // 2,
                actual.width(),
                actual.height(),
            )
            icon.paint(painter, icon_rect, Qt.AlignCenter, QIcon.Normal, QIcon.Off)
        elif text:
            painter.setFont(opt.font)
            painter.setPen(foreground)
            painter.drawText(text_rect, Qt.AlignCenter | Qt.TextWordWrap, text)

        painter.restore()


class AttendanceTableWidget(QTableWidget):
    def __init__(self, page: "AttendancePage"):
        super().__init__(0, 0, page)
        self._page = page

    def paintEvent(self, event):
        # 공휴일/일요일 배경을 열 전체에 직접 칠하면 근로자 행 아래 빈 공간까지
        # 색이 길게 내려간다. 각 셀의 배경은 항목별로만 지정하고,
        # 표의 남는 빈 영역은 기본 흰색으로 유지한다.
        super().paintEvent(event)


class AttendancePage(QWidget):
    request_settings = Signal()
    request_payroll = Signal()  # 급여관리 페이지로 이동 요청

    def __init__(self, state):
        super().__init__()
        # 근태관리 화면은 바깥 페이지 스크롤 없이 현재 작업영역 안에 맞춘다.
        # 많은 근로자/날짜는 월간 근태표 내부에서만 처리한다.
        self.setProperty("disableOuterVerticalScroll", True)
        self.setProperty("disableOuterHorizontalScroll", True)
        self.setMinimumWidth(0)
        self.setMaximumWidth(16777215)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.state = state
        self.state.employees_changed.connect(self.refresh_from_state)
        self.state.attendance_changed.connect(self.refresh_from_state)
        self.state.records_changed.connect(self.refresh_from_state)
        self.state.settings_changed.connect(self.refresh_from_state)
        if hasattr(self.state, "holidays_changed"):
            self.state.holidays_changed.connect(self.refresh_from_state)

        # 화면 상태는 AppState 공개 메서드를 통해서만 읽고 쓴다.
        self.selected_employee_id: int | None = None
        self.selected_date: str | None = None
        today = QDate.currentDate()
        self.range_start_month = QDate(today.year(), today.month(), 1)
        self.range_end_month = QDate(today.year(), today.month(), 1)
        self.active_display_month = QDate(today.year(), today.month(), 1)
        self.month_buttons: list[QPushButton] = []
        self.quick_buttons: list[QPushButton] = []
        self.selected_cells: list[tuple[int, str]] = []
        self._selected_target_set: set[tuple[int, str]] = set()
        self._body_sizes_initialized = False
        self._server_attendance_pull_running = False
        self._server_attendance_last_month = ""
        self._server_attendance_last_notice = ""
        self._server_attendance_auto_interval_ms = 10 * 60 * 1000
        self._server_attendance_last_result = "자동 10분"
        self._server_attendance_timer = QTimer(self)
        self._server_attendance_timer.setInterval(self._server_attendance_auto_interval_ms)
        self._server_attendance_timer.timeout.connect(self._auto_pull_server_attendance)
        self._server_attendance_timer.start()

        self._month_dates_cache_key = ""
        self._month_dates_cache: list[str] = []
        self._column_date_cache: dict[int, str] = {}
        self._row_employee_cache: dict[int, dict] = {}
        self._employee_by_id_cache: dict[int, dict] = {}
        self._cell_index_cache: dict[tuple[int, str], tuple[int, int]] = {}
        self._monthly_record_cache: dict[tuple[int, str], dict] = {}
        self._server_highlight_cells: set[tuple[int, str]] = set()
        self._server_highlight_clear_timer = QTimer(self)
        self._server_highlight_clear_timer.setSingleShot(True)
        self._server_highlight_clear_timer.setInterval(6000)
        self._server_highlight_clear_timer.timeout.connect(self._clear_server_highlight_cells)

        self._selection_timer = QTimer()
        self._selection_timer.setSingleShot(True)
        self._selection_timer.setInterval(40)
        self._selection_timer.timeout.connect(self._do_sync_selected_cells)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*PAGE_OUTER_MARGINS)
        layout.setSpacing(PAGE_OUTER_SPACING)
        layout.addWidget(self._create_content(), 1)
        self._set_server_attendance_status("idle", "자동 10분")
        self.refresh_from_state()


    def _create_hero(self):
        hero = QFrame()
        hero.setObjectName("HeroCard")
        hero.setFixedHeight(78)
        row = QHBoxLayout(hero)
        row.setContentsMargins(6, 6, 6, 6)
        row.setSpacing(6)

        left = QVBoxLayout()
        left.setSpacing(6)
        badge = QLabel("ATTENDANCE MANAGEMENT")
        badge.setObjectName("HeroBadge")
        title = QLabel("근태 관리")
        title.setObjectName("HeroTitle")
        desc = QLabel("월 단위로 조회하고 근태 상태를 바로 입력하며 급여관리와 연결합니다.")
        desc.setObjectName("HeroDesc")
        desc.setWordWrap(True)
        left.addWidget(badge)
        left.addWidget(title)
        left.addWidget(desc)
        left.addStretch()
        row.addLayout(left, 1)
        return hero

    def _set_panel_density(self, panel: Panel, *, header_margins=(6, 6, 6, 6), body_margins=(6, 6, 6, 6), body_spacing=6):
        if panel.root.count() >= 1:
            header = panel.root.itemAt(0).widget()
            if header is not None and header.layout() is not None:
                header.layout().setContentsMargins(*header_margins)
                header.layout().setSpacing(6)
        panel.body_layout.setContentsMargins(*body_margins)
        panel.body_layout.setSpacing(body_spacing)

    def _monthly_record(self, employee_id: int, date: str) -> dict:
        key = (int(employee_id), str(date))
        cached = self._monthly_record_cache.get(key)
        if cached is None:
            cached = self.state.get_monthly_record(int(employee_id), date)
            self._monthly_record_cache[key] = cached
        return cached

    def _employee_for_id(self, employee_id: int) -> dict | None:
        return self._employee_by_id_cache.get(int(employee_id))

    def _rebuild_board_caches(self, employees: list[dict], dates: list[str]):
        self._employee_by_id_cache = {int(row["id"]): row for row in self.state.employees}
        self._row_employee_cache = {row_index: employee for row_index, employee in enumerate(employees)}
        self._column_date_cache = {column: date for column, date in enumerate(dates, start=1)}
        self._cell_index_cache = {}
        for row_index, employee in enumerate(employees):
            employee_id = int(employee["id"])
            for column_index, date in enumerate(dates, start=1):
                self._cell_index_cache[(employee_id, date)] = (row_index, column_index)
        self._selected_target_set = {target for target in self._selected_target_set if target in self._cell_index_cache}

    def _refresh_single_selection_visual(self, employee_id: int, date: str):
        position = self._cell_index_cache.get((int(employee_id), date))
        if position is None:
            return
        row, column = position
        item = self.board_table.item(row, column)
        if item is None:
            return
        employee = self._row_employee_cache.get(row) or self._employee_for_id(employee_id)
        status = self._monthly_record(int(employee_id), date).get("status", "")
        self._paint_status_item(item, employee, date, status, (int(employee_id), date) in self._selected_target_set)

    def _create_content(self):
        outer_frame = QFrame()
        outer_frame.setObjectName("ScrollPageOuterFrame")
        outer_frame.setProperty("disableOuterVerticalScroll", True)
        outer_frame.setProperty("disableOuterHorizontalScroll", True)
        outer_frame.setMinimumWidth(0)
        outer_frame.setMaximumWidth(16777215)
        outer_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        root = QVBoxLayout(outer_frame)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(PAGE_INNER_SPACING)

        # 상단 고정 배너는 MainWindow에서 표시합니다.

        filter_panel = Panel("근태 관리", "월 기준 조회 · 이벤트 등록 · 급여 연동")
        filter_panel.setProperty("panelRole", "toolbar")
        filter_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self._set_panel_density(filter_panel, header_margins=(6, 6, 6, 6), body_margins=(6, 6, 6, 6), body_spacing=6)
        filter_panel.body_layout.addLayout(self._create_filters())
        root.addWidget(filter_panel)

        self.board_panel = Panel("월간 근태표", "조회 기준 월을 확인하세요")
        self.board_panel.setProperty("panelRole", "board")
        self.board_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._set_panel_density(self.board_panel, header_margins=(6, 6, 6, 6), body_margins=(6, 6, 6, 6), body_spacing=6)
        self.month_strip = self._create_month_button_strip()
        self.board_panel.body_layout.addWidget(self.month_strip, 0)
        self.board_panel.body_layout.addWidget(self._create_board_table(), 1)
        self.board_panel.body_layout.setStretch(0, 0)
        self.board_panel.body_layout.setStretch(1, 1)
        self.board_panel.body_layout.setAlignment(self.month_strip, Qt.AlignTop)

        right_wrap = QWidget()
        right_wrap.setObjectName("AttendanceRightWrap")
        right_wrap.setMinimumWidth(300)
        right_wrap.setMaximumWidth(330)
        right_wrap.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        right_layout = QVBoxLayout(right_wrap)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        self.selected_panel = self._create_selected_panel()
        self.quick_action_panel = self._create_quick_action_panel()
        self.guide_panel = self._create_guide_panel()
        self.selected_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.quick_action_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.guide_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        right_layout.addWidget(self.selected_panel)
        right_layout.addWidget(self.quick_action_panel)
        right_layout.addWidget(self.guide_panel)
        right_layout.addStretch(1)

        self.body_splitter = QSplitter(Qt.Horizontal)
        self.body_splitter.setChildrenCollapsible(False)
        self.body_splitter.setHandleWidth(6)
        self.body_splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.body_splitter.addWidget(self.board_panel)
        self.body_splitter.addWidget(right_wrap)
        self.body_splitter.setStretchFactor(0, 1)
        self.body_splitter.setStretchFactor(1, 0)
        self.body_splitter.setSizes([980, 300])
        root.addWidget(self.body_splitter, 1)
        return outer_frame

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
        combo.setMinimumWidth(72)
        combo.setMaximumWidth(78)
        combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._set_combo_value(combo, year, str(year))
        return combo

    def _make_month_combo(self, month: int) -> QComboBox:
        combo = QComboBox()
        for value in range(1, 13):
            combo.addItem(f"{value}월", value)
        combo.setMinimumWidth(56)
        combo.setMaximumWidth(64)
        combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
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

        self.business_combo = QComboBox()
        self.business_combo.currentIndexChanged.connect(self._business_changed)

        self.site_combo = QComboBox()

        self.status_filter_combo = QComboBox()
        self.status_filter_combo.addItem("전체상태")
        for status in STATUS_OPTIONS:
            self.status_filter_combo.addItem(status)
        self.status_filter_combo.currentIndexChanged.connect(self.refresh_from_state)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("이름 / 사업자 / 근무 사업장 검색")
        self.search_edit.returnPressed.connect(self._apply_query_filters)

        self.query_btn = QPushButton("조회")
        self.query_btn.setObjectName("PrimaryButton")
        self.query_btn.clicked.connect(self._apply_query_filters)

        self.server_attendance_btn = QPushButton("서버근태")
        self.server_attendance_btn.setObjectName("ServerAttendanceButton")
        self.server_attendance_btn.setToolTip("현재 표시 월의 서버 근태 기록을 다시 불러옵니다. 자동 반영은 10분마다 실행됩니다.")
        self.server_attendance_btn.clicked.connect(self._manual_pull_server_attendance)

        self.server_attendance_status_label = QLabel("자동 10분")
        self.server_attendance_status_label.setObjectName("FilterLabel")
        self.server_attendance_status_label.setMinimumHeight(30)
        self.server_attendance_status_label.setMinimumWidth(172)
        self.server_attendance_status_label.setMaximumWidth(210)
        self.server_attendance_status_label.setToolTip("서버근태 자동 반영 상태와 마지막 반영 시간을 표시합니다")

        payroll_btn = QPushButton("급여관리로 내보내기 →")
        payroll_btn.setObjectName("PrimaryButton")
        payroll_btn.setToolTip("현재 표시 월 근태값을 급여관리 입력표 초안으로 내보내고 페이지를 이동합니다")
        payroll_btn.clicked.connect(self._apply_to_payroll)

        score_settings_btn = QPushButton("점수 기준")
        score_settings_btn.setObjectName("GhostButton")
        score_settings_btn.setToolTip("설정의 근태 점수 기준으로 이동합니다")
        score_settings_btn.clicked.connect(self.request_settings.emit)

        for widget in [
            self.start_year_combo,
            self.start_month_combo,
            self.end_year_combo,
            self.end_month_combo,
            self.business_combo,
            self.site_combo,
            self.search_edit,
            self.status_filter_combo,
            self.query_btn,
            self.server_attendance_btn,
            self.server_attendance_status_label,
            score_settings_btn,
            payroll_btn,
        ]:
            widget.setMinimumHeight(30)

        self.business_combo.setMinimumWidth(96)
        self.site_combo.setMinimumWidth(108)
        self.search_edit.setMinimumWidth(120)
        self.status_filter_combo.setMinimumWidth(76)
        self.status_filter_combo.setMaximumWidth(90)
        self.query_btn.setMinimumWidth(50)
        self.server_attendance_btn.setMinimumWidth(74)
        self.server_attendance_status_label.setMinimumWidth(132)
        self.server_attendance_status_label.setMaximumWidth(160)
        score_settings_btn.setMinimumWidth(66)
        payroll_btn.setMinimumWidth(106)

        for compact_widget in [self.status_filter_combo, self.query_btn, self.server_attendance_btn, score_settings_btn]:
            compact_widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        row.addWidget(filter_label("기간"))
        row.addWidget(self.start_year_combo)
        row.addWidget(filter_label("년"))
        row.addWidget(self.start_month_combo)
        row.addWidget(filter_label("~"))
        row.addWidget(self.end_year_combo)
        row.addWidget(filter_label("년"))
        row.addWidget(self.end_month_combo)
        row.addWidget(filter_label("사업자"))
        row.addWidget(self.business_combo, 1)
        row.addWidget(filter_label("근무사업장"))
        row.addWidget(self.site_combo, 1)
        row.addWidget(self.search_edit, 2)
        row.addWidget(self.status_filter_combo)
        row.addWidget(self.query_btn)
        row.addWidget(self.server_attendance_btn)
        row.addWidget(self.server_attendance_status_label)
        row.addWidget(score_settings_btn)
        row.addWidget(payroll_btn)
        return row

    def _clear_server_highlight_cells(self):
        self._server_highlight_cells.clear()
        if hasattr(self, "board_table"):
            self.refresh_from_state()

    def _set_server_attendance_status(self, mode: str = "idle", message: str = ""):
        mode = str(mode or "idle").strip().lower()
        palette = {
            "idle": ("#2563eb", "#ffffff"),
            "loading": ("#f97316", "#ffffff"),
            "success": ("#16a34a", "#ffffff"),
            "error": ("#dc2626", "#ffffff"),
        }
        background, foreground = palette.get(mode, palette["idle"])
        if hasattr(self, "server_attendance_btn"):
            # Qt 스타일 경고를 막기 위해 버튼에는 복잡한 선택자 대신
            # 단순 속성형 스타일만 적용한다.
            self.server_attendance_btn.setStyleSheet(
                f"background-color: {background}; "
                f"color: {foreground}; "
                "border: none; "
                "border-radius: 8px; "
                "padding: 6px 6px; "
                "font-weight: bold;"
            )
            self.server_attendance_btn.setText("반영중" if mode == "loading" else "서버근태")
            self.server_attendance_btn.setEnabled(mode != "loading")
        if hasattr(self, "server_attendance_status_label"):
            label = str(message or "").strip() or "자동 10분"
            self.server_attendance_status_label.setText(label)
            self.server_attendance_status_label.setStyleSheet(
                "QLabel { color: #334155; background-color: #f8fafc; border: 1px solid #dbeafe; "
                "border-radius: 8px; padding: 6px 6px; }"
            )

    def _auto_pull_server_attendance(self):
        if not self.isVisible():
            return
        if self._server_attendance_pull_running:
            return
        if not hasattr(self, "board_table"):
            return
        self._pull_server_attendance_for_display(force=True, show_notice=False, auto=True)
        self.refresh_from_state()

    def _current_display_month_key(self) -> str:
        display_month = self._current_display_month()
        return f"{display_month.year()}-{display_month.month():02d}"

    def _pull_server_attendance_for_display(self, *, force: bool = False, show_notice: bool = False, auto: bool = False) -> bool:
        if self._server_attendance_pull_running:
            return False
        month_key = self._current_display_month_key()
        if not force and self._server_attendance_last_month == month_key:
            return False
        if not hasattr(self.state, "pull_attendance_month_from_server"):
            self._set_server_attendance_status("error", "서버설정 없음")
            return False
        self._server_attendance_pull_running = True
        self._set_server_attendance_status("loading", "자동 확인중" if auto else "수동 반영중")
        try:
            result = self.state.pull_attendance_month_from_server(month_key)
            self._server_attendance_last_month = month_key
            status = str((result or {}).get("status") or "").lower()
            count = int((result or {}).get("count", 0) or 0)
            skipped = int((result or {}).get("skipped", 0) or 0)
            server_count = int((result or {}).get("server_count", count + skipped) or 0)
            applied_keys = []
            for key in (result or {}).get("applied_keys") or []:
                if not isinstance(key, (list, tuple)) or len(key) < 2:
                    continue
                try:
                    employee_id = int(key[0])
                except (TypeError, ValueError):
                    continue
                record_date = str(key[1] or "")
                if employee_id > 0 and record_date:
                    applied_keys.append((employee_id, record_date))
            now_text = datetime.now().strftime("%H:%M")
            if status == "ok":
                notice = f"서버 근태 반영: {month_key} · {count}건"
                if skipped:
                    notice += f" · 미반영 {skipped}건"
                    details = (result or {}).get("skipped_details") or []
                    if isinstance(details, list) and details:
                        detail_lines = []
                        for item in details[:6]:
                            if not isinstance(item, dict):
                                continue
                            worker = str(item.get("worker_name") or "이름없음")
                            worker_id = str(item.get("worker_id") or "")
                            business = str(item.get("business") or "")
                            site = str(item.get("site") or "")
                            record_date = str(item.get("date") or "")
                            state = str(item.get("state") or "")
                            reason = str(item.get("reason") or "미반영")
                            parts = [worker]
                            if worker_id:
                                parts.append(worker_id)
                            if business or site:
                                parts.append("/".join([v for v in (business, site) if v]))
                            if record_date:
                                parts.append(record_date)
                            if state:
                                parts.append(state)
                            parts.append(reason)
                            detail_lines.append(" · ".join(parts))
                        if detail_lines:
                            notice += "\n\n미반영 상세:\n- " + "\n- ".join(detail_lines)
                status_text = f"자동 10분 · {now_text} · {count}건"
                if skipped:
                    status_text += f" / 미반영 {skipped}"
                elif server_count and server_count != count:
                    status_text += f" / 서버 {server_count}"
                self._server_attendance_last_notice = notice
                self._server_attendance_last_result = status_text
                if applied_keys:
                    self._server_highlight_cells = set(applied_keys)
                    self._server_highlight_clear_timer.start()
                self._set_server_attendance_status("success", status_text)
                if show_notice:
                    QMessageBox.information(self, "서버 근태 불러오기", notice)
                return bool((result or {}).get("changed"))
            message = str((result or {}).get("message") or "서버 근태를 불러오지 못했습니다.")
            self._server_attendance_last_notice = message
            self._server_attendance_last_result = f"서버 확인 필요 · {now_text}"
            self._set_server_attendance_status("error", self._server_attendance_last_result)
            if show_notice:
                QMessageBox.information(self, "서버 근태 불러오기", message)
            return False
        except Exception as exc:
            now_text = datetime.now().strftime("%H:%M")
            self._server_attendance_last_notice = f"서버 근태 불러오기 실패: {exc}"
            self._server_attendance_last_result = f"오류 · {now_text}"
            self._set_server_attendance_status("error", self._server_attendance_last_result)
            if show_notice:
                QMessageBox.warning(self, "서버 근태 불러오기", self._server_attendance_last_notice)
            return False
        finally:
            self._server_attendance_pull_running = False

    def _manual_pull_server_attendance(self):
        self._server_attendance_last_month = ""
        self._pull_server_attendance_for_display(force=True, show_notice=True)
        self.refresh_from_state()

    def _apply_to_payroll(self):
        """현재 표시 월의 근태값을 급여관리 입력표 초안으로 내보내고 페이지 이동."""
        display_month = self._current_display_month()
        month_key = f"{display_month.year()}-{display_month.month():02d}"
        employee_ids = [int(row["id"]) for row in self._employees()]
        self.state.import_payroll_month_from_attendance(month_key, employee_ids=employee_ids, overwrite=True)
        self.state.set_payroll_active_month(month_key)
        self.request_payroll.emit()


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
        return frame

    def _create_board_table(self):
        self.board_table = AttendanceTableWidget(self)
        self.board_table.setItemDelegate(AttendanceCellDelegate(self.board_table))
        self.calendar_header = CalendarHeaderView(Qt.Horizontal, self.board_table)
        self.board_table.setHorizontalHeader(self.calendar_header)
        self.board_table.verticalHeader().setVisible(False)
        self.board_table.verticalHeader().setDefaultSectionSize(30)
        self.board_table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.board_table.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.board_table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.board_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.board_table.setDragDropMode(QAbstractItemView.NoDragDrop)
        self.board_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.board_table.setShowGrid(True)
        self.board_table.setAlternatingRowColors(False)
        self.board_table.setWordWrap(False)
        self.board_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.board_table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.board_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.board_table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.board_table.setSizeAdjustPolicy(QAbstractScrollArea.AdjustIgnored)
        self.board_table.setIconSize(QSize(18, 18))
        self.board_table.setStyleSheet(
            "QTableWidget { font-size: 10px; gridline-color: #D6DEE8; selection-background-color: transparent; selection-color: #0F172A; outline: 0; }"
            "QTableWidget::item { border: 0px; padding: 0px; }"
            "QTableWidget::item:selected { background: transparent; color: #0F172A; border: 0px; }"
            "QTableWidget::item:focus { outline: 0; border: 0px; }"
            "QHeaderView::section { padding: 6px 6px; font-size: 9px; font-weight: 800; background: #F1F5F9; }"
        )
        self.board_table.cellClicked.connect(self._toggle_attendance_cell)
        self.board_table.itemSelectionChanged.connect(self._sync_selected_cells)
        self.board_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.board_table.customContextMenuRequested.connect(self._open_cell_menu)
        return self.board_table

    def _create_selected_panel(self):
        panel = Panel("선택 셀 상세", "근태 처리")
        self.selected_name = QLabel("셀 선택 전")
        self.selected_name.setObjectName("DetailName")
        self.selected_name.setWordWrap(True)

        self.selected_meta1 = QLabel("근로자 · 사업자 · 근무 사업장")
        self.selected_meta1.setObjectName("DetailMeta")
        self.selected_meta1.setWordWrap(True)

        self.selected_meta2 = QLabel("날짜 · 현재 상태")
        self.selected_meta2.setObjectName("DetailMeta")
        self.selected_meta2.setWordWrap(True)

        self.selected_status = QLabel("상태 없음")
        self.selected_status.setObjectName("StatusBadge")
        self.selected_status.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

        self.selected_memo = QLabel("메모 없음")
        self.selected_memo.setObjectName("SectionSub")
        self.selected_memo.setWordWrap(True)

        self._set_panel_density(panel, header_margins=(6, 6, 6, 6), body_margins=(6, 6, 6, 6), body_spacing=6)
        panel.setMinimumHeight(138)
        panel.setMaximumHeight(170)
        panel.body_layout.addWidget(self.selected_name)
        panel.body_layout.addWidget(self.selected_meta1)
        panel.body_layout.addWidget(self.selected_meta2)
        panel.body_layout.addWidget(self.selected_status, alignment=Qt.AlignLeft)
        panel.body_layout.addWidget(self.selected_memo)
        return panel

    def _create_quick_action_panel(self):
        panel = Panel("빠른 상태 변경", "현재 선택 셀에 바로 적용")
        self._set_panel_density(panel, header_margins=(6, 6, 6, 6), body_margins=(6, 6, 6, 6), body_spacing=6)
        vbox = QVBoxLayout()
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(6)

        # 상태 전환 버튼 그리드
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)

        display_labels = {
            "출석": "출석",
            "결근": "결근",
            "휴무": "휴무",
            "병원": "병원",
            "지각": "지각",
            "조퇴": "조퇴",
            "무단결근": "무단\n결근",
            "무단이탈": "무단\n이탈",
        }

        action_rows = [
            ("출석", "결근"),
            ("휴무", "병원"),
            ("지각", "조퇴"),
            ("무단결근", "무단이탈"),
        ]
        for row_index, row_statuses in enumerate(action_rows):
            for col_index, status in enumerate(row_statuses):
                icon_name = STATUS_ICONS.get(status, "home")
                btn = QPushButton(display_labels.get(status, status))
                if status == "출석":
                    icon_color = DAY_WORK_COLORS[1]
                else:
                    icon_color = STATUS_COLORS.get(status, ("#ffffff", "#183153"))[1]
                btn.setIcon(get_qicon(icon_name, icon_color))
                btn.setIconSize(QSize(14, 14))
                btn.setObjectName("IconActionButton")
                btn.setMinimumHeight(30)
                btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                btn.setToolTip(f"{status} (공장 기본시간 자동 적용)" if status in ("출석", "지각", "조퇴", "병원") else status)
                btn.clicked.connect(lambda _=False, s=status: self._set_selected_status(s))
                self.quick_buttons.append(btn)
                grid.addWidget(btn, row_index, col_index)

        clear_btn = QPushButton("해제")
        clear_btn.setIcon(get_qicon("empty", "#64748b"))
        clear_btn.setObjectName("IconClearButton")
        clear_btn.setMinimumHeight(30)
        clear_btn.clicked.connect(lambda: self._set_selected_status(""))
        self.quick_buttons.append(clear_btn)
        grid.addWidget(clear_btn, len(action_rows), 0, 1, 2)
        vbox.addLayout(grid)

        hours_info = QLabel("기본/연장/심야 시간은 설정에서 공장별로 관리합니다.\n근무 방식이 교대이면 1주 교대 기준으로 자동 적용됩니다.")
        hours_info.setObjectName("SectionSub")
        hours_info.setWordWrap(True)
        vbox.addWidget(hours_info)

        panel.body_layout.addLayout(vbox)
        return panel


    def _create_guide_panel(self):
        panel = Panel("사용 규칙", "표 안 클릭 중심으로 사용")
        self._set_panel_density(panel, header_margins=(6, 6, 6, 6), body_margins=(6, 6, 6, 6), body_spacing=6)
        panel.setMinimumHeight(82)
        panel.setMaximumHeight(100)
        for text in [
            "표 안 클릭·드래그 후 오른쪽 빠른 상태 변경으로 한 번에 적용합니다.",
            "일요일 휴일 칸은 클릭 시 특근 출석으로 전환되고, 다시 선택해 상태를 바꿀 수 있습니다.",
        ]:
            label = QLabel(text)
            label.setObjectName("SectionSub")
            label.setWordWrap(True)
            panel.body_layout.addWidget(label)
        return panel

    def _employees(self) -> list[dict]:
        business = self.business_combo.currentText().strip() if hasattr(self, "business_combo") else "전체 사업자"
        work_site = self.site_combo.currentText().strip() if hasattr(self, "site_combo") else "전체 근무 사업장"
        search = self.search_edit.text().strip().lower() if hasattr(self, "search_edit") else ""
        status_filter = self.status_filter_combo.currentText().strip() if hasattr(self, "status_filter_combo") else "전체상태"
        month_dates = set(self._month_dates())

        rows = [row for row in self.state.employees if row.get("status") != "퇴사"]
        filtered: list[dict] = []
        for row in rows:
            if business and business != "전체 사업자" and row.get("affiliated_business") != business:
                continue
            if work_site and work_site != "전체 근무 사업장" and row.get("work_site") != work_site:
                continue
            if search:
                haystack = " ".join([
                    str(row.get("name", "")),
                    str(row.get("nation", "")),
                    str(row.get("affiliated_business", "")),
                    str(row.get("work_site", "")),
                ]).lower()
                if search not in haystack:
                    continue
            if status_filter != "전체상태":
                has_status = any(self._monthly_record(int(row["id"]), date).get("status") == status_filter for date in month_dates)
                if not has_status:
                    continue
            filtered.append(row)

        def sort_key(employee: dict):
            business_key = str(employee.get("affiliated_business") or employee.get("business") or "").strip().casefold()
            site_key = str(employee.get("work_site") or employee.get("company") or employee.get("client") or "").strip().casefold()
            name_key = str(employee.get("name") or "").strip().casefold()
            try:
                employee_id = int(employee.get("id", 0) or 0)
            except (TypeError, ValueError):
                employee_id = 0
            return (business_key, site_key, name_key, employee_id)

        return sorted(filtered, key=sort_key)

    def _employee_display_number(self, employee: dict | int) -> str:
        """화면에 보여줄 사원 표시번호입니다.

        긴 내부 고유번호는 저장/동기화용으로 유지하고,
        근태관리 화면에서는 0001 형식만 보여줍니다.
        """
        if hasattr(self.state, "employee_display_number"):
            return self.state.employee_display_number(employee)

        raw_id = employee.get("id", 0) if isinstance(employee, dict) else employee
        try:
            target_id = int(raw_id or 0)
        except (TypeError, ValueError):
            target_id = 0

        ordered_ids: list[int] = []
        seen: set[int] = set()
        for row in getattr(self.state, "employees", []):
            try:
                employee_id = int((row or {}).get("id", 0) or 0)
            except (TypeError, ValueError, AttributeError):
                employee_id = 0
            if employee_id > 0 and employee_id not in seen:
                seen.add(employee_id)
                ordered_ids.append(employee_id)

        if target_id > 0:
            if target_id not in seen:
                ordered_ids.append(target_id)
            try:
                return f"{ordered_ids.index(target_id) + 1:04d}"
            except ValueError:
                pass
        return "0000"

    def _month_key(self, date: QDate) -> str:
        return date.toString("yyyy-MM")

    def _current_display_month(self) -> QDate:
        if self.active_display_month.isValid():
            return self.active_display_month
        return QDate.currentDate()

    def _month_dates(self) -> list[str]:
        date = self._current_display_month()
        cache_key = f"{date.year():04d}-{date.month():02d}"
        if self._month_dates_cache_key != cache_key:
            year = date.year()
            month = date.month()
            last_day = monthrange(year, month)[1]
            self._month_dates_cache = [f"{year:04d}-{month:02d}-{day:02d}" for day in range(1, last_day + 1)]
            self._month_dates_cache_key = cache_key
        return self._month_dates_cache

    def _month_sequence(self, start: QDate, end: QDate) -> list[QDate]:
        cursor = QDate(start.year(), start.month(), 1)
        last = QDate(end.year(), end.month(), 1)
        items = []
        while cursor <= last:
            items.append(cursor)
            cursor = cursor.addMonths(1)
        return items

    def _refresh_display_month_buttons(self, start: QDate, end: QDate, preferred: QDate | None = None):
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

    def _set_display_month(self, month: QDate):
        self.active_display_month = QDate(month.year(), month.month(), 1)
        self._server_attendance_last_month = ""
        for button, candidate in zip(self.month_buttons, self._month_sequence(self.range_start_month, self.range_end_month)):
            button.setChecked(candidate.year() == month.year() and candidate.month() == month.month())
        self.refresh_from_state()

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
        self._server_attendance_last_month = ""
        self.refresh_from_state()

    def _business_changed(self, *_args):
        self._refresh_work_site_combo()
        self.refresh_from_state()

    def _refresh_business_combo(self):
        current = self.business_combo.currentText().strip() if hasattr(self, "business_combo") else ""
        self.business_combo.blockSignals(True)
        self.business_combo.clear()
        self.business_combo.addItem("전체 사업자")
        for b in self.state.business_master_records():
            if b.get("name"): self.business_combo.addItem(b["name"])
        index = self.business_combo.findText(current)
        self.business_combo.setCurrentIndex(index if index >= 0 else 0)
        self.business_combo.blockSignals(False)
        self._refresh_work_site_combo()

    def _refresh_work_site_combo(self):
        current = self.site_combo.currentText().strip() if hasattr(self, "site_combo") else ""
        business = self.business_combo.currentText().strip() if hasattr(self, "business_combo") else "전체 사업자"
        if business == "전체 사업자": business = None
        self.site_combo.blockSignals(True)
        self.site_combo.clear()
        self.site_combo.addItem("전체 근무 사업장")
        for s in self.state.work_site_records(business):
            if s.get("name"): self.site_combo.addItem(s["name"])
        index = self.site_combo.findText(current)
        self.site_combo.setCurrentIndex(index if index >= 0 else 0)
        self.site_combo.blockSignals(False)

    def _toggle_attendance_cell(self, row: int, column: int):
        if column == 0:
            return
        employee = self._row_employee(row)
        if employee is None:
            return
        clicked_target = (int(employee["id"]), self._column_date(column))
        targets = self._selected_targets()
        modifiers = QApplication.keyboardModifiers()
        if len(targets) > 1:
            self.selected_employee_id = clicked_target[0]
            self.selected_date = clicked_target[1]
            self._refresh_selected_panel()
            if modifiers & (Qt.ControlModifier | Qt.ShiftModifier):
                return
            # 다중 선택 상태에서는 단일 클릭으로 범위를 해제하고, 다시 클릭했을 때 토글되도록 유지
            return
        date = clicked_target[1]
        record = self._monthly_record(clicked_target[0], clicked_target[1])
        current_status = record.get("status", "")
        next_status = self._next_click_status(date, current_status)
        self._apply_statuses([clicked_target], next_status)

    def _next_click_status(self, date: str, current_status: str) -> str:
        # 휴일은 기본 상태가 '휴일'로 보이므로, 클릭하면 특근 출석(내부 저장은 출석)으로 전환
        if self._is_holiday_date(date):
            return "" if current_status == "출석" else "출석"
        return "" if current_status == "출석" else "출석"

    def _open_cell_menu(self, pos: QPoint):
        item = self.board_table.itemAt(pos)
        if item is None:
            return
        row = item.row()
        column = item.column()
        if column == 0:
            return
        employee = self._row_employee(row)
        if employee is None:
            return
        date = self._column_date(column)
        targets = self._context_targets(row, column)
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #ffffff; color: #183153; border: 1px solid #d8e3f2; border-radius: 10px; padding: 6px 0; }"
            "QMenu::item { background: transparent; color: #183153; padding: 6px 6px 6px 6px; font-size: 12px; font-weight: 700; }"
            "QMenu::item:selected { background: #edf4ff; color: #1d4ed8; }"
            "QMenu::separator { height: 1px; background: #e6edf8; margin: 6px 6px; }"
        )
        for status in STATUS_ACTION_ORDER:
            action = menu.addAction(status)
            action.triggered.connect(lambda checked=False, s=status, t=list(targets): self._apply_statuses(t, s))
        menu.addSeparator()
        clear_action = menu.addAction("해제")
        clear_action.triggered.connect(lambda checked=False, t=list(targets): self._apply_statuses(t, ""))
        menu.exec(self.board_table.viewport().mapToGlobal(pos))

    def _apply_statuses(self, targets: list[tuple[int, str]], status: str, base: float | None = None, over: float | None = None, night: float | None = None):
        cleaned: list[tuple[int, str]] = []
        seen: set[tuple[int, str]] = set()
        for employee_id, date in targets:
            key = (int(employee_id), date)
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(key)
        if not cleaned:
            return
        updates: dict[tuple[int, str], dict] = {}
        removals: list[tuple[int, str]] = []
        for employee_id, date in cleaned:
            key = (int(employee_id), date)
            existing = self._monthly_record(int(employee_id), date)
            if status:
                employee = self._employee_for_id(int(employee_id))
                resolved_base, resolved_over, resolved_night = (base, over, night)
                if resolved_base is None or resolved_over is None or resolved_night is None:
                    resolved_base, resolved_over, resolved_night = self.state.get_default_attendance_hours(employee, date, status)
                updates[key] = {
                    "status": status,
                    "base": float(resolved_base or 0),
                    "over": float(resolved_over or 0),
                    "night": float(resolved_night or 0),
                    "memo": existing.get("memo", "")
                }
            else:
                removals.append(key)
        self.state.set_monthly_records_bulk(updates, remove_keys=removals)
        for key, payload in updates.items():
            self._monthly_record_cache[key] = dict(payload)
        for key in removals:
            self._monthly_record_cache.pop(key, None)
        self.selected_employee_id = cleaned[-1][0]
        self.selected_date = cleaned[-1][1]

    def _set_selected_status(self, status: str):
        targets = self._selected_targets()
        if not targets:
            if self.selected_employee_id is None or not self.selected_date:
                QMessageBox.information(self, "근태 관리", "먼저 근로자 날짜 셀을 선택해 주세요.")
                return
            targets = [(self.selected_employee_id, self.selected_date)]
        
        self._apply_statuses(targets, status)

    def _sync_selected_cells(self):
        self._selection_timer.start()

    def _do_sync_selected_cells(self):
        new_selected_cells = self._selected_targets()
        new_selected_set = set(new_selected_cells)
        changed_targets = new_selected_set.symmetric_difference(self._selected_target_set)
        self.selected_cells = new_selected_cells
        self._selected_target_set = new_selected_set
        if self.selected_cells:
            self.selected_employee_id = self.selected_cells[-1][0]
            self.selected_date = self.selected_cells[-1][1]
        self._refresh_selected_panel()
        try:
            self._refresh_selection_visuals(changed_targets)
        except AttributeError:
            pass

    def _selected_targets(self) -> list[tuple[int, str]]:
        targets: list[tuple[int, str]] = []
        seen: set[tuple[int, str]] = set()
        ranges = sorted(self.board_table.selectedRanges(), key=lambda rng: (rng.topRow(), rng.leftColumn(), rng.bottomRow(), rng.rightColumn()))
        for selected_range in ranges:
            top = selected_range.topRow()
            bottom = selected_range.bottomRow()
            left = max(1, selected_range.leftColumn())
            right = selected_range.rightColumn()
            for row in range(top, bottom + 1):
                employee = self._row_employee(row)
                if employee is None:
                    continue
                employee_id = int(employee["id"])
                for column in range(left, right + 1):
                    date = self._column_date(column)
                    if not date:
                        continue
                    key = (employee_id, date)
                    if key in seen:
                        continue
                    seen.add(key)
                    targets.append(key)
        return targets

    def _context_targets(self, row: int, column: int) -> list[tuple[int, str]]:
        employee = self._row_employee(row)
        if employee is None:
            return []
        clicked_target = (int(employee["id"]), self._column_date(column))
        selected = self._selected_targets()
        if clicked_target in selected and len(selected) > 1:
            self.selected_employee_id = clicked_target[0]
            self.selected_date = clicked_target[1]
            return selected
        self.board_table.clearSelection()
        clicked_item = self.board_table.item(row, column)
        if clicked_item is not None:
            clicked_item.setSelected(True)
        self.selected_cells = [clicked_target]
        self.selected_employee_id = clicked_target[0]
        self.selected_date = clicked_target[1]
        self._refresh_selected_panel()
        return [clicked_target]

    def _row_employee(self, row: int) -> dict | None:
        employee = self._row_employee_cache.get(row)
        if employee is not None:
            return employee
        item = self.board_table.item(row, 0)
        if item is None:
            return None
        employee_id = item.data(Qt.UserRole)
        if employee_id is None:
            return None
        employee = self._employee_for_id(int(employee_id))
        if employee is not None:
            self._row_employee_cache[row] = employee
        return employee

    def _column_date(self, column: int) -> str:
        return self._column_date_cache.get(column, "")

    def _refresh_board_header(self):
        if not hasattr(self, "board_panel"):
            return
        current_month = self._month_key(self._current_display_month())
        start_month = self._month_key(self.range_start_month)
        end_month = self._month_key(self.range_end_month)
        self.board_panel.header.title_lbl.setText(f"월간 근태표 ({current_month})")
        if start_month == end_month:
            self.board_panel.header.note_lbl.setText(f"조회 기간: {start_month}")
        else:
            self.board_panel.header.note_lbl.setText(f"조회 기간: {start_month} ~ {end_month}")

    def _refresh_selected_panel(self):
        employee = None
        if self.selected_employee_id is not None:
            employee = self._employee_for_id(int(self.selected_employee_id))
        if employee is None:
            self.selected_name.setText("셀 선택 전")
            self.selected_meta1.setText("근로자 · 사업자 · 근무 사업장")
            self.selected_meta2.setText("날짜 · 현재 상태")
            self.selected_status.setText("상태 없음")
            self.selected_memo.setText("메모 없음")
            return

        if len(self.selected_cells) > 1:
            first_employee = self._employee_for_id(int(self.selected_cells[0][0]))
            first_name = first_employee.get("name", "선택") if first_employee else "선택"
            start_date = self.selected_cells[0][1]
            end_date = self.selected_cells[-1][1]
            self.selected_name.setText(f"{len(self.selected_cells)}칸 선택 중")
            self.selected_meta1.setText(f"첫 선택: {first_name} / {start_date}")
            self.selected_meta2.setText(f"마지막 선택: {end_date} · 빠른 상태 변경/우클릭 일괄 적용")
            self.selected_status.setText("다중 선택")
            self.selected_memo.setText("드래그한 선택 범위 전체에 상태를 한 번에 적용할 수 있습니다.")
            return

        date = self.selected_date or self._month_dates()[0]
        record = self._monthly_record(int(employee["id"]), date)
        status = record.get("status", "")
        display_status = self._display_status(date, status)
        
        base = record.get("base", 0)
        over = record.get("over", 0)
        night = record.get("night", 0)
        hours_str = ""
        if status in ("출석", "특근 출석", "지각", "조퇴"):
            hours_str = f" [기본 {base}H | 연장 {over}H | 심야 {night}H]"
        
        self.selected_name.setText(f'{employee["name"]} / {self._employee_display_number(employee)}')
        self.selected_meta1.setText(f'{employee["affiliated_business"]} · {employee["work_site"]}')
        self.selected_meta2.setText(f'{date} · 현재 상태: {display_status}')
        self.selected_status.setText(display_status + hours_str)
        self.selected_memo.setText(record.get("memo") or "메모 없음")

    def _status_symbol(self, status: str) -> str:
        return STATUS_ICONS.get(status, "") if status else ""

    def _cell_symbol(self, date: str, status: str) -> str:
        return ""

    def _holiday_name(self, date: str) -> str:
        value = QDate.fromString(date, "yyyy-MM-dd")
        if not value.isValid():
            return ""
        return build_korean_holiday_map(value.year()).get(date, "")

    def _holiday_short_name(self, date: str) -> str:
        name = self._holiday_name(date)
        if not name:
            return ""
        return HOLIDAY_SHORT_NAMES.get(name, name if len(name) <= 4 else name[:4])

    def _is_named_holiday(self, date: str) -> bool:
        return bool(self._holiday_name(date))

    def _is_saturday(self, date: str) -> bool:
        value = QDate.fromString(date, "yyyy-MM-dd")
        return value.isValid() and value.dayOfWeek() == 6

    def _is_holiday_date(self, date: str) -> bool:
        value = QDate.fromString(date, "yyyy-MM-dd")
        return value.isValid() and (value.dayOfWeek() == 7 or self._is_named_holiday(date))

    def _header_number_color(self, date: str) -> str:
        if self._is_named_holiday(date):
            return HOLIDAY_COLORS[1]
        if self._is_saturday(date):
            return "#2563EB"
        value = QDate.fromString(date, "yyyy-MM-dd")
        if value.isValid() and value.dayOfWeek() == 7:
            return HOLIDAY_COLORS[1]
        return "#183153"

    def _header_tooltip(self, date: str) -> str:
        value = QDate.fromString(date, "yyyy-MM-dd")
        if not value.isValid():
            return date
        weekday_name = WEEKDAY_NAMES.get(value.dayOfWeek(), "")
        holiday_name = self._holiday_name(date)
        if holiday_name:
            return f"{date} · {weekday_name} · {holiday_name}"
        return f"{date} · {weekday_name}"

    def _display_status(self, date: str, status: str) -> str:
        holiday_name = self._holiday_name(date)
        holiday_label = holiday_name or "휴일"
        if self._is_holiday_date(date):
            if status == "출석":
                return f"{holiday_label} · 특근 출석"
            if not status:
                return holiday_label
        return status or "없음"

    def _blend_colors(self, base_hex: str, overlay_hex: str, alpha: float) -> QColor:
        base = QColor(base_hex)
        overlay = QColor(overlay_hex)
        ratio = max(0.0, min(1.0, alpha))
        red = round(base.red() * (1 - ratio) + overlay.red() * ratio)
        green = round(base.green() * (1 - ratio) + overlay.green() * ratio)
        blue = round(base.blue() * (1 - ratio) + overlay.blue() * ratio)
        return QColor(red, green, blue)

    def _presence_colors(self, employee: dict | None, date: str) -> tuple[str, str]:
        if self._is_holiday_date(date):
            return SPECIAL_WORK_COLORS
        work_type = str((employee or {}).get("work_type", "")).strip()
        if work_type == "교대":
            effective_group = self.state.get_effective_shift_group(employee, date)
            return NIGHT_WORK_COLORS if effective_group == "야간" else DAY_WORK_COLORS
        if work_type == "야간":
            return NIGHT_WORK_COLORS
        return DAY_WORK_COLORS

    def _cell_palette(self, employee: dict | None, date: str, status: str) -> tuple[QColor, QColor, QFont]:
        is_holiday = self._is_holiday_date(date)
        # 공휴일/일요일 실제 표 셀은 상태 유무와 관계없이 연한 빨간 배경을 유지한다.
        # 다만 근로자 행 아래의 빈 여백은 표 셀 자체가 아니므로 별도 색을 칠하지 않는다.
        base_bg = HOLIDAY_COLORS[0] if is_holiday else "#ffffff"
        if status == "출석":
            _unused_bg, fg = self._presence_colors(employee, date)
            bg = base_bg
        elif status:
            _unused_bg, fg = STATUS_COLORS.get(status, ("#ffffff", "#27314d"))
            bg = base_bg
        else:
            bg, fg = (base_bg, "#27314d")

        if is_holiday and not status:
            font = _attendance_font(11, False)
        elif status:
            font = _attendance_font(15, True)
        else:
            font = _attendance_font(11, False)
        return QColor(bg), QColor(fg), font

    def _paint_status_item(self, item: QTableWidgetItem, employee: dict | None, date: str, status: str, selected: bool = False):
        background, foreground, font = self._cell_palette(employee, date, status)
        try:
            employee_id = int((employee or {}).get("id", 0) or 0)
        except (TypeError, ValueError, AttributeError):
            employee_id = 0
        if employee_id and (employee_id, date) in self._server_highlight_cells:
            background = self._blend_colors(background.name(), "#fde68a", 0.55)
            font.setBold(True)
        if selected:
            base_name = background.name()
            if self._is_holiday_date(date) and not status:
                background = self._blend_colors(base_name, "#8fb7ff", 0.18)
            else:
                background = self._blend_colors(base_name, "#dbeafe", 0.38)
        item.setFont(font)
        item.setData(Qt.BackgroundRole, background)
        item.setData(Qt.ForegroundRole, foreground)

        icon_name = STATUS_ICON_MAP.get(status)
        if icon_name:
            item.setIcon(get_qicon(icon_name, foreground.name()))
        else:
            item.setIcon(QIcon())

        item.setBackground(QBrush(background))
        item.setForeground(QBrush(foreground))


    def _refresh_selection_visuals(self, changed_targets: set[tuple[int, str]] | None = None):
        if not hasattr(self, "board_table"):
            return
        targets = self._selected_target_set if changed_targets is None else set(changed_targets)
        if not targets:
            return
        for employee_id, date in targets:
            self._refresh_single_selection_visual(int(employee_id), date)


    def _fit_board_size(self):
        if not hasattr(self, "board_table") or not hasattr(self, "month_strip"):
            return
        dates = self._month_dates()
        if not dates:
            return

        table = self.board_table
        total_days = len(dates)
        frame_width = table.frameWidth() * 2
        scroll_width = table.verticalScrollBar().sizeHint().width() if table.verticalScrollBar() else 16
        h_scroll_height = table.horizontalScrollBar().sizeHint().height() if table.horizontalScrollBar() else 16

        if hasattr(self, "board_panel") and self.board_panel.body.width() > 0:
            panel_width = self.board_panel.body.width()
        else:
            panel_width = max(table.width(), self.width() - 280)
        available_width = max(840, panel_width - frame_width - 4)

        name_width = 92
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        table.setColumnWidth(0, name_width)

        for column in range(1, total_days + 1):
            table.horizontalHeader().setSectionResizeMode(column, QHeaderView.Stretch)


        row_height = 26
        header_height = 42
        table.verticalHeader().setDefaultSectionSize(row_height)
        for row in range(table.rowCount()):
            table.setRowHeight(row, row_height)
        table.horizontalHeader().setFixedHeight(header_height)

        if hasattr(self, "board_panel") and self.board_panel.body.height() > 0:
            month_height = max(self.month_strip.height(), self.month_strip.sizeHint().height())
            body_available = self.board_panel.body.height() - month_height - self.board_panel.body_layout.spacing() - 2
        else:
            body_available = self.height() - 280

        min_body_height = header_height + (row_height * 6) + frame_width + 6

        # 표 높이를 현재 표/패널 높이에 다시 맞추면 바깥 페이지 스크롤 영역이
        # 커지고, 그 커진 높이를 기준으로 표가 또 커지는 순환이 생길 수 있다.
        # 창 높이를 기준으로 안전한 최대값을 두고, 많은 근로자는 표 내부 스크롤로만 본다.
        window = self.window()
        window_height = window.height() if window is not None and window.height() > 0 else self.height()
        page_height = self.height() if self.height() > 0 else window_height
        # 바깥 페이지 스크롤이 생기지 않도록 표 높이는 현재 근태관리 페이지 높이를 우선 기준으로 잡는다.
        # 근로자가 많을 때는 표 내부 세로 스크롤만 사용한다.
        safe_max_height = max(min_body_height, min(520, max(260, page_height - 190), max(260, window_height - 360)))
        requested_height = body_available if body_available > 0 else page_height - 220
        body_height = max(min_body_height, min(requested_height, safe_max_height))

        table.setMinimumHeight(body_height)
        table.setMaximumHeight(body_height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._fit_board_size)

    def showEvent(self, event):
        super().showEvent(event)
        first_show = not getattr(self, "_show_layout_initialized", False)
        if hasattr(self, "body_splitter") and not self._body_sizes_initialized:
            total = max(1, self.body_splitter.size().width())
            right = min(320, max(290, total // 5 + 36))
            self.body_splitter.setSizes([max(720, total - right), right])
            self._body_sizes_initialized = True
            first_show = True
        if first_show:
            self._show_layout_initialized = True
            QTimer.singleShot(0, self._fit_board_size)

    def refresh_from_state(self, *_args):
        if hasattr(self, "business_combo"):
            self._refresh_business_combo()

        if hasattr(self, "month_button_layout"):
            self._refresh_display_month_buttons(self.range_start_month, self.range_end_month, self.active_display_month)

        self._pull_server_attendance_for_display(force=False, show_notice=False)
        self._monthly_record_cache.clear()
        employees = self._employees()
        dates = list(self._month_dates())
        self._rebuild_board_caches(employees, dates)
        self._refresh_board_header()

        headers = ["이름"] + [str(index + 1) for index in range(len(dates))]
        self.board_table.setColumnCount(len(headers))
        self.board_table.setRowCount(len(employees))
        self.calendar_header.clear_section_meta()
        self.calendar_header.set_section_meta(0, {
            "main_text": "이름",
            "background": "#f8fbff",
            "main_color": "#183153",
            "main_font_size": 9,
            "tooltip": "근로자 이름",
        })

        for col_index, date in enumerate(dates, start=1):
            holiday_label = self._holiday_short_name(date)
            is_holiday = self._is_holiday_date(date)
            self.calendar_header.set_section_meta(col_index, {
                "main_text": str(col_index),
                "note_text": holiday_label,
                "split": True,
                "background": "#f8fbff",
                "main_background": "#f8fbff",
                "note_background": "#f8fbff",
                "main_color": self._header_number_color(date),
                "note_color": HOLIDAY_COLORS[1],
                "main_font_size": 9,
                "note_font_size": 7,
                "tooltip": self._header_tooltip(date),
            })

        for row_index, employee in enumerate(employees):
            name_item = QTableWidgetItem(employee["name"])
            name_item.setData(Qt.UserRole, int(employee["id"]))
            name_item.setToolTip(self._employee_display_number(employee))
            name_item.setTextAlignment(Qt.AlignCenter)
            self.board_table.setItem(row_index, 0, name_item)

            for col_index, date in enumerate(dates, start=1):
                record = self._monthly_record(int(employee["id"]), date)
                status = record.get("status", "")
                symbol = self._cell_symbol(date, status)
                item = QTableWidgetItem(symbol)
                item.setTextAlignment(Qt.AlignCenter)
                tooltip = self._header_tooltip(date) + "\n현재 상태: " + self._display_status(date, status)
                try:
                    employee_id = int(employee.get("id", 0) or 0)
                except (TypeError, ValueError, AttributeError):
                    employee_id = 0
                if employee_id and (employee_id, date) in self._server_highlight_cells:
                    tooltip += "\n서버근태에서 방금 반영됨"
                item.setToolTip(tooltip)
                self._paint_status_item(item, employee, date, status)
                self.board_table.setItem(row_index, col_index, item)

        self._fit_board_size()
        self.selected_cells = self._selected_targets()
        self._selected_target_set = set(self.selected_cells)
        self._refresh_selected_panel()
        self._refresh_selection_visuals()
