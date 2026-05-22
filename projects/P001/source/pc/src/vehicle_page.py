from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDateEdit,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from .table_column_manager import install_resizable_table_columns
from .widgets import Panel, InnerScrollFrame, PAGE_OUTER_MARGINS, PAGE_OUTER_SPACING


class VehiclePage(QWidget):
    request_settings = Signal()

    def __init__(self, state):
        super().__init__()
        self.state = state
        self.selected_vehicle_id: str = ""
        self.selected_run_log_id: str = ""
        self.selected_fuel_log_id: str = ""
        self.selected_cost_log_id: str = ""

        self.state.vehicles_changed.connect(self.refresh_from_state)
        self.state.settings_changed.connect(self.refresh_from_state)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*PAGE_OUTER_MARGINS)
        layout.setSpacing(PAGE_OUTER_SPACING)
        # 바깥 큰 테두리는 고정하고, 차량관리 내용은 그 안쪽에서만 스크롤합니다.
        layout.addWidget(self._create_content(), 1)

        self._apply_default_period()
        self.refresh_from_state()

    def _apply_default_period(self):
        today = QDate.currentDate()
        self.year_combo.setCurrentText(str(today.year()))
        self.month_combo.setCurrentIndex(max(0, today.month() - 1))
        self.run_date_edit.setDate(today)
        self.fuel_date_edit.setDate(QDate.currentDate())
        self.cost_date_edit.setDate(QDate.currentDate())

    def _create_content(self):
        wrap = QWidget()
        root = QVBoxLayout(wrap)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        # 상단 고정 배너는 MainWindow에서 표시합니다.

        toolbar_panel = Panel("조회 조건", "월 기준 조회 · 운행기록 · 주유기록 · 기타비용 · 렌트카 경고 확인", icon_name="vehicle")
        toolbar_panel.body_layout.addLayout(self._create_filter_row())
        toolbar_panel.body_layout.addLayout(self._create_filter_subrow())
        root.addWidget(toolbar_panel)

        self.body_splitter = QSplitter(Qt.Horizontal)
        self.body_splitter.setChildrenCollapsible(False)
        self.body_splitter.setHandleWidth(6)

        self.summary_panel = self._create_vehicle_summary_panel()
        self.log_panel = self._create_log_panel()
        self.detail_panel = self._create_detail_and_editor_panel()

        self.body_splitter.addWidget(self.summary_panel)
        self.body_splitter.addWidget(self.log_panel)
        self.body_splitter.addWidget(self.detail_panel)
        self.body_splitter.setStretchFactor(0, 0)
        self.body_splitter.setStretchFactor(1, 1)
        self.body_splitter.setStretchFactor(2, 0)
        self.body_splitter.setSizes([360, 700, 300])
        root.addWidget(self.body_splitter, 1)
        scroll_frame = InnerScrollFrame(wrap, margins=(0, 0, 0, 0), min_content_height=620)
        scroll_frame.setObjectName("ScrollPageOuterFrame")
        return scroll_frame

    def _create_hero(self):
        hero = QFrame()
        hero.setObjectName("HeroCard")
        hero.setFixedHeight(78)

        row = QHBoxLayout(hero)
        row.setContentsMargins(6, 6, 6, 6)
        row.setSpacing(6)

        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(6)

        badge = QLabel("VEHICLE MANAGEMENT")
        badge.setObjectName("HeroBadge")

        title = QLabel("차량관리")
        title.setObjectName("HeroTitle")

        desc = QLabel("차량 목록, 월간 운행기록, 주유내역, 렌트카 경고 상태를 한 화면에서 확인합니다.")
        desc.setObjectName("HeroDesc")
        desc.setWordWrap(True)

        left.addWidget(badge)
        left.addWidget(title)
        left.addWidget(desc)
        left.addStretch()
        row.addLayout(left, 1)
        return hero

    def _create_filter_row(self):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        self.year_combo = QComboBox()
        for year in ["2025", "2026", "2027", "2028"]:
            self.year_combo.addItem(year)

        self.month_combo = QComboBox()
        for month in range(1, 13):
            self.month_combo.addItem(f"{month}월", month)

        self.vehicle_type_combo = QComboBox()
        self.vehicle_type_combo.addItems(["전체", "자차", "렌트카"])

        self.vehicle_combo = QComboBox()
        self.vehicle_combo.addItem("전체 차량", "")

        self.driver_search = QLineEdit()
        self.driver_search.setPlaceholderText("운전자 이름 검색")
        self.driver_search.returnPressed.connect(self.refresh_from_state)

        self.query_btn = QPushButton("조회")
        self.query_btn.setObjectName("PrimaryButton")
        self.query_btn.clicked.connect(self.refresh_from_state)
        self.reset_btn = QPushButton("초기화")
        self.reset_btn.setObjectName("GhostButton")
        self.reset_btn.clicked.connect(self._reset_filters)

        for widget in [self.year_combo, self.month_combo, self.vehicle_type_combo, self.vehicle_combo, self.driver_search, self.query_btn, self.reset_btn]:
            widget.setMinimumHeight(30)

        row.addWidget(QLabel("연도"))
        row.addWidget(self.year_combo)
        row.addWidget(QLabel("월"))
        row.addWidget(self.month_combo)
        row.addWidget(QLabel("구분"))
        row.addWidget(self.vehicle_type_combo)
        row.addWidget(QLabel("차량"))
        row.addWidget(self.vehicle_combo, 1)
        row.addWidget(self.driver_search, 1)
        row.addWidget(self.query_btn)
        row.addWidget(self.reset_btn)
        return row

    def _create_filter_subrow(self):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        self.status_combo = QComboBox()
        self.status_combo.addItems(["전체 상태", "정상", "km임박", "계약임박", "초과", "무제한"])
        self.status_combo.setMinimumHeight(28)
        self.status_combo.currentIndexChanged.connect(self.refresh_from_state)

        self.new_run_btn = QPushButton("신규 운행기록")
        self.new_run_btn.setObjectName("GhostButton")
        self.new_run_btn.clicked.connect(self._new_run_log)
        self.new_fuel_btn = QPushButton("신규 주유기록")
        self.new_fuel_btn.setObjectName("GhostButton")
        self.new_fuel_btn.clicked.connect(self._new_fuel_log)
        self.new_cost_btn = QPushButton("신규 기타비용")
        self.new_cost_btn.setObjectName("GhostButton")
        self.new_cost_btn.clicked.connect(self._new_cost_log)

        hint = QLabel("차량 등록·배치·경고 기준은 설정에서 관리")
        hint.setObjectName("PanelNote")

        row.addWidget(QLabel("상태"))
        row.addWidget(self.status_combo)
        row.addSpacing(6)
        row.addWidget(self.new_run_btn)
        row.addWidget(self.new_fuel_btn)
        row.addWidget(self.new_cost_btn)
        row.addStretch(1)
        row.addWidget(hint)
        return row

    def _create_vehicle_summary_panel(self):
        panel = Panel("차량 목록", "차량 선택 · 렌트카 경고 상태 확인", icon_name="vehicle")
        panel.setMinimumWidth(280)
        panel.setMaximumWidth(390)

        metrics = QGridLayout()
        metrics.setContentsMargins(0, 0, 0, 0)
        metrics.setHorizontalSpacing(6)
        metrics.setVerticalSpacing(6)

        self.total_vehicle_value = self._metric_card("전체 차량", "0대", "등록 차량 수")
        self.monthly_km_value = self._metric_card("월간 주행", "0km", "선택 월 합계")
        self.monthly_fuel_value = self._metric_card("월간 주유비", "0원", "선택 월 합계")
        self.monthly_cost_value = self._metric_card("월간 기타비용", "0원", "선택 월 합계")
        metrics.addWidget(self.total_vehicle_value[0], 0, 0)
        metrics.addWidget(self.monthly_km_value[0], 0, 1)
        metrics.addWidget(self.monthly_fuel_value[0], 1, 0)
        metrics.addWidget(self.monthly_cost_value[0], 1, 1)
        panel.body_layout.addLayout(metrics)

        self.vehicle_table = QTableWidget(0, 4)
        self.vehicle_table.setHorizontalHeaderLabels(["차량명", "번호", "구분", "상태"])
        self.vehicle_table.verticalHeader().setVisible(False)
        self.vehicle_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.vehicle_table.setSelectionMode(QTableWidget.SingleSelection)
        self.vehicle_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.vehicle_table.setAlternatingRowColors(False)
        self.vehicle_table.setWordWrap(False)
        self.vehicle_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.vehicle_table.itemSelectionChanged.connect(self._vehicle_row_changed)
        install_resizable_table_columns(
            self.vehicle_table,
            state=self.state,
            key="vehicle/vehicle_table",
            default_widths=[150, 110, 82, 76],
            min_widths=[108, 92, 66, 62],
        )
        panel.body_layout.addWidget(self.vehicle_table, 1)
        return panel

    def _metric_card(self, title: str, value: str, sub: str):
        frame = QFrame()
        frame.setObjectName("DetailSummaryCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        title_lbl = QLabel(title)
        title_lbl.setObjectName("DetailKey")
        value_lbl = QLabel(value)
        value_lbl.setObjectName("DetailName")
        value_lbl.setStyleSheet("font-size:18px;")
        sub_lbl = QLabel(sub)
        sub_lbl.setObjectName("DetailMeta")
        layout.addWidget(title_lbl)
        layout.addWidget(value_lbl)
        layout.addWidget(sub_lbl)
        return frame, value_lbl, sub_lbl

    def _create_log_panel(self):
        panel = Panel("월간 기록", "운행기록 / 주유기록 / 기타비용", icon_name="attendance")
        self.log_tabs = QTabWidget()
        self.log_tabs.currentChanged.connect(self._on_tab_changed)

        self.run_table = QTableWidget(0, 8)
        self.run_table.setHorizontalHeaderLabels(["날짜", "차량", "실제 운전자", "이전 km", "종료 km", "주행 km", "왕복", "기타"])
        self._setup_table(self.run_table)
        self.run_table.itemSelectionChanged.connect(self._run_row_changed)
        install_resizable_table_columns(
            self.run_table,
            state=self.state,
            key="vehicle/run_table",
            default_widths=[96, 122, 120, 86, 86, 82, 58, 150],
            min_widths=[82, 92, 94, 74, 74, 70, 48, 90],
        )

        self.fuel_table = QTableWidget(0, 5)
        self.fuel_table.setHorizontalHeaderLabels(["주유일시", "차량", "구분", "주유비", "비고"])
        self._setup_table(self.fuel_table)
        self.fuel_table.itemSelectionChanged.connect(self._fuel_row_changed)
        install_resizable_table_columns(
            self.fuel_table,
            state=self.state,
            key="vehicle/fuel_table",
            default_widths=[126, 130, 84, 96, 170],
            min_widths=[98, 94, 66, 78, 98],
        )

        self.cost_table = QTableWidget(0, 7)
        self.cost_table.setHorizontalHeaderLabels(["일자", "차량", "비용구분", "금액", "내용", "입력구분", "비고"])
        self._setup_table(self.cost_table)
        self.cost_table.itemSelectionChanged.connect(self._cost_row_changed)
        install_resizable_table_columns(
            self.cost_table,
            state=self.state,
            key="vehicle/cost_table",
            default_widths=[96, 126, 104, 92, 160, 96, 150],
            min_widths=[78, 92, 82, 72, 96, 78, 90],
        )

        self.log_tabs.addTab(self.run_table, "운행기록")
        self.log_tabs.addTab(self.fuel_table, "주유기록")
        self.log_tabs.addTab(self.cost_table, "기타비용")
        panel.body_layout.addWidget(self.log_tabs, 1)
        return panel

    def _setup_table(self, table: QTableWidget):
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)

    def _create_detail_and_editor_panel(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setMinimumWidth(260)
        scroll.setMaximumWidth(340)

        wrap = QWidget()
        wrap.setObjectName("VehicleDetailScrollContent")
        wrap.setMinimumWidth(0)
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        detail = Panel("선택 차량 상세", "선택 차량 핵심 정보 · 차량 등록·배치는 설정에서 관리", icon_name="vehicle")
        detail.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.vehicle_name_lbl = QLabel("차량 선택 전")
        self.vehicle_name_lbl.setObjectName("DetailName")
        self.vehicle_meta_lbl = QLabel("차량 구분 / 차량번호")
        self.vehicle_meta_lbl.setObjectName("DetailMeta")
        detail.body_layout.addWidget(self.vehicle_name_lbl)
        detail.body_layout.addWidget(self.vehicle_meta_lbl)

        self.detail_grid = QGridLayout()
        self.detail_grid.setContentsMargins(0, 6, 0, 0)
        self.detail_grid.setHorizontalSpacing(6)
        self.detail_grid.setVerticalSpacing(6)
        self.detail_labels: dict[str, QLabel] = {}
        rows = [
            ("주 운전자", "main_driver"),
            ("배치 사업장", "work_site_name"),
            ("최근 종료 km", "current_odometer"),
            ("월간 주행", "monthly_km"),
            ("월간 주유비", "fuel_total"),
            ("월간 기타비용", "cost_total"),
            ("최근 주유일", "recent_fuel_date"),
            ("남은 km", "remaining_km"),
            ("계약 종료", "contract_end"),
            ("상태", "status_text"),
            ("첨부 서류", "attachment_document"),
        ]
        for idx, (label_text, key) in enumerate(rows):
            lbl = QLabel(label_text)
            lbl.setObjectName("DetailKey")
            val = QLabel("-")
            val.setObjectName("DetailValue")
            val.setWordWrap(True)
            self.detail_grid.addWidget(lbl, idx, 0)
            self.detail_grid.addWidget(val, idx, 1)
            self.detail_labels[key] = val
        detail.body_layout.addLayout(self.detail_grid)
        self.settings_hint_btn = QPushButton("설정에서 차량 배치/경고 기준 관리")
        self.settings_hint_btn.setObjectName("GhostButton")
        self.settings_hint_btn.clicked.connect(self.request_settings.emit)
        detail.body_layout.addWidget(self.settings_hint_btn)
        layout.addWidget(detail)

        editor = Panel("기록 입력 / 수정", "앱 등록 중심 · PC에서도 신규 입력 및 수정 가능", icon_name="registration")
        editor.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        editor_toolbar = QHBoxLayout()
        editor_toolbar.setContentsMargins(0, 0, 0, 0)
        editor_toolbar.setSpacing(6)
        self.editor_new_btn = QPushButton("신규")
        self.editor_new_btn.setObjectName("GhostButton")
        self.editor_new_btn.clicked.connect(self._new_current_tab_record)
        self.editor_save_btn = QPushButton("저장")
        self.editor_save_btn.setObjectName("PrimaryButton")
        self.editor_save_btn.clicked.connect(self._save_current_tab_record)
        self.editor_delete_btn = QPushButton("삭제")
        self.editor_delete_btn.setObjectName("DangerButton")
        self.editor_delete_btn.clicked.connect(self._delete_current_tab_record)
        self.editor_cancel_btn = QPushButton("초기화")
        self.editor_cancel_btn.setObjectName("GhostButton")
        self.editor_cancel_btn.clicked.connect(self._reset_current_editor)
        editor_toolbar.addWidget(self.editor_new_btn)
        editor_toolbar.addWidget(self.editor_save_btn)
        editor_toolbar.addWidget(self.editor_delete_btn)
        editor_toolbar.addWidget(self.editor_cancel_btn)
        editor.body_layout.addLayout(editor_toolbar)

        self.editor_stack = QStackedWidget()
        self.editor_stack.addWidget(self._create_run_editor())
        self.editor_stack.addWidget(self._create_fuel_editor())
        self.editor_stack.addWidget(self._create_cost_editor())
        editor.body_layout.addWidget(self.editor_stack)
        layout.addWidget(editor)
        layout.addStretch(1)
        scroll.setWidget(wrap)
        return scroll

    def _create_run_editor(self):
        wrap = QWidget()
        form = QFormLayout(wrap)
        form.setContentsMargins(0, 6, 0, 0)
        form.setSpacing(6)
        self.run_log_id_edit = QLineEdit()
        self.run_log_id_edit.hide()
        self.run_date_edit = QDateEdit()
        self.run_date_edit.setCalendarPopup(True)
        self.run_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.run_vehicle_combo = QComboBox()
        self.run_driver_combo = QComboBox()
        self._configure_searchable_combo(self.run_driver_combo, "비워두면 기본 주 운전자 자동 적용")
        self.run_prev_km_label = QLabel("0")
        self.run_prev_km_label.setObjectName("StatusBadge")
        self.run_end_km_edit = QLineEdit()
        self.run_round_combo = QComboBox()
        self.run_round_combo.addItems(["1회", "2회", "3회", "4회", "5회"])
        self.run_km_preview = QLabel("0 km")
        self.run_km_preview.setObjectName("StatusBadge")
        self.run_note_edit = QTextEdit()
        self.run_note_edit.setPlaceholderText("예: 직원 병원이송, 현장 추가 이동, 자재 운반")
        self.run_note_edit.setFixedHeight(72)

        self.run_vehicle_combo.currentIndexChanged.connect(self._refresh_run_preview)
        self.run_vehicle_combo.currentIndexChanged.connect(self._reload_run_driver_candidates)
        self.run_date_edit.dateChanged.connect(self._refresh_run_preview)
        self.run_end_km_edit.textChanged.connect(self._refresh_run_preview)

        form.addRow("기록 ID", self.run_log_id_edit)
        form.addRow("날짜", self.run_date_edit)
        form.addRow("차량", self.run_vehicle_combo)
        form.addRow("실제 운전자", self.run_driver_combo)
        form.addRow("이전 계기판 km", self.run_prev_km_label)
        form.addRow("종료 계기판 km", self.run_end_km_edit)
        form.addRow("이번 주행 km", self.run_km_preview)
        form.addRow("왕복 횟수", self.run_round_combo)
        form.addRow("기타 메모", self.run_note_edit)
        return wrap

    def _create_fuel_editor(self):
        wrap = QWidget()
        form = QFormLayout(wrap)
        form.setContentsMargins(0, 6, 0, 0)
        form.setSpacing(6)
        self.fuel_log_id_edit = QLineEdit()
        self.fuel_log_id_edit.hide()
        self.fuel_date_edit = QDateEdit()
        self.fuel_date_edit.setCalendarPopup(True)
        self.fuel_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.fuel_date_edit.setDate(QDate.currentDate())
        self.fuel_vehicle_combo = QComboBox()
        self.fuel_amount_edit = QLineEdit()
        self.fuel_note_edit = QTextEdit()
        self.fuel_note_edit.setPlaceholderText("예: 일반 주유, 장거리 이동 전 주유")
        self.fuel_note_edit.setFixedHeight(82)

        form.addRow("기록 ID", self.fuel_log_id_edit)
        form.addRow("주유일시", self.fuel_date_edit)
        form.addRow("차량", self.fuel_vehicle_combo)
        form.addRow("주유비 (원)", self.fuel_amount_edit)
        form.addRow("비고", self.fuel_note_edit)
        return wrap

    def _create_cost_editor(self):
        wrap = QWidget()
        form = QFormLayout(wrap)
        form.setContentsMargins(0, 6, 0, 0)
        form.setSpacing(6)
        self.cost_log_id_edit = QLineEdit()
        self.cost_log_id_edit.hide()
        self.cost_date_edit = QDateEdit()
        self.cost_date_edit.setCalendarPopup(True)
        self.cost_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.cost_date_edit.setDate(QDate.currentDate())
        self.cost_vehicle_combo = QComboBox()
        self.cost_category_combo = QComboBox()
        self.cost_category_combo.addItems(["통행료", "주차비", "정비비", "세차비", "소모품", "타이어", "보험", "과태료", "기타"])
        self.cost_amount_edit = QLineEdit()
        self.cost_description_edit = QLineEdit()
        self.cost_description_edit.setPlaceholderText("예: 고속도로 통행료, 엔진오일 교체")
        self.cost_source_combo = QComboBox()
        self.cost_source_combo.addItems(["PC수동", "모바일"])
        self.cost_note_edit = QTextEdit()
        self.cost_note_edit.setPlaceholderText("영수증 번호, 처리 내용, 특이사항")
        self.cost_note_edit.setFixedHeight(76)

        form.addRow("기록 ID", self.cost_log_id_edit)
        form.addRow("날짜", self.cost_date_edit)
        form.addRow("차량", self.cost_vehicle_combo)
        form.addRow("비용구분", self.cost_category_combo)
        form.addRow("금액 (원)", self.cost_amount_edit)
        form.addRow("내용", self.cost_description_edit)
        form.addRow("입력구분", self.cost_source_combo)
        form.addRow("비고", self.cost_note_edit)
        return wrap


    def _adjust_splitter_sizes(self):
        if not hasattr(self, "body_splitter"):
            return
        total = max(self.width() - 12, 760)
        left = min(max(int(total * 0.28), 280), 380)
        right = min(max(int(total * 0.23), 260), 340)
        middle = max(360, total - left - right)
        self.body_splitter.setSizes([left, middle, right])

    def showEvent(self, event):
        super().showEvent(event)
        if getattr(self, "_show_layout_initialized", False):
            return
        self._show_layout_initialized = True
        self._adjust_splitter_sizes()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adjust_splitter_sizes()

    def _current_year_month(self) -> tuple[int, int]:
        year = int(self.year_combo.currentText() or date.today().year)
        month = int(self.month_combo.currentData() or self.month_combo.currentIndex() + 1)
        return year, month

    def _populate_vehicle_selectors(self):
        vehicles = self.state.vehicle_records()
        combo_data = [(f"{row.get('vehicle_name', '')} · {row.get('plate_number', '')}", row.get("vehicle_id", "")) for row in vehicles]
        current_filter = self.vehicle_combo.currentData() if self.vehicle_combo.count() else ""
        current_run = self.run_vehicle_combo.currentData() if self.run_vehicle_combo.count() else ""
        current_fuel = self.fuel_vehicle_combo.currentData() if self.fuel_vehicle_combo.count() else ""
        current_cost = self.cost_vehicle_combo.currentData() if self.cost_vehicle_combo.count() else ""

        self.vehicle_combo.blockSignals(True)
        self.vehicle_combo.clear()
        self.vehicle_combo.addItem("전체 차량", "")
        for label, vid in combo_data:
            self.vehicle_combo.addItem(label, vid)
        self._restore_combo_data(self.vehicle_combo, current_filter)
        self.vehicle_combo.blockSignals(False)

        for combo, current in [(self.run_vehicle_combo, current_run), (self.fuel_vehicle_combo, current_fuel), (self.cost_vehicle_combo, current_cost)]:
            combo.blockSignals(True)
            combo.clear()
            for label, vid in combo_data:
                combo.addItem(label, vid)
            self._restore_combo_data(combo, current or self.selected_vehicle_id)
            combo.blockSignals(False)
        self._reload_run_driver_candidates()

    def _restore_combo_data(self, combo: QComboBox, target):
        target = str(target or "")
        if not target and combo.count():
            combo.setCurrentIndex(0)
            return
        for idx in range(combo.count()):
            if str(combo.itemData(idx) or "") == target:
                combo.setCurrentIndex(idx)
                return
        if combo.count():
            combo.setCurrentIndex(0)

    def _configure_searchable_combo(self, combo: QComboBox, placeholder: str):
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        if combo.lineEdit() is not None:
            combo.lineEdit().setPlaceholderText(placeholder)
        completer = QCompleter(combo.model(), combo)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        combo.setCompleter(completer)

    def _selected_run_vehicle(self) -> dict:
        vehicle_id = str(self.run_vehicle_combo.currentData() or self.selected_vehicle_id or "").strip()
        return self.state.get_vehicle_by_id(vehicle_id) or {}

    def _reload_run_driver_candidates(self, preserve_text: str | None = None):
        current = str(preserve_text if preserve_text is not None else self.run_driver_combo.currentText()).strip()
        vehicle = self._selected_run_vehicle()
        business_name = str(vehicle.get("business_name", "") or "").strip()
        names = self.state.vehicle_driver_candidates(business_name)
        self.run_driver_combo.blockSignals(True)
        self.run_driver_combo.clear()
        for name in names:
            self.run_driver_combo.addItem(name)
        if current:
            idx = self.run_driver_combo.findText(current)
            if idx < 0:
                self.run_driver_combo.addItem(current)
                idx = self.run_driver_combo.findText(current)
            self.run_driver_combo.setCurrentIndex(idx)
            self.run_driver_combo.setEditText(current)
        else:
            self.run_driver_combo.setCurrentIndex(-1)
            if self.run_driver_combo.lineEdit() is not None:
                self.run_driver_combo.lineEdit().clear()
        self.run_driver_combo.blockSignals(False)

    def _reset_filters(self):
        today = date.today()
        self.year_combo.setCurrentText(str(today.year))
        self.month_combo.setCurrentIndex(today.month - 1)
        self.vehicle_type_combo.setCurrentIndex(0)
        self.vehicle_combo.setCurrentIndex(0)
        self.status_combo.setCurrentIndex(0)
        self.driver_search.clear()
        self.refresh_from_state()

    def refresh_from_state(self):
        self._populate_vehicle_selectors()
        self._load_vehicle_summary_table()
        self._load_log_tables()
        self._refresh_run_preview()

    def _load_vehicle_summary_table(self):
        year, month = self._current_year_month()
        rows = self.state.vehicle_summary_rows(
            year,
            month,
            vehicle_type=self.vehicle_type_combo.currentText(),
            vehicle_id=self.vehicle_combo.currentData(),
            driver_filter=self.driver_search.text(),
        )
        status_filter = self.status_combo.currentText()
        if status_filter != "전체 상태":
            rows = [row for row in rows if str(row.get("status_text", "")) == status_filter]

        self.vehicle_table.setRowCount(len(rows))
        total_monthly_km = 0.0
        total_fuel = 0
        total_cost = 0
        for row_idx, row in enumerate(rows):
            total_monthly_km += float(row.get("monthly_km", 0) or 0)
            total_fuel += int(row.get("fuel_total", 0) or 0)
            total_cost += int(row.get("cost_total", 0) or 0)
            values = [
                row.get("vehicle_name", ""),
                row.get("plate_number", ""),
                row.get("vehicle_type", ""),
                row.get("status_text", "정상"),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col in (2, 3):
                    item.setTextAlignment(Qt.AlignCenter)
                self.vehicle_table.setItem(row_idx, col, item)
            self.vehicle_table.item(row_idx, 0).setData(Qt.UserRole, row)

        self.total_vehicle_value[1].setText(f"{len(rows)}대")
        self.monthly_km_value[1].setText(f"{int(total_monthly_km):,}km")
        self.monthly_fuel_value[1].setText(f"{total_fuel:,}원")
        self.monthly_cost_value[1].setText(f"{total_cost:,}원")

        if rows:
            selected = False
            for row_idx in range(self.vehicle_table.rowCount()):
                data = self.vehicle_table.item(row_idx, 0).data(Qt.UserRole)
                if str((data or {}).get("vehicle_id", "")) == self.selected_vehicle_id:
                    self.vehicle_table.selectRow(row_idx)
                    selected = True
                    break
            if not selected:
                self.vehicle_table.selectRow(0)
        else:
            self.selected_vehicle_id = ""
            self._update_vehicle_detail({})

    def _vehicle_row_changed(self):
        row = self.vehicle_table.currentRow()
        if row < 0:
            return
        data = self.vehicle_table.item(row, 0).data(Qt.UserRole) or {}
        self.selected_vehicle_id = str(data.get("vehicle_id", "") or "")
        self._update_vehicle_detail(data)
        self._load_log_tables()
        self._prefill_vehicle_for_editors()

    def _update_vehicle_detail(self, data: dict):
        if not data:
            self.vehicle_name_lbl.setText("차량 선택 전")
            self.vehicle_meta_lbl.setText("차량 구분 / 차량번호")
            for lbl in self.detail_labels.values():
                lbl.setText("-")
            return
        self.vehicle_name_lbl.setText(str(data.get("vehicle_name", "-")))
        self.vehicle_meta_lbl.setText(f"{data.get('vehicle_type', '-')} · {data.get('plate_number', '-')}")
        mapping = {
            "main_driver": data.get("main_driver", "-"),
            "work_site_name": data.get("work_site_name", "-"),
            "current_odometer": f"{int(float(data.get('current_odometer', 0) or 0)):,} km",
            "monthly_km": f"{int(float(data.get('monthly_km', 0) or 0)):,} km",
            "fuel_total": f"{int(float(data.get('fuel_total', 0) or 0)):,} 원",
            "cost_total": f"{int(float(data.get('cost_total', 0) or 0)):,} 원",
            "recent_fuel_date": data.get("recent_fuel_date", "-") or "-",
            "remaining_km": "무제한" if data.get("unlimited") else (f"{int(float(data.get('remaining_km', 0) or 0)):,} km" if data.get("remaining_km") is not None else "-"),
            "contract_end": data.get("contract_end", "-") or "-",
            "status_text": f"{data.get('status_text', '-')} · {data.get('status_note', '-')}",
            "attachment_document": Path(str(data.get("attachment_document_path", "") or "")).name or "-",
        }
        for key, lbl in self.detail_labels.items():
            lbl.setText(str(mapping.get(key, "-")))

    def _load_log_tables(self):
        year, month = self._current_year_month()
        target_vehicle = self.selected_vehicle_id or self.vehicle_combo.currentData()
        driver_filter = self.driver_search.text()
        run_rows = self.state.vehicle_run_log_rows(year, month, vehicle_id=target_vehicle, driver_filter=driver_filter)
        self.run_table.setRowCount(len(run_rows))
        for row_idx, row in enumerate(run_rows):
            values = [
                row.get("date", ""),
                row.get("vehicle_name", ""),
                row.get("driver_name", ""),
                f"{int(float(row.get('prev_odometer', 0) or 0)):,}",
                f"{int(float(row.get('end_odometer', 0) or 0)):,}",
                f"{int(float(row.get('run_km', 0) or 0)):,}",
                f"{int(row.get('round_trips', 0) or 0)}회",
                row.get("note", ""),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col in (3, 4, 5, 6):
                    item.setTextAlignment(Qt.AlignCenter)
                self.run_table.setItem(row_idx, col, item)
            self.run_table.item(row_idx, 0).setData(Qt.UserRole, row)

        fuel_rows = self.state.vehicle_fuel_log_rows(year, month, vehicle_id=target_vehicle)
        self.fuel_table.setRowCount(len(fuel_rows))
        for row_idx, row in enumerate(fuel_rows):
            values = [
                row.get("fuel_date", ""),
                row.get("vehicle_name", ""),
                row.get("vehicle_type", ""),
                f"{int(float(row.get('amount', 0) or 0)):,}",
                row.get("note", ""),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col == 3:
                    item.setTextAlignment(Qt.AlignCenter)
                self.fuel_table.setItem(row_idx, col, item)
            self.fuel_table.item(row_idx, 0).setData(Qt.UserRole, row)

        cost_rows = self.state.vehicle_cost_log_rows(year, month, vehicle_id=target_vehicle)
        self.cost_table.setRowCount(len(cost_rows))
        for row_idx, row in enumerate(cost_rows):
            values = [
                str(row.get("cost_date", ""))[:10],
                row.get("vehicle_name", ""),
                row.get("category", ""),
                f"{int(float(row.get('amount', 0) or 0)):,}",
                row.get("description", ""),
                row.get("source", ""),
                row.get("note", ""),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col in (2, 3, 5):
                    item.setTextAlignment(Qt.AlignCenter)
                self.cost_table.setItem(row_idx, col, item)
            self.cost_table.item(row_idx, 0).setData(Qt.UserRole, row)

        if self.log_tabs.currentIndex() == 0:
            self._restore_run_selection()
        elif self.log_tabs.currentIndex() == 1:
            self._restore_fuel_selection()
        else:
            self._restore_cost_selection()

    def _clear_run_table_selection(self):
        try:
            self.run_table.blockSignals(True)
            self.run_table.clearSelection()
            try:
                self.run_table.setCurrentCell(-1, -1)
            except Exception:
                pass
        finally:
            self.run_table.blockSignals(False)

    def _clear_fuel_table_selection(self):
        try:
            self.fuel_table.blockSignals(True)
            self.fuel_table.clearSelection()
            try:
                self.fuel_table.setCurrentCell(-1, -1)
            except Exception:
                pass
        finally:
            self.fuel_table.blockSignals(False)

    def _clear_cost_table_selection(self):
        try:
            self.cost_table.blockSignals(True)
            self.cost_table.clearSelection()
            try:
                self.cost_table.setCurrentCell(-1, -1)
            except Exception:
                pass
        finally:
            self.cost_table.blockSignals(False)

    def _reset_run_editor_for_new_entry(self, vehicle_id: str | None = None):
        self.selected_run_log_id = ""
        self.run_log_id_edit.clear()
        if vehicle_id:
            self._restore_combo_data(self.run_vehicle_combo, vehicle_id)
        self._reload_run_driver_candidates("")
        self.run_end_km_edit.clear()
        self.run_note_edit.clear()
        self.run_round_combo.setCurrentIndex(0)
        self.editor_stack.setCurrentIndex(0)
        self.log_tabs.setCurrentIndex(0)
        self._refresh_run_preview(exclude_log_id="")

    def _restore_run_selection(self):
        if self.run_table.rowCount() == 0:
            self._clear_run_table_selection()
            self._reset_run_editor_for_new_entry(self.selected_vehicle_id)
            return
        if not str(self.selected_run_log_id or "").strip():
            self._clear_run_table_selection()
            self._reset_run_editor_for_new_entry(self.selected_vehicle_id)
            return
        for row_idx in range(self.run_table.rowCount()):
            row = self.run_table.item(row_idx, 0).data(Qt.UserRole) or {}
            if str(row.get("log_id", "")) == self.selected_run_log_id:
                self.run_table.selectRow(row_idx)
                return
        self._clear_run_table_selection()
        self._reset_run_editor_for_new_entry(self.selected_vehicle_id)

    def _restore_fuel_selection(self):
        if self.fuel_table.rowCount() == 0:
            self._clear_fuel_table_selection()
            self.selected_fuel_log_id = ""
            self._new_fuel_log()
            return
        if not str(self.selected_fuel_log_id or "").strip():
            self._clear_fuel_table_selection()
            self._new_fuel_log()
            return
        for row_idx in range(self.fuel_table.rowCount()):
            row = self.fuel_table.item(row_idx, 0).data(Qt.UserRole) or {}
            if str(row.get("fuel_id", "")) == self.selected_fuel_log_id:
                self.fuel_table.selectRow(row_idx)
                return
        self._clear_fuel_table_selection()
        self.selected_fuel_log_id = ""
        self._new_fuel_log()

    def _restore_cost_selection(self):
        if self.cost_table.rowCount() == 0:
            self._clear_cost_table_selection()
            self.selected_cost_log_id = ""
            self._new_cost_log()
            return
        if not str(self.selected_cost_log_id or "").strip():
            self._clear_cost_table_selection()
            self._new_cost_log()
            return
        for row_idx in range(self.cost_table.rowCount()):
            row = self.cost_table.item(row_idx, 0).data(Qt.UserRole) or {}
            if str(row.get("cost_id", "")) == self.selected_cost_log_id:
                self.cost_table.selectRow(row_idx)
                return
        self._clear_cost_table_selection()
        self.selected_cost_log_id = ""
        self._new_cost_log()

    def _run_row_changed(self):
        row = self.run_table.currentRow()
        if row < 0:
            return
        data = self.run_table.item(row, 0).data(Qt.UserRole) or {}
        self.selected_run_log_id = str(data.get("log_id", "") or "")
        self._fill_run_editor(data)

    def _fuel_row_changed(self):
        row = self.fuel_table.currentRow()
        if row < 0:
            return
        data = self.fuel_table.item(row, 0).data(Qt.UserRole) or {}
        self.selected_fuel_log_id = str(data.get("fuel_id", "") or "")
        self._fill_fuel_editor(data)

    def _cost_row_changed(self):
        row = self.cost_table.currentRow()
        if row < 0:
            return
        data = self.cost_table.item(row, 0).data(Qt.UserRole) or {}
        self.selected_cost_log_id = str(data.get("cost_id", "") or "")
        self._fill_cost_editor(data)

    def _prefill_vehicle_for_editors(self):
        if self.selected_vehicle_id:
            self._restore_combo_data(self.run_vehicle_combo, self.selected_vehicle_id)
            self._restore_combo_data(self.fuel_vehicle_combo, self.selected_vehicle_id)
            self._restore_combo_data(self.cost_vehicle_combo, self.selected_vehicle_id)
            self._reload_run_driver_candidates()
            self._refresh_run_preview()

    def _new_current_tab_record(self):
        if self.log_tabs.currentIndex() == 0:
            self._new_run_log()
        elif self.log_tabs.currentIndex() == 1:
            self._new_fuel_log()
        else:
            self._new_cost_log()

    def _new_run_log(self):
        self.selected_run_log_id = ""
        self.run_date_edit.setDate(QDate(int(self.year_combo.currentText() or date.today().year), int(self.month_combo.currentData() or date.today().month), min(date.today().day, 28)))
        self._prefill_vehicle_for_editors()
        self._clear_run_table_selection()
        self._reset_run_editor_for_new_entry(self.selected_vehicle_id or str(self.run_vehicle_combo.currentData() or ""))

    def _new_fuel_log(self):
        self.selected_fuel_log_id = ""
        self.fuel_log_id_edit.clear()
        self.fuel_date_edit.setDate(QDate.currentDate())
        self._prefill_vehicle_for_editors()
        self.fuel_amount_edit.clear()
        self.fuel_note_edit.clear()
        self.editor_stack.setCurrentIndex(1)
        self.log_tabs.setCurrentIndex(1)

    def _new_cost_log(self):
        self.selected_cost_log_id = ""
        self.cost_log_id_edit.clear()
        self.cost_date_edit.setDate(QDate.currentDate())
        self._prefill_vehicle_for_editors()
        self.cost_category_combo.setCurrentIndex(0)
        self.cost_amount_edit.clear()
        self.cost_description_edit.clear()
        self.cost_source_combo.setCurrentText("PC수동")
        self.cost_note_edit.clear()
        self.editor_stack.setCurrentIndex(2)
        self.log_tabs.setCurrentIndex(2)

    def _fill_run_editor(self, data: dict):
        if not data:
            self._new_run_log()
            return
        self.editor_stack.setCurrentIndex(0)
        self.run_log_id_edit.setText(str(data.get("log_id", "") or ""))
        parsed = QDate.fromString(str(data.get("date", "")), "yyyy-MM-dd")
        if parsed.isValid():
            self.run_date_edit.setDate(parsed)
        self._restore_combo_data(self.run_vehicle_combo, data.get("vehicle_id"))
        self._reload_run_driver_candidates(str(data.get("driver_name", "") or ""))
        self.run_end_km_edit.setText(str(int(float(data.get("end_odometer", 0) or 0))))
        round_trips = max(1, min(5, int(data.get("round_trips", 1) or 1)))
        self.run_round_combo.setCurrentIndex(round_trips - 1)
        self.run_note_edit.setPlainText(str(data.get("note", "") or ""))
        self._refresh_run_preview(exclude_log_id=str(data.get("log_id", "") or ""))

    def _fill_fuel_editor(self, data: dict):
        if not data:
            self._new_fuel_log()
            return
        self.editor_stack.setCurrentIndex(1)
        self.fuel_log_id_edit.setText(str(data.get("fuel_id", "") or ""))
        parsed = QDate.fromString(str(data.get("fuel_date", ""))[:10], "yyyy-MM-dd")
        if parsed.isValid():
            self.fuel_date_edit.setDate(parsed)
        self._restore_combo_data(self.fuel_vehicle_combo, data.get("vehicle_id"))
        self.fuel_amount_edit.setText(str(int(float(data.get("amount", 0) or 0))))
        self.fuel_note_edit.setPlainText(str(data.get("note", "") or ""))

    def _fill_cost_editor(self, data: dict):
        if not data:
            self._new_cost_log()
            return
        self.editor_stack.setCurrentIndex(2)
        self.cost_log_id_edit.setText(str(data.get("cost_id", "") or ""))
        parsed = QDate.fromString(str(data.get("cost_date", ""))[:10], "yyyy-MM-dd")
        if parsed.isValid():
            self.cost_date_edit.setDate(parsed)
        self._restore_combo_data(self.cost_vehicle_combo, data.get("vehicle_id"))
        category = str(data.get("category", "") or "기타")
        idx = self.cost_category_combo.findText(category)
        self.cost_category_combo.setCurrentIndex(idx if idx >= 0 else self.cost_category_combo.findText("기타"))
        self.cost_amount_edit.setText(str(int(float(data.get("amount", 0) or 0))))
        self.cost_description_edit.setText(str(data.get("description", "") or ""))
        source = str(data.get("source", "") or "PC수동")
        source_idx = self.cost_source_combo.findText(source)
        self.cost_source_combo.setCurrentIndex(source_idx if source_idx >= 0 else 0)
        self.cost_note_edit.setPlainText(str(data.get("note", "") or ""))

    def _refresh_run_preview(self, *_, exclude_log_id: str | None = None):
        vehicle_id = self.run_vehicle_combo.currentData()
        if not vehicle_id:
            self.run_prev_km_label.setText("0")
            self.run_km_preview.setText("0 km")
            return
        prev = self.state.previous_vehicle_odometer_before(
            vehicle_id,
            self.run_date_edit.date().toString("yyyy-MM-dd"),
            exclude_log_id=exclude_log_id or self.run_log_id_edit.text(),
        )
        self.run_prev_km_label.setText(f"{int(prev):,} km")
        try:
            end_km = float(self.run_end_km_edit.text().replace(",", "") or 0)
        except ValueError:
            end_km = 0.0
        run_km = max(0.0, end_km - prev)
        self.run_km_preview.setText(f"{int(run_km):,} km")

    def _save_current_tab_record(self):
        if self.log_tabs.currentIndex() == 0:
            self._save_run_log()
        elif self.log_tabs.currentIndex() == 1:
            self._save_fuel_log()
        else:
            self._save_cost_log()

    def _save_run_log(self):
        vehicle_id = str(self.run_vehicle_combo.currentData() or "").strip()
        if not vehicle_id:
            QMessageBox.warning(self, "운행기록", "차량을 선택해 주세요.")
            return
        try:
            end_odometer = float(self.run_end_km_edit.text().replace(",", "") or 0)
        except ValueError:
            QMessageBox.warning(self, "운행기록", "종료 계기판 km는 숫자로 입력해 주세요.")
            return
        payload = {
            "log_id": self.run_log_id_edit.text(),
            "date": self.run_date_edit.date().toString("yyyy-MM-dd"),
            "vehicle_id": vehicle_id,
            "driver_name": self.run_driver_combo.currentText().strip() or (self.state.get_vehicle_by_id(vehicle_id) or {}).get("main_driver", ""),
            "end_odometer": end_odometer,
            "round_trips": self.run_round_combo.currentIndex() + 1,
            "note": self.run_note_edit.toPlainText().strip(),
            "source": "PC",
        }
        try:
            saved = self.state.save_vehicle_run_log(payload)
        except ValueError as error:
            QMessageBox.warning(self, "운행기록", str(error))
            return
        # 저장 후에는 기존 기록 선택/수정 상태가 아니라 바로 다음 신규 입력 상태로 유지합니다.
        # 목록 갱신 과정에서 방금 저장한 기록이 다시 선택되면 종료 km, 운전자, 왕복 횟수, 메모가
        # 입력칸에 되살아나는 문제가 생기므로 선택 ID를 먼저 비웁니다.
        self.selected_run_log_id = ""
        self.refresh_from_state()
        self._prepare_next_run_log_after_save(saved)

    def _prepare_next_run_log_after_save(self, saved: dict):
        vehicle_id = str(saved.get("vehicle_id", "") or "").strip()
        run_date = str(saved.get("date", "") or "").strip()
        driver_name = str(saved.get("driver_name", "") or "").strip()
        parsed = QDate.fromString(run_date, "yyyy-MM-dd")

        self.selected_run_log_id = ""
        self.run_log_id_edit.clear()
        if parsed.isValid():
            self.run_date_edit.setDate(parsed)
        if vehicle_id:
            self._restore_combo_data(self.run_vehicle_combo, vehicle_id)
        self._reload_run_driver_candidates(driver_name)
        self.run_end_km_edit.clear()
        self.run_note_edit.clear()
        self.run_round_combo.setCurrentIndex(0)
        self.editor_stack.setCurrentIndex(0)
        self.log_tabs.setCurrentIndex(0)
        self._clear_run_table_selection()
        self._refresh_run_preview(exclude_log_id="")

    def _save_fuel_log(self):
        vehicle_id = str(self.fuel_vehicle_combo.currentData() or "").strip()
        if not vehicle_id:
            QMessageBox.warning(self, "주유기록", "차량을 선택해 주세요.")
            return
        try:
            amount = float(self.fuel_amount_edit.text().replace(",", "") or 0)
        except ValueError:
            QMessageBox.warning(self, "주유기록", "주유비는 숫자로 입력해 주세요.")
            return
        payload = {
            "fuel_id": self.fuel_log_id_edit.text(),
            "fuel_date": self.fuel_date_edit.date().toString("yyyy-MM-dd") + " 09:00",
            "vehicle_id": vehicle_id,
            "amount": amount,
            "note": self.fuel_note_edit.toPlainText().strip(),
            "source": "PC",
        }
        try:
            saved = self.state.save_vehicle_fuel_log(payload)
        except ValueError as error:
            QMessageBox.warning(self, "주유기록", str(error))
            return
        # 저장 후에는 방금 저장한 주유기록이 다시 선택되어 금액/비고가 살아나지 않도록
        # 선택 ID를 비우고 신규 입력 상태로 전환합니다.
        self.selected_fuel_log_id = ""
        self.refresh_from_state()
        self._prepare_next_fuel_log_after_save(saved)

    def _prepare_next_fuel_log_after_save(self, saved: dict):
        vehicle_id = str(saved.get("vehicle_id", "") or "").strip()
        fuel_date = str(saved.get("fuel_date", "") or "")[:10]
        parsed = QDate.fromString(fuel_date, "yyyy-MM-dd")

        self.selected_fuel_log_id = ""
        self.fuel_log_id_edit.clear()
        if parsed.isValid():
            self.fuel_date_edit.setDate(parsed)
        if vehicle_id:
            self._restore_combo_data(self.fuel_vehicle_combo, vehicle_id)
        self.fuel_amount_edit.clear()
        self.fuel_note_edit.clear()
        self.editor_stack.setCurrentIndex(1)
        self.log_tabs.setCurrentIndex(1)
        self._clear_fuel_table_selection()

    def _save_cost_log(self):
        vehicle_id = str(self.cost_vehicle_combo.currentData() or "").strip()
        if not vehicle_id:
            QMessageBox.warning(self, "기타비용", "차량을 선택해 주세요.")
            return
        try:
            amount = float(self.cost_amount_edit.text().replace(",", "") or 0)
        except ValueError:
            QMessageBox.warning(self, "기타비용", "금액은 숫자로 입력해 주세요.")
            return
        payload = {
            "cost_id": self.cost_log_id_edit.text(),
            "cost_date": self.cost_date_edit.date().toString("yyyy-MM-dd") + " 09:00",
            "vehicle_id": vehicle_id,
            "category": self.cost_category_combo.currentText(),
            "amount": amount,
            "description": self.cost_description_edit.text().strip(),
            "note": self.cost_note_edit.toPlainText().strip(),
            "source": self.cost_source_combo.currentText() or "PC수동",
        }
        try:
            saved = self.state.save_vehicle_cost_log(payload)
        except ValueError as error:
            QMessageBox.warning(self, "기타비용", str(error))
            return
        # 저장 후에는 방금 저장한 기타비용이 다시 선택되어 금액/내용/비고가 살아나지 않도록
        # 선택 ID를 비우고 신규 입력 상태로 전환합니다.
        self.selected_cost_log_id = ""
        self.refresh_from_state()
        self._prepare_next_cost_log_after_save(saved)

    def _prepare_next_cost_log_after_save(self, saved: dict):
        vehicle_id = str(saved.get("vehicle_id", "") or "").strip()
        cost_date = str(saved.get("cost_date", "") or "")[:10]
        category = str(saved.get("category", "") or "").strip()
        source = str(saved.get("source", "") or "PC수동").strip() or "PC수동"
        parsed = QDate.fromString(cost_date, "yyyy-MM-dd")

        self.selected_cost_log_id = ""
        self.cost_log_id_edit.clear()
        if parsed.isValid():
            self.cost_date_edit.setDate(parsed)
        if vehicle_id:
            self._restore_combo_data(self.cost_vehicle_combo, vehicle_id)
        if category:
            idx = self.cost_category_combo.findText(category)
            if idx >= 0:
                self.cost_category_combo.setCurrentIndex(idx)
        source_idx = self.cost_source_combo.findText(source)
        self.cost_source_combo.setCurrentIndex(source_idx if source_idx >= 0 else 0)
        self.cost_amount_edit.clear()
        self.cost_description_edit.clear()
        self.cost_note_edit.clear()
        self.editor_stack.setCurrentIndex(2)
        self.log_tabs.setCurrentIndex(2)
        self._clear_cost_table_selection()

    def _confirm_vehicle_log_delete(self, title: str) -> bool:
        message = f"선택한 {title}을 삭제할까요?\n서버에도 삭제 상태가 반영되어 수동 동기화 후 다시 표시되지 않습니다."
        return QMessageBox.question(
            self,
            title,
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) == QMessageBox.Yes

    def _delete_current_tab_record(self):
        if self.log_tabs.currentIndex() == 0:
            if not self.run_log_id_edit.text().strip():
                return
            if not self._confirm_vehicle_log_delete("운행기록"):
                return
            try:
                self.state.delete_vehicle_run_log(self.run_log_id_edit.text().strip())
            except ValueError as error:
                QMessageBox.warning(self, "운행기록", str(error))
                return
            self.selected_run_log_id = ""
            self.refresh_from_state()
        elif self.log_tabs.currentIndex() == 1:
            if not self.fuel_log_id_edit.text().strip():
                return
            if not self._confirm_vehicle_log_delete("주유기록"):
                return
            try:
                self.state.delete_vehicle_fuel_log(self.fuel_log_id_edit.text().strip())
            except ValueError as error:
                QMessageBox.warning(self, "주유기록", str(error))
                return
            self.selected_fuel_log_id = ""
            self.refresh_from_state()
        else:
            if not self.cost_log_id_edit.text().strip():
                return
            if not self._confirm_vehicle_log_delete("기타비용"):
                return
            try:
                self.state.delete_vehicle_cost_log(self.cost_log_id_edit.text().strip())
            except ValueError as error:
                QMessageBox.warning(self, "기타비용", str(error))
                return
            self.selected_cost_log_id = ""
            self.refresh_from_state()

    def _reset_current_editor(self):
        if self.log_tabs.currentIndex() == 0:
            self._new_run_log()
        elif self.log_tabs.currentIndex() == 1:
            self._new_fuel_log()
        else:
            self._new_cost_log()

    def _on_tab_changed(self, index: int):
        if not hasattr(self, "editor_stack"):
            return
        self.editor_stack.setCurrentIndex(index)
        if index == 0:
            if self.run_table.currentRow() >= 0:
                self._run_row_changed()
            else:
                self._new_run_log()
        elif index == 1:
            if self.fuel_table.currentRow() >= 0:
                self._fuel_row_changed()
            else:
                self._new_fuel_log()
        else:
            if self.cost_table.currentRow() >= 0:
                self._cost_row_changed()
            else:
                self._new_cost_log()
