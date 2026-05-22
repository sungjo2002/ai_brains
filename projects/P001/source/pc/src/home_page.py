from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QDate, Signal, QRectF, QSettings, QTimer, QEvent
from PySide6.QtGui import QColor, QBrush, QPixmap, QPainter, QPainterPath, QCursor, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QHeaderView,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .widgets import Panel, StatCard, STATUS_BADGES, GRADE_BADGES, DonutChartWidget, RadarChartWidget, BannerIllustration
from .home_employee_dialog import HomeEmployeeDetailDialog
from .icons import get_svg_icon
from .table_column_manager import install_resizable_table_columns, schedule_table_column_fit






def _qevent_types(*names):
    values = []
    for name in names:
        value = getattr(QEvent, name, None)
        if value is None and hasattr(QEvent, "Type"):
            value = getattr(QEvent.Type, name, None)
        if value is not None:
            values.append(value)
    return tuple(values)


FILTER_CARDS = [
    ("근무중", "", "#10B981", "check_plain"),
    ("출근전", "", "#F59E0B", "clock_plain"),
    ("결근", "", "#EF4444", "x_plain"),
    ("무단결근", "", "#E11D48", "alert_plain"),
    ("무단이탈", "", "#F97316", "exit_plain"),
    ("병원", "", "#8B5CF6", "medical_plain"),
    ("퇴사", "", "#6B7280", "x_plain"),
]


class HomeDetailNumberBadge(QLabel):
    """선택 인원 번호 표시용 배지.

    선택 인원 상세 영역의 hover/active 효과를 제거하기 위해 클릭/마우스 상태를
    사용하지 않는 단순 표시용 QLabel로 유지한다.
    """

    _BASE_STYLE = (
        "QLabel#HomeDetailNumberBadge {"
        "background: #EAF3FF;"
        "color: #1D4ED8;"
        "border: 1px solid #93C5FD;"
        "border-radius: 13px;"
        "padding: 6px 6px;"
        "font-size: 12px;"
        "font-weight: 900;"
        "}"
    )

    def __init__(self, text: str = "0000", parent=None):
        super().__init__(text, parent)
        self.setObjectName("HomeDetailNumberBadge")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(28)
        self.setFixedWidth(66)
        self.setToolTip("선택된 근로자 번호")
        self.setCursor(Qt.ArrowCursor)
        self.setStyleSheet(self._BASE_STYLE)

    def set_active(self, active: bool):
        # 선택 인원 상세 효과 제거: active 상태에서도 표시 스타일을 바꾸지 않는다.
        self.setStyleSheet(self._BASE_STYLE)


