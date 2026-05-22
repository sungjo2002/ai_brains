from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QDate, QRegularExpression, QSettings, QTimer
from PySide6.QtGui import QColor, QBrush, QPixmap, QRegularExpressionValidator
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QScrollArea,
    QTableWidget,
    QTextEdit,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)

from .state import STATUS_TYPES
from .table_column_manager import install_resizable_table_columns, schedule_table_column_fit
from .widgets import MiniMetricCard, Panel, StatCard, PAGE_OUTER_MARGINS, PAGE_OUTER_SPACING, PAGE_INNER_MARGINS, PAGE_INNER_SPACING
from .icons import get_svg_icon, get_qicon

NATIONS = ["대한민국", "베트남", "태국", "중국", "네팔", "캄보디아", "인도네시아", "필리핀"]
WORK_TYPES = ["주간", "야간", "교대"]
PAY_TYPES = ["월급제", "일급제", "시급제"]
BANK_OPTIONS = [
    "은행 선택",
    "국민은행",
    "신한은행",
    "우리은행",
    "하나은행",
    "농협은행",
    "기업은행",
    "SC제일은행",
    "씨티은행",
    "대구은행",
    "부산은행",
    "경남은행",
    "광주은행",
    "전북은행",
    "제주은행",
    "수협은행",
    "새마을금고",
    "신협",
    "우체국",
    "카카오뱅크",
    "케이뱅크",
    "토스뱅크",
    "직접입력",
]
STATUS_COLORS = {
    "근무중": ("#ECFDF5", "#10B981"),
    "출근전": ("#FFFBEB", "#F59E0B"),
    "퇴근": ("#F9FAFB", "#6B7280"),
    "지각": ("#FFFBEB", "#F59E0B"),
    "병원": ("#F5F3FF", "#8B5CF6"),
    "결근": ("#FEF2F2", "#EF4444"),
    "무단결근": ("#FFF1F2", "#E11D48"),
    "무단이탈": ("#FFF7ED", "#F97316"),
    "휴무": ("#F9FAFB", "#6B7280"),
    "퇴사": ("#FEF2F2", "#EF4444"),
}

ALL_STATUS_FILTER_LABEL = "전체상태"



def _parse_base_wage_input(raw_text) -> tuple[bool, float, str]:
    """기본급/급여금액 입력값을 검증합니다. 빈칸은 허용하고, 입력된 경우 숫자만 허용합니다."""
    text = str(raw_text or "").strip().replace(",", "")
    if not text:
        return True, 0.0, ""
    if text.startswith("-"):
        return False, 0.0, "기본급은 0 이상으로 입력해 주세요."
    if any(not ch.isdigit() for ch in text):
        return False, 0.0, "기본급은 숫자와 쉼표만 입력해 주세요."
    try:
        value = float(text)
    except ValueError:
        return False, 0.0, "기본급은 숫자만 입력해 주세요."
    if value < 0:
        return False, 0.0, "기본급은 0 이상으로 입력해 주세요."
    return True, value, ""

PAYROLL_TREATMENT_OPTIONS = ["근무", "결근", "휴무"]
PAYROLL_HOURS_MODE_OPTIONS = ["기본시간 적용", "0시간", "절반 적용", "수동 조정"]
SHIFT_GROUP_OPTIONS = ["주간", "야간"]
SEVERANCE_METHOD_OPTIONS = [
    ("두 방식 모두 표시", "both"),
    ("법정 계산식만", "legal"),
    ("고정 합의 방식만", "fixed"),
]

class ResignEmployeeDialog(QDialog):
    def __init__(self, employee_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("퇴사 처리")
        self.setModal(True)
        self.setFixedWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        guide = QLabel(f"{employee_name} 퇴사 정보를 입력해 주세요.")
        guide.setWordWrap(True)
        layout.addWidget(guide)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        form.setHorizontalSpacing(6)
        form.setVerticalSpacing(6)

        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.end_date_edit.setDate(QDate.currentDate())
        form.addRow("퇴사일", self.end_date_edit)

        self.reason_combo = QComboBox()
        self.reason_combo.setEditable(True)
        self.reason_combo.addItems(["일반 퇴사", "계약만료", "개인사정", "무단결근", "무단이탈", "연락두절"])
        self.reason_combo.setCurrentText("일반 퇴사")
        form.addRow("퇴사 사유", self.reason_combo)

        self.note_edit = QTextEdit()
        self.note_edit.setPlaceholderText("필요하면 참고 메모를 입력하세요.")
        self.note_edit.setMinimumHeight(88)
        form.addRow("비고", self.note_edit)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("퇴사 처리")
        buttons.button(QDialogButtonBox.Cancel).setText("취소")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self):
        if not self.reason():
            QMessageBox.information(self, "퇴사 처리", "퇴사 사유를 입력해 주세요.")
            return
        self.accept()

    def resign_date(self) -> str:
        return self.end_date_edit.date().toString("yyyy-MM-dd")

    def reason(self) -> str:
        return self.reason_combo.currentText().strip()

    def note(self) -> str:
        return self.note_edit.toPlainText().strip()


PERSONAL_PAYROLL_SETTING_DEFS = [
    {"group": "개인 기준", "key": "work_type", "label": "개인 근무형태", "kind": "choice", "options": WORK_TYPES},
    {"group": "개인 기준", "key": "pay_type", "label": "개인 급여형태", "kind": "choice", "options": PAY_TYPES},
    {"group": "근무/교대", "key": "day_start", "label": "주간 시작 시각", "kind": "text"},
    {"group": "근무/교대", "key": "day_end", "label": "주간 종료 시각", "kind": "text"},
    {"group": "근무/교대", "key": "night_start", "label": "야간 시작 시각", "kind": "text"},
    {"group": "근무/교대", "key": "night_end", "label": "야간 종료 시각", "kind": "text"},
    {"group": "근무/교대", "key": "shift_start_group", "label": "교대 시작 그룹", "kind": "choice", "options": SHIFT_GROUP_OPTIONS},
    {"group": "급여 기준", "key": "day_hourly_rate", "label": "주간 시급 (원)", "kind": "number"},
    {"group": "급여 기준", "key": "night_hourly_rate", "label": "야간 시급 (원)", "kind": "number"},
    {"group": "급여 기준", "key": "night_multiplier", "label": "야간 수당 배율", "kind": "number"},
    {"group": "급여 기준", "key": "attendance_base_hours", "label": "기본 시간 (시간)", "kind": "number"},
    {"group": "급여 기준", "key": "attendance_over_hours", "label": "연장 시간 (시간)", "kind": "number"},
    {"group": "급여 기준", "key": "attendance_night_hours", "label": "심야 시간 (시간)", "kind": "number"},
    {"group": "공제/퇴직", "key": "late_deduct", "label": "지각 1회 차감 (원)", "kind": "number"},
    {"group": "공제/퇴직", "key": "absent_deduct", "label": "결근 1일 차감 (원)", "kind": "number"},
    {"group": "공제/퇴직", "key": "unauthorized_absence_deduct", "label": "무단결근 차감 (원)", "kind": "number"},
    {"group": "공제/퇴직", "key": "default_meal_deduct", "label": "식대 공제 기본값 (원)", "kind": "number"},
    {"group": "공제/퇴직", "key": "severance_method", "label": "퇴직금 방식", "kind": "choice", "options": SEVERANCE_METHOD_OPTIONS},
    {"group": "공제/퇴직", "key": "severance_multiplier", "label": "퇴직금 배율", "kind": "number"},
    {"group": "상태 처리", "key": "hospital_payroll_treatment", "label": "병원 급여 처리", "kind": "choice", "options": PAYROLL_TREATMENT_OPTIONS},
    {"group": "상태 처리", "key": "hospital_hours_mode", "label": "병원 시간 처리", "kind": "choice", "options": PAYROLL_HOURS_MODE_OPTIONS},
    {"group": "상태 처리", "key": "hospital_note", "label": "병원 메모", "kind": "text"},
    {"group": "상태 처리", "key": "late_payroll_treatment", "label": "지각 급여 처리", "kind": "choice", "options": PAYROLL_TREATMENT_OPTIONS},
    {"group": "상태 처리", "key": "late_hours_mode", "label": "지각 시간 처리", "kind": "choice", "options": PAYROLL_HOURS_MODE_OPTIONS},
    {"group": "상태 처리", "key": "late_note", "label": "지각 메모", "kind": "text"},
    {"group": "상태 처리", "key": "early_leave_payroll_treatment", "label": "조퇴 급여 처리", "kind": "choice", "options": PAYROLL_TREATMENT_OPTIONS},
    {"group": "상태 처리", "key": "early_leave_hours_mode", "label": "조퇴 시간 처리", "kind": "choice", "options": PAYROLL_HOURS_MODE_OPTIONS},
    {"group": "상태 처리", "key": "early_leave_note", "label": "조퇴 메모", "kind": "text"},
]