class HomeSelectedDetailCard(QFrame):
    """선택 인원 상세 카드.

    pc_8~pc_9에서 넣었던 hover/pressed/active 강조 효과를 제거하고,
    기본 카드 내용 영역으로만 동작하게 유지한다.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._number_badge = None
        self.setObjectName("HomeSelectedDetailCard")
        self.setCursor(Qt.ArrowCursor)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.setContentsMargins(0, 0, 0, 0)

    def set_number_badge(self, badge):
        self._number_badge = badge

    def reset_active(self):
        # 선택 인원 상세 효과 제거: 상태 변화 없음.
        if self._number_badge is not None and hasattr(self._number_badge, "set_active"):
            self._number_badge.set_active(False)

    def set_active(self, active: bool):
        # 선택 인원 상세 효과 제거: 상태 변화 없음.
        if self._number_badge is not None and hasattr(self._number_badge, "set_active"):
            self._number_badge.set_active(False)

    def install_child_event_filters(self):
        # hover/active 효과 제거: 자식 위젯 이벤트 감시를 하지 않는다.
        return


class HomePage(QWidget):
    navigate_employee = Signal()
    navigate_registration = Signal()
    navigate_attendance = Signal()
    navigate_settings = Signal()

    def __init__(self, state):
        super().__init__()
        self.state = state
        self.employees: list[dict] = []
        self.selected_employee: dict | None = None
        self.selected_employee_id: int | None = None
        self.employee_map: dict[int, dict] = {}
        self.current_filter_key: str | None = None
        self.status_cards: dict[str, StatCard] = {}
        self.status_card_order: list[str] = []
        self.page_size_options = [10, 15, 20, 30, 50]
        self.search_message: QLabel | None = None
        self._raw_portrait_cache: dict[tuple[str, int], QPixmap] = {}
        self._rounded_portrait_cache: dict[tuple[str, int, int, int, int], QPixmap] = {}
        self._summary_avatar_state: tuple[str, int, int, int] | None = None
        self._summary_default_icon = QPixmap()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        outer_frame = QFrame()
        outer_frame.setObjectName("ScrollPageOuterFrame")
        outer_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        outer_layout = QVBoxLayout(outer_frame)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(6)
        outer_layout.setAlignment(Qt.AlignTop)

        # 상단 고정 배너는 MainWindow에서 표시합니다.
        self.top_status_panel = self._build_overview_panel()
        outer_layout.addWidget(self.top_status_panel, 0, Qt.AlignTop)
        outer_layout.addWidget(self._create_dashboard(), 1)
        layout.addWidget(outer_frame, 1)

        self.state.employees_changed.connect(self.refresh_from_state)
        self.state.attendance_changed.connect(self.refresh_from_state)
        self.state.records_changed.connect(self.refresh_from_state)
        self.state.settings_changed.connect(self.refresh_from_state)
        self.refresh_from_state(select_first=True)


    def refresh_from_state(self, select_first: bool = False):
        self.employees = list(self.state.employees)
        self.employee_map = {int(emp["id"]): emp for emp in self.employees}
        previous_selected_id = self.selected_employee_id

        if hasattr(self, "status_filter_combo"):
            self._refresh_filter_options()
        self._refresh_status_cards()
        self._refresh_overall_table(select_first=select_first)

        if previous_selected_id and previous_selected_id in self.employee_map:
            self.selected_employee = self.employee_map[previous_selected_id]
            self._select_employee(self.selected_employee, source="자동 갱신")
            self._select_matching_row(self.overall_table, previous_selected_id)
        elif select_first and self.employees:
            first = self.employees[0]
            self.selected_employee_id = int(first["id"])
            self._select_employee(first, source="기본 선택")
            self._select_matching_row(self.overall_table, self.selected_employee_id)
        elif not self.employees and hasattr(self, "search_message") and self.search_message is not None:
            self.search_message.setText("등록된 인원이 없습니다.")

    def _create_hero(self):
        hero = QFrame()
        hero.setObjectName("HeroCard")
        hero.setFixedHeight(78)

        layout = QHBoxLayout(hero)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        left = QVBoxLayout()
        left.setSpacing(6)

        badge = QLabel("WORKFORCE OPERATIONS")
        badge.setObjectName("HeroBadge")
        title = QLabel("멀티사업자 인력·근태 운영 대시보드")
        title.setObjectName("HeroTitle")
        desc = QLabel("상태 카드로 인원을 바로 걸러보고, 선택 인원의 핵심 정보와 점수를 빠르게 확인합니다.")
        desc.setObjectName("HeroDesc")
        desc.setWordWrap(True)

        left.addWidget(badge)
        left.addWidget(title)
        left.addWidget(desc)
        left.addStretch()
        layout.addLayout(left, 1)

        return hero

    def _create_dashboard(self):
        self.overall_panel = self._build_overall_panel()

        left_wrap = QWidget()
        left_wrap.setMinimumWidth(360)
        left_layout = QVBoxLayout(left_wrap)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        left_layout.addWidget(self.overall_panel, 1)

        right = self._build_detail_column()
        right.setMinimumWidth(320)
        right.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.dashboard_splitter = QSplitter(Qt.Horizontal)
        self.dashboard_splitter.setChildrenCollapsible(False)
        self.dashboard_splitter.setHandleWidth(6)
        self.dashboard_splitter.addWidget(left_wrap)
        self.dashboard_splitter.addWidget(right)
        self.dashboard_splitter.setStretchFactor(0, 3)
        self.dashboard_splitter.setStretchFactor(1, 2)
        return self.dashboard_splitter

    def _create_overview_banner(self):
        banner = QFrame()
        banner.setObjectName("HomeOverviewBanner")
        banner.setFixedHeight(98)

        row = QHBoxLayout(banner)
        row.setContentsMargins(6, 6, 6, 6)
        row.setSpacing(6)

        icon_wrap = QLabel()
        icon_wrap.setObjectName("BannerIconCircle")
        icon_wrap.setFixedSize(54, 54)
        icon_wrap.setAlignment(Qt.AlignCenter)
        icon_wrap.setPixmap(get_svg_icon("home", "#2563EB", 28))
        row.addWidget(icon_wrap, 0, Qt.AlignVCenter)

        texts = QVBoxLayout()
        texts.setContentsMargins(0, 0, 0, 0)
        texts.setSpacing(6)

        badge = QLabel("HOME DASHBOARD")
        badge.setObjectName("HomeOverviewBadge")
        title = QLabel("전체 인력 현황")
        title.setObjectName("HomeOverviewTitle")
        desc = QLabel("전체 인력의 현재 상태를 요약하여 보여줍니다. 상태 카드를 눌러 바로 인원을 걸러보고, 아래 목록에서 선택 인원의 상세와 근태 평가지표를 빠르게 확인합니다.")
        desc.setObjectName("HomeOverviewDesc")
        desc.setWordWrap(True)

        texts.addWidget(badge)
        texts.addWidget(title)
        texts.addWidget(desc)
        texts.addStretch()
        row.addLayout(texts, 1)

        art_wrap = QFrame()
        art_wrap.setObjectName("HomeOverviewArtWrap")
        art_wrap.setFixedWidth(196)
        art_layout = QHBoxLayout(art_wrap)
        art_layout.setContentsMargins(6, 6, 6, 6)
        art_layout.setSpacing(0)

        art = BannerIllustration(compact=False)
        art.setFixedSize(176, 72)
        art.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        art_layout.addWidget(art, 0, Qt.AlignCenter)
        row.addWidget(art_wrap, 0, Qt.AlignRight | Qt.AlignVCenter)
        return banner

    def _build_overview_panel(self):
        wrap = QWidget()
        self.status_grid = QGridLayout(wrap)
        self.status_grid.setContentsMargins(0, 0, 0, 0)
        self.status_grid.setHorizontalSpacing(6)
        self.status_grid.setVerticalSpacing(6)
        for index, (key, subtitle, accent, badge) in enumerate(FILTER_CARDS):
            card = StatCard(
                key,
                self._count_filter_text(key),
                subtitle,
                accent,
                badge,
                filter_key=key,
                show_subtitle=False,
                icon_background=False,
                icon_size=22,
                variant="home_summary",
            )
            card.setFixedHeight(96)
            card.clicked.connect(self._toggle_status_filter)
            self.status_cards[key] = card
            self.status_card_order.append(key)
            self.status_grid.addWidget(card, 0, index)
        self._refresh_status_cards()
        self._layout_status_cards()
        return wrap

    def _layout_status_cards(self):
        if not hasattr(self, "status_grid"):
            return
        width = max(self.top_status_panel.width() if hasattr(self, "top_status_panel") else self.width(), 0)
        if width >= 980:
            columns = 7
        elif width >= 640:
            columns = 4
        else:
            columns = 2
        for index, key in enumerate(self.status_card_order):
            card = self.status_cards.get(key)
            if card is None:
                continue
            self.status_grid.removeWidget(card)
            self.status_grid.addWidget(card, index // columns, index % columns)

    def _build_overall_panel(self):
        panel = Panel("전체 인원 현황", "")
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        panel.setMinimumHeight(470)
        panel.body_layout.setAlignment(Qt.AlignTop)
        panel.body_layout.setContentsMargins(6, 6, 6, 6)
        panel.body_layout.setSpacing(6)

        filter_wrap = QWidget()
        filter_wrap.setObjectName("HomeFilterRow")
        filter_row = QHBoxLayout(filter_wrap)
        filter_row.setContentsMargins(0, 0, 0, 0)
        filter_row.setSpacing(6)

        self.overall_search = QLineEdit()
        self.overall_search.setObjectName("HomeSearchField")
        self.overall_search.setPlaceholderText("번호 / 이름 / 영문이름 / 사업자 / 사업장 검색")
        self.overall_search.setClearButtonEnabled(True)
        self.overall_search.setMinimumHeight(30)
        self.overall_search.setFocusPolicy(Qt.ClickFocus)
        self.overall_search.returnPressed.connect(self._search_employee)

        self.status_filter_combo = QComboBox()
        self.status_filter_combo.setObjectName("HomeFilterCombo")
        self.status_filter_combo.setMinimumHeight(30)
        self.status_filter_combo.setMinimumWidth(120)
        self.status_filter_combo.addItem("전체 상태")
        self.status_filter_combo.currentIndexChanged.connect(lambda _=0: self._refresh_overall_table(select_first=False))

        self.business_filter_combo = QComboBox()
        self.business_filter_combo.setObjectName("HomeFilterCombo")
        self.business_filter_combo.setMinimumHeight(30)
        self.business_filter_combo.setMinimumWidth(120)
        self.business_filter_combo.addItem("전체 사업자")
        self.business_filter_combo.currentIndexChanged.connect(lambda _=0: self._refresh_overall_table(select_first=False))

        self.site_filter_combo = QComboBox()
        self.site_filter_combo.setObjectName("HomeFilterCombo")
        self.site_filter_combo.setMinimumHeight(30)
        self.site_filter_combo.setMinimumWidth(120)
        self.site_filter_combo.addItem("전체 사업장")
        self.site_filter_combo.currentIndexChanged.connect(lambda _=0: self._refresh_overall_table(select_first=False))

        reset_btn = QPushButton("초기화")
        reset_btn.setObjectName("HomeFilterResetButton")
        reset_btn.setMinimumHeight(30)
        reset_btn.setMinimumWidth(86)
        reset_btn.clicked.connect(self._reset_filters)

        filter_row.addWidget(self.overall_search, 4)
        filter_row.addWidget(self.status_filter_combo, 1)
        filter_row.addWidget(self.business_filter_combo, 1)
        filter_row.addWidget(self.site_filter_combo, 1)
        filter_row.addWidget(reset_btn, 0)
        panel.body_layout.addWidget(filter_wrap)

        self.current_filter_note = QLabel("총 0명")
        self.current_filter_note.setObjectName("SectionSub")
        self.current_filter_note.setWordWrap(True)
        panel.body_layout.addWidget(self.current_filter_note)

        self.overall_table = self._make_table(
            ["번호", "이름", "영문이름", "사업자", "근무 사업장", "근무 형태", "현재 상태"],
            [],
            badge_cols={6: STATUS_BADGES},
            clickable_name_col=1,
            min_height=340,
            max_height=None,
        )
        self.overall_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._setup_overall_table_columns()
        self.overall_table.cellClicked.connect(self._handle_overall_click)
        panel.body_layout.addWidget(self.overall_table, 1)
        return panel

    def _column_width_settings_key(self) -> str:
        return "home/overall_table_column_widths"

    def _parse_saved_column_widths(self, raw, expected_count: int) -> list[int]:
        if raw is None:
            return []
        if isinstance(raw, (list, tuple)):
            values = raw
        else:
            values = str(raw).split(",")
        widths: list[int] = []
        for value in values:
            try:
                width = int(value)
            except Exception:
                return []
            if width < 32:
                return []
            widths.append(width)
        return widths if len(widths) == expected_count else []

    def _read_saved_column_widths(self, expected_count: int) -> list[int]:
        key = self._column_width_settings_key()
        raw = None
        if hasattr(self.state, "get_local_ui_setting"):
            raw = self.state.get_local_ui_setting(key, None)
        widths = self._parse_saved_column_widths(raw, expected_count)
        if widths:
            return widths

        legacy_raw = QSettings("SmartWorkforce365", "PC").value(key, "")
        widths = self._parse_saved_column_widths(legacy_raw, expected_count)
        if widths:
            self._write_saved_column_widths(widths)
            return widths
        return []

    def _write_saved_column_widths(self, widths: list[int]) -> None:
        safe_widths = [max(32, int(width)) for width in widths]
        key = self._column_width_settings_key()
        if hasattr(self.state, "set_local_ui_setting"):
            self.state.set_local_ui_setting(key, safe_widths)
        QSettings("SmartWorkforce365", "PC").setValue(key, ",".join(str(width) for width in safe_widths))

    def _overall_table_min_widths(self) -> list[int]:
        return [56, 88, 120, 82, 86, 74, 82]

    def _overall_table_default_widths(self) -> list[int]:
        return [68, 132, 180, 112, 112, 90, 92]

    def _overall_table_resize_priority(self) -> list[int]:
        return [2, 1, 3, 4, 5, 6, 0]

    def _overall_table_available_width(self) -> int:
        if not hasattr(self, "overall_table"):
            return 0
        return max(0, self.overall_table.viewport().width() - 2)

    def _fit_overall_table_widths(self, widths: list[int], locked_column: int | None = None) -> list[int]:
        table = self.overall_table
        count = table.columnCount()
        minimums = self._overall_table_min_widths()
        if len(widths) != count:
            widths = self._overall_table_default_widths()
        widths = [max(minimums[index], int(widths[index])) for index in range(count)]
        available = self._overall_table_available_width()
        if available <= 0:
            return widths
        min_total = sum(minimums)
        available = max(available, min_total)
        total = sum(widths)
        if total < available:
            expand_column = count - 1
            if locked_column == expand_column and count > 1:
                expand_column = count - 2
            widths[expand_column] += available - total
            return widths
        if total > available:
            overflow = total - available
            priority = [column for column in self._overall_table_resize_priority() if column != locked_column]
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

    def _apply_overall_table_widths(self, widths: list[int], save: bool = False, locked_column: int | None = None, fit_to_table: bool = True):
        if not hasattr(self, "overall_table"):
            return
        table = self.overall_table
        count = table.columnCount()
        if len(widths) != count:
            widths = self._overall_table_default_widths()
        minimums = self._overall_table_min_widths()
        safe_widths = [max(minimums[index], int(widths[index])) for index in range(count)]
        if fit_to_table:
            safe_widths = self._fit_overall_table_widths(safe_widths, locked_column=locked_column)
        self._applying_overall_column_widths = True
        try:
            for column, width in enumerate(safe_widths):
                table.setColumnWidth(column, width)
        finally:
            self._applying_overall_column_widths = False
        if save:
            self._write_saved_column_widths(safe_widths)

    def _rebalance_overall_table_widths_after_drag(self, widths: list[int], logical_index: int, old_size: int, new_size: int) -> list[int]:
        table = self.overall_table
        count = table.columnCount()
        minimums = self._overall_table_min_widths()
        if len(widths) != count or not (0 <= logical_index < count):
            return self._fit_overall_table_widths(widths)
        widths = [max(minimums[index], int(widths[index])) for index in range(count)]
        pair_index = logical_index + 1 if logical_index + 1 < count else logical_index - 1
        if not (0 <= pair_index < count):
            return self._fit_overall_table_widths(widths)

        delta = int(new_size) - int(old_size)
        if delta == 0:
            return widths

        if delta > 0:
            pair_can_reduce = max(0, widths[pair_index] - minimums[pair_index])
            allowed_delta = min(delta, pair_can_reduce)
            widths[logical_index] = max(minimums[logical_index], int(old_size) + allowed_delta)
            widths[pair_index] = max(minimums[pair_index], widths[pair_index] - allowed_delta)
        else:
            shrink_amount = int(old_size) - max(minimums[logical_index], int(new_size))
            widths[logical_index] = max(minimums[logical_index], int(old_size) - shrink_amount)
            widths[pair_index] = widths[pair_index] + shrink_amount

        return widths

    def _current_overall_table_widths(self) -> list[int]:
        if not hasattr(self, "overall_table"):
            return []
        return [max(32, self.overall_table.columnWidth(column)) for column in range(self.overall_table.columnCount())]

    def _save_overall_table_column_widths(self):
        if getattr(self, "_applying_overall_column_widths", False):
            return
        if not hasattr(self, "overall_table"):
            return
        widths = self._fit_overall_table_widths(self._current_overall_table_widths())
        self._write_saved_column_widths(widths)

    def _on_overall_table_section_resized(self, logical_index: int, old_size: int, new_size: int):
        if getattr(self, "_applying_overall_column_widths", False):
            return
        widths = self._current_overall_table_widths()
        widths = self._rebalance_overall_table_widths_after_drag(widths, logical_index, old_size, new_size)
        self._apply_overall_table_widths(widths, save=True, locked_column=logical_index, fit_to_table=False)

    def _schedule_overall_table_width_fit(self, save: bool = False):
        if getattr(self, "_overall_width_fit_pending", False):
            return
        self._overall_width_fit_pending = True

        def apply_later():
            self._overall_width_fit_pending = False
            if hasattr(self, "overall_table"):
                saved_widths = self._read_saved_column_widths(self.overall_table.columnCount())
                if saved_widths and not save:
                    widths = saved_widths
                else:
                    widths = self._current_overall_table_widths() or saved_widths or self._overall_table_default_widths()
                self._apply_overall_table_widths(widths, save=save)

        QTimer.singleShot(0, apply_later)

    def _restore_saved_overall_table_widths_after_layout(self):
        if getattr(self, "_applying_overall_column_widths", False):
            return
        if not hasattr(self, "overall_table"):
            return
        saved_widths = self._read_saved_column_widths(self.overall_table.columnCount())
        if not saved_widths:
            return
        self._apply_overall_table_widths(saved_widths, save=False, fit_to_table=False)

    def _setup_overall_table_columns(self):
        table = self.overall_table
        table.setShowGrid(False)
        install_resizable_table_columns(
            table,
            state=self.state,
            key="home/overall_table",
            default_widths=[64, 144, 196, 116, 126, 86, 104],
            min_widths=[52, 104, 120, 92, 96, 70, 82],
        )

    def _build_detail_column(self):
        wrap = QScrollArea()
        wrap.setWidgetResizable(True)
        wrap.setFrameShape(QFrame.NoFrame)
        wrap.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        wrap.setMinimumWidth(320)
        wrap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        right = QWidget()
        layout = QVBoxLayout(right)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.detail_panel = Panel("선택 인원 상세", "")
        self.detail_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.detail_panel.setMinimumHeight(240)
        self.detail_panel.body_layout.setContentsMargins(6, 6, 6, 6)
        self.detail_panel.body_layout.setSpacing(6)

        self.detail_card = HomeSelectedDetailCard()
        detail_card = self.detail_card
        detail_card_layout = QHBoxLayout(detail_card)
        detail_card_layout.setContentsMargins(0, 0, 0, 0)
        detail_card_layout.setSpacing(6)

        self.summary_avatar = QLabel()
        self.summary_avatar.setObjectName("DetailAvatar")
        self.summary_avatar.setAlignment(Qt.AlignCenter)
        self.summary_avatar.setFixedSize(100, 120)
        self.summary_avatar.setAttribute(Qt.WA_StaticContents, True)
        detail_card_layout.addWidget(self.summary_avatar, 0, Qt.AlignTop)

        info_area = QVBoxLayout()
        info_area.setContentsMargins(0, 0, 0, 0)
        info_area.setSpacing(6)

        name_row = QHBoxLayout()
        name_row.setContentsMargins(0, 0, 0, 0)
        name_row.setSpacing(6)
        self.summary_name = QLabel("직원을 선택해주세요")
        self.summary_name.setObjectName("DetailSummaryName")
        self.summary_name.setWordWrap(True)
        self.summary_number = HomeDetailNumberBadge("0000")
        if hasattr(self, "detail_card") and hasattr(self.detail_card, "set_number_badge"):
            self.detail_card.set_number_badge(self.summary_number)
        more = QLabel("⋮")
        more.setObjectName("HomeDetailMoreButton")
        more.setAlignment(Qt.AlignCenter)
        more.setFixedSize(24, 28)
        name_row.addWidget(self.summary_name, 1)
        name_row.addWidget(self.summary_number, 0, Qt.AlignTop)
        name_row.addWidget(more, 0, Qt.AlignTop)
        info_area.addLayout(name_row)

        detail_grid = QGridLayout()
        detail_grid.setContentsMargins(0, 0, 0, 0)
        detail_grid.setHorizontalSpacing(6)
        detail_grid.setVerticalSpacing(6)
        detail_grid.setColumnMinimumWidth(0, 70)
        detail_grid.setColumnStretch(0, 0)
        detail_grid.setColumnStretch(1, 1)

        self.summary_status = QLabel("상태 대기")
        self.summary_status.setObjectName("StatusBadge")
        self.summary_status.setAlignment(Qt.AlignCenter)
        self.summary_status.setMinimumHeight(26)
        self.summary_status.setFixedWidth(72)

        detail_fields = ["영문이름", "사업자", "근무 사업장", "직책", "연락처", "입사일", "현재 상태", "메모"]
        self.detail_value_labels = {}
        for row_index, field in enumerate(detail_fields):
            key = QLabel(field)
            key.setObjectName("HomeDetailKey")
            if field == "현재 상태":
                value_widget = self.summary_status
            else:
                value_widget = QLabel("-")
                value_widget.setObjectName("HomeDetailValue")
                value_widget.setWordWrap(True)
                self.detail_value_labels[field] = value_widget
            detail_grid.addWidget(key, row_index, 0, alignment=Qt.AlignTop)
            detail_grid.addWidget(value_widget, row_index, 1, alignment=Qt.AlignLeft | Qt.AlignVCenter)
        info_area.addLayout(detail_grid)
        info_area.addStretch(1)
        detail_card_layout.addLayout(info_area, 1)

        self.detail_panel.body_layout.addWidget(detail_card)
        if hasattr(self, "detail_card") and hasattr(self.detail_card, "install_child_event_filters"):
            self.detail_card.install_child_event_filters()
        layout.addWidget(self.detail_panel, 0)
        self._set_default_summary_avatar()

        self.score_panel = Panel("근태 평가지표", "")
        self.score_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.score_panel.body_layout.setContentsMargins(6, 6, 6, 6)
        self.score_panel.body_layout.setSpacing(6)

        self.score_message = QLabel("")
        self.score_message.setObjectName("SectionSub")
        self.score_message.setWordWrap(True)
        self.score_message.hide()

        score_query = QHBoxLayout()
        score_query.setContentsMargins(0, 0, 0, 0)
        score_query.setSpacing(6)

        score_date_style = """
            QDateEdit {
                min-height: 34px;
                max-height: 34px;
                padding: 0 6px 0 6px;
                font-size: 12px;
                font-weight: 700;
            }
            QDateEdit::drop-down {
                subcontrol-origin: border;
                subcontrol-position: center right;
                width: 26px;
                border-left: 1px solid #CBD5E1;
                border-top-right-radius: 8px;
                border-bottom-right-radius: 8px;
                background: #F8FAFC;
            }
            QDateEdit::down-arrow {
                image: url(assets/combo_arrow_down.svg);
                width: 7px;
                height: 5px;
            }
        """

        self.score_start = QDateEdit()
        self.score_start.setObjectName("ScoreDateEdit")
        self.score_start.setCalendarPopup(True)
        self.score_start.setDisplayFormat("yyyy-MM")
        self.score_start.setDate(QDate(2026, 1, 1))
        self.score_start.setAlignment(Qt.AlignCenter)
        self.score_start.setFixedWidth(112)
        self.score_start.setFixedHeight(34)
        self.score_start.setStyleSheet(score_date_style)

        self.score_end = QDateEdit()
        self.score_end.setObjectName("ScoreDateEdit")
        self.score_end.setCalendarPopup(True)
        self.score_end.setDisplayFormat("yyyy-MM")
        self.score_end.setDate(QDate(2026, 12, 31))
        self.score_end.setAlignment(Qt.AlignCenter)
        self.score_end.setFixedWidth(112)
        self.score_end.setFixedHeight(34)
        self.score_end.setStyleSheet(score_date_style)

        self.score_lookup_btn = QPushButton("조회")
        self.score_lookup_btn.setObjectName("PrimaryButton")
        self.score_lookup_btn.setFixedWidth(64)
        self.score_lookup_btn.setFixedHeight(34)
        self.score_lookup_btn.clicked.connect(self._refresh_score_panel)

        score_query.addWidget(self.score_start)
        score_query.addWidget(self.score_end)
        score_query.addWidget(self.score_lookup_btn)
        score_query.addStretch()

        self.score_panel.body_layout.addLayout(score_query)

        # -----------------------------------
        # Score Header (85점 양호)
        # -----------------------------------
        score_header = QHBoxLayout()
        score_header.setContentsMargins(0, 6, 0, 0)
        
        self.score_title = QLabel("85점")
        self.score_title.setObjectName("ScoreNumber")
        self.score_title.setStyleSheet("font-size: 24px; font-weight: 900;")
        
        self.score_grade = QLabel("양호")
        self.score_grade.setObjectName("ScoreGrade")
        
        score_header.addWidget(self.score_title)
        score_header.addWidget(self.score_grade)
        score_header.addStretch()
        
        self.score_panel.body_layout.addLayout(score_header)

        # -----------------------------------
        # Chart & Legend Area
        # -----------------------------------
        chart_layout = QHBoxLayout()
        chart_layout.setContentsMargins(0, 0, 0, 0)
        chart_layout.setSpacing(6)

        self.radar_chart = RadarChartWidget()
        self.radar_chart.setMinimumSize(200, 200)
        self.radar_chart.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        chart_layout.addWidget(self.radar_chart, 1)

        legend_container = QWidget()
        legend_container.setFixedWidth(120)
        legend_layout = QVBoxLayout(legend_container)
        legend_layout.setContentsMargins(0, 0, 0, 0)
        legend_layout.setSpacing(0)
        legend_layout.addStretch()

        self.event_labels = {}
        self.event_count_labels = {}
        self.event_color_map = {
            "병원": "#8B5CF6", "지각": "#F97316", "조퇴": "#3B82F6", 
            "결근": "#EF4444", "무단결근": "#E11D48", "무단이탈": "#F59E0B"
        }
        
        event_keys = ["병원", "지각", "조퇴", "결근", "무단결근", "무단이탈"]
        self.radar_chart.set_chart_data([(key, 0, self.event_color_map[key]) for key in event_keys])
        for key in event_keys:
            row = QFrame()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(6, 6, 6, 6)
            row_layout.setSpacing(6)
            
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {self.event_color_map[key]}; font-size: 10px;")
            
            name = QLabel(key)
            name.setObjectName("ScoreLegendName")
            name.setStyleSheet("font-size: 12px; font-weight: 600; color: #475569;")
            
            count = QLabel("0회")
            count.setObjectName("ScoreLegendValue")
            count.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            count.setStyleSheet("font-size: 12px; font-weight: 800; color: #0F172A;")
            
            self.event_labels[key] = name
            self.event_count_labels[key] = count
            
            row_layout.addWidget(dot)
            row_layout.addWidget(name, 1)
            row_layout.addWidget(count, 0)
            legend_layout.addWidget(row)
            
        legend_layout.addStretch()
        chart_layout.addWidget(legend_container, 0)

        self.score_panel.body_layout.addLayout(chart_layout, 1)
        layout.addWidget(self.score_panel, 1)

        wrap.setWidget(right)
        return wrap

    def _refresh_filter_options(self):
        def refill(combo: QComboBox, default_label: str, values: list[str]):
            current = combo.currentText() if combo.count() else default_label
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(default_label)
            for value in values:
                combo.addItem(value)
            index = combo.findText(current)
            combo.setCurrentIndex(index if index >= 0 else 0)
            combo.blockSignals(False)

        statuses = sorted({str(emp.get("status") or "").strip() for emp in self.employees if str(emp.get("status") or "").strip()})
        businesses = sorted({str(emp.get("affiliated_business") or "").strip() for emp in self.employees if str(emp.get("affiliated_business") or "").strip()})
        sites = sorted({str(emp.get("work_site") or "").strip() for emp in self.employees if str(emp.get("work_site") or "").strip()})
        refill(self.status_filter_combo, "전체 상태", statuses)
        refill(self.business_filter_combo, "전체 사업자", businesses)
        refill(self.site_filter_combo, "전체 사업장", sites)

    def _employee_matches_filter(self, employee: dict, filter_key: str | None) -> bool:
        if not filter_key:
            return True
        if filter_key == "무단결근":
            return employee.get("unauthorized_absence", 0) > 0
        if filter_key == "무단이탈":
            return employee.get("unauthorized_leave", 0) > 0
        return employee.get("status") == filter_key

    def _employee_display_number(self, employee: dict | int) -> str:
        if hasattr(self.state, "employee_display_number"):
            return self.state.employee_display_number(employee)
        raw_id = employee.get("id", 0) if isinstance(employee, dict) else employee
        try:
            return f"{int(raw_id):04d}"
        except Exception:
            return "0000"

    def _employee_english_name(self, employee: dict | None) -> str:
        employee = employee or {}
        return str(employee.get("english_name") or employee.get("name_english") or "").strip()

    def _count_filter_text(self, filter_key: str) -> str:
        count = sum(1 for emp in self.employees if self._employee_matches_filter(emp, filter_key))
        return f"{count}명"

    def _refresh_status_cards(self):
        for key, card in self.status_cards.items():
            card.set_value(self._count_filter_text(key))
            card.set_active(self.current_filter_key == key)

    def _toggle_status_filter(self, key: str):
        self.current_filter_key = None if self.current_filter_key == key else key
        self._refresh_status_cards()
        self._refresh_overall_table(select_first=True)

    def _reset_filters(self):
        self.current_filter_key = None
        self.overall_search.clear()
        if hasattr(self, "status_filter_combo"):
            self.status_filter_combo.setCurrentIndex(0)
        if hasattr(self, "business_filter_combo"):
            self.business_filter_combo.setCurrentIndex(0)
        if hasattr(self, "site_filter_combo"):
            self.site_filter_combo.setCurrentIndex(0)
        self._refresh_status_cards()
        self._refresh_overall_table(select_first=False)
        if self.search_message is not None:
            self.search_message.setText("직원을 선택하면 기본 정보가 표시됩니다.")

    def _current_page_limit(self) -> int:
        if not hasattr(self, "page_size_combo"):
            return 9999
        return int(self.page_size_combo.currentData() or 9999)

    def _visible_employees(self, employees: list[dict]) -> list[dict]:
        return employees

    def _filter_employees(self) -> list[dict]:
        keyword = self.overall_search.text().strip().lower()
        filtered = [emp for emp in self.employees if self._employee_matches_filter(emp, self.current_filter_key)]
        selected_status = self.status_filter_combo.currentText() if hasattr(self, "status_filter_combo") else "전체 상태"
        selected_business = self.business_filter_combo.currentText() if hasattr(self, "business_filter_combo") else "전체 사업자"
        selected_site = self.site_filter_combo.currentText() if hasattr(self, "site_filter_combo") else "전체 사업장"
        if selected_status and selected_status != "전체 상태":
            filtered = [emp for emp in filtered if str(emp.get("status") or "") == selected_status]
        if selected_business and selected_business != "전체 사업자":
            filtered = [emp for emp in filtered if str(emp.get("affiliated_business") or "") == selected_business]
        if selected_site and selected_site != "전체 사업장":
            filtered = [emp for emp in filtered if str(emp.get("work_site") or "") == selected_site]
        if keyword:
            filtered = [
                emp for emp in filtered
                if keyword in " ".join([
                    self._employee_display_number(emp),
                    str(emp.get("id") or ""),
                    str(emp.get("name") or ""),
                    self._employee_english_name(emp),
                    str(emp.get("affiliated_business") or ""),
                    str(emp.get("work_site") or ""),
                    str(emp.get("work_type") or ""),
                    str(emp.get("status") or ""),
                ]).lower()
            ]
        return filtered

    def _refresh_overall_table(self, select_first: bool = False):
        rows = self._filter_employees()
        self.filtered_employees = rows
        self._populate_overall_table(rows)

        status_text = self.current_filter_key or "전체"
        note_parts = [f"총 {len(rows)}명"]
        if status_text != "전체":
            note_parts.append(f"상태 카드: {status_text}")
        if hasattr(self, "status_filter_combo") and self.status_filter_combo.currentText() != "전체 상태":
            note_parts.append(f"상태: {self.status_filter_combo.currentText()}")
        if hasattr(self, "business_filter_combo") and self.business_filter_combo.currentText() != "전체 사업자":
            note_parts.append(f"사업자: {self.business_filter_combo.currentText()}")
        if hasattr(self, "site_filter_combo") and self.site_filter_combo.currentText() != "전체 사업장":
            note_parts.append(f"사업장: {self.site_filter_combo.currentText()}")
        search_text = self.overall_search.text().strip()
        if search_text:
            note_parts.append(f"검색: {search_text}")
        self.current_filter_note.setText(" / ".join(note_parts))

        if select_first and rows:
            self.overall_table.selectRow(0)
            self._select_employee(rows[0], source=f"{status_text} 필터")
        elif not rows and self.search_message is not None:
            self.search_message.setText("조건에 맞는 인원이 없습니다.")

    def _populate_overall_table(self, employees: list[dict]):
        self.overall_table.setRowCount(len(employees))
        for r, emp in enumerate(employees):
            row = [
                self._employee_display_number(emp),
                str(emp.get("name") or "-"),
                self._employee_english_name(emp) or "-",
                emp.get("affiliated_business", "-") or "-",
                emp.get("work_site", "-") or "-",
                emp.get("work_type", "-") or "-",
                emp.get("status", "-") or "-",
            ]
            for c, value in enumerate(row):
                item = QTableWidgetItem(value)
                font = item.font()
                if c == 0:
                    item.setData(Qt.UserRole, int(emp.get("id", 0) or 0))
                    item.setBackground(QBrush(QColor("#EAF2FF")))
                    item.setForeground(QBrush(QColor("#2F6FED")))
                    font.setBold(True)
                elif c == 1:
                    item.setForeground(QBrush(QColor("#2455C9")))
                    font.setBold(True)
                elif c == 6 and value in STATUS_BADGES:
                    bg, fg = STATUS_BADGES[value]
                    item.setBackground(QBrush(QColor(bg)))
                    item.setForeground(QBrush(QColor(fg)))
                    font.setBold(True)
                else:
                    item.setForeground(QBrush(QColor("#334155")))
                item.setFont(font)
                item.setTextAlignment(Qt.AlignCenter if c != 1 else Qt.AlignVCenter)
                self.overall_table.setItem(r, c, item)
        if employees:
            self.overall_table.selectRow(0)

    def _search_employee(self):
        self._refresh_overall_table(select_first=True)
        if not self.filtered_employees and self.search_message is not None:
            self.search_message.setText("검색 결과가 없습니다.")

    def _handle_overall_click(self, row: int, column: int):
        employee = self._employee_from_table(self.overall_table, row)
        if not employee:
            return
        if column == 1:
            dialog = HomeEmployeeDetailDialog(employee, self.state, self)
            dialog.exec()
        self._select_employee(employee, source="전체 인력 현황")

    def _employee_from_table(self, table: QTableWidget, row: int) -> dict | None:
        item = table.item(row, 0)
        if item is None:
            return None
        employee_id = item.data(Qt.UserRole)
        if employee_id is None:
            return None
        return self.employee_map.get(int(employee_id))

    def _select_matching_row(self, table: QTableWidget, employee_id: int):
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if item and int(item.data(Qt.UserRole) or 0) == int(employee_id):
                table.selectRow(row)
                break

    def _select_employee(self, employee: dict, source: str = "조회"):
        self.selected_employee = employee
        self.selected_employee_id = int(employee["id"])
        display_no = self._employee_display_number(employee)
        english_name = self._employee_english_name(employee)
        if self.search_message is not None:
            name_label = f"{employee['name']} ({english_name})" if english_name else str(employee["name"])
            self.search_message.setText(f"{source} 선택: {name_label} / {display_no}")
        if self.score_message is not None:
            self.score_message.setText("")

        name = str(employee.get("name") or "-")
        business = str(employee.get("affiliated_business") or "-")
        site = str(employee.get("work_site") or "-")
        work_type = str(employee.get("work_type") or "-")
        role = str(employee.get("job") or employee.get("role") or employee.get("position") or employee.get("department") or "-").strip() or "-"
        phone = str(employee.get("phone") or "-")
        status = str(employee.get("status") or "-")
        memo = str(employee.get("memo") or employee.get("notes") or "-")
        hire_date = str(employee.get("hire_date") or "-")

        self.summary_name.setText(name)
        self.summary_number.setText(display_no)
        # 새 직원을 선택하면 상세 카드와 번호 배지는 기본 상태에서 시작한다.
        if hasattr(self, "detail_card") and hasattr(self.detail_card, "reset_active"):
            self.detail_card.reset_active()
        if hasattr(self.summary_number, "set_active"):
            self.summary_number.set_active(False)
        self._apply_badge(self.summary_status, status, STATUS_BADGES)
        self._update_summary_avatar(employee)

        detail_values = {
            "영문이름": english_name or "-",
            "사업자": business,
            "근무 사업장": site,
            "직책": work_type if work_type and work_type != "-" else role,
            "연락처": phone,
            "입사일": hire_date,
            "메모": memo,
        }
        for field, value in detail_values.items():
            if field in self.detail_value_labels:
                self.detail_value_labels[field].setText(value)

        self._refresh_score_panel()

    def _refresh_score_panel(self):
        if self.selected_employee is None:
            if self.score_message is not None:
                self.score_message.setText("직원을 먼저 선택해주세요.")
            return

        start_str = self.score_start.date().toString("yyyy-MM-dd")
        end_str = self.score_end.date().toString("yyyy-MM-dd")

        summary = self.state.get_attendance_score_summary(int(self.selected_employee["id"]), start_str, end_str)
        score = int(summary.get("score", 0) or 0)
        grade = summary.get("grade", "-")

        grade_color_map = {
            "양호": "#10B981", "주의": "#F59E0B", "재검토": "#F97316", "비추천": "#E11D48"
        }
        color = grade_color_map.get(grade, "#64748B")
        record_count = int(summary.get("record_count", 0) or 0)

        if record_count <= 0:
            grade = "기록 없음"
            color = "#64748B"
            score = 0

        self.score_title.setText(f"{score}점")
        self.score_grade.setText(grade)
        self.score_grade.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 14px;")

        counts = summary.get("counts", {}) if isinstance(summary.get("counts", {}), dict) else {}
        segments = []
        for key, color_hex in self.event_color_map.items():
            value = int(counts.get(key, 0) or 0)
            self.event_count_labels[key].setText(f"{value}회")
            segments.append((key, value, color_hex))

        self.radar_chart.set_chart_data(segments=segments)

    def _apply_badge(self, label: QLabel, text: str, mapping: dict[str, tuple[str, str]]):
        bg, fg = mapping.get(text, ("#F4F7FC", "#475467"))
        label.setText(text)
        label.setStyleSheet(
            f"background:{bg}; color:{fg}; border:1px solid {bg}; border-radius:12px; padding: 6px 6px; font-size:11px; font-weight:800;"
        )

    def _apply_value_highlight(self, label: QLabel, text: str):
        bg, fg = GRADE_BADGES.get(text, ("#F4F7FC", "#475467"))
        label.setText(text)
        label.setStyleSheet(
            f"background:{bg}; color:{fg}; border:1px solid {bg}; border-radius:10px; padding: 6px 6px; font-size:11px; font-weight:800;"
        )

    def _set_default_summary_avatar(self):
        width = max(1, self.summary_avatar.width())
        height = max(1, self.summary_avatar.height())
        state_key = ("__default__", 0, width, height)
        if self._summary_avatar_state == state_key:
            return
        if self._summary_default_icon.isNull():
            self._summary_default_icon = get_svg_icon("employee", "#5C7CFA", 26)
        self.summary_avatar.setText("")
        self.summary_avatar.setPixmap(self._summary_default_icon)
        self._summary_avatar_state = state_key

    def _resolve_employee_portrait(self, employee: dict) -> str:
        portrait_raw = str(employee.get("portrait_path", "") or "").strip()
        portrait_path = self.state.resolve_storage_file_path(portrait_raw)
        if portrait_path:
            return str(portrait_path)
        try:
            target_path, _rel = self.state.get_employee_portrait_storage_path(employee["id"], ".png")
            if target_path.exists():
                return str(target_path)
        except Exception:
            pass
        return ""

    def _portrait_mtime_key(self, portrait_path: str) -> int:
        try:
            return int(Path(portrait_path).stat().st_mtime_ns)
        except Exception:
            return 0

    def _load_portrait_pixmap_cached(self, portrait_path: str, mtime_key: int) -> QPixmap:
        cache_key = (portrait_path, mtime_key)
        cached = self._raw_portrait_cache.get(cache_key)
        if cached is None:
            loaded = QPixmap(portrait_path)
            cached = loaded if not loaded.isNull() else QPixmap()
            self._raw_portrait_cache[cache_key] = cached
        return cached

    def _make_rounded_pixmap(self, pixmap: QPixmap, width: int, height: int, radius: int = 16) -> QPixmap:
        if pixmap.isNull():
            return QPixmap()
        scaled = pixmap.scaled(width, height, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        result = QPixmap(width, height)
        result.fill(Qt.transparent)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, width, height), radius, radius)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, scaled)
        painter.end()
        return result

    def _rounded_portrait_pixmap_cached(self, portrait_path: str, mtime_key: int, width: int, height: int, radius: int = 16) -> QPixmap:
        cache_key = (portrait_path, mtime_key, width, height, radius)
        cached = self._rounded_portrait_cache.get(cache_key)
        if cached is None:
            raw = self._load_portrait_pixmap_cached(portrait_path, mtime_key)
            cached = self._make_rounded_pixmap(raw, width, height, radius) if not raw.isNull() else QPixmap()
            self._rounded_portrait_cache[cache_key] = cached
        return cached

    def _update_summary_avatar(self, employee: dict):
        portrait_path = self._resolve_employee_portrait(employee)
        width = max(1, self.summary_avatar.width())
        height = max(1, self.summary_avatar.height())
        if portrait_path and Path(portrait_path).exists():
            mtime_key = self._portrait_mtime_key(portrait_path)
            state_key = (portrait_path, mtime_key, width, height)
            if self._summary_avatar_state == state_key:
                return
            pixmap = self._rounded_portrait_pixmap_cached(portrait_path, mtime_key, width, height, 16)
            if not pixmap.isNull():
                self.summary_avatar.setText("")
                self.summary_avatar.setPixmap(pixmap)
                self._summary_avatar_state = state_key
                return
        self._set_default_summary_avatar()


    def _adjust_splitter_sizes(self):
        if not hasattr(self, "dashboard_splitter"):
            return
        available_width = max(self.width() - 12, 0)
        if available_width < 920:
            if self.dashboard_splitter.orientation() != Qt.Vertical:
                self.dashboard_splitter.setOrientation(Qt.Vertical)
            total_height = max(self.height() - 12, 720)
            self.dashboard_splitter.setSizes([int(total_height * 0.58), int(total_height * 0.42)])
            return

        if self.dashboard_splitter.orientation() != Qt.Horizontal:
            self.dashboard_splitter.setOrientation(Qt.Horizontal)
        right = min(max(int(available_width * 0.34), 320), 440)
        self.dashboard_splitter.setSizes([max(360, available_width - right), right])

    def showEvent(self, event):
        super().showEvent(event)
        if getattr(self, "_show_layout_initialized", False):
            return
        self._show_layout_initialized = True
        self._layout_status_cards()
        self._adjust_splitter_sizes()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_status_cards()
        self._adjust_splitter_sizes()
        schedule_table_column_fit(getattr(self, "overall_table", None))

    def _make_table(self, headers, rows, badge_cols=None, clickable_name_col=None, min_height=188, max_height=196):
        badge_cols = badge_cols or {}
        table = QTableWidget(len(rows), len(headers))
        table.setObjectName("HomeOverviewTable")
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setShowGrid(False)
        table.setAlternatingRowColors(True)
        table.setFocusPolicy(Qt.NoFocus)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setDefaultSectionSize(108)
        table.horizontalHeader().setMinimumHeight(30)
        table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        table.verticalHeader().setDefaultSectionSize(42)
        table.setMinimumHeight(min_height)
        if max_height is not None:
            table.setMaximumHeight(max_height)
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignCenter if c != clickable_name_col else Qt.AlignVCenter)
                if c in badge_cols and value in badge_cols[c]:
                    bg, fg = badge_cols[c][value]
                    item.setBackground(QBrush(QColor(bg)))
                    item.setForeground(QBrush(QColor(fg)))
                elif clickable_name_col is not None and c == clickable_name_col:
                    item.setForeground(QBrush(QColor("#2455c9")))
                table.setItem(r, c, item)
        if table.rowCount() > 0:
            table.selectRow(0)
        return table