ITEM_GROUP_TITLES = {
    "allowance": "개인 수당 항목",
    "deduction": "개인 공제 항목",
}


class EmployeeDetailDialog(QDialog):
    request_document_edit = Signal(int)
    _raw_photo_cache: dict[tuple[str, int], QPixmap] = {}
    _scaled_photo_cache: dict[tuple[str, int, int, int], QPixmap] = {}

    def __init__(self, state, employee: dict, parent=None):
        super().__init__(parent)
        self.state = state
        self.employee = deepcopy(employee)
        self.setWindowTitle("근로자 상세 / 수정")
        self.setModal(True)
        self._collapsed_width = 700
        self._expanded_width = 1120
        self.resize(self._collapsed_width, 560)

        self.personal_setting_widgets: dict[str, dict] = {}
        self.personal_item_widgets: dict[str, dict] = {}
        self._loaded_setting_override_keys: set[str] = set()
        self._loaded_item_override_keys: set[str] = set()
        self._document_edit_requested = False

        root = QHBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        left_widget = QWidget()
        left_root = QVBoxLayout(left_widget)
        left_root.setContentsMargins(0, 0, 0, 0)
        left_root.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(6)

        photo_box = QFrame()
        photo_box.setObjectName("Panel")
        photo_layout = QVBoxLayout(photo_box)
        photo_layout.setContentsMargins(6, 6, 6, 6)
        photo_layout.setSpacing(6)
        photo_title = QLabel("여권 사진")
        photo_title.setObjectName("StatBadge")
        self.photo_label = QLabel("사진 없음")
        self.photo_label.setObjectName("DetailPhotoLabel")
        self.photo_label.setAlignment(Qt.AlignCenter)
        self.photo_label.setFixedSize(112, 140)
        self.photo_label.setAttribute(Qt.WA_StaticContents, True)
        photo_layout.addWidget(photo_title)
        photo_layout.addWidget(self.photo_label, alignment=Qt.AlignCenter)
        top.addWidget(photo_box, 0, Qt.AlignTop)

        title_box = QVBoxLayout()
        title = QLabel(f'{self.employee.get("name", "-")} 상세 정보')
        title.setObjectName("DetailTitle")
        subtitle = QLabel("공용 상태에 저장되며 홈 / 근태 / 근로자 등록 화면과 같은 데이터를 공유합니다.")
        subtitle.setObjectName("DetailSub")
        subtitle.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        document_edit_row = QHBoxLayout()
        document_edit_row.setContentsMargins(0, 0, 0, 0)
        document_edit_row.addStretch(1)
        self.document_edit_btn = QPushButton("사진/문서 수정")
        self.document_edit_btn.setObjectName("GhostButton")
        self.document_edit_btn.setToolTip("근로자 등록 화면의 사진/OCR 처리 흐름으로 현재 사진과 문서를 다시 수정합니다.")
        self.document_edit_btn.clicked.connect(self._request_document_edit)
        document_edit_row.addWidget(self.document_edit_btn, 0, Qt.AlignRight)
        title_box.addLayout(document_edit_row)

        top.addLayout(title_box, 1)
        left_root.addLayout(top)

        self._load_portrait()

        form = QGridLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(6)
        form.setVerticalSpacing(6)
        form.setColumnStretch(1, 1)
        form.setColumnStretch(3, 1)

        def _fit_field(widget: QWidget, width: int = 220):
            widget.setMinimumHeight(30)
            widget.setMaximumWidth(width)
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        def _add_pair(row: int, left_label: str, left_widget: QWidget, right_label: str, right_widget: QWidget):
            left = QLabel(left_label)
            right = QLabel(right_label)
            left.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            right.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            form.addWidget(left, row, 0)
            form.addWidget(left_widget, row, 1)
            form.addWidget(right, row, 2)
            form.addWidget(right_widget, row, 3)

        self._internal_employee_id = int(self.employee.get("id", 0) or 0)
        display_no = self.state.employee_display_number(self.employee) if hasattr(self.state, "employee_display_number") else str(self._internal_employee_id)
        self.id_edit = QLineEdit(display_no)
        self.id_edit.setReadOnly(True)
        self.name_edit = QLineEdit(self.employee.get("name", ""))
        self.english_name_edit = QLineEdit(str(self.employee.get("english_name") or self.employee.get("name_english") or ""))
        self.english_name_edit.setPlaceholderText("영문이름")
        self.nation_combo = QComboBox()
        self.nation_combo.setEditable(True)
        self.nation_combo.addItems(NATIONS)
        self.nation_combo.setCurrentText(self.employee.get("nation", "대한민국"))

        self.business_edit = QComboBox()
        self.business_edit.setEditable(True)
        for b in self.state.business_master_records():
            if b.get("name"):
                self.business_edit.addItem(b["name"])
        self.business_edit.setCurrentText(self.employee.get("affiliated_business", ""))

        # 예전 저장 호환용 필드입니다. 화면에는 표시하지 않고 근무 사업장 값과 동기화합니다.
        self.company_edit = QLineEdit(self.employee.get("company", "") or self.employee.get("work_site", ""))
        self.company_edit.hide()

        self.site_edit = QComboBox()
        self.site_edit.setEditable(True)
        for s in self.state.work_site_records():
            if s.get("name"):
                self.site_edit.addItem(s["name"])
        self.site_edit.setCurrentText(self.employee.get("work_site", ""))

        self.work_type_combo = QComboBox()
        self.work_type_combo.addItems(WORK_TYPES)
        self.work_type_combo.setCurrentText(self.employee.get("work_type", WORK_TYPES[0]))
        self.pay_type_combo = QComboBox()
        self.pay_type_combo.addItems(PAY_TYPES)
        self.pay_type_combo.setCurrentText(self.employee.get("pay_type", PAY_TYPES[0]))

        self.base_wage_edit = QLineEdit()
        self.base_wage_edit.setValidator(QRegularExpressionValidator(QRegularExpression(r"^[0-9,]*$"), self.base_wage_edit))
        self.bank_name_combo = QComboBox()
        self.bank_name_combo.setEditable(True)
        self.bank_name_combo.setInsertPolicy(QComboBox.NoInsert)
        self.bank_name_combo.addItems(BANK_OPTIONS)
        bank_name = str(self.employee.get("bank_name") or self.employee.get("bank") or "").strip()
        self.bank_name_combo.setCurrentText(bank_name or "은행 선택")
        if self.bank_name_combo.lineEdit() is not None:
            self.bank_name_combo.lineEdit().setPlaceholderText("은행 선택/입력")
        self.bank_account_edit = QLineEdit(str(self.employee.get("bank_account") or self.employee.get("account_number") or ""))
        self.bank_account_edit.setValidator(QRegularExpressionValidator(QRegularExpression(r"^[0-9\-]*$"), self.bank_account_edit))
        self.bank_account_edit.setPlaceholderText("계좌번호")
        raw_wage = self.employee.get("base_wage", "")
        self.base_wage_edit.setPlaceholderText("급여금액")
        if str(raw_wage or "").strip():
            current_wage = float(raw_wage or 0)
            self.base_wage_edit.setText(f"{int(current_wage)}" if current_wage.is_integer() else f"{current_wage}")
        else:
            self.base_wage_edit.clear()

        def _date_from_employee(*keys: str) -> QDate:
            for key in keys:
                raw_value = str(self.employee.get(key) or "").strip()
                if not raw_value:
                    continue
                parsed = QDate.fromString(raw_value, "yyyy-MM-dd")
                if parsed.isValid():
                    return parsed
            return QDate.currentDate()

        self.work_site_move_date_edit = QDateEdit()
        self.work_site_move_date_edit.setCalendarPopup(True)
        self.work_site_move_date_edit.setDate(_date_from_employee("work_site_move_date", "hire_date"))
        self.work_site_move_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.work_site_move_date_edit.setToolTip("사업자, 근무 사업장, 근무 형태를 변경할 때 적용할 이동 시작일입니다.")

        self.pay_change_date_edit = QDateEdit()
        self.pay_change_date_edit.setCalendarPopup(True)
        self.pay_change_date_edit.setDate(_date_from_employee("pay_change_date", "pay_effective_date", "hire_date"))
        self.pay_change_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.pay_change_date_edit.setToolTip("급여형태 또는 급여금액을 변경할 때 적용할 변경일입니다.")

        self.status_combo = QComboBox()
        self.status_combo.addItems(STATUS_TYPES)
        self.status_combo.setCurrentText(self.employee.get("status", STATUS_TYPES[0]))

        for widget in [
            self.id_edit,
            self.name_edit,
            self.english_name_edit,
            self.nation_combo,
            self.business_edit,
            self.site_edit,
            self.base_wage_edit,
            self.bank_name_combo,
            self.bank_account_edit,
            self.work_site_move_date_edit,
            self.pay_change_date_edit,
            self.status_combo,
        ]:
            _fit_field(widget)

        _add_pair(0, "사번", self.id_edit, "상태", self.status_combo)
        _add_pair(1, "이름", self.name_edit, "영문이름", self.english_name_edit)
        _add_pair(2, "국적", self.nation_combo, "사업자", self.business_edit)
        _add_pair(3, "근무 사업장", self.site_edit, "근무사업장 이동일", self.work_site_move_date_edit)
        _add_pair(4, "급여 변경일", self.pay_change_date_edit, "개인 급여금액", self.base_wage_edit)
        _add_pair(5, "은행", self.bank_name_combo, "계좌번호", self.bank_account_edit)
        left_root.addLayout(form)

        note = QLabel("근무형태와 급여형태는 오른쪽 개인별 설정에서 체크한 경우 개인값으로 적용됩니다. 체크하지 않으면 공장 기본값을 따릅니다.")
        note.setObjectName("SectionSub")
        left_root.addWidget(note)

        buttons = QDialogButtonBox()
        cancel_btn = QPushButton("취소")
        cancel_btn.setObjectName("GhostButton")
        save_btn = QPushButton("저장")
        save_btn.setObjectName("PrimaryButton")
        buttons.addButton(cancel_btn, QDialogButtonBox.RejectRole)
        buttons.addButton(save_btn, QDialogButtonBox.AcceptRole)
        cancel_btn.clicked.connect(self.reject)
        save_btn.clicked.connect(self._validate)
        left_root.addWidget(buttons)

        root.addWidget(left_widget, 1)

        self.personal_toggle_btn = QPushButton("설\n정\n>")
        self.personal_toggle_btn.setObjectName("PersonalToggleButton")
        self.personal_toggle_btn.setCheckable(True)
        self.personal_toggle_btn.setCursor(Qt.PointingHandCursor)
        self.personal_toggle_btn.setToolTip("개인설정")
        self.personal_toggle_btn.setFixedWidth(18)
        self.personal_toggle_btn.setMinimumHeight(150)
        self.personal_toggle_btn.setMaximumHeight(190)
        self.personal_toggle_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.personal_toggle_btn.clicked.connect(self._toggle_personal_panel)
        root.addWidget(self.personal_toggle_btn, 0, Qt.AlignVCenter)

        self.personal_panel = Panel("개인별 설정", "근무형태와 급여형태도 개인값으로 지정할 수 있습니다. 체크하지 않은 항목은 공장 기본값을 따릅니다.")
        self.personal_panel.setFixedWidth(452)
        self.personal_panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.personal_panel.body_layout.setContentsMargins(6, 6, 6, 6)
        self.personal_panel.body_layout.setSpacing(6)
        self.personal_panel.header.layout().setContentsMargins(6, 6, 6, 6)

        control_row = QHBoxLayout()
        control_row.setContentsMargins(0, 0, 0, 0)
        control_row.setSpacing(6)
        self.personal_enabled_check = QCheckBox("개인설정 사용")
        self.personal_enabled_check.stateChanged.connect(self._update_personal_panel_state)
        self.personal_status_label = QLabel("공장값 사용 중")
        self.personal_status_label.setObjectName("PanelNote")
        clear_btn = QPushButton("전체 해제")
        clear_btn.setObjectName("GhostButton")
        clear_btn.setFixedHeight(30)
        clear_btn.clicked.connect(self._clear_personal_overrides)
        control_row.addWidget(self.personal_enabled_check)
        control_row.addStretch(1)
        control_row.addWidget(self.personal_status_label)
        control_row.addWidget(clear_btn)
        self.personal_panel.body_layout.addLayout(control_row)

        table_head = QHBoxLayout()
        table_head.setContentsMargins(0, 0, 0, 0)
        table_head.setSpacing(6)
        for text, width in [("", 20), ("항목", 124), ("공장값", 78), ("개인값", 148)]:
            label = QLabel(text)
            label.setObjectName("PanelNote")
            if width > 0:
                label.setFixedWidth(width)
            table_head.addWidget(label)
        table_head.addStretch(1)
        self.personal_panel.body_layout.addLayout(table_head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_body = QWidget()
        self.personal_scroll_layout = QVBoxLayout(scroll_body)
        self.personal_scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.personal_scroll_layout.setSpacing(6)
        scroll.setWidget(scroll_body)
        self.personal_panel.body_layout.addWidget(scroll, 1)

        self._build_personal_settings_ui()
        root.addWidget(self.personal_panel, 0)
        self.personal_panel.hide()

        self.business_edit.currentTextChanged.connect(self._refresh_personal_defaults)
        self.site_edit.currentTextChanged.connect(self._refresh_personal_defaults)
        self.site_edit.currentTextChanged.connect(lambda text: self.company_edit.setText(text))

        self._load_personal_settings_from_employee()
        self._refresh_personal_defaults()
        self._update_personal_panel_state()
        if self.personal_enabled_check.isChecked() or self._checked_personal_count() > 0:
            self._toggle_personal_panel(force_open=True)

    def _request_document_edit(self):
        self._document_edit_requested = True
        self.request_document_edit.emit(int(self._internal_employee_id or self.employee.get("id", 0) or 0))
        self.reject()

    def document_edit_requested(self) -> bool:
        return bool(self._document_edit_requested)

    def _build_personal_settings_ui(self):
        current_group = None
        for spec in PERSONAL_PAYROLL_SETTING_DEFS:
            group_name = str(spec.get("group", ""))
            if group_name != current_group:
                self.personal_scroll_layout.addWidget(self._section_label(group_name))
                current_group = group_name
            row = self._create_setting_override_row(spec)
            self.personal_scroll_layout.addWidget(row)

        current_item_group = None
        for row in self._current_payroll_detail_items():
            group = str(row.get("group", "") or "")
            title = ITEM_GROUP_TITLES.get(group, group)
            if title and title != current_item_group:
                self.personal_scroll_layout.addWidget(self._section_label(title))
                current_item_group = title
            item_row = self._create_item_override_row(row)
            self.personal_scroll_layout.addWidget(item_row)
        self.personal_scroll_layout.addStretch(1)

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("PanelTitle")
        label.setStyleSheet("font-size: 13px; font-weight: 800; padding: 6px 0 0 0;")
        return label

    def _create_setting_override_row(self, spec: dict) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        check = QCheckBox()
        check.setFixedWidth(20)
        check.stateChanged.connect(self._update_personal_panel_state)

        name_label = QLabel(str(spec.get("label", "")))
        name_label.setFixedWidth(124)
        name_label.setWordWrap(False)
        name_label.setToolTip(str(spec.get("label", "")))
        name_label.setStyleSheet("font-size: 12px; font-weight: 600;")

        default_label = QLabel("-")
        default_label.setObjectName("PanelNote")
        default_label.setFixedWidth(78)
        default_label.setWordWrap(False)
        default_label.setStyleSheet("font-size: 12px; font-weight: 600;")

        editor = self._create_override_editor(spec)
        editor.setMinimumHeight(30)
        layout.addWidget(check)
        layout.addWidget(name_label)
        layout.addWidget(default_label)
        layout.addWidget(editor, 1)

        row.setMinimumHeight(30)

        key = str(spec.get("key", ""))
        self.personal_setting_widgets[key] = {
            "spec": spec,
            "check": check,
            "default_label": default_label,
            "editor": editor,
        }
        return row

    def _create_item_override_row(self, item: dict) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        check = QCheckBox()
        check.setFixedWidth(20)
        check.stateChanged.connect(self._update_personal_panel_state)

        name_label = QLabel(str(item.get("label", item.get("key", ""))))
        name_label.setFixedWidth(124)
        name_label.setWordWrap(False)
        name_label.setToolTip(str(item.get("label", item.get("key", ""))))
        name_label.setStyleSheet("font-size: 12px; font-weight: 600;")

        default_label = QLabel("-")
        default_label.setObjectName("PanelNote")
        default_label.setFixedWidth(78)
        default_label.setWordWrap(False)
        default_label.setStyleSheet("font-size: 12px; font-weight: 600;")

        editor = QLineEdit()
        editor.setPlaceholderText("개인값")
        editor.setMinimumHeight(30)

        layout.addWidget(check)
        layout.addWidget(name_label)
        layout.addWidget(default_label)
        layout.addWidget(editor, 1)

        row.setMinimumHeight(30)

        key = str(item.get("key", ""))
        self.personal_item_widgets[key] = {
            "item": deepcopy(item),
            "check": check,
            "default_label": default_label,
            "editor": editor,
            "label": str(item.get("label", key)),
        }
        return row

    def _create_override_editor(self, spec: dict):
        kind = str(spec.get("kind", "text"))
        if kind == "choice":
            combo = QComboBox()
            for option in spec.get("options", []):
                if isinstance(option, tuple):
                    combo.addItem(str(option[0]), option[1])
                else:
                    combo.addItem(str(option), option)
            combo.setMinimumHeight(30)
            return combo
        if kind == "date":
            edit = QDateEdit()
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("yyyy-MM-dd")
            edit.setDate(QDate.currentDate())
            edit.setMinimumHeight(30)
            return edit
        edit = QLineEdit()
        if kind == "number":
            edit.setPlaceholderText("숫자")
        else:
            edit.setPlaceholderText("개인값")
        edit.setMinimumHeight(30)
        return edit

    def _resize_photo_box(self, pixmap: QPixmap):
        if pixmap.isNull():
            return
        img_w = pixmap.width()
        img_h = pixmap.height()
        if img_w <= 0 or img_h <= 0:
            return
        max_w, max_h = 130, 170
        min_w, min_h = 90, 110
        scale = min(max_w / img_w, max_h / img_h)
        box_w = max(min_w, int(img_w * scale))
        box_h = max(min_h, int(img_h * scale))
        self.photo_label.setFixedSize(min(max_w, box_w), min(max_h, box_h))

    def _photo_mtime_key(self, portrait_path: str) -> int:
        try:
            return int(Path(portrait_path).stat().st_mtime_ns)
        except Exception:
            return 0

    def _load_portrait_pixmap_cached(self, portrait_path: str, mtime_key: int) -> QPixmap:
        cache_key = (portrait_path, mtime_key)
        cached = self._raw_photo_cache.get(cache_key)
        if cached is None:
            loaded = QPixmap(portrait_path)
            cached = loaded if not loaded.isNull() else QPixmap()
            self._raw_photo_cache[cache_key] = cached
        return cached

    def _scaled_portrait_pixmap_cached(self, portrait_path: str, mtime_key: int, width: int, height: int) -> QPixmap:
        cache_key = (portrait_path, mtime_key, width, height)
        cached = self._scaled_photo_cache.get(cache_key)
        if cached is None:
            raw = self._load_portrait_pixmap_cached(portrait_path, mtime_key)
            cached = raw.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation) if not raw.isNull() else QPixmap()
            self._scaled_photo_cache[cache_key] = cached
        return cached

    def _load_portrait(self):
        portrait_raw = str(self.employee.get("portrait_path", "") or "").strip()
        portrait_path = self.state.resolve_storage_file_path(portrait_raw)
        if not portrait_path:
            target_path, _rel = self.state.get_employee_portrait_storage_path(self.employee.get("id", ""), ".png")
            portrait_path = str(target_path) if target_path.exists() else ""
        if portrait_path and Path(portrait_path).exists():
            mtime_key = self._photo_mtime_key(portrait_path)
            raw = self._load_portrait_pixmap_cached(portrait_path, mtime_key)
            if not raw.isNull():
                self._resize_photo_box(raw)
                scaled = self._scaled_portrait_pixmap_cached(
                    portrait_path,
                    mtime_key,
                    max(1, self.photo_label.width()),
                    max(1, self.photo_label.height()),
                )
                if not scaled.isNull():
                    self.photo_label.setPixmap(scaled)
                    self.photo_label.setText("")
                    return

    def _load_personal_settings_from_employee(self):
        enabled = bool(self.employee.get("individual_payroll_enabled", False))
        field_overrides = self.employee.get("individual_payroll_field_overrides") or {}
        item_overrides = self.employee.get("individual_payroll_item_overrides") or {}

        self.personal_enabled_check.setChecked(enabled)

        factory_settings = self._current_payroll_settings()
        for key, bundle in self.personal_setting_widgets.items():
            raw = field_overrides.get(key)
            checked, value = self._decode_override(raw)
            if key in {"work_type", "pay_type"} and raw in (None, ""):
                employee_value = str(self.employee.get(key, "") or "").strip()
                factory_value = str(factory_settings.get(key, "") or "").strip()
                if employee_value and employee_value != factory_value:
                    checked = True
                    value = employee_value
            bundle["check"].setChecked(checked)
            if checked:
                self._loaded_setting_override_keys.add(key)
            self._set_editor_value(bundle["editor"], bundle["spec"], value)

        for key, bundle in self.personal_item_widgets.items():
            raw = item_overrides.get(key)
            checked, value = self._decode_override(raw)
            bundle["check"].setChecked(checked)
            if checked:
                self._loaded_item_override_keys.add(key)
            self._set_item_editor_value(bundle["editor"], value)

    def _decode_override(self, raw) -> tuple[bool, object]:
        if isinstance(raw, dict):
            return bool(raw.get("enabled", False)), raw.get("value")
        if raw in (None, ""):
            return False, None
        return True, raw

    def _current_business_name(self) -> str:
        return self.business_edit.currentText().strip()

    def _current_site_name(self) -> str:
        return self.site_edit.currentText().strip() or self.company_edit.text().strip()

    def _current_payroll_settings(self) -> dict:
        return self.state.get_payroll_settings(self._current_site_name(), self._current_business_name() or None)

    def _current_payroll_detail_items(self) -> list[dict]:
        rows = self.state.get_payroll_detail_item_configs(self._current_site_name(), self._current_business_name() or None)
        return [row for row in rows if row.get("enabled", True) and row.get("group") in {"allowance", "deduction"}]

    def _refresh_personal_defaults(self):
        settings = self._current_payroll_settings()
        for key, bundle in self.personal_setting_widgets.items():
            spec = bundle["spec"]
            default_value = settings.get(key)
            bundle["default_label"].setText(self._format_default_text(default_value, spec))
            if key not in self._loaded_setting_override_keys:
                self._set_editor_default_if_empty(bundle["editor"], spec, default_value)

        item_defaults = {str(row.get("key", "")): row for row in self._current_payroll_detail_items()}
        for key, bundle in self.personal_item_widgets.items():
            row = item_defaults.get(key, bundle.get("item", {}))
            default_value = row.get("default_value", 0)
            bundle["default_label"].setText(self._format_number(default_value))
            if key not in self._loaded_item_override_keys and not bundle["editor"].text().strip():
                bundle["editor"].setText(self._format_number(default_value))
        self._update_personal_panel_state()

    def _toggle_personal_panel(self, force_open: bool | None = None):
        target_open = (not self.personal_panel.isVisible()) if force_open is None else bool(force_open)
        self.personal_panel.setVisible(target_open)
        self.personal_toggle_btn.blockSignals(True)
        self.personal_toggle_btn.setChecked(target_open)
        self.personal_toggle_btn.blockSignals(False)
        self.personal_toggle_btn.setText("<\n닫\n기" if target_open else "개\n인\n설\n정\n>")
        target_width = self._expanded_width if target_open else self._collapsed_width
        self.setMinimumWidth(target_width)
        self.resize(target_width, max(self.height(), 560))
        self.layout().activate()
        self.adjustSize()
        self.resize(target_width, max(self.height(), 560))
        self.updateGeometry()

    def _clear_personal_overrides(self):
        self.personal_enabled_check.setChecked(False)
        for key, bundle in self.personal_setting_widgets.items():
            bundle["check"].setChecked(False)
            self._loaded_setting_override_keys.discard(key)
        for key, bundle in self.personal_item_widgets.items():
            bundle["check"].setChecked(False)
            self._loaded_item_override_keys.discard(key)
        self._refresh_personal_defaults()
        self._update_personal_panel_state()

    def _checked_personal_count(self) -> int:
        count = 0
        count += sum(1 for bundle in self.personal_setting_widgets.values() if bundle["check"].isChecked())
        count += sum(1 for bundle in self.personal_item_widgets.values() if bundle["check"].isChecked())
        return count

    def _update_personal_panel_state(self):
        enabled = self.personal_enabled_check.isChecked()
        for bundle in self.personal_setting_widgets.values():
            check = bundle["check"]
            editor = bundle["editor"]
            check.setEnabled(enabled)
            editor.setEnabled(enabled and check.isChecked())
        for bundle in self.personal_item_widgets.values():
            check = bundle["check"]
            editor = bundle["editor"]
            check.setEnabled(enabled)
            editor.setEnabled(enabled and check.isChecked())
        count = self._checked_personal_count() if enabled else 0
        self.personal_status_label.setText(f"개인값 {count}개 적용" if enabled and count else ("개인설정 켜짐" if enabled else "공장값 사용 중"))

    def _set_editor_default_if_empty(self, editor, spec: dict, value):
        kind = str(spec.get("kind", "text"))
        if isinstance(editor, QLineEdit):
            if not editor.text().strip():
                editor.setText(self._format_default_text(value, spec))
        elif isinstance(editor, QComboBox):
            self._set_editor_value(editor, spec, value)
        elif isinstance(editor, QDateEdit):
            if value:
                self._set_editor_value(editor, spec, value)

    def _set_editor_value(self, editor, spec: dict, value):
        kind = str(spec.get("kind", "text"))
        if isinstance(editor, QComboBox):
            options = spec.get("options", [])
            for idx in range(editor.count()):
                data = editor.itemData(idx)
                text = editor.itemText(idx)
                if value == data or str(value or "") == str(text):
                    editor.setCurrentIndex(idx)
                    return
            if editor.count() > 0:
                editor.setCurrentIndex(0)
        elif isinstance(editor, QDateEdit):
            parsed = QDate.fromString(str(value or ""), "yyyy-MM-dd")
            editor.setDate(parsed if parsed.isValid() else QDate.currentDate())
        elif isinstance(editor, QLineEdit):
            if kind == "number":
                editor.setText(self._format_number(value))
            else:
                editor.setText(str(value or ""))

    def _set_item_editor_value(self, editor: QLineEdit, value):
        editor.setText(self._format_number(value))

    def _editor_value(self, editor, spec: dict):
        kind = str(spec.get("kind", "text"))
        if isinstance(editor, QComboBox):
            return editor.itemData(editor.currentIndex()) or editor.currentText()
        if isinstance(editor, QDateEdit):
            return editor.date().toString("yyyy-MM-dd")
        raw = editor.text().strip()
        if kind == "number":
            return self._parse_number(raw, allow_empty=True)
        return raw

    def _item_editor_value(self, editor: QLineEdit):
        return self._parse_number(editor.text().strip(), allow_empty=True)

    def _parse_number(self, raw: str, allow_empty: bool = False):
        text = str(raw or "").strip().replace(",", "")
        if not text:
            return None if allow_empty else 0.0
        value = float(text)
        return int(value) if float(value).is_integer() else value

    def _format_number(self, value) -> str:
        if value in (None, ""):
            return ""
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
        return f"{int(number):,}" if number.is_integer() else f"{number:,}"

    def _format_default_text(self, value, spec: dict) -> str:
        kind = str(spec.get("kind", "text"))
        if kind == "number":
            return self._format_number(value)
        if kind == "choice":
            options = spec.get("options", [])
            for option in options:
                if isinstance(option, tuple):
                    if option[1] == value or str(option[1]) == str(value):
                        return str(option[0])
                elif str(option) == str(value):
                    return str(option)
        return str(value or "-")

    def _collect_personal_override_payload(self) -> tuple[bool, dict, dict]:
        enabled = self.personal_enabled_check.isChecked()
        field_payload: dict[str, dict] = {}
        item_payload: dict[str, dict] = {}
        for key, bundle in self.personal_setting_widgets.items():
            checked = bundle["check"].isChecked()
            value = self._editor_value(bundle["editor"], bundle["spec"])
            field_payload[key] = {"enabled": bool(enabled and checked), "value": value}
        for key, bundle in self.personal_item_widgets.items():
            checked = bundle["check"].isChecked()
            value = self._item_editor_value(bundle["editor"])
            item_payload[key] = {
                "enabled": bool(enabled and checked),
                "value": value,
                "label": bundle.get("label", key),
                "group": bundle.get("item", {}).get("group", ""),
            }
        return enabled, field_payload, item_payload

    def _current_base_wage_value(self) -> float:
        valid, base_wage, _message = _parse_base_wage_input(self.base_wage_edit.text())
        return base_wage if valid else 0.0

    @staticmethod
    def _clean_compare_text(value) -> str:
        return str(value or "").strip()

    def _active_personal_setting_value(self, key: str, fallback: str) -> str:
        bundle = self.personal_setting_widgets.get(key)
        if bundle and self.personal_enabled_check.isChecked() and bundle["check"].isChecked():
            value = self._editor_value(bundle["editor"], bundle["spec"])
            return str(value or fallback or "").strip() or str(fallback or "").strip()
        return str(fallback or "").strip()

    def _factory_setting_value(self, key: str, fallback: str) -> str:
        settings = self._current_payroll_settings()
        return str(settings.get(key, fallback) or fallback or "").strip()

    def _effective_work_type_value(self) -> str:
        fallback = self._factory_setting_value("work_type", self.employee.get("work_type", "교대") or "교대")
        return self._active_personal_setting_value("work_type", fallback) or "교대"

    def _effective_pay_type_value(self) -> str:
        fallback = self._factory_setting_value("pay_type", self.employee.get("pay_type", "시급제") or "시급제")
        return self._active_personal_setting_value("pay_type", fallback) or "시급제"

    def _work_info_changed(self) -> bool:
        previous_business = self._clean_compare_text(self.employee.get("affiliated_business") or self.employee.get("business"))
        previous_site = self._clean_compare_text(self.employee.get("work_site") or self.employee.get("company") or self.employee.get("department"))
        previous_work_type = self._clean_compare_text(self.employee.get("work_type"))
        return any([
            previous_business != self._clean_compare_text(self.business_edit.currentText()),
            previous_site != self._clean_compare_text(self.site_edit.currentText()),
            previous_work_type != self._clean_compare_text(self._effective_work_type_value()),
        ])

    def _pay_info_changed(self, base_wage: float) -> bool:
        previous_pay_type = self._clean_compare_text(self.employee.get("pay_type"))
        try:
            previous_wage = float(self.employee.get("base_wage", 0) or 0)
        except (TypeError, ValueError):
            previous_wage = 0.0
        return any([
            previous_pay_type != self._clean_compare_text(self._effective_pay_type_value()),
            abs(previous_wage - float(base_wage or 0)) > 0.0001,
        ])

    def _confirm_past_change_dates(self, base_wage: float) -> bool:
        today = QDate.currentDate()
        warning_items: list[str] = []

        if self._work_info_changed() and self.work_site_move_date_edit.date().toJulianDay() < today.toJulianDay():
            warning_items.append(
                f"- 근무사업장 이동일: {self.work_site_move_date_edit.date().toString('yyyy-MM-dd')}\n"
                "  사업자/근무 사업장/근무 형태 기준이 해당 날짜부터 적용됩니다."
            )

        if self._pay_info_changed(base_wage) and self.pay_change_date_edit.date().toJulianDay() < today.toJulianDay():
            warning_items.append(
                f"- 급여 변경일: {self.pay_change_date_edit.date().toString('yyyy-MM-dd')}\n"
                "  급여형태/급여금액 기준이 해당 날짜부터 적용됩니다."
            )

        if not warning_items:
            return True

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("과거 날짜 변경 확인")
        box.setText("오늘 이전 날짜로 변경하려고 합니다.")
        box.setInformativeText(
            "과거 날짜로 저장하면 해당 날짜 이후의 근무/급여 기준이 다시 적용될 수 있습니다.\n\n"
            + "\n\n".join(warning_items)
            + "\n\n계속 변경하시겠습니까?"
        )
        confirm_btn = box.addButton("확인", QMessageBox.AcceptRole)
        cancel_btn = box.addButton("아니요", QMessageBox.RejectRole)
        box.setDefaultButton(cancel_btn)
        box.exec()
        return box.clickedButton() == confirm_btn

    def _validate(self):
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "근로자 정보", "이름을 입력해 주세요.")
            return
        if not self.business_edit.currentText().strip():
            QMessageBox.warning(self, "근로자 정보", "사업자를 입력해 주세요.")
            return
        if not self.site_edit.currentText().strip():
            QMessageBox.warning(self, "근로자 정보", "근무 사업장을 입력해 주세요.")
            return
        valid_wage, base_wage, wage_message = _parse_base_wage_input(self.base_wage_edit.text())
        if not valid_wage:
            QMessageBox.warning(self, "근로자 정보", wage_message)
            return
        if not self._confirm_past_change_dates(base_wage):
            return
        try:
            for key, bundle in self.personal_setting_widgets.items():
                if not (self.personal_enabled_check.isChecked() and bundle["check"].isChecked()):
                    continue
                if str(bundle["spec"].get("kind", "")) == "number":
                    self._editor_value(bundle["editor"], bundle["spec"])
            for bundle in self.personal_item_widgets.values():
                if self.personal_enabled_check.isChecked() and bundle["check"].isChecked():
                    self._item_editor_value(bundle["editor"])
        except ValueError:
            QMessageBox.warning(self, "개인별 설정", "개인별 설정의 숫자 항목은 숫자만 입력해 주세요.")
            return
        self.accept()

    def get_employee_data(self) -> dict:
        status = self.status_combo.currentText().strip()
        updated = deepcopy(self.employee)
        personal_enabled, field_payload, item_payload = self._collect_personal_override_payload()
        updated.update({
            "id": int(self._internal_employee_id or self.employee.get("id", 0)),
            "name": self.name_edit.text().strip(),
            "english_name": self.english_name_edit.text().strip(),
            "nation": self.nation_combo.currentText().strip() or "대한민국",
            "affiliated_business": self.business_edit.currentText().strip(),
            "company": self.site_edit.currentText().strip(),
            "client": self.site_edit.currentText().strip(),
            "work_site": self.site_edit.currentText().strip(),
            "department": self.site_edit.currentText().strip(),
            "work_type": self._effective_work_type_value(),
            "pay_type": self._effective_pay_type_value(),
            "base_wage": _parse_base_wage_input(self.base_wage_edit.text())[1],
            "bank_name": "" if self.bank_name_combo.currentText().strip() == "은행 선택" else self.bank_name_combo.currentText().strip(),
            "bank": "" if self.bank_name_combo.currentText().strip() == "은행 선택" else self.bank_name_combo.currentText().strip(),
            "bank_account": self.bank_account_edit.text().strip(),
            "account_number": self.bank_account_edit.text().strip(),
            "work_site_move_date": self.work_site_move_date_edit.date().toString("yyyy-MM-dd"),
            "pay_change_date": self.pay_change_date_edit.date().toString("yyyy-MM-dd"),
            "pay_effective_date": self.pay_change_date_edit.date().toString("yyyy-MM-dd"),
            "status": status,
            "active": status != "퇴사",
            "individual_payroll_enabled": personal_enabled,
            "individual_payroll_field_overrides": field_payload,
            "individual_payroll_item_overrides": item_payload,
        })
        return updated


class EmployeePage(QWidget):
    request_registration = Signal()
    request_document_edit = Signal(int)

    def __init__(self, state):
        super().__init__()
        self.state = state
        self.employees = list(self.state.employees)
        self.filtered_employees: list[dict] = []
        self.selected_employee_id: int | None = None
        self.state.employees_changed.connect(self.refresh_table)

        root = QVBoxLayout(self)
        root.setContentsMargins(*PAGE_OUTER_MARGINS)
        root.setSpacing(PAGE_OUTER_SPACING)
        # 상단 고정 배너는 MainWindow에서 표시합니다.

        left_wrap = QWidget()
        left_wrap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        left_layout = QVBoxLayout(left_wrap)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        left_layout.addWidget(self._build_stats_panel())
        left_layout.addWidget(self._build_table_panel(), 1)

        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)
        right_layout.addWidget(self._build_summary_panel())
        right_layout.addStretch()

        right_scroll = QScrollArea()
        right_scroll.setWidget(right_container)
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.NoFrame)
        right_scroll.setMinimumWidth(320)
        right_scroll.setMaximumWidth(400)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        right_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        right_scroll.setStyleSheet("QScrollArea { background: transparent; }")

        self.body_splitter = QSplitter(Qt.Horizontal)
        self.body_splitter.setChildrenCollapsible(False)
        self.body_splitter.setHandleWidth(6)
        self.body_splitter.addWidget(left_wrap)
        self.body_splitter.addWidget(right_scroll)
        self.body_splitter.setStretchFactor(0, 1)
        self.body_splitter.setStretchFactor(1, 0)
        self.body_splitter.setSizes([980, 340])

        outer_frame = QFrame()
        outer_frame.setObjectName("ScrollPageOuterFrame")
        outer_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        outer_layout = QVBoxLayout(outer_frame)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(PAGE_INNER_SPACING)
        outer_layout.addWidget(self.body_splitter, 1)
        root.addWidget(outer_frame, 1)

        self._splitter_initialized = False
        self.refresh_table()

    def _build_hero(self):
        wrap = QFrame()
        wrap.setObjectName("EmployeeHero")
        wrap.setFixedHeight(78)
        layout = QHBoxLayout(wrap)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        texts = QVBoxLayout()
        texts.setSpacing(6)
        badge = QLabel("WORKER MANAGEMENT")
        badge.setObjectName("HeroBadge")
        title = QLabel("근로자 관리")
        title.setObjectName("HeroTitle")
        sub = QLabel("목록 중심으로 근로자 현황을 보고, 선택한 인원을 오른쪽에서 바로 확인합니다.")
        sub.setObjectName("HeroDesc")
        sub.setWordWrap(True)
        texts.addWidget(badge)
        texts.addWidget(title)
        texts.addWidget(sub)
        texts.addStretch()
        layout.addLayout(texts, 1)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        for text in ["목록 중심 운영", "상세 / 수정 연동"]:
            chip = QLabel(text)
            chip.setObjectName("HeroChip")
            chip.setAlignment(Qt.AlignCenter)
            chips.addWidget(chip, alignment=Qt.AlignVCenter)
        layout.addLayout(chips)
        return wrap

    def _build_stats_panel(self):
        panel = Panel("오늘의 근로자 현황", "상태 요약")
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        panel.setMaximumHeight(188)
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)
        self.total_card = StatCard("전체 근로자", "0명", "등록 인원", "#1D4ED8", "user", icon_background=False, icon_size=19, variant="employee_summary")
        self.work_card = StatCard("근무중", "0명", "현재 운영", "#10B981", "check_plain", icon_background=False, icon_size=19, variant="employee_summary")
        self.pre_card = StatCard("출근전", "0명", "출근 대기", "#F59E0B", "clock_plain", icon_background=False, icon_size=19, variant="employee_summary")
        self.resign_card = StatCard("퇴사", "0명", "퇴사 인원", "#EF4444", "x_plain", icon_background=False, icon_size=19, variant="employee_summary")
        for index, widget in enumerate([self.total_card, self.work_card, self.pre_card, self.resign_card]):
            widget.setFixedHeight(108)
            widget.clicked.connect(self._handle_stats_card_clicked)
            grid.addWidget(widget, 0, index)
        panel.body_layout.addLayout(grid)
        return panel

    def _build_table_panel(self):
        panel = Panel("근로자 목록", "운영형 목록")
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        controls = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("이름 / 영문이름 / 사업자 / 근무 사업장 검색")
        self.search_edit.textChanged.connect(self.refresh_table)
        controls.addWidget(self.search_edit, 1)

        self.status_filter = QComboBox()
        self.status_filter.addItems([ALL_STATUS_FILTER_LABEL] + STATUS_TYPES)
        self.status_filter.currentTextChanged.connect(self.refresh_table)
        controls.addWidget(self.status_filter)

        add_btn = QPushButton("근로자 등록")
        add_btn.setObjectName("PrimaryButton")
        add_btn.clicked.connect(self.open_registration_page)
        controls.addWidget(add_btn)

        panel.body_layout.addLayout(controls)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["번호", "이름", "영문이름", "국적", "사업자", "근무 사업장", "근무 형태", "상태"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setObjectName("EmployeeListTable")
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setMinimumHeight(220)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table.cellClicked.connect(self._handle_click)
        self.table.cellDoubleClicked.connect(lambda *_: self.open_employee_detail())
        panel.body_layout.addWidget(self.table, 1)
        self._apply_table_column_sizes()

        self.status_message = QLabel("")
        self.status_message.setObjectName("StatusMessage")
        self.status_message.hide()
        panel.body_layout.addWidget(self.status_message)
        return panel

    def _build_summary_panel(self):
        self.summary_panel = Panel("선택 근로자 상세", "요약 / 주요 작업")
        self.summary_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.summary_panel.setMinimumHeight(320)
        self.summary_name = QLabel("선택된 근로자가 없습니다")
        self.summary_name.setObjectName("DetailName")
        self.summary_english = QLabel("영문이름")
        self.summary_english.setObjectName("DetailMeta")
        self.summary_meta1 = QLabel("국적")
        self.summary_meta1.setObjectName("DetailMeta")
        self.summary_meta2 = QLabel("사업자")
        self.summary_meta2.setObjectName("DetailMeta")
        self.summary_meta3 = QLabel("근무 사업장")
        self.summary_meta3.setObjectName("DetailMeta")
        self.summary_meta4 = QLabel("근무 형태")
        self.summary_meta4.setObjectName("DetailMeta")
        self.summary_status = QLabel("대기")
        self.summary_status.setObjectName("StatusBadge")
        self.summary_panel.body_layout.addWidget(self.summary_name)
        self.summary_panel.body_layout.addWidget(self.summary_english)
        self.summary_panel.body_layout.addWidget(self.summary_meta1)
        self.summary_panel.body_layout.addWidget(self.summary_meta2)
        self.summary_panel.body_layout.addWidget(self.summary_meta3)
        self.summary_panel.body_layout.addWidget(self.summary_meta4)
        self.summary_panel.body_layout.addWidget(self.summary_status, alignment=Qt.AlignLeft)

        metric_grid = QGridLayout()
        metric_grid.setContentsMargins(0, 0, 0, 0)
        metric_grid.setHorizontalSpacing(6)
        metric_grid.setVerticalSpacing(6)
        metric_grid.setColumnStretch(0, 1)
        metric_grid.setColumnStretch(1, 1)
        self.score_card = MiniMetricCard("현재 점수", "0점", "근태 누적", "settings")
        self.absence_card = MiniMetricCard("무단결근", "0회", "차감 핵심", "unauthorized_absence")
        self.leave_card = MiniMetricCard("무단이탈", "0회", "현장 이탈", "warning")
        self.warning_card = MiniMetricCard("경고", "0회", "누적 경고", "warning")
        for index, widget in enumerate([self.score_card, self.absence_card, self.leave_card, self.warning_card]):
            metric_grid.addWidget(widget, index // 2, index % 2)
        self.summary_panel.body_layout.addLayout(metric_grid)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 6, 0, 0)
        action_row.setSpacing(6)

        detail_btn = QPushButton("상세/수정")
        detail_btn.setObjectName("PrimaryButton")
        detail_btn.setMinimumHeight(30)
        detail_btn.clicked.connect(self.open_employee_detail)
        action_row.addWidget(detail_btn, 1)

        resign_btn = QPushButton("퇴사 처리")
        resign_btn.setObjectName("WarnButton")
        resign_btn.setMinimumHeight(30)
        resign_btn.clicked.connect(self.resign_employee)
        action_row.addWidget(resign_btn, 1)

        delete_btn = QPushButton("선택 근로자 삭제")
        delete_btn.setObjectName("DangerButton")
        delete_btn.setMinimumHeight(30)
        delete_btn.clicked.connect(self.delete_employee)
        action_row.addWidget(delete_btn, 1)

        self.summary_panel.body_layout.addLayout(action_row)
        return self.summary_panel

    def _build_action_panel(self):
        panel = Panel("작업", "선택 근로자 작업")
        panel.setMinimumHeight(120)
        note = QLabel("작업 버튼은 오른쪽 상세 영역 안으로 정리되었습니다.")
        note.setObjectName("SectionSub")
        note.setWordWrap(True)
        panel.body_layout.addWidget(note)
        return panel

    def _selected_employee(self) -> dict | None:
        if self.selected_employee_id is None:
            return None
        return self.state.get_employee_by_id(self.selected_employee_id)

    def _employee_english_name(self, employee: dict | None) -> str:
        employee = employee or {}
        return str(employee.get("english_name") or employee.get("name_english") or "").strip()

    def _handle_click(self, row: int, _column: int):
        if row < 0 or row >= len(self.filtered_employees):
            return
        employee = self.filtered_employees[row]
        try:
            employee_id = int((employee or {}).get("id", 0) or 0)
        except (TypeError, ValueError, AttributeError):
            employee_id = 0
        self.selected_employee_id = employee_id if employee_id > 0 else None
        self._refresh_summary()

    def _handle_stats_card_clicked(self, key: str):
        if not hasattr(self, "status_filter"):
            return
        target = ALL_STATUS_FILTER_LABEL if key == self.total_card.key else key
        index = self.status_filter.findText(target)
        if index < 0:
            return
        if self.status_filter.currentIndex() == index:
            self.refresh_table()
            return
        self.status_filter.setCurrentIndex(index)

    def _sync_stats_card_active_states(self, status: str):
        if not all(hasattr(self, name) for name in ("total_card", "work_card", "pre_card", "resign_card")):
            return
        self.total_card.set_active(status == ALL_STATUS_FILTER_LABEL)
        self.work_card.set_active(status == self.work_card.key)
        self.pre_card.set_active(status == self.pre_card.key)
        self.resign_card.set_active(status == self.resign_card.key)

    def _column_width_settings_key(self) -> str:
        return "employee/list_table_column_widths"

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

    def _table_min_widths(self) -> list[int]:
        return [56, 92, 120, 70, 86, 86, 74, 82]

    def _table_default_widths(self) -> list[int]:
        return [68, 150, 190, 84, 104, 102, 86, 86]

    def _table_resize_priority(self) -> list[int]:
        return [2, 1, 4, 5, 3, 6, 7, 0]

    def _table_available_width(self) -> int:
        if not hasattr(self, "table"):
            return 0
        return max(0, self.table.viewport().width() - 2)

    def _fit_table_widths(self, widths: list[int], locked_column: int | None = None) -> list[int]:
        count = self.table.columnCount()
        minimums = self._table_min_widths()
        if len(widths) != count:
            widths = self._table_default_widths()
        widths = [max(minimums[index], int(widths[index])) for index in range(count)]
        available = self._table_available_width()
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
            priority = [column for column in self._table_resize_priority() if column != locked_column]
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

    def _apply_table_widths(self, widths: list[int], save: bool = False, locked_column: int | None = None, fit_to_table: bool = True):
        if not hasattr(self, "table") or self.table is None:
            return
        count = self.table.columnCount()
        if len(widths) != count:
            widths = self._table_default_widths()
        minimums = self._table_min_widths()
        safe_widths = [max(minimums[index], int(widths[index])) for index in range(count)]
        if fit_to_table:
            safe_widths = self._fit_table_widths(safe_widths, locked_column=locked_column)
        self._applying_table_column_widths = True
        try:
            for column, width in enumerate(safe_widths):
                self.table.setColumnWidth(column, width)
        finally:
            self._applying_table_column_widths = False
        if save:
            self._write_saved_column_widths(safe_widths)

    def _rebalance_table_widths_after_drag(self, widths: list[int], logical_index: int, old_size: int, new_size: int) -> list[int]:
        count = self.table.columnCount()
        minimums = self._table_min_widths()
        if len(widths) != count or not (0 <= logical_index < count):
            return self._fit_table_widths(widths)
        widths = [max(minimums[index], int(widths[index])) for index in range(count)]
        pair_index = logical_index + 1 if logical_index + 1 < count else logical_index - 1
        if not (0 <= pair_index < count):
            return self._fit_table_widths(widths)

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

    def _current_table_widths(self) -> list[int]:
        if not hasattr(self, "table") or self.table is None:
            return []
        return [max(32, self.table.columnWidth(column)) for column in range(self.table.columnCount())]

    def _save_table_column_widths(self):
        if getattr(self, "_applying_table_column_widths", False):
            return
        if not hasattr(self, "table"):
            return
        widths = self._fit_table_widths(self._current_table_widths())
        self._write_saved_column_widths(widths)

    def _on_table_section_resized(self, logical_index: int, old_size: int, new_size: int):
        if getattr(self, "_applying_table_column_widths", False):
            return
        widths = self._current_table_widths()
        widths = self._rebalance_table_widths_after_drag(widths, logical_index, old_size, new_size)
        self._apply_table_widths(widths, save=True, locked_column=logical_index, fit_to_table=False)

    def _schedule_table_width_fit(self, save: bool = False):
        if getattr(self, "_table_width_fit_pending", False):
            return
        self._table_width_fit_pending = True

        def apply_later():
            self._table_width_fit_pending = False
            if hasattr(self, "table") and self.table is not None:
                saved_widths = self._read_saved_column_widths(self.table.columnCount())
                if saved_widths and not save:
                    widths = saved_widths
                else:
                    widths = self._current_table_widths() or saved_widths or self._table_default_widths()
                self._apply_table_widths(widths, save=save)

        QTimer.singleShot(0, apply_later)

    def _restore_saved_table_widths_after_layout(self):
        if getattr(self, "_applying_table_column_widths", False):
            return
        if not hasattr(self, "table") or self.table is None:
            return
        saved_widths = self._read_saved_column_widths(self.table.columnCount())
        if not saved_widths:
            return
        self._apply_table_widths(saved_widths, save=False, fit_to_table=False)

    def _apply_table_column_sizes(self):
        if not hasattr(self, "table") or self.table is None:
            return
        install_resizable_table_columns(
            self.table,
            state=self.state,
            key="employee/list_table",
            default_widths=[64, 150, 200, 88, 120, 136, 92, 86],
            min_widths=[52, 104, 126, 70, 92, 104, 76, 70],
        )

    def refresh_table(self):
        self.employees = list(self.state.employees)
        keyword = self.search_edit.text().strip().lower() if hasattr(self, "search_edit") else ""
        status = self.status_filter.currentText() if hasattr(self, "status_filter") else ALL_STATUS_FILTER_LABEL

        self.filtered_employees = []
        for employee in self.employees:
            searchable = " ".join([
                self.state.employee_display_number(employee) if hasattr(self.state, "employee_display_number") else str(employee["id"]),
                str(employee["id"]),
                employee["name"],
                self._employee_english_name(employee),
                employee["nation"],
                employee["affiliated_business"],
                employee["work_site"],
                employee["work_type"],
                employee["status"],
            ]).lower()
            if keyword and keyword not in searchable:
                continue
            if status != ALL_STATUS_FILTER_LABEL and employee["status"] != status:
                continue
            self.filtered_employees.append(employee)

        self.table.setRowCount(len(self.filtered_employees))
        for row, employee in enumerate(self.filtered_employees):
            values = [
                self.state.employee_display_number(employee) if hasattr(self.state, "employee_display_number") else f"{row + 1:04d}",
                employee["name"],
                self._employee_english_name(employee) or "-",
                employee["nation"],
                employee["affiliated_business"],
                employee["work_site"],
                employee["work_type"],
                employee["status"],
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setData(Qt.UserRole, int(employee.get("id", 0) or 0))
                item.setTextAlignment(Qt.AlignCenter if col not in (1, 2) else Qt.AlignVCenter)
                if col == 7:
                    bg, fg = STATUS_COLORS.get(value, ("#F8FAFC", "#334155"))
                    item.setBackground(QBrush(QColor(bg)))
                    item.setForeground(QBrush(QColor(fg)))
                self.table.setItem(row, col, item)

        self.total_card.set_value(f"{len(self.employees)}명")
        self.work_card.set_value(f'{sum(1 for row in self.employees if row["status"] == "근무중")}명')
        self.pre_card.set_value(f'{sum(1 for row in self.employees if row["status"] == "출근전")}명')
        self.resign_card.set_value(f'{sum(1 for row in self.employees if row["status"] == "퇴사")}명')
        self._sync_stats_card_active_states(status)

        if self.filtered_employees and self._selected_employee() is None:
            first_id = 0
            try:
                first_id = int((self.filtered_employees[0] or {}).get("id", 0) or 0)
            except (TypeError, ValueError, AttributeError):
                first_id = 0
            self.selected_employee_id = first_id if first_id > 0 else None
            if first_id > 0:
                self.table.selectRow(0)
        self._refresh_summary()

    def _set_metric_card_value(self, card: MiniMetricCard, value: str):
        if hasattr(card, "set_value"):
            card.set_value(value)
            return
        labels = card.findChildren(QLabel)
        if len(labels) >= 2:
            labels[1].setText(value)

    def _adjust_splitter_sizes(self):
        if not hasattr(self, "body_splitter"):
            return
        total = max(self.width() - 28, 1120)
        right = min(max(int(total * 0.28), 330), 390)
        self.body_splitter.setSizes([max(760, total - right), right])

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_splitter_initialized", False):
            self._splitter_initialized = True
            self._adjust_splitter_sizes()


    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, "_splitter_initialized", False):
            self._adjust_splitter_sizes()
        schedule_table_column_fit(getattr(self, "table", None))


    def _refresh_summary(self):
        employee = self._selected_employee()
        if employee is None:
            self.summary_name.setText("선택된 근로자가 없습니다")
            self.summary_english.setText("영문이름")
            self.summary_meta1.setText("국적")
            self.summary_meta2.setText("사업자")
            self.summary_meta3.setText("근무 사업장")
            self.summary_meta4.setText("근무 형태")
            self.summary_status.setText("대기")
            for card, value in [
                (self.score_card, "0점"),
                (self.absence_card, "0회"),
                (self.leave_card, "0회"),
                (self.warning_card, "0회"),
            ]:
                self._set_metric_card_value(card, value)
            return

        self.summary_name.setText(f'{employee["name"]}')
        english_name = self._employee_english_name(employee)
        self.summary_english.setText(f'영문이름: {english_name or "-"}')
        self.summary_meta1.setText(f'국적: {employee["nation"]}')
        self.summary_meta2.setText(f'사업자: {employee["affiliated_business"]}')
        self.summary_meta3.setText(f'근무 사업장: {employee["work_site"]}')
        self.summary_meta4.setText(f'근무 형태: {employee["work_type"]}')
        self.summary_status.setText(employee["status"])
        self._set_metric_card_value(self.score_card, f'{employee.get("attendance_score", 0)}점')
        self._set_metric_card_value(self.absence_card, f'{employee.get("unauthorized_absence", 0)}회')
        self._set_metric_card_value(self.leave_card, f'{employee.get("unauthorized_leave", 0)}회')
        self._set_metric_card_value(self.warning_card, f'{employee.get("warning_count", 0)}회')

    def open_registration_page(self):
        self.request_registration.emit()
        self.status_message.setText("근로자 등록 화면으로 이동합니다.")

    def open_employee_detail(self):
        employee = self._selected_employee()
        if employee is None:
            QMessageBox.information(self, "근로자 관리", "먼저 근로자 한 명을 선택해 주세요.")
            return
        dialog = EmployeeDetailDialog(self.state, employee, self)
        result = dialog.exec()
        if dialog.document_edit_requested():
            self.request_document_edit.emit(int(employee["id"]))
            return
        if result:
            updated_employee = dialog.get_employee_data()
            self.state.update_employee(int(employee["id"]), updated_employee)
            self.selected_employee_id = int(updated_employee.get("id", employee["id"]))
            self.refresh_table()
            self.status_message.setText(f'{updated_employee.get("name", employee["name"])} 정보 저장 완료')

    def edit_employee(self):
        self.open_employee_detail()

    def resign_employee(self):
        employee = self._selected_employee()
        if employee is None:
            QMessageBox.information(self, "근로자 관리", "먼저 근로자 한 명을 선택해 주세요.")
            return

        dialog = ResignEmployeeDialog(str(employee.get("name") or "선택 근로자"), self)
        if not dialog.exec():
            return

        reason = dialog.reason()
        end_date = dialog.resign_date()
        note = dialog.note()
        try:
            self.state.resign_employee(int(employee["id"]), reason=reason, note=note, end_date=end_date)
        except Exception as error:
            QMessageBox.warning(self, "퇴사 처리", str(error))
            return
        self.status_message.setText(f'{employee["name"]} 퇴사처리 완료 · {end_date} · {reason}')

    def delete_employee(self):
        employee = self._selected_employee()
        if employee is None:
            QMessageBox.information(self, "근로자 관리", "먼저 근로자 한 명을 선택해 주세요.")
            return
        answer = QMessageBox.warning(
            self,
            "근로자 영구 삭제 경고",
            f"⚠️ 주의: '{employee['name']}' 근로자의 모든 정보 및 근태 기록이 데이터베이스에서 완전히 영구적으로 삭제되며 절대 복구할 수 없습니다.\n\n정말 삭제하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            try:
                employee_id = int((employee or {}).get("id", self.selected_employee_id or 0) or self.selected_employee_id or 0)
            except (TypeError, ValueError, AttributeError):
                employee_id = int(self.selected_employee_id or 0)
            if employee_id <= 0:
                QMessageBox.warning(self, "근로자 삭제", "근로자 ID가 올바르지 않아 삭제할 수 없습니다. 동기화 후 다시 시도해 주세요.")
                return
            try:
                self.state.delete_employee(employee_id)
            except Exception as error:
                QMessageBox.warning(self, "근로자 삭제", str(error))
                return
            self.selected_employee_id = None
            self.status_message.setText(f'{employee["name"]} 삭제 완료')
